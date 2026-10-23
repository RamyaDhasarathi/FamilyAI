"""Where a notice came from, as a key a household can attach a fact to.

A pasted circular names no school. The group it was pasted from is the
school. This turns an artifact's `source` -- whatever the channel adapter
recorded -- into one stable string per origin, so that "this Telegram group
is First Cry's" can be said once and applied to every later message from it.

Only origins that identify an institution get a key. A parent's own private
chat with the bot, a Cloud API forward (Meta strips the group), an upload or
a paste: none of these say where the notice was before the parent had it, so
none of them get one. Guessing a school from the parent would attribute
every notice they forward to one child.
"""
from __future__ import annotations

import uuid
from email.utils import parseaddr

import asyncpg

from familyos import audit
from familyos.db import pool
from familyos.identity import NotAllowed, Principal
from familyos.intake.gateway import sender_domain


def source_key(channel: str | None, source: dict | None) -> str | None:
    source = source or {}
    if channel in ("telegram", "telegram_media"):
        if source.get("chat_type") in ("group", "supergroup") and source.get("chat_id") is not None:
            return f"telegram:chat:{source['chat_id']}"
        return None
    if channel in ("email", "email_attachment", "gmail", "gmail_attachment"):
        # The From as stored may still carry a display name.
        domain = sender_domain(parseaddr(source.get("from") or "")[1])
        return f"email:{domain}" if domain else None
    if channel in ("whatsapp", "whatsapp_media"):
        # Only the development bridge sees a group; the Cloud API does not.
        group = (source.get("group_name") or source.get("chat_name") or "").strip()
        return f"whatsapp:group:{group.casefold()}" if group else None
    return None


# ----------------------------------------------------------------------------
# what a household has said about its sources
# ----------------------------------------------------------------------------

async def school_for(conn: asyncpg.Connection, household_id: uuid.UUID, key: str | None) -> str | None:
    if not key:
        return None
    return await conn.fetchval("SELECT school FROM source_schools WHERE household_id = $1 AND source_key = $2",
                               household_id, key)


async def remember(p: Principal, key: str, school: str) -> dict:
    """This source is that school. Said once by a guardian; applied to every
    later notice from it. Saying it again replaces."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can say which school a source belongs to")
    key, school = key.strip(), " ".join(school.split())
    if not key or not school:
        raise ValueError("a source and a school are both needed")
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "INSERT INTO source_schools (household_id, source_key, school, set_by) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (household_id, source_key) DO UPDATE SET school = EXCLUDED.school, set_by = EXCLUDED.set_by "
            "RETURNING source_key, school, created_at", p.household_id, key, school, p.member_id)
        await audit.record(p.household_id, "source.school_set", actor_member_id=p.member_id,
                           target_type="source", detail={"source_key": key}, conn=conn)
    return dict(row)


async def forget(p: Principal, key: str) -> bool:
    if not p.is_guardian:
        raise NotAllowed("only a guardian can forget a source")
    return bool(await pool().fetchval(
        "DELETE FROM source_schools WHERE household_id = $1 AND source_key = $2 RETURNING TRUE",
        p.household_id, key.strip()))


async def list_for(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        "SELECT source_key, school, created_at FROM source_schools WHERE household_id = $1 ORDER BY created_at",
        p.household_id)
    return [dict(r) for r in rows]
