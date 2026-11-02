"""Google, read for the collecting layer (widened 2 Nov 2026): Gmail -- every message of the last 180 days (500 at most)
with its full text, HTML, cc, labels and attachments (saved as owner-only files beside the cache, 25 MB each at most),
and any one-time code in it, for the browser agent; Calendar -- every calendar the person can read, a year back to a year
ahead, with description, organiser and attendees; Tasks -- every list, every task. With the permission given at Google sign-in
(`settings.google_sign_in_collect`). Into the local cache (store.py), nowhere else.

Reuses the founder's Google plumbing (intake/google.py): the token refresh and its HTTP helper, so a test can stand in
for Google through the same `transport` seam. One run at a time per account; a source Google refuses (an API not
switched on in the Cloud project, a permission not given) is said for that source and the others still run.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote

from familyos.collect import store
from familyos.collect.otp import extract_otp
from familyos.intake import google
from familyos.settings import settings

logger = logging.getLogger(__name__)

TASKS_SCOPE = "https://www.googleapis.com/auth/tasks.readonly"
COLLECT_SCOPES = (google.GMAIL_SCOPE, google.CALENDAR_SCOPE, TASKS_SCOPE)
TASKS = "https://tasks.googleapis.com/tasks/v1"

# Everything Google lets the permission read (decided 2 Nov 2026: full mail text and attachments, every calendar, longer).
GMAIL_DAYS = 180
GMAIL_LIMIT = 500
ATTACHMENT_MAX = 25 * 1024 * 1024        # larger ones are listed, not saved
BODY_MAX = 200_000
CALENDAR_BACK = dt.timedelta(days=365)
CALENDAR_AHEAD = dt.timedelta(days=365)
_API_NAMES = {"gmail": "Gmail API", "calendar": "Google Calendar API", "tasks": "Google Tasks API"}

_running: dict[str, asyncio.Task] = {}


def _said(kind: str, exc: Exception) -> str:
    text = str(exc)
    if "accessNotConfigured" in text or "has not been used in project" in text or "SERVICE_DISABLED" in text:
        return (f"Google says the {_API_NAMES[kind]} is not switched on for this project: enable it in Google Cloud Console "
                "→ APIs & Services → Library, then collect again.")
    if "insufficient" in text.lower() or "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in text:
        return f"Permission to read {kind} was not given at sign-in: sign in with Google again and allow it."
    return f"Could not read {kind}: {text[:200]}"


GMAIL_AT_ONCE = 4                        # full messages read together; Gmail's per-user quota is per minute
QUOTA = ("Quota exceeded", "rateLimitExceeded", "userRateLimitExceeded", "RESOURCE_EXHAUSTED")
QUOTA_TRIES = 5


async def _get(transport, url: str, headers: dict, what: str, **params) -> dict:
    """A Google read; when Google says the per-user quota or rate limit is used up, wait and ask again (2, 4, 8, 16 s)."""
    for attempt in range(QUOTA_TRIES):
        try:
            return await google._json(transport, "GET", url, what=what, headers=headers, params=params)
        except google.GoogleError as exc:
            if attempt == QUOTA_TRIES - 1 or not (getattr(exc, "status", None) in (403, 429) and any(q in str(exc) for q in QUOTA)):
                raise
            await asyncio.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


async def _pages(transport, url: str, headers: dict, what: str, key: str, limit: int, **params) -> list[dict]:
    """Every page of a Google list, up to `limit` items."""
    out: list[dict] = []
    token = None
    while len(out) < limit:
        body = await _get(transport, url, headers, what, **params, **({"pageToken": token} if token else {}))
        out.extend(body.get(key, []))
        token = body.get("nextPageToken")
        if not token:
            break
    return out[:limit]


def _b64(data: str | None) -> bytes:
    return base64.urlsafe_b64decode((data or "") + "=" * (-len(data or "") % 4))


def _parts(part: dict):
    yield part
    for p in part.get("parts") or []:
        yield from _parts(p)


def _attachment_dir(email: str, message_id: str) -> Path:
    root = Path(os.path.expanduser(settings.collect_dir)) / "attachments"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = root / hashlib.sha256(email.encode()).hexdigest()[:16] / re.sub(r"[^A-Za-z0-9_-]", "_", message_id)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


async def _attachments(email: str, m: dict, headers: dict, transport) -> int:
    n = 0
    for part in _parts(m.get("payload") or {}):
        name, body = part.get("filename") or "", part.get("body") or {}
        if not name or not (body.get("attachmentId") or body.get("data")):
            continue
        aid = body.get("attachmentId") or hashlib.sha256(f"{m['id']}|{name}".encode()).hexdigest()[:24]
        size = int(body.get("size") or 0)
        path = None
        if size <= ATTACHMENT_MAX:
            data = _b64(body["data"]) if body.get("data") else _b64(
                (await _get(transport, f"{google.GMAIL}/messages/{m['id']}/attachments/{aid}", headers, "reading an attachment")).get("data"))
            target = _attachment_dir(email, m["id"]) / (re.sub(r"[/\\:\x00]", "_", name)[:120] or "attachment")
            target.write_bytes(data)
            os.chmod(target, 0o600)
            path = str(target)
        store.keep_attachment(email, m["id"], aid, name, part.get("mimeType") or "", size, path)
        n += 1
    return n


def _text(m: dict, mime: str) -> str | None:
    for part in _parts(m.get("payload") or {}):
        if part.get("mimeType") == mime and not part.get("filename") and (part.get("body") or {}).get("data"):
            return _b64(part["body"]["data"]).decode("utf-8", "replace")[:BODY_MAX]
    return None


async def _gmail(email: str, headers: dict, transport) -> list[dict]:
    listed = await _pages(transport, f"{google.GMAIL}/messages", headers, "listing mail", "messages", GMAIL_LIMIT,
                          q=f"newer_than:{GMAIL_DAYS}d", maxResults=100)
    ids = [m["id"] for m in listed]
    have = store.gmail_known(email, ids)
    rows: list[dict] = []
    todo = [i for i in ids if i not in have]
    for start in range(0, len(todo), GMAIL_AT_ONCE):     # a few at a time, kept as they come: a stop keeps what was read
        batch = await asyncio.gather(*(_get(transport, f"{google.GMAIL}/messages/{mid}", headers, "reading a message", format="full")
                                       for mid in todo[start:start + GMAIL_AT_ONCE]))
        kept = len(rows)
        for m in batch:
            h = {x["name"].lower(): x["value"] for x in (m.get("payload") or {}).get("headers", [])}
            sent = dt.datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, dt.UTC).isoformat(timespec="seconds")
            text, html = _text(m, "text/plain"), _text(m, "text/html")
            plain = text or (re.sub(r"<[^>]+>", " ", html) if html else "")
            rows.append({"id": m["id"], "thread_id": m.get("threadId"), "sender": h.get("from"), "recipients": h.get("to"),
                         "subject": h.get("subject"), "snippet": m.get("snippet"), "sent_at": sent,
                         "labels": ",".join(m.get("labelIds", [])), "cc": h.get("cc"), "body": text or plain or "",
                         "body_html": html, "attachments": await _attachments(email, m, headers, transport),
                         "otp": extract_otp(f"{h.get('subject') or ''} {plain[:3000]}"), "history_id": m.get("historyId"),
                         "size": m.get("sizeEstimate")})
        store.upsert("gmail", email, rows[kept:])
        await asyncio.sleep(0.5)
    return rows


async def _calendar(email: str, headers: dict, transport) -> list[dict]:
    now = dt.datetime.now(dt.UTC)
    calendars = await _pages(transport, f"{google.CALENDAR}/users/me/calendarList", headers, "listing calendars", "items", 250)
    rows = []
    for cal in calendars:
        if cal.get("accessRole") == "freeBusyReader":
            continue
        events = await _pages(transport, f"{google.CALENDAR}/calendars/{quote(cal['id'], safe='')}/events", headers,
                              "reading a calendar", "items", 5000, timeMin=(now - CALENDAR_BACK).isoformat(),
                              timeMax=(now + CALENDAR_AHEAD).isoformat(), singleEvents="true", orderBy="startTime", maxResults=2500)
        for e in events:
            start, end = e.get("start", {}), e.get("end", {})
            rows.append({"id": e["id"], "summary": e.get("summary"), "starts": start.get("dateTime") or start.get("date"),
                         "ends": end.get("dateTime") or end.get("date"), "all_day": int("date" in start and "dateTime" not in start),
                         "location": e.get("location"), "status": e.get("status"), "updated": e.get("updated"),
                         "calendar_id": cal["id"], "calendar_name": cal.get("summaryOverride") or cal.get("summary"),
                         "description": e.get("description"), "organizer": (e.get("organizer") or {}).get("email"),
                         "attendees": json.dumps([{"email": a.get("email"), "name": a.get("displayName"), "response": a.get("responseStatus")}
                                                  for a in e.get("attendees", [])]) if e.get("attendees") else None,
                         "html_link": e.get("htmlLink"), "recurring_event_id": e.get("recurringEventId"), "created": e.get("created")})
    return rows


async def _tasks(email: str, headers: dict, transport) -> list[dict]:
    lists = await _pages(transport, f"{TASKS}/users/@me/lists", headers, "listing task lists", "items", 100, maxResults=100)
    rows = []
    for tl in lists:
        tasks = await _pages(transport, f"{TASKS}/lists/{tl['id']}/tasks", headers, "reading tasks", "items", 5000,
                             showCompleted="true", showHidden="true", showDeleted="false", maxResults=100)
        for t in tasks:
            rows.append({"id": t["id"], "list_title": tl.get("title"), "title": t.get("title"), "notes": t.get("notes"),
                         "due": t.get("due"), "status": t.get("status"), "completed": t.get("completed"), "updated": t.get("updated"),
                         "list_id": tl["id"], "parent": t.get("parent"), "position": t.get("position"),
                         "links": json.dumps(t["links"]) if t.get("links") else None})
    return rows


async def otp_since(email: str, since: dt.datetime, *, transport=None) -> str | None:
    """The newest one-time code mailed since `since`, asked of Gmail itself (for the browser agent waiting on a code)."""
    from familyos.intake import mailbox
    refresh = store.google_refresh_token(email)
    if refresh is None:
        return None
    client_id, client_secret = mailbox._require_client()
    token = await google.refresh(refresh, client_id=client_id, client_secret=client_secret, transport=transport)
    headers = {"Authorization": f"Bearer {token.access_token}"}
    listed = await _get(transport, f"{google.GMAIL}/messages", headers, "looking for a code",
                        q=f"after:{int(since.timestamp())}", maxResults=5)
    for ref in listed.get("messages", []):
        m = await _get(transport, f"{google.GMAIL}/messages/{ref['id']}", headers, "reading a code", format="full")
        if int(m.get("internalDate", "0")) / 1000 < since.timestamp():
            continue
        h = {x["name"].lower(): x["value"] for x in (m.get("payload") or {}).get("headers", [])}
        html = _text(m, "text/html")
        found = extract_otp(f"{h.get('subject') or ''} {_text(m, 'text/plain') or (re.sub(r'<[^>]+>', ' ', html) if html else '')}"[:4000])
        if found:
            return found
    return None


SOURCES = (("gmail", _gmail), ("calendar", _calendar), ("tasks", _tasks))


async def run(email: str, *, transport=None) -> dict:
    """Read the three sources for one connected Google account into the local cache; say what came and what did not."""
    from familyos.intake import mailbox
    started = store._now()
    refresh = store.google_refresh_token(email)
    if refresh is None:
        return {"counts": {}, "errors": {"google": "Google is not connected for this account."}}
    client_id, client_secret = mailbox._require_client()
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    try:
        token = await google.refresh(refresh, client_id=client_id, client_secret=client_secret, transport=transport)
    except google.GoogleError as exc:
        errors["google"] = "Google will not refresh this connection: sign in with Google again." if isinstance(exc, google.NeedsReconnect) \
            else f"Could not reach Google: {str(exc)[:200]}"
        store.record_run(email, "google", started, counts, errors)
        return {"counts": counts, "errors": errors}
    headers = {"Authorization": f"Bearer {token.access_token}"}
    for kind, read in SOURCES:
        try:
            counts[kind] = store.upsert(kind, email, await read(email, headers, transport))
        except google.GoogleError as exc:
            errors[kind] = _said(kind, exc)
            logger.warning("collect: %s for one account: %s", kind, exc)
    store.record_run(email, "google", started, counts, errors)
    return {"counts": counts, "errors": errors}


def start(email: str) -> bool:
    """Collect in the background (after sign-in, or "Collect now"); False when a run is already going."""
    key = (email or "").strip().lower()
    going = _running.get(key)
    if going and not going.done():
        return False
    task = asyncio.get_running_loop().create_task(run(key))
    _running[key] = task
    task.add_done_callback(lambda t: t.exception() and logger.warning("collect: a Google run failed: %s", t.exception()))
    return True


def is_running(email: str) -> bool:
    t = _running.get((email or "").strip().lower())
    return bool(t and not t.done())
