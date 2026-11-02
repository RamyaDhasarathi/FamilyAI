"""Connecting a person's own assistant to FamilyOS, and what its key may do.

A key belongs to one adult member and is shown once. It reaches only the tools in mcp.py, each run as that member: what the
member may see is what the assistant sees, and no more. By default a key can read and can propose (a proposal is staged as a card
the member confirms; nothing runs on an assistant's say-so). A key the member marks "may share" can also put a note in front
of the whole family, as an ordinary shared notice labelled with the assistant's name. Keys expire (up to a year), can be
revoked at once, are rate limited, and every call is audited with the key's label and the tool, never its arguments.

The text in tool results comes from household notices and can contain instructions aimed at a model; each result says so, and
nothing here acts on text a result contains.
"""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

from familyos import audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal, _hash

MAX_DAYS = 365
CALLS_PER_MINUTE = 60


class AgentPrincipal:
    def __init__(self, key_id, label, can_share, principal: Principal, task_id=None):
        self.key_id, self.label, self.can_share, self.principal, self.task_id = key_id, label, can_share, principal, task_id


async def issue(p: Principal, label: str, *, can_share: bool = False, days: int = 90) -> dict:
    if p.role == "child":
        raise NotAllowed("children do not connect assistants")
    label = " ".join((label or "").split())[:60]
    if not label:
        raise Invalid("name the assistant, so you can tell your connections apart")
    if not 1 <= days <= MAX_DAYS:
        raise Invalid(f"a connection lasts from 1 to {MAX_DAYS} days")
    token = "agt_" + secrets.token_urlsafe(32)
    expires = dt.datetime.now(dt.UTC) + dt.timedelta(days=days)
    kid = await pool().fetchval("INSERT INTO agent_keys (household_id, member_id, label, token_hash, can_share, expires_at) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                                p.household_id, p.member_id, label, _hash(token), can_share, expires)
    await audit.record(p.household_id, "agent.connected", actor_member_id=p.member_id, target_type="member", target_id=p.member_id,
                       detail={"label": label, "can_share": can_share, "days": days})
    return {"id": kid, "label": label, "token": token, "can_share": can_share, "expires_at": expires,
            "can": ["read what you can see", "propose things for you to confirm"] + (["share a note with the family"] if can_share else [])}


async def list_for(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        "SELECT k.id, k.label, k.can_share, k.created_at, k.expires_at, k.revoked_at, k.last_used_at, "
        "(SELECT count(*) FROM agent_calls c WHERE c.key_id = k.id AND c.at > NOW() - interval '7 days') AS calls_7d "
        "FROM agent_keys k WHERE k.member_id = $1 AND k.task_id IS NULL ORDER BY k.created_at DESC", p.member_id)
    now = dt.datetime.now(dt.UTC)
    return [{**dict(r), "active": r["revoked_at"] is None and r["expires_at"] > now} for r in rows]


async def revoke(p: Principal, key_id: uuid.UUID) -> None:
    done = await pool().execute("UPDATE agent_keys SET revoked_at = NOW() WHERE id = $1 AND member_id = $2 AND revoked_at IS NULL", key_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("connection")
    await audit.record(p.household_id, "agent.revoked", actor_member_id=p.member_id, target_type="member", target_id=p.member_id)


async def authenticate(token: str) -> AgentPrincipal | None:
    row = await pool().fetchrow(
        "UPDATE agent_keys k SET last_used_at = NOW() FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE k.token_hash = $1 AND k.revoked_at IS NULL AND k.expires_at > NOW() AND m.id = k.member_id AND m.role <> 'child' AND h.status = 'active' "
        "RETURNING k.id, k.label, k.can_share, k.task_id, m.id AS member_id, m.household_id, m.role, m.display_name", _hash(token or ""))
    if row is None:
        return None
    return AgentPrincipal(row["id"], row["label"], row["can_share"], Principal(member_id=row["member_id"], household_id=row["household_id"], role=row["role"], display_name=row["display_name"]), row["task_id"])


async def allow_call(a: AgentPrincipal, tool: str) -> bool:
    """Record the call and say whether the key is inside its rate limit."""
    recent = await pool().fetchval("SELECT count(*) FROM agent_calls WHERE key_id = $1 AND at > NOW() - interval '1 minute'", a.key_id)
    if recent >= CALLS_PER_MINUTE:
        return False
    await pool().execute("INSERT INTO agent_calls (key_id, tool) VALUES ($1, $2)", a.key_id, tool[:60])
    await audit.record(a.principal.household_id, "agent.called", actor_member_id=a.principal.member_id, detail={"via": a.label, "tool": tool[:60]})
    return True
