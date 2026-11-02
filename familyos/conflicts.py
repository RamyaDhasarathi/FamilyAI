"""Calendar conflicts that say who could cover, not just that there is one.

"You have a clash" is a fact; "the meeting ends at 5:15 but pickup is at 5:00, and Arun looks free then: shall I hand it to
him?" is something a person can say yes to. For a dated item with a time that overlaps something in the asker's calendar,
this looks at the household's other adults and says, for each, free, busy or unknown at that time.

Only free or busy is read from another person's calendar, never what the event is: a private appointment is "busy" and
nothing more. An adult with no calendar connected is "unknown", not "free". Nothing is changed here; the answer feeds the
decision card, whose buttons hand the notice to someone, and a hand-off asks them first.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from zoneinfo import ZoneInfo

from familyos.db import pool
from familyos.identity import Principal

DEFAULT_MINUTES = 60          # how long a timed date is taken to last when it does not say


async def _tz(household_id: uuid.UUID) -> ZoneInfo:
    name = await pool().fetchval("SELECT timezone FROM households WHERE id = $1", household_id)
    try:
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001 - an unknown zone name falls back rather than failing a card
        return ZoneInfo("UTC")


def window_of(due: dt.date, at: str | dt.time | None, tz: ZoneInfo, minutes: int = DEFAULT_MINUTES) -> tuple[dt.datetime, dt.datetime] | None:
    """The span a timed date occupies, in UTC; None for a date with no time."""
    if at is None:
        return None
    if isinstance(at, str):
        m = re.search(r"(\d{1,2}):(\d{2})", at)         # the same reading the clash query makes of "17:00" or "5:00 PM"
        if m is None:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
        if re.search(r"p\.?m", at, re.I) and h < 12:
            h += 12
        t = dt.time(h % 24, mi)
    else:
        t = at
    start = dt.datetime.combine(due, t, tzinfo=tz)
    return start.astimezone(dt.UTC), (start + dt.timedelta(minutes=minutes)).astimezone(dt.UTC)


async def free_busy(household_id: uuid.UUID, member_ids: list[uuid.UUID], start: dt.datetime, end: dt.datetime) -> dict[uuid.UUID, str]:
    """free / busy / unknown per member for that span. Unknown = no calendar connected to say."""
    connected = {r["member_id"] for r in await pool().fetch(
        "SELECT DISTINCT member_id FROM calendar_events WHERE household_id = $1 AND member_id = ANY($2::uuid[]) "
        "UNION SELECT member_id FROM google_accounts WHERE household_id = $1 AND member_id = ANY($2::uuid[]) "
        "AND disconnected_at IS NULL AND calendar_synced_at IS NOT NULL", household_id, member_ids)}
    busy = {r["member_id"] for r in await pool().fetch(
        "SELECT DISTINCT member_id FROM calendar_events WHERE household_id = $1 AND member_id = ANY($2::uuid[]) "
        "AND starts_at < $4 AND ends_at > $3", household_id, member_ids, start, end)}
    return {m: ("busy" if m in busy else "free" if m in connected else "unknown") for m in member_ids}


async def cover_for(p: Principal, due: dt.date, at: str | None, adults: list[dict]) -> dict | None:
    """For a timed date: each other adult's free/busy then, free ones first. None when the date has no time."""
    tz = await _tz(p.household_id)
    span = window_of(due, at, tz)
    if span is None or not adults:
        return None
    state = await free_busy(p.household_id, [uuid.UUID(a["id"]) for a in adults], *span)
    order = {"free": 0, "unknown": 1, "busy": 2}
    ranked = sorted(({**a, "state": state[uuid.UUID(a["id"])]} for a in adults), key=lambda a: order[a["state"]])
    return {"window": [span[0].astimezone(tz).strftime("%H:%M"), span[1].astimezone(tz).strftime("%H:%M")], "people": ranked}
