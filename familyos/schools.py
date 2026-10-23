"""The household's schools: one record each, the children attached, the
portal and the groups that belong to it. A child's school is set by name
as before; the name finds or makes the record. Attribution still matches
on the name, so nothing it relied on moved."""
from __future__ import annotations

import datetime as dt
import re
import uuid

import asyncpg

from familyos import audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal


async def find_or_make(conn: asyncpg.Connection, household_id: uuid.UUID, name: str | None) -> uuid.UUID | None:
    """The school record for a name, made on first use. None clears."""
    name = " ".join((name or "").split())
    if not name:
        return None
    row = await conn.fetchrow("SELECT id FROM schools WHERE household_id = $1 AND lower(name) = lower($2)", household_id, name)
    if row:
        return row["id"]
    school_id = uuid.uuid4()
    await conn.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, $3)", school_id, household_id, name)
    return school_id


async def list_for(p: Principal) -> list[dict]:
    """Every school, with the children in it and the sources mapped to it."""
    rows = await pool().fetch(
        "SELECT s.id, s.name, s.portal_url, s.address, s.lat, s.lon, s.starts_at, s.ends_at, s.exam_sheet_url, s.exam_sheet_read_at, s.created_at, "
        "COALESCE((SELECT array_agg(m.display_name ORDER BY m.display_name) FROM members m WHERE m.school_id = s.id), '{}') AS children, "
        "COALESCE((SELECT array_agg(src.source_key ORDER BY src.source_key) FROM source_schools src "
        "          WHERE src.household_id = s.household_id AND lower(src.school) = lower(s.name)), '{}') AS sources "
        "FROM schools s WHERE s.household_id = $1 ORDER BY s.name", p.household_id)
    return [dict(r) for r in rows]


FIELDS = ("name", "portal_url", "exam_sheet_url", "address", "lat", "lon", "starts_at", "ends_at")


async def update(p: Principal, school_id: uuid.UUID, **changes) -> dict:
    """Rename a school, set its portal, its address or its timings. Only the
    fields given change; an explicit null clears one. Guardians only. A rename
    follows through to the children's rows and the source map, which match on it."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can change a school")
    if unknown := set(changes) - set(FIELDS):
        raise Invalid(f"unknown school field: {', '.join(sorted(unknown))}")
    async with pool().acquire() as conn, conn.transaction():
        before = await conn.fetchrow("SELECT * FROM schools WHERE id = $1 AND household_id = $2", school_id, p.household_id)
        if before is None:
            raise NotFound("school")
        new_name = " ".join((changes.get("name") or before["name"]).split())
        sheet = (changes["exam_sheet_url"] or "").strip() or None if "exam_sheet_url" in changes else before["exam_sheet_url"]
        if sheet and not sheet.startswith("https://"):
            raise Invalid("the exam date sheet must be an https address")
        portal = (changes["portal_url"] or "").strip() or None if "portal_url" in changes else before["portal_url"]
        address = " ".join((changes["address"] or "").split())[:200] or None if "address" in changes else before["address"]
        lat, lon = before["lat"], before["lon"]
        if "lat" in changes or "lon" in changes:
            # A point picked on the map search comes with its words.
            lat, lon = changes.get("lat"), changes.get("lon")
            if (lat is None) != (lon is None) or (lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180)):
                raise Invalid("a place is a latitude and a longitude together")
        elif "address" in changes and address != before["address"]:
            # Words typed without a point: the first place the map suggests, or no point.
            from familyos import publiccontext
            lat = lon = None
            if address:
                home = await conn.fetchrow("SELECT home_lat, home_lon FROM households WHERE id = $1", p.household_id)
                try:
                    found = await publiccontext.resolve(address, (home["home_lat"], home["home_lon"]) if home and home["home_lat"] is not None else None)
                except Exception:  # noqa: BLE001
                    found = []
                if found:
                    lat, lon = found[0]["lat"], found[0]["lon"]
                    if address.startswith(("http://", "https://")):
                        address = found[0]["label"][:200]
        starts = _time(changes["starts_at"]) if "starts_at" in changes else before["starts_at"]
        ends = _time(changes["ends_at"]) if "ends_at" in changes else before["ends_at"]
        if starts and ends and ends <= starts:
            raise Invalid("the school day must end after it starts")
        row = await conn.fetchrow(
            "UPDATE schools SET name = $3, portal_url = $4, exam_sheet_url = $5, address = $6, starts_at = $7, ends_at = $8, lat = $9, lon = $10, "
            "exam_sheet_sha256 = CASE WHEN $5 IS DISTINCT FROM exam_sheet_url THEN NULL ELSE exam_sheet_sha256 END "
            "WHERE id = $1 AND household_id = $2 RETURNING *",
            school_id, p.household_id, new_name, portal, sheet, address, starts, ends, lat, lon)
        if new_name.lower() != before["name"].lower():
            await conn.execute("UPDATE members SET school = $2 WHERE school_id = $1", school_id, new_name)
            await conn.execute("UPDATE source_schools SET school = $3 WHERE household_id = $1 AND lower(school) = lower($2)",
                               p.household_id, before["name"], new_name)
            await conn.execute("UPDATE member_classes SET school = $3 WHERE household_id = $1 AND lower(school) = lower($2)",
                               p.household_id, before["name"], new_name)
        await audit.record(p.household_id, "school.updated", actor_member_id=p.member_id, target_type="school",
                           target_id=school_id, detail={"renamed": new_name.lower() != before["name"].lower(), "portal": bool(row["portal_url"]),
                                                        "timings": bool(row["starts_at"])}, conn=conn)
    if "starts_at" in changes or "address" in changes or "lat" in changes:
        # The morning's traffic alert follows the timings and the address.
        from familyos import publiccontext
        await publiccontext.ensure_run_scheduled(p.household_id)
    return dict(row)


def _time(value) -> dt.time | None:
    """A time as HH:MM, a time object, or nothing."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.time):
        return value.replace(second=0, microsecond=0, tzinfo=None)
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise Invalid("a time is HH:MM")
    return dt.time(int(m.group(1)), int(m.group(2)))


def describe() -> str:
    return "schools: one record each with the children, the portal and the groups mapped to it; a child's school is set by name and the name finds or makes the record"
