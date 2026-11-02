"""What the Android app collects, made into the local cache's rows (store.py). The phone sends the shapes the user's own
collector app used (Mobile-UI-Agent, `KT/collector/*`): SMS `{id, sender, body, date, dateSent, type, read, seen, subject,
serviceCenter, person, protocol, threadId}`, calls `{number, type, date, duration}`, notifications `{package, title, text,
postTime}`, locations `{lat, lng, accuracy, time}`, photo names `{id, name, size, mimeType, date}` (times in milliseconds
since 1970, a photo's date in seconds).

Every SMS is kept, one-time codes included, with the code pulled out (otp.py) for the browser agent -- decided 2 Nov 2026,
as the collector app does; this overrides, for our local cache only, the founder's "codes are never kept" (intake/codes.py,
still in force for mail intake). After keeping, Qwen sorts each SMS and notification (categorize.py) and a location gets a
place name (geocode.py), in the background. A notification from an app whose collect switch is off is not kept.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from familyos.collect import store
from familyos.collect.otp import extract_otp

KINDS = tuple(store.DEVICE)


def _iso(ms: object, *, seconds: bool = False) -> str | None:
    try:
        n = float(ms)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return dt.datetime.fromtimestamp(n if seconds else n / 1000, dt.UTC).isoformat(timespec="seconds")


def _int(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _sms(x: dict) -> dict:
    return {"id": str(x.get("id") or x.get("smsId") or f"{x.get('sender')}|{x.get('date')}"), "sender": x.get("sender"),
            "body": x.get("body"), "sent_at": _iso(x.get("date")), "thread_id": str(x.get("threadId") or "") or None,
            "date_sent": _iso(x.get("dateSent")) if x.get("dateSent") else None, "type": _int(x.get("type")),
            "read": _int(x.get("read")), "seen": _int(x.get("seen")), "subject": x.get("subject") or None,
            "service_center": x.get("serviceCenter") or None, "person": str(x.get("person") or "") or None,
            "protocol": _int(x.get("protocol")), "otp": extract_otp(x.get("body"))}


def _call(x: dict) -> dict:
    return {"id": f"{x.get('number')}|{x.get('date')}", "number": x.get("number"), "kind": x.get("type"),
            "started_at": _iso(x.get("date")), "duration_s": int(x.get("duration") or 0)}


def _notification(x: dict, labels: dict[str, str]) -> dict | None:
    package = x.get("package") or x.get("packageName")
    if package not in labels:
        return None
    digest = hashlib.sha256(f"{x.get('title')}|{x.get('text')}".encode()).hexdigest()[:12]
    return {"id": f"{package}|{x.get('postTime')}|{digest}", "package": package, "app_label": labels[package],
            "title": x.get("title"), "text": x.get("text"), "posted_at": _iso(x.get("postTime")),
            "otp": extract_otp(" ".join(str(t) for t in (x.get("title"), x.get("text")) if t))}


def _location(x: dict) -> dict:
    return {"id": str(x.get("time")), "lat": x.get("lat"), "lon": x.get("lng", x.get("lon")), "accuracy": x.get("accuracy"),
            "fixed_at": _iso(x.get("time"))}


def _file(x: dict) -> dict:
    return {"id": str(x.get("id") or x.get("name")), "name": x.get("name"), "size": x.get("size"), "mime": x.get("mimeType"),
            "added_at": _iso(x.get("date"), seconds=True)}


def keep(kind: str, email: str, items: list[dict]) -> dict:
    """Keep what the phone sent; say how many were kept and how many were left out on purpose."""
    if kind == "notifications":
        labels = {a["package"]: a["label"] for a in store.apps(email) if a["collect"]}
        rows = [_notification(x, labels) for x in items]
    elif kind == "sms":
        rows = [_sms(x) for x in items]
    else:
        rows = [{"calls": _call, "locations": _location, "files": _file}[kind](x) for x in items]
    kept = [r for r in rows if r is not None]
    store.upsert(kind, email, kept)
    if kept and kind in ("sms", "notifications"):
        from familyos.collect import categorize
        categorize.start(email)
    elif kept and kind == "locations":
        from familyos.collect import geocode
        geocode.start(email)
    return {"kept": len(kept), "dropped": len(rows) - len(kept)}
