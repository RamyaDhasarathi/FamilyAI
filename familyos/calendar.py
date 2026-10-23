"""The family's own calendar: read so a notice can be told it clashes, and
-- when a member has granted it -- written to, so an accepted date is on
their phone without a second step.

`calendar.readonly` is a *sensitive* scope, not a restricted one -- ordinary
OAuth verification, no CASA assessment, no yearly re-audit. That is the whole
reason this can ship before the mailbox does.

What it is for: a school circular says the trip is on the 14th at 09:00, and
the family already has something at 09:30 that day. Nobody reads two calendars
side by side at 7am, which is exactly when it matters.

What it is not: a copy of anyone's life. Events are stored per member, private
to that member unless shared, and only inside the window the brief looks at.

Writing
-------
An accepted obligation becomes one event on the calendar of the member who
accepted it, if that member connected Google with `calendar.events.owned`
(sensitive, not restricted: ordinary verification, no CASA). One reconciler
decides, per obligation, what should be true -- accepted, not superseded, its
notice not handled, dated -- and makes the calendar match: insert when it
should exist and does not, delete when it exists and should not. Every
change that can flip that answer (decide, handled, reopen, re-read) queues
the reconciler; nothing calls Google inline from a request.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from familyos import audit, jobs
from familyos.db import pool
from familyos.identity import Principal
from familyos.intake import google
from familyos.intake.mailbox import _mark_reconnect, _open_token, _require_client
from familyos.settings import settings

logger = logging.getLogger(__name__)

# How far ahead to keep. Matched to the brief's horizon: holding more would be
# keeping a family's diary for no one's benefit.
AHEAD_DAYS = 45
BEHIND_DAYS = 1
# A notice with a time clashes when it overlaps. A notice with only a date is
# compared against the whole day.
DAY = dt.timedelta(days=1)


async def accounts_with_calendar() -> list[dict]:
    rows = await pool().fetch(
        "SELECT * FROM google_accounts WHERE disconnected_at IS NULL AND NOT needs_reconnect "
        "AND ($1 = ANY(scopes) OR $2 = ANY(scopes))", google.CALENDAR_SCOPE, google.CALENDAR_WRITE_SCOPE)
    return [dict(r) for r in rows]


async def sync(account_id: uuid.UUID, *, now: dt.datetime | None = None, transport=None) -> dict:
    """Read one account's primary calendar for the window the brief cares about."""
    now = now or dt.datetime.now(dt.UTC)
    client_id, client_secret = _require_client()
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM google_accounts WHERE id = $1 AND disconnected_at IS NULL AND NOT needs_reconnect",
            account_id)
        if row is None:
            return {"skipped": "gone"}
        if not google.has_calendar(row["scopes"]):
            return {"skipped": "no_calendar_scope"}
        refresh_token = await _open_token(conn, row)
    if not refresh_token:
        await _mark_reconnect(account_id, "the stored token could not be read")
        return {"skipped": "unreadable_token"}

    try:
        token = await google.refresh(refresh_token, client_id=client_id, client_secret=client_secret,
                                     transport=transport)
    except google.NeedsReconnect as exc:
        await _mark_reconnect(account_id, str(exc))
        return {"skipped": "needs_reconnect"}

    try:
        events, _ = await google.list_events(
            token.access_token, time_min=now - dt.timedelta(days=BEHIND_DAYS),
            time_max=now + dt.timedelta(days=AHEAD_DAYS), transport=transport)
    except google.GoogleError as exc:
        await pool().execute(
            "UPDATE google_accounts SET calendar_synced_at = NOW(), calendar_error = $2 WHERE id = $1",
            account_id, str(exc)[:500])
        return {"skipped": "failed"}

    kept = dropped = 0
    async with pool().acquire() as conn, conn.transaction():
        seen: list[str] = []
        for event in events:
            if event.status == "cancelled":
                continue
            seen.append(event.event_id)
            await conn.execute(
                "INSERT INTO calendar_events (id, household_id, member_id, account_id, external_id, "
                "summary, starts_at, ends_at, all_day) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
                "ON CONFLICT (account_id, external_id) DO UPDATE SET summary = EXCLUDED.summary, "
                "starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, "
                "all_day = EXCLUDED.all_day, synced_at = NOW()",
                uuid.uuid4(), row["household_id"], row["member_id"], account_id, event.event_id,
                event.summary, event.starts_at, event.ends_at, event.all_day)
            kept += 1
        # Anything no longer in the window, or deleted at Google, goes. A stale
        # event would raise a clash against something that is not happening.
        dropped = await conn.fetchval(
            "WITH gone AS (DELETE FROM calendar_events WHERE account_id = $1 AND NOT (external_id = ANY($2::text[])) "
            "RETURNING 1) SELECT count(*) FROM gone", account_id, seen)
        await conn.execute(
            "UPDATE google_accounts SET calendar_synced_at = NOW(), calendar_error = NULL WHERE id = $1",
            account_id)
        await audit.record(row["household_id"], "calendar.synced", actor_kind="system",
                           target_type="google_account", target_id=account_id,
                           detail={"kept": kept, "dropped": dropped}, conn=conn)
    return {"kept": kept, "dropped": dropped}


# ----------------------------------------------------------------------------
# clashes
# ----------------------------------------------------------------------------

# An event the asking member may see: their own, or one shared with the
# household. The same shape as the artifact rule, deliberately.
VISIBLE_EVENT = "(e.household_id = $1 AND (e.visibility = 'shared' OR e.member_id = $2))"

# The window an obligation occupies, and what overlaps it.
#
#   with a time : [due_date + due_time, + 1 hour)
#   without one : the whole day
#
# Both bounds are built as timestamps and pinned to UTC, so a clash does not
# depend on the database server's timezone.
_CLASHES = f"""
WITH span AS (
    -- A clock time is an hour's slot. No clock time ("EOD", "any time", nothing)
    -- is the whole day, and only an obligation that asks for presence (attend)
    -- can collide as a day: a thing to sign or pay by the end of the day is a
    -- deadline, not a slot, and does not clash with an all-day entry (seen
    -- 10 Oct 2026, when "EOD" read as 00:00 and clashed with one).
    SELECT o.id,
           ((o.due_date + COALESCE(t.at, time '00:00')) AT TIME ZONE 'UTC') AS starts,
           ((o.due_date + COALESCE(t.at, time '00:00'))
             + CASE WHEN t.at IS NULL THEN interval '1 day' ELSE interval '1 hour' END) AT TIME ZONE 'UTC' AS ends
    FROM obligations o
    CROSS JOIN LATERAL (SELECT NULLIF(substring(o.due_time from '(\\d{{1,2}}:\\d{{2}})'), '')::time AS at) t
    WHERE o.household_id = $1 AND o.id = ANY($3::uuid[]) AND o.due_date IS NOT NULL
      AND (t.at IS NOT NULL OR o.action = 'attend')
)
SELECT w.id AS obligation_id, e.summary, e.starts_at, e.ends_at, e.all_day
FROM span w
JOIN calendar_events e ON {VISIBLE_EVENT}
 AND e.starts_at < w.ends
 AND e.ends_at > w.starts
ORDER BY e.starts_at
"""


async def clashes_for(p: Principal, obligation_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    """Which of these obligations collide with something already in a calendar
    the asking member may see."""
    if not obligation_ids or not settings.calendar_enabled:
        return {}
    rows = await pool().fetch(_CLASHES, p.household_id, p.member_id, obligation_ids)
    found: dict[uuid.UUID, list[dict]] = {}
    for row in rows:
        found.setdefault(row["obligation_id"], []).append(
            {"summary": row["summary"], "starts_at": row["starts_at"],
             "ends_at": row["ends_at"], "all_day": row["all_day"]})
    return found


async def upcoming(p: Principal, *, days: int = 7) -> list[dict]:
    now = dt.datetime.now(dt.UTC)
    rows = await pool().fetch(
        f"SELECT e.id, e.summary, e.starts_at, e.ends_at, e.all_day FROM calendar_events e "
        f"WHERE {VISIBLE_EVENT} AND e.ends_at > $3 AND e.starts_at < $4 ORDER BY e.starts_at LIMIT 100",
        p.household_id, p.member_id, now, now + dt.timedelta(days=days))
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# the sweep
# ----------------------------------------------------------------------------

KIND = "sync_calendars"
HANDLER_VERSION = "1"


async def sweep(transport=None) -> dict[str, int]:
    counts = {"synced": 0, "skipped": 0}
    if not settings.calendar_enabled:
        return counts
    for account in await accounts_with_calendar():
        try:
            result = await sync(account["id"], transport=transport)
        except Exception:  # noqa: BLE001 - one account must not stop the rest
            logger.warning("calendar %s could not be synced", account["id"], exc_info=True)
            counts["skipped"] += 1
            continue
        counts["synced" if "kept" in result else "skipped"] += 1
    return counts


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    await ctx.plan(["Read the calendars members connected"])
    await ctx.step("0")
    counts = await sweep()
    await ctx.finish_step("0")
    if not settings.calendar_enabled:
        return {**counts, "stopped": "calendar is disabled"}
    every = max(300, settings.calendar_sync_seconds)
    return {**counts, "next_run_at": (now + dt.timedelta(seconds=every)).isoformat()}


async def ensure_scheduled() -> dict | None:
    from familyos import jobs
    if not settings.calendar_enabled:
        return None
    existing = await pool().fetchrow(
        "SELECT id FROM jobs WHERE kind = $1 AND status NOT IN ('succeeded', 'failed', 'cancelled') LIMIT 1", KIND)
    if existing is not None:
        return None
    return await jobs.create(KIND, {}, next_run_at=dt.datetime.now(dt.UTC))


def register() -> None:
    from familyos import jobs
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("calendar_sync_seconds",))
    jobs.register(WRITE_KIND, _handle_write, version=WRITE_VERSION, settings_keys=("timezone", "console_url"))


def describe() -> str:
    if not settings.calendar_enabled:
        return "Calendar is off (FAMILYOS_CALENDAR_ENABLED=false)."
    return ("Calendar is on, read-only, for clashes only: calendar.readonly is a sensitive scope, "
            f"not a restricted one, so no CASA assessment. Window: {AHEAD_DAYS} days ahead.")


# ----------------------------------------------------------------------------
# writing: one reconciler per obligation
# ----------------------------------------------------------------------------

WRITE_KIND = "calendar_event"
WRITE_VERSION = "1"

_DESIRED = """
SELECT o.id, o.household_id, o.title, o.due_date, o.end_date, o.due_time, o.status, o.superseded_at,
       o.decided_by, o.calendar_event_id, o.calendar_account_id, a.handled_at, a.id AS artifact_id,
       COALESCE(NULLIF(a.source->>'subject', ''), a.filename, a.channel) AS headline
FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id WHERE o.id = $1
"""


def _hhmm(text: str | None) -> dt.time | None:
    """A due_time as the extractor writes it ("17:00", "5:00 p.m.", "1545 Hrs")."""
    import re
    if not text:
        return None
    m = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*(a\.?m\.?|p\.?m\.?)?", text, re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "").replace(".", "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return dt.time(hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None


def _span(text: str | None) -> tuple[dt.time | None, dt.time | None]:
    """A time, or a span of times as the notice wrote it ("8:30 a.m. to
    12:30 p.m.", "0830-1230 Hrs"): the start, and the end when there is one."""
    import re
    if not text:
        return None, None
    parts = re.split(r"\s*(?:to|till|until|-|\u2013|\u2014)\s*", text, maxsplit=1)
    start = _hhmm(parts[0])
    end = _hhmm(parts[1]) if len(parts) > 1 else None
    if start and end and not re.search(r"a\.?m|p\.?m", parts[0], re.I) and re.search(r"p\.?m", parts[1], re.I) and start.hour < 12 and start.hour + 12 <= end.hour:
        start = start.replace(hour=start.hour + 12)   # "3 to 5 p.m."
    return start, (end if end and start and end > start else None)


def _until_utc(last: dt.date, tz: str | None = None) -> str:
    """The end of a day in the household's zone, as RRULE UNTIL wants it."""
    from zoneinfo import ZoneInfo
    end = dt.datetime.combine(last, dt.time(23, 59, 59), tzinfo=ZoneInfo(tz or settings.timezone)).astimezone(dt.UTC)
    return end.strftime("%Y%m%dT%H%M%SZ")


def event_for(row: dict, tz: str | None = None) -> dict:
    """The API's own shape, from the obligation: all-day on its date, or an
    hour from its time; over a range with a time, the same hours every school
    day until the range ends. The notice's headline rides in the description;
    the obligation id in a private property so the event can be found."""
    start, finish = _span(row["due_time"])
    if start:
        begins = dt.datetime.combine(row["due_date"], start)
        ends = dt.datetime.combine(row["due_date"], finish) if finish else begins + dt.timedelta(hours=1)
        when = {"start": {"dateTime": begins.isoformat(), "timeZone": tz or settings.timezone},
                "end": {"dateTime": ends.isoformat(), "timeZone": tz or settings.timezone}}
        if row.get("end_date") and row["end_date"] > row["due_date"]:
            when["recurrence"] = [f"RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL={_until_utc(row['end_date'])}"]
    else:
        last = row["end_date"] or row["due_date"]
        when = {"start": {"date": row["due_date"].isoformat()},
                "end": {"date": (last + dt.timedelta(days=1)).isoformat()}}
    return {
        "summary": row["title"][:200],
        "description": f"From FamilyOS \u2014 {row['headline']}\n{settings.console_url}#/notices/{row['artifact_id']}",
        "extendedProperties": {"private": {"familyos_obligation": str(row["id"])}},
        **when,
    }


async def _writer_account(conn, household_id: uuid.UUID, member_id: uuid.UUID | None) -> dict | None:
    """The deciding member's connected Google account with the write grant."""
    if member_id is None:
        return None
    row = await conn.fetchrow(
        "SELECT * FROM google_accounts WHERE household_id = $1 AND member_id = $2 AND disconnected_at IS NULL "
        "AND NOT needs_reconnect ORDER BY connected_at DESC LIMIT 1", household_id, member_id)
    return dict(row) if row and google.has_calendar_write(row["scopes"]) else None


async def sync_obligation(obligation_id: uuid.UUID, *, transport=None) -> dict:
    """Make the calendar match what the obligation says now."""
    async with pool().acquire() as conn:
        row = await conn.fetchrow(_DESIRED, obligation_id)
        if row is None:
            return {"skipped": "gone"}
        row = dict(row)
        wanted = (row["status"] == "accepted" and row["superseded_at"] is None and row["handled_at"] is None
                  and row["due_date"] is not None)
        if wanted and row["calendar_event_id"]:
            return {"skipped": "already_there"}
        if not wanted and not row["calendar_event_id"]:
            return {"skipped": "nothing_to_do"}
        if wanted and not await conn.fetchval("SELECT calendar_follows_decisions FROM households WHERE id = $1",
                                              row["household_id"]):
            # The household turned the rule off after this was queued. An
            # event already there is still taken off when its date is dropped.
            return {"skipped": "rule_off"}
        account = None
        if row["calendar_account_id"]:
            account = await conn.fetchrow("SELECT * FROM google_accounts WHERE id = $1", row["calendar_account_id"])
            account = dict(account) if account else None
        if account is None:
            account = await _writer_account(conn, row["household_id"], row["decided_by"])
        if account is None:
            return {"skipped": "no_calendar_write"}
        refresh_token = await _open_token(conn, account)
    if not refresh_token:
        await _mark_reconnect(account["id"], "the stored token could not be read")
        return {"skipped": "unreadable_token"}
    client_id, client_secret = _require_client()
    try:
        token = await google.refresh(refresh_token, client_id=client_id, client_secret=client_secret, transport=transport)
    except google.NeedsReconnect as exc:
        await _mark_reconnect(account["id"], str(exc))
        return {"skipped": "needs_reconnect"}

    if wanted:
        tz = await pool().fetchval("SELECT timezone FROM households WHERE id = $1", row["household_id"])
        event_id = await google.insert_event(token.access_token, event_for(row, tz), transport=transport)
        await pool().execute("UPDATE obligations SET calendar_event_id = $2, calendar_account_id = $3 WHERE id = $1",
                             obligation_id, event_id, account["id"])
        await audit.record(row["household_id"], "calendar.event_written", actor_kind="system",
                           target_type="obligation", target_id=obligation_id, detail={"account_id": str(account["id"])})
        return {"written": event_id}
    removed = await google.delete_event(token.access_token, row["calendar_event_id"], transport=transport)
    await pool().execute("UPDATE obligations SET calendar_event_id = NULL, calendar_account_id = NULL WHERE id = $1",
                         obligation_id)
    await audit.record(row["household_id"], "calendar.event_removed", actor_kind="system",
                       target_type="obligation", target_id=obligation_id, detail={"was_there": removed})
    return {"removed": row["calendar_event_id"]}


async def enqueue_obligations(conn, household_id: uuid.UUID, obligation_ids: list[uuid.UUID], *, force: bool = False) -> int:
    """Queue the reconciler for each, inside the caller's transaction, when
    writing is on. Cheap when nothing is connected: the job says so and ends.
    `force` queues it with the household's switch off too: for a date that
    is gone (dismissed, superseded), whose event must come off regardless."""
    if not settings.calendar_write_enabled:
        return 0
    if not force and not await conn.fetchval("SELECT calendar_follows_decisions FROM households WHERE id = $1", household_id):
        return 0
    for oid in obligation_ids:
        await jobs.create(WRITE_KIND, {"obligation_id": str(oid)}, household_id=household_id, conn=conn)
    return len(obligation_ids)


async def _handle_write(job: dict, ctx) -> dict:
    spec = job["spec"]
    if spec.get("todo_id"):
        return await sync_todo(uuid.UUID(spec["todo_id"]))
    if spec.get("remove_event_id"):
        return await remove_event(uuid.UUID(spec["account_id"]), spec["remove_event_id"], household_id=uuid.UUID(job["household_id"]))
    return await sync_obligation(uuid.UUID(spec["obligation_id"]))


# ----------------------------------------------------------------------------
# writing: a to-do with a date, under the same rule
# ----------------------------------------------------------------------------

_TODO = """
SELECT t.id, t.household_id, t.title, t.note, t.due_date, t.due_time, t.done_at, t.assigned_to, t.created_by,
       t.calendar_event_id, t.calendar_account_id
FROM todos t WHERE t.id = $1
"""


def event_for_todo(row: dict, tz: str | None = None) -> dict:
    """An hour from its time, else all-day on its date. The to-do id rides in
    a private property so the event can be told from the obligations'."""
    if row["due_time"]:
        begins = dt.datetime.combine(row["due_date"], row["due_time"])
        when = {"start": {"dateTime": begins.isoformat(), "timeZone": tz or settings.timezone},
                "end": {"dateTime": (begins + dt.timedelta(hours=1)).isoformat(), "timeZone": tz or settings.timezone}}
    else:
        when = {"start": {"date": row["due_date"].isoformat()},
                "end": {"date": (row["due_date"] + dt.timedelta(days=1)).isoformat()}}
    return {
        "summary": row["title"][:200],
        "description": "From FamilyOS \u2014 a to-do" + (f"\n{row['note']}" if row.get("note") else "") + f"\n{settings.console_url}#/today",
        "extendedProperties": {"private": {"familyos_todo": str(row["id"])}},
        **when,
    }


async def enqueue_todos(conn, household_id: uuid.UUID, todo_ids: list[uuid.UUID]) -> int:
    """Queue the reconciler for each dated to-do, inside the caller's
    transaction, when writing is on and the household wants it."""
    if not settings.calendar_write_enabled:
        return 0
    if not await conn.fetchval("SELECT calendar_follows_decisions FROM households WHERE id = $1", household_id):
        return 0
    for tid in todo_ids:
        await jobs.create(WRITE_KIND, {"todo_id": str(tid)}, household_id=household_id, conn=conn)
    return len(todo_ids)


async def enqueue_event_removal(conn, household_id: uuid.UUID, account_id: uuid.UUID, event_id: str) -> None:
    """A to-do that was removed outright: its row is gone, so the event is
    taken off by its own ids. Always, whatever the switch says now: an event
    for a thing that no longer exists is wrong on any setting."""
    if not settings.calendar_write_enabled:
        return
    await jobs.create(WRITE_KIND, {"remove_event_id": event_id, "account_id": str(account_id)}, household_id=household_id, conn=conn)


async def _token_for(conn, account: dict, *, transport=None):
    refresh_token = await _open_token(conn, account)
    if not refresh_token:
        await _mark_reconnect(account["id"], "the stored token could not be read")
        return None, {"skipped": "unreadable_token"}
    client_id, client_secret = _require_client()
    try:
        return await google.refresh(refresh_token, client_id=client_id, client_secret=client_secret, transport=transport), None
    except google.NeedsReconnect as exc:
        await _mark_reconnect(account["id"], str(exc))
        return None, {"skipped": "needs_reconnect"}


async def sync_todo(todo_id: uuid.UUID, *, transport=None) -> dict:
    """Make the calendar match what the to-do says now: there while it is
    open and dated, gone once it is done or undated."""
    async with pool().acquire() as conn:
        row = await conn.fetchrow(_TODO, todo_id)
        if row is None:
            return {"skipped": "gone"}
        row = dict(row)
        wanted = row["done_at"] is None and row["due_date"] is not None
        if wanted and row["calendar_event_id"]:
            return {"skipped": "already_there"}
        if not wanted and not row["calendar_event_id"]:
            return {"skipped": "nothing_to_do"}
        if wanted and not await conn.fetchval("SELECT calendar_follows_decisions FROM households WHERE id = $1", row["household_id"]):
            return {"skipped": "rule_off"}
        account = None
        if row["calendar_account_id"]:
            account = await conn.fetchrow("SELECT * FROM google_accounts WHERE id = $1", row["calendar_account_id"])
            account = dict(account) if account else None
        if account is None:
            # Whoever it is for, else whoever wrote it.
            account = (await _writer_account(conn, row["household_id"], row["assigned_to"])
                       or await _writer_account(conn, row["household_id"], row["created_by"]))
        if account is None:
            return {"skipped": "no_calendar_write"}
        token, why = await _token_for(conn, account, transport=transport)
    if token is None:
        return why
    if wanted:
        tz = await pool().fetchval("SELECT timezone FROM households WHERE id = $1", row["household_id"])
        event_id = await google.insert_event(token.access_token, event_for_todo(row, tz), transport=transport)
        await pool().execute("UPDATE todos SET calendar_event_id = $2, calendar_account_id = $3 WHERE id = $1",
                             todo_id, event_id, account["id"])
        await audit.record(row["household_id"], "calendar.event_written", actor_kind="system",
                           target_type="todo", target_id=todo_id, detail={"account_id": str(account["id"])})
        return {"written": event_id}
    removed = await google.delete_event(token.access_token, row["calendar_event_id"], transport=transport)
    await pool().execute("UPDATE todos SET calendar_event_id = NULL, calendar_account_id = NULL WHERE id = $1", todo_id)
    await audit.record(row["household_id"], "calendar.event_removed", actor_kind="system",
                       target_type="todo", target_id=todo_id, detail={"was_there": removed})
    return {"removed": row["calendar_event_id"]}


async def remove_event(account_id: uuid.UUID, event_id: str, *, household_id: uuid.UUID, transport=None) -> dict:
    """Take one event off by its ids: for a to-do that no longer exists."""
    async with pool().acquire() as conn:
        account = await conn.fetchrow("SELECT * FROM google_accounts WHERE id = $1", account_id)
        if account is None:
            return {"skipped": "no_account"}
        token, why = await _token_for(conn, dict(account), transport=transport)
    if token is None:
        return why
    removed = await google.delete_event(token.access_token, event_id, transport=transport)
    await audit.record(household_id, "calendar.event_removed", actor_kind="system", target_type="todo", target_id=None,
                       detail={"was_there": removed, "event_id": event_id})
    return {"removed": event_id}
