"""One place for what is known about a person, and what only they (and a guardian) may change.

A member's profile gathers what used to be on four pages: how they are reached (their number, Telegram, quiet hours and the morning message), where they
work and when they usually start (for the commute on Today), and, for a guardian looking at anyone, the details the emergency card and the school
rules use. Reading and writing follow one rule: a person may read and change their own; a guardian may read and change anyone's; nobody else sees a
thing, and a child has no work place and no reach settings of their own.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import audit, interruptions
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal


async def _target(p: Principal, member_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT * FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id)
    if row is None:
        raise NotFound("member")
    if member_id != p.member_id and not p.is_guardian:
        raise NotAllowed("only that person, or a guardian, sees their profile")
    return dict(row)


def _time(value: str | dt.time | None) -> dt.time | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.time):
        return value.replace(second=0, microsecond=0)
    try:
        return dt.time.fromisoformat(str(value)[:5])
    except ValueError:
        raise Invalid("a time is written like 09:30") from None


async def get(p: Principal, member_id: uuid.UUID) -> dict:
    m = await _target(p, member_id)
    child = m["role"] == "child"
    out = {
        "id": m["id"], "display_name": m["display_name"], "role": m["role"], "email": m["email"], "phone": m["phone"],
        "date_of_birth": m["date_of_birth"], "school": m["school"], "class_label": m["class_label"],
        "allergies": m["allergies"], "blood_group": m["blood_group"], "is_me": member_id == p.member_id,
        "work": None if child else {"place": m["work_place"], "lat": m["work_lat"], "lon": m["work_lon"],
                                    "starts": m["work_starts"].strftime("%H:%M") if m["work_starts"] else None},
        "telegram_linked": (m["telegram_chat_id"] is not None) if member_id == p.member_id else None,
        "reach": None,
    }
    if member_id == p.member_id and not child:
        out["reach"] = await interruptions.prefs(member_id)
    return out


async def set_work(p: Principal, member_id: uuid.UUID, *, label: str | None, lat: float | None, lon: float | None, starts: str | None) -> dict:
    """Where they work and when they usually start. The words and the point come together (as for the household's places); null clears."""
    m = await _target(p, member_id)
    if m["role"] == "child":
        raise Invalid("a child has no work place")
    if (lat is None) != (lon is None) or (label is None and lat is not None):
        raise Invalid("a place is its words and a point together")
    label = " ".join((label or "").split())[:200] or None
    at = _time(starts)
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("UPDATE members SET work_place = $2, work_lat = $3, work_lon = $4, work_starts = $5 WHERE id = $1", member_id, label, lat, lon, at)
        await audit.record(p.household_id, "member.work_set", actor_member_id=p.member_id, target_type="member", target_id=member_id,
                           detail={"set": lat is not None, "own": member_id == p.member_id}, conn=conn)
    return await get(p, member_id)
