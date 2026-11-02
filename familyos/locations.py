"""Where the household's adults are, for each other, if and only if they each said so.

- Opt-in is per member and theirs alone: nobody, a guardian included, can switch it on for someone else.
- Only the latest point is kept. There is no trail, and switching sharing off deletes the point.
- Seeing others needs sharing yourself: you see exactly the people who see you.
- Children do not sign in and are never located here.
- An arrival at a saved place (home or the office) is said once to the other sharing adults, when the point
  moves from outside the place to inside it. Leaving is not announced.
"""
from __future__ import annotations

import datetime as dt
import math

from familyos import audit, notify
from familyos.db import pool
from familyos.identity import NotAllowed, Principal

ARRIVAL_RADIUS_M = 200
MAX_ACCURACY_M = 500           # a fix worse than this says nothing about being at a place
STALE = dt.timedelta(hours=24)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def _places(household_id) -> dict[str, tuple[float, float, str]]:
    h = await pool().fetchrow("SELECT home_place, home_lat, home_lon, work_place, work_lat, work_lon FROM households WHERE id = $1", household_id)
    out = {}
    if h and h["home_lat"] is not None:
        out["home"] = (h["home_lat"], h["home_lon"], "home")
    if h and h["work_lat"] is not None:
        out["work"] = (h["work_lat"], h["work_lon"], "the office")
    return out


def _label(key: str | None) -> str | None:
    return {"home": "home", "work": "the office"}.get(key or "")


async def sharing(p: Principal) -> dict:
    row = await pool().fetchrow("SELECT location_sharing FROM members WHERE id = $1", p.member_id)
    return {"sharing": bool(row and row["location_sharing"])}


async def set_sharing(p: Principal, on: bool) -> dict:
    if p.role == "child":
        raise NotAllowed("children are not located")
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("UPDATE members SET location_sharing = $2 WHERE id = $1", p.member_id, on)
        if not on:
            await conn.execute("DELETE FROM member_locations WHERE member_id = $1", p.member_id)
        await audit.record(p.household_id, "location.sharing", actor_member_id=p.member_id, target_type="member", target_id=p.member_id,
                           detail={"on": on}, conn=conn)
    return {"sharing": on}


async def record(p: Principal, lat: float, lon: float, accuracy_m: int | None, at: dt.datetime | None) -> dict:
    """The phone's latest fix. Refused unless this member is sharing; an older fix than the one kept changes nothing."""
    if p.role == "child":
        raise NotAllowed("children are not located")
    at = (at or dt.datetime.now(dt.UTC))
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt.UTC)
    if at > dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5):
        at = dt.datetime.now(dt.UTC)
    places = await _places(p.household_id)
    here = None
    if accuracy_m is None or accuracy_m <= MAX_ACCURACY_M:
        for key, (plat, plon, _name) in places.items():
            if distance_m(lat, lon, plat, plon) <= ARRIVAL_RADIUS_M:
                here = key
                break
    arrived = None
    async with pool().acquire() as conn, conn.transaction():
        sharing_on = await conn.fetchval("SELECT location_sharing FROM members WHERE id = $1 FOR UPDATE", p.member_id)
        if not sharing_on:
            raise NotAllowed("location sharing is off for you")
        before = await conn.fetchrow("SELECT recorded_at, at_place FROM member_locations WHERE member_id = $1 FOR UPDATE", p.member_id)
        if before and before["recorded_at"] >= at:
            return {"kept": False}
        await conn.execute(
            "INSERT INTO member_locations (member_id, household_id, lat, lon, accuracy_m, recorded_at, at_place, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, NOW()) ON CONFLICT (member_id) DO UPDATE SET lat = $3, lon = $4, accuracy_m = $5, "
            "recorded_at = $6, at_place = $7, updated_at = NOW()", p.member_id, p.household_id, lat, lon, accuracy_m, at, here)
        if here and (before is None or before["at_place"] != here) and (before is not None):
            arrived = here
    if arrived:
        await _say_arrival(p, arrived)
    return {"kept": True, "at": here}


async def _say_arrival(p: Principal, place: str) -> None:
    others = await pool().fetch(
        "SELECT id FROM members WHERE household_id = $1 AND id <> $2 AND role <> 'child' AND location_sharing", p.household_id, p.member_id)
    label = _label(place) or place
    for o in others:
        await notify.member(o["id"], f"{p.display_name} reached {label}", f"{p.display_name} has arrived at {label}.")


async def family(p: Principal) -> dict:
    """Who is where. Needs the asker to be sharing too; otherwise only the fact that they are not."""
    me = await sharing(p)
    if not me["sharing"]:
        return {"sharing": False, "people": []}
    now = dt.datetime.now(dt.UTC)
    rows = await pool().fetch(
        "SELECT m.id, m.display_name, l.lat, l.lon, l.accuracy_m, l.recorded_at, l.at_place FROM members m "
        "LEFT JOIN member_locations l ON l.member_id = m.id WHERE m.household_id = $1 AND m.role <> 'child' AND m.location_sharing "
        "ORDER BY m.display_name", p.household_id)
    people = []
    for r in rows:
        if r["recorded_at"] is None:
            people.append({"member_id": r["id"], "name": r["display_name"], "place": None, "lat": None, "lon": None,
                           "recorded_at": None, "stale": True, "waiting": True})
            continue
        people.append({"member_id": r["id"], "name": r["display_name"], "place": _label(r["at_place"]), "lat": r["lat"], "lon": r["lon"],
                       "recorded_at": r["recorded_at"], "stale": now - r["recorded_at"] > STALE, "waiting": False})
    return {"sharing": True, "people": people}
