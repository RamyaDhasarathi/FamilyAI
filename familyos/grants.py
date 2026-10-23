"""Delegation: a carer sees the pickup and nothing else.

A grant bounds *objects*, not people. Instead of inventing a `carer` role --
and then `tutor`, `driver` and `grandparent_but_only_schedules` -- a guardian
names which obligations a member may see, about whom, until when, and why.

Two rules make this safe to add to a system that already works:

  * A grant reaches **obligations, never artifacts.** The carer is told
    "collect Kabir at 15:30 on Thursday"; the notice it was read from may also
    name a fee, a medical appointment and another child, and they never see it.
    `artifacts.VISIBLE_TO_MEMBER` is therefore untouched -- one fragment, the
    same thirteen call sites, unwidened.

  * A guardian may only delegate what they can already see, so this is
    delegation and never escalation.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import artifacts, audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

ACTIONS = ("sign", "pay", "attend", "submit", "prepare", "note")
DEFAULT_DAYS = 90
MAX_DAYS = 365

# The obligation rule: what the member can see in their own right, plus what a
# live grant lets them see. Parameters match artifacts.VISIBLE_TO_MEMBER --
# $1 household, $2 member -- so it drops into the same queries.
VISIBLE_OBLIGATION = f"""({artifacts.VISIBLE_TO_MEMBER} OR EXISTS (
    SELECT 1 FROM grants g
    WHERE g.grantee_member_id = $2
      AND g.household_id = $1
      AND g.revoked_at IS NULL
      AND g.expires_at > NOW()
      AND o.action = ANY(g.actions)
      AND (g.subject_member_id IS NULL OR g.subject_member_id = o.subject_member_id)))"""


def _clean_actions(actions: list[str]) -> list[str]:
    chosen = [a.strip().lower() for a in (actions or []) if a and a.strip()]
    unknown = sorted(set(chosen) - set(ACTIONS))
    if unknown:
        raise Invalid(f"not an action: {', '.join(unknown)}. Choose from: {', '.join(ACTIONS)}")
    if not chosen:
        raise Invalid("a grant with no actions grants nothing; say what the member may see")
    return sorted(set(chosen))


async def issue(actor: Principal, *, grantee_member_id: uuid.UUID, actions: list[str], reason: str,
                subject_member_id: uuid.UUID | None = None, days: int = DEFAULT_DAYS) -> dict:
    """A guardian delegates part of their own view, for a while, with a reason."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can grant access")
    if grantee_member_id == actor.member_id:
        raise Invalid("granting to yourself is not delegation")
    chosen = _clean_actions(actions)
    why = (reason or "").strip()
    if not why:
        raise Invalid("say why, in words the family will understand when they read it later")
    if not 1 <= days <= MAX_DAYS:
        raise Invalid(f"a grant lasts between 1 and {MAX_DAYS} days")

    async with pool().acquire() as conn, conn.transaction():
        grantee = await conn.fetchrow(
            "SELECT id, role FROM members WHERE id = $1 AND household_id = $2",
            grantee_member_id, actor.household_id)
        if grantee is None:
            raise NotFound("member")
        if grantee["role"] == "child":
            raise Invalid("a child does not sign in, so there is nothing to grant them")
        if subject_member_id is not None:
            subject = await conn.fetchval(
                "SELECT 1 FROM members WHERE id = $1 AND household_id = $2",
                subject_member_id, actor.household_id)
            if subject is None:
                raise NotFound("subject")
        row = await conn.fetchrow(
            "INSERT INTO grants (id, household_id, grantee_member_id, granted_by, subject_member_id, "
            "actions, reason, expires_at) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW() + make_interval(days => $8)) "
            "RETURNING *",
            uuid.uuid4(), actor.household_id, grantee_member_id, actor.member_id,
            subject_member_id, chosen, why, days)
        await audit.record(actor.household_id, "grant.issued", actor_member_id=actor.member_id,
                           target_type="member", target_id=grantee_member_id,
                           detail={"actions": chosen, "days": days,
                                   "about": str(subject_member_id) if subject_member_id else "anyone"},
                           conn=conn)
        return await _with_names(conn, row["id"])


_NAMED = (
    "SELECT g.*, gm.display_name AS grantee_name, bm.display_name AS granted_by_name, "
    "sm.display_name AS subject_name FROM grants g "
    "JOIN members gm ON gm.id = g.grantee_member_id "
    "JOIN members bm ON bm.id = g.granted_by "
    "LEFT JOIN members sm ON sm.id = g.subject_member_id "
)


async def _with_names(conn, grant_id: uuid.UUID) -> dict:
    return dict(await conn.fetchrow(_NAMED + "WHERE g.id = $1", grant_id))


async def revoke(actor: Principal, grant_id: uuid.UUID) -> dict:
    """Instant, and recorded at both ends."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can revoke a grant")
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "UPDATE grants SET revoked_at = NOW(), revoked_by = $3 "
            "WHERE id = $1 AND household_id = $2 AND revoked_at IS NULL RETURNING *",
            grant_id, actor.household_id, actor.member_id)
        if row is None:
            raise NotFound("grant")
        await audit.record(actor.household_id, "grant.revoked", actor_member_id=actor.member_id,
                           target_type="member", target_id=row["grantee_member_id"], conn=conn)
    return dict(row)


async def list_for(actor: Principal) -> list[dict]:
    """Every live grant in the household, for the page the family can read.

    Not guardians-only on purpose: a member is entitled to know who can see
    things about them, and a carer is entitled to know what they hold.
    """
    rows = await pool().fetch(
        _NAMED + "WHERE g.household_id = $1 AND g.revoked_at IS NULL AND g.expires_at > NOW() "
        "ORDER BY g.created_at DESC", actor.household_id)
    return [dict(r) for r in rows]


async def expire(now: dt.datetime | None = None) -> int:
    """Nothing to run: expiry is a comparison in the read path, not a sweep.
    Kept as a counter for the console and for anyone looking for the job."""
    return await pool().fetchval(
        "SELECT count(*) FROM grants WHERE revoked_at IS NULL AND expires_at <= $1",
        now or dt.datetime.now(dt.UTC))


def describe() -> str:
    return "grants: delegation reaches obligations only, never artifacts"
