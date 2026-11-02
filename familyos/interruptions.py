"""How much FamilyOS may say to a member without being asked.

Reminders for something the person accepted are not counted: they asked for those. This budget covers what FamilyOS
starts on its own (routines now; ideas and nudges next): a quiet window each night and a cap per day. Over the budget
it waits, it does not drop. A person sets their own, and a dismissed suggestion costs the same type its priority
(that part lives with the suggestions).
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos.db import pool


def in_quiet(hour: int, quiet_from: int, quiet_to: int) -> bool:
    """Whether this hour falls in the quiet window, which may cross midnight (22 to 7). Equal ends mean no quiet window."""
    if quiet_from == quiet_to:
        return False
    if quiet_from < quiet_to:
        return quiet_from <= hour < quiet_to
    return hour >= quiet_from or hour < quiet_to


async def prefs(member_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT quiet_from, quiet_to, proactive_daily_cap, morning_hour FROM members WHERE id = $1", member_id)
    return {"quiet_from": row["quiet_from"], "quiet_to": row["quiet_to"], "daily_cap": row["proactive_daily_cap"], "morning_hour": row["morning_hour"]}


async def set_prefs(member_id: uuid.UUID, *, quiet_from: int | None, quiet_to: int | None, daily_cap: int | None,
                    morning_hour: int | None = None, morning_off: bool | None = None) -> dict:
    for name, v, hi in (("quiet_from", quiet_from, 23), ("quiet_to", quiet_to, 23), ("daily_cap", daily_cap, 20), ("morning_hour", morning_hour, 23)):
        if v is not None and not 0 <= v <= hi:
            raise ValueError(f"{name} is a whole number from 0 to {hi}")
    await pool().execute(
        "UPDATE members SET quiet_from = COALESCE($2, quiet_from), quiet_to = COALESCE($3, quiet_to), proactive_daily_cap = COALESCE($4, proactive_daily_cap) WHERE id = $1",
        member_id, quiet_from, quiet_to, daily_cap)
    if morning_off:
        await pool().execute("UPDATE members SET morning_hour = NULL WHERE id = $1", member_id)
    elif morning_hour is not None:
        await pool().execute("UPDATE members SET morning_hour = $2 WHERE id = $1", member_id, morning_hour)
    return await prefs(member_id)


async def allow(member_id: uuid.UUID, local_now: dt.datetime) -> tuple[bool, str | None]:
    """May FamilyOS start a message to this member now? Returns (yes, or the reason it waits)."""
    pr = await prefs(member_id)
    if in_quiet(local_now.hour, pr["quiet_from"], pr["quiet_to"]):
        return False, "quiet hours"
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    sent = await pool().fetchval("SELECT count(*) FROM proactive_log WHERE member_id = $1 AND sent_at >= $2", member_id, start)
    if sent >= pr["daily_cap"]:
        return False, "daily cap reached"
    return True, None


async def record(household_id: uuid.UUID, member_id: uuid.UUID, kind: str) -> None:
    await pool().execute("INSERT INTO proactive_log (id, household_id, member_id, kind) VALUES ($1, $2, $3, $4)", uuid.uuid4(), household_id, member_id, kind)
