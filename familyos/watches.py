"""Watch a public page, and say when what it says changes.

The generic task, in the only shape that costs the architecture nothing:

  * It reads through **class 1**, which holds no credential. The worst a hostile
    page can do is be wrong.
  * It tells **the member who asked**, through the mail path already used for
    reminders. No third-party recipient, so no new action kind, and
    `actions.kind IN ('reply', 'calendar')` stays exactly as narrow as it was.
  * It produces no claim and no obligation. Nothing an institution did not ask
    the family to do becomes an obligation.

"Search an air conditioner and tell me when it is in stock" is this. "Add it to
a cart" is not: that needs a credential, a session-persistent container, and a
widened deny-list -- three separate decisions that should be made on purpose.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from urllib.parse import urlsplit

from familyos import audit, mail
from familyos.db import pool
from familyos.execution import disposable
from familyos.identity import Invalid, NotFound, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

MAX_PER_HOUSEHOLD = 20
DEFAULT_DAYS = 30
MAX_DAYS = 180
EXCERPT_CHARS = 400


def _hosts(url: str, extra: list[str] | None = None) -> list[str]:
    """The allowlist defaults to the one host asked for. A redirect elsewhere is
    refused rather than followed."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        raise Invalid("that is not a URL we can read")
    return sorted({host, *[h.strip().lower() for h in (extra or []) if h.strip()]})


async def create(p: Principal, *, url: str, look_for: str, label: str,
                 every_hours: int = 24, days: int = DEFAULT_DAYS,
                 allow_hosts: list[str] | None = None) -> dict:
    text = (look_for or "").strip()
    name = (label or "").strip()
    if not text:
        raise Invalid("say what to look for on the page")
    if not name:
        raise Invalid("give it a name you will recognise later")
    if not 1 <= every_hours <= 720:
        raise Invalid("check between once an hour and once a month")
    if not 1 <= days <= MAX_DAYS:
        raise Invalid(f"a watch lasts between 1 and {MAX_DAYS} days")
    hosts = _hosts(url, allow_hosts)
    # Refuse now, in the member's hands, rather than failing quietly in a sweep.
    # The full check, not just the syntax: "localhost" is not an address
    # literal, so it passes every syntactic test and still points inside.
    disposable.vet(url, frozenset(hosts))

    async with pool().acquire() as conn, conn.transaction():
        live = await conn.fetchval(
            "SELECT count(*) FROM watches WHERE household_id = $1 AND paused_at IS NULL AND expires_at > NOW()",
            p.household_id)
        if live >= MAX_PER_HOUSEHOLD:
            raise Invalid(f"a household keeps at most {MAX_PER_HOUSEHOLD} watches at a time")
        row = await conn.fetchrow(
            "INSERT INTO watches (id, household_id, member_id, url, allow_hosts, look_for, label, "
            "every_hours, expires_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW() + make_interval(days => $9)) "
            "RETURNING *",
            uuid.uuid4(), p.household_id, p.member_id, url, hosts, text, name, every_hours, days)
        await audit.record(p.household_id, "watch.created", actor_member_id=p.member_id,
                           target_type="watch", target_id=row["id"],
                           detail={"host": hosts[0], "every_hours": every_hours}, conn=conn)
    return dict(row)


async def list_for(p: Principal) -> list[dict]:
    """Your own watches. A watch is a member's errand, not household business."""
    rows = await pool().fetch(
        "SELECT * FROM watches WHERE household_id = $1 AND member_id = $2 AND expires_at > NOW() "
        "ORDER BY created_at DESC", p.household_id, p.member_id)
    return [dict(r) for r in rows]


async def cancel(p: Principal, watch_id: uuid.UUID) -> dict:
    row = await pool().fetchrow(
        "UPDATE watches SET paused_at = NOW() WHERE id = $1 AND household_id = $2 AND member_id = $3 "
        "AND paused_at IS NULL RETURNING *", watch_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("watch")
    return dict(row)


async def due(now: dt.datetime | None = None, limit: int = 20) -> list[dict]:
    now = now or dt.datetime.now(dt.UTC)
    rows = await pool().fetch(
        "SELECT w.*, m.email, m.display_name FROM watches w JOIN members m ON m.id = w.member_id "
        "WHERE w.paused_at IS NULL AND w.expires_at > $1::timestamptz "
        "AND (w.last_checked_at IS NULL OR w.last_checked_at < $1::timestamptz "
        "     - make_interval(hours => w.every_hours)) "
        "ORDER BY w.last_checked_at NULLS FIRST LIMIT $2", now, limit)
    return [dict(r) for r in rows]


async def check_one(row: dict, *, client=None) -> str:
    """Read the page once and tell the member if the answer changed.

    Returns what happened, for the sweep's counters: 'notified', 'same',
    'failed'.
    """
    try:
        page = await _read(row["url"], frozenset(row["allow_hosts"]), client=client)
    except disposable.Refused as exc:
        await pool().execute(
            "UPDATE watches SET last_checked_at = NOW(), last_error = $2 WHERE id = $1",
            row["id"], str(exc)[:500])
        return "failed"

    needle = row["look_for"].lower()
    found = needle in page.text.lower()
    excerpt = ""
    if found:
        at = page.text.lower().index(needle)
        start = max(0, at - EXCERPT_CHARS // 3)
        excerpt = page.text[start:start + EXCERPT_CHARS].strip()

    first_look = row["last_checked_at"] is None
    changed = (row["last_found"] is not None and row["last_found"] != found)
    await pool().execute(
        "UPDATE watches SET last_checked_at = NOW(), last_sha256 = $2, last_found = $3, "
        "last_excerpt = $4, last_error = NULL WHERE id = $1",
        row["id"], page.sha256, found, excerpt or None)

    # Say something when the answer appears, and when it goes away again --
    # not on every sweep, and not on the first look, which has nothing to
    # compare against.
    if first_look or not changed:
        return "same"
    if not row.get("email"):
        return "same"

    subject = (f"{row['label']}: found" if found else f"{row['label']}: no longer there")
    body = (f"Hello {row['display_name']},\n\n"
            f"You asked FamilyOS to watch for \"{row['look_for']}\" on:\n{page.url}\n\n"
            + (f"It is there now:\n\n{excerpt}\n\n" if found
               else "It is no longer on that page.\n\n")
            + "FamilyOS only read the page. It did not sign in, buy anything, or act on your behalf.\n")
    await mail.send(row["email"], subject, body)
    await pool().execute("UPDATE watches SET notified_at = NOW() WHERE id = $1", row["id"])
    await audit.record(row["household_id"], "watch.notified", actor_kind="system",
                       target_type="watch", target_id=row["id"],
                       detail={"found": found, "host": urlsplit(page.url).hostname})
    return "notified"


async def _read(url: str, allow_hosts: frozenset[str], *, client=None):
    """Plain HTTP, or the research provider when one is on: the same vetting
    first, so a page behind a private address is refused either way, and a
    JavaScript page comes back as what a person would see."""
    from familyos.execution import research
    if not research.configured():
        return await disposable.read(url, allow_hosts, client=client)
    disposable.vet(url, allow_hosts)
    try:
        got = await research.current().extract(url)
    except Exception as exc:  # noqa: BLE001 - said as a refusal, like a plain fetch's
        raise disposable.Refused(f"could not read through {research.current().name}: {exc}") from exc
    return disposable.Page(url=got.url, title=got.title or "", text=got.text[:disposable.TEXT_LIMIT],
                           sha256=__import__("hashlib").sha256(got.text.encode()).hexdigest(),
                           bytes=len(got.text), truncated=len(got.text) > disposable.TEXT_LIMIT)


async def sweep(limit: int = 20) -> dict[str, int]:
    counts = {"notified": 0, "same": 0, "failed": 0}
    if not settings.watches_enabled:
        return counts
    for row in await due(limit=limit):
        try:
            counts[await check_one(row)] += 1
        except Exception:  # noqa: BLE001 - one bad page must not stop the sweep
            logger.warning("watch %s could not be checked", row["id"], exc_info=True)
            counts["failed"] += 1
    return counts


KIND = "check_watches"
HANDLER_VERSION = "1"


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    await ctx.plan(["Check what members asked us to watch"])
    await ctx.step("0")
    counts = await sweep()
    await ctx.finish_step("0")
    if not settings.watches_enabled:
        return {**counts, "stopped": "watches are disabled"}
    return {**counts, "next_run_at": (now + dt.timedelta(seconds=max(300, settings.watch_sweep_seconds))).isoformat()}


async def ensure_scheduled() -> dict | None:
    from familyos import jobs
    if not settings.watches_enabled:
        return None
    existing = await pool().fetchrow(
        "SELECT id FROM jobs WHERE kind = $1 AND status NOT IN ('succeeded', 'failed', 'cancelled') LIMIT 1", KIND)
    if existing is not None:
        return None
    return await jobs.create(KIND, {}, next_run_at=dt.datetime.now(dt.UTC))


def register() -> None:
    from familyos import jobs
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("watch_sweep_seconds",))


def describe() -> str:
    if not settings.watches_enabled:
        return "Watches are off (FAMILYOS_WATCHES_ENABLED=false)."
    return ("Watches are on: public pages only, no credential is ever held, and the result is mailed "
            "to the member who asked -- never acted on.")
