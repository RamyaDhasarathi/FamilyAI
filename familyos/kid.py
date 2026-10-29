"""Child and teen mode: a day a child can run themselves, and the parts that are theirs.

A child never signs in as a member. A guardian hands them a separate key (up to a year, revocable at once) that reaches only
the calls in this file, and each call is keyed by the child the key belongs to, so there is no route from here to the
household's notices, money, other members or settings.

What the child sees: today and tomorrow as a short visual list (what is on, what to bring or wear), a morning and an evening
routine the guardians set, ticks that are theirs, answers to the things they asked a parent, and their own savings goals.
What the child can do: tick things off, ask a parent (which reaches the guardians as a card to answer yes, no or later),
write a private journal, share an entry if they choose, and press "I need a grown-up", which tells the guardians now.

What guardians do not get: the journal. An entry reaches a guardian only if the child shares it. Nothing here scans, scores or
reports on a child; the one escalation is a button the child presses.
"""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

from familyos import audit, clock, notify
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal, _hash

MAX_DAYS = 365
ICONS = ("🪥", "🎒", "👕", "🍽️", "📚", "🛁", "😴", "🧺", "💧", "🚌", "")


class KidPrincipal:
    def __init__(self, child_id, household_id, name, token_id):
        self.child_id, self.household_id, self.name, self.token_id = child_id, household_id, name, token_id


async def authenticate(token: str) -> KidPrincipal | None:
    row = await pool().fetchrow(
        "UPDATE kid_tokens t SET last_used_at = NOW() FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE t.token_hash = $1 AND t.revoked_at IS NULL AND t.expires_at > NOW() AND m.id = t.child_id AND m.role = 'child' AND h.status = 'active' "
        "RETURNING t.id, t.child_id, t.household_id, m.display_name", _hash(token or ""))
    return KidPrincipal(row["child_id"], row["household_id"], row["display_name"], row["id"]) if row else None


# ------------------------------------------------------------------ a guardian's side

async def _child(p: Principal, child_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT id, display_name FROM members WHERE id = $1 AND household_id = $2 AND role = 'child'", child_id, p.household_id)
    if row is None:
        raise NotFound("child")
    return dict(row)


async def issue_token(p: Principal, child_id: uuid.UUID, days: int = 180) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian gives a child their key")
    kid = await _child(p, child_id)
    if not 1 <= days <= MAX_DAYS:
        raise Invalid(f"a key lasts from 1 to {MAX_DAYS} days")
    token = "kid_" + secrets.token_urlsafe(24)
    expires = dt.datetime.now(dt.UTC) + dt.timedelta(days=days)
    tid = await pool().fetchval("INSERT INTO kid_tokens (household_id, child_id, token_hash, created_by, expires_at) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                                p.household_id, child_id, _hash(token), p.member_id, expires)
    await audit.record(p.household_id, "kid.key_issued", actor_member_id=p.member_id, target_type="member", target_id=child_id, detail={"days": days})
    return {"id": tid, "child": kid["display_name"], "token": token, "path": f"/kid/#{token}", "expires_at": expires}


async def tokens(p: Principal, child_id: uuid.UUID) -> list[dict]:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sees a child's keys")
    await _child(p, child_id)
    rows = await pool().fetch("SELECT id, created_at, expires_at, revoked_at, last_used_at FROM kid_tokens WHERE child_id = $1 ORDER BY created_at DESC", child_id)
    now = dt.datetime.now(dt.UTC)
    return [{**dict(r), "active": r["revoked_at"] is None and r["expires_at"] > now} for r in rows]


async def revoke_token(p: Principal, token_id: uuid.UUID) -> None:
    if not p.is_guardian:
        raise NotAllowed("only a guardian revokes a child's key")
    done = await pool().execute("UPDATE kid_tokens SET revoked_at = NOW() WHERE id = $1 AND household_id = $2 AND revoked_at IS NULL", token_id, p.household_id)
    if done.endswith(" 0"):
        raise NotFound("key")
    await audit.record(p.household_id, "kid.key_revoked", actor_member_id=p.member_id, target_type="kid", target_id=token_id)


async def set_routine(p: Principal, child_id: uuid.UUID, items: list[dict]) -> list[dict]:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sets a child's routine")
    await _child(p, child_id)
    clean = []
    for i, it in enumerate(items[:20]):
        label = " ".join(str(it.get("label") or "").split())[:60]
        if label and it.get("slot") in ("morning", "evening"):
            clean.append((it["slot"], label, it.get("icon") if it.get("icon") in ICONS else "", i))
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM kid_routine WHERE child_id = $1", child_id)
        for slot, label, icon, pos in clean:
            await conn.execute("INSERT INTO kid_routine (household_id, child_id, slot, label, icon, position) VALUES ($1, $2, $3, $4, $5, $6)", p.household_id, child_id, slot, label, icon, pos)
        await audit.record(p.household_id, "kid.routine_set", actor_member_id=p.member_id, target_type="member", target_id=child_id, detail={"items": len(clean)}, conn=conn)
    return await _routine(child_id)


async def _routine(child_id: uuid.UUID) -> list[dict]:
    return [dict(r) for r in await pool().fetch("SELECT id, slot, label, icon FROM kid_routine WHERE child_id = $1 ORDER BY slot DESC, position", child_id)]


async def requests_for_guardians(p: Principal) -> list[dict]:
    if not p.is_guardian:
        raise NotAllowed("only a guardian answers a child's questions")
    rows = await pool().fetch("SELECT r.id, r.child_id, m.display_name AS child, r.text, r.created_at FROM kid_requests r JOIN members m ON m.id = r.child_id "
                              "WHERE r.household_id = $1 AND r.answered_at IS NULL ORDER BY r.created_at", p.household_id)
    return [dict(r) for r in rows]


async def answer(p: Principal, request_id: uuid.UUID, answer_: str, note: str | None = None) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian answers a child's questions")
    if answer_ not in ("yes", "no", "later"):
        raise Invalid("yes, no or later")
    row = await pool().fetchrow("UPDATE kid_requests SET answered_at = NOW(), answered_by = $3, answer = $4, note = $5 WHERE id = $1 AND household_id = $2 AND answered_at IS NULL "
                                "RETURNING id, child_id", request_id, p.household_id, p.member_id, answer_, (note or "").strip()[:200] or None)
    if row is None:
        raise NotFound("question")
    await audit.record(p.household_id, "kid.request_answered", actor_member_id=p.member_id, target_type="member", target_id=row["child_id"], detail={"answer": answer_})
    return {"id": row["id"], "answer": answer_}


async def shared_journal(p: Principal, child_id: uuid.UUID) -> list[dict]:
    """Only entries the child chose to share."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian reads what a child shared")
    await _child(p, child_id)
    rows = await pool().fetch("SELECT id, at, text, shared_at FROM kid_journal WHERE child_id = $1 AND shared_at IS NOT NULL ORDER BY at DESC LIMIT 50", child_id)
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ the child's side

_DAY = """
SELECT o.id, o.artifact_id, o.title, o.action, o.due_date, o.due_time
FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id
WHERE o.household_id = $1 AND o.subject_member_id = $2 AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed')
  AND a.visibility = 'shared' AND o.due_date BETWEEN $3::date AND $4::date ORDER BY o.due_date, o.due_time NULLS LAST
"""


async def day(k: KidPrincipal, today: dt.date | None = None) -> dict:
    today = today or clock.today()
    rows = [dict(r) for r in await pool().fetch(_DAY, k.household_id, k.child_id, today, today + dt.timedelta(days=1))]
    rows.sort(key=lambda r: (r["due_date"], r["due_time"] is None, str(r["due_time"] or ""), r["title"] or ""))     # the title tie-break is made here: titles are sealed
    top = {r["id"]: r["top"] for r in await pool().fetch("SELECT id, COALESCE(parent_id, id) AS top FROM input_artifacts WHERE id = ANY($1::uuid[])", [r["artifact_id"] for r in rows])} if rows else {}
    bring: list[str] = []
    if rows:
        for r in await pool().fetch(
            "SELECT c.title FROM claims c JOIN input_artifacts a ON a.id = c.artifact_id JOIN extractions x ON x.id = c.extraction_id "
            "WHERE c.kind = 'instruction' AND x.superseded_at IS NULL AND COALESCE(a.parent_id, a.id) = ANY($1::uuid[]) ORDER BY c.ordinal", list(set(top.values()))):
            if r["title"] not in bring:
                bring.append(r["title"])
    done = {r["key"] for r in await pool().fetch("SELECT key FROM kid_checks WHERE child_id = $1 AND day = $2", k.child_id, today)}
    routine = await _routine(k.child_id)
    slot = lambda s: [{"key": f"routine:{r['id']}", "label": r["label"], "icon": r["icon"], "done": f"routine:{r['id']}" in done} for r in routine if r["slot"] == s]  # noqa: E731
    asked = await pool().fetch("SELECT id, text, answer, note, answered_at, created_at FROM kid_requests WHERE child_id = $1 AND created_at > NOW() - interval '14 days' ORDER BY created_at DESC LIMIT 10", k.child_id)
    goals = await pool().fetch(
        "SELECT g.title, g.target_amount, g.currency, COALESCE((SELECT sum(amount) FROM goal_contributions c WHERE c.goal_id = g.id), 0) AS saved "
        "FROM savings_goals g WHERE g.owner_member_id = $1 AND g.closed_at IS NULL ORDER BY g.created_at", k.child_id)
    return {
        "name": k.name.split()[0], "date": today,
        "today": [{"title": r["title"], "time": r["due_time"], "when": "today" if r["due_date"] == today else "tomorrow"} for r in rows],
        "bring": [{"key": f"bring:{i}:{t[:30]}", "text": t, "done": f"bring:{i}:{t[:30]}" in done} for i, t in enumerate(bring)],
        "morning": slot("morning"), "evening": slot("evening"),
        "asked": [{"id": r["id"], "text": r["text"], "answer": r["answer"], "note": r["note"]} for r in asked],
        "goals": [{"title": g["title"], "target": float(g["target_amount"]), "saved": round(float(g["saved"]), 2), "currency": g["currency"],
                   "percent": round(min(100.0, 100 * float(g["saved"]) / float(g["target_amount"])), 1)} for g in goals],
    }


async def check(k: KidPrincipal, key: str, done: bool, today: dt.date | None = None) -> dict:
    today = today or clock.today()
    key = key[:80]
    if done:
        await pool().execute("INSERT INTO kid_checks (child_id, day, key) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", k.child_id, today, key)
    else:
        await pool().execute("DELETE FROM kid_checks WHERE child_id = $1 AND day = $2 AND key = $3", k.child_id, today, key)
    return {"key": key, "done": done}


async def ask_parent(k: KidPrincipal, text: str) -> dict:
    text = " ".join((text or "").split())[:200]
    if not text:
        raise Invalid("say what you want to ask")
    recent = await pool().fetchval("SELECT count(*) FROM kid_requests WHERE child_id = $1 AND created_at > NOW() - interval '1 hour'", k.child_id)
    if recent >= 5:
        raise NotAllowed("that is a lot of questions in an hour; let them answer first")
    rid = await pool().fetchval("INSERT INTO kid_requests (household_id, child_id, text) VALUES ($1, $2, $3) RETURNING id", k.household_id, k.child_id, text)
    for g in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role = 'guardian'", k.household_id):
        await notify.member(g["id"], f"{k.name.split()[0]} asks: {text[:60]}", f"{k.name.split()[0]} asked: “{text}”. Open FamilyOS, Needs you, to say yes, no or later.")
    return {"id": rid}


async def need_grownup(k: KidPrincipal) -> dict:
    await audit.record(k.household_id, "kid.help", actor_kind="system", target_type="member", target_id=k.child_id)
    for g in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role IN ('guardian', 'adult')", k.household_id):
        await notify.member(g["id"], f"{k.name.split()[0]} needs a grown-up", f"{k.name.split()[0]} pressed “I need a grown-up”. Please go to them or call now.")
    return {"told": True}


async def journal(k: KidPrincipal) -> list[dict]:
    rows = await pool().fetch("SELECT id, at, text, shared_at FROM kid_journal WHERE child_id = $1 ORDER BY at DESC LIMIT 100", k.child_id)
    return [{**dict(r), "shared": r["shared_at"] is not None} for r in rows]


async def write_journal(k: KidPrincipal, text: str) -> dict:
    text = (text or "").strip()[:2000]
    if not text:
        raise Invalid("write something first")
    jid = await pool().fetchval("INSERT INTO kid_journal (child_id, text) VALUES ($1, $2) RETURNING id", k.child_id, text)
    return {"id": jid}


async def share_entry(k: KidPrincipal, entry_id: uuid.UUID) -> dict:
    done = await pool().execute("UPDATE kid_journal SET shared_at = NOW() WHERE id = $1 AND child_id = $2 AND shared_at IS NULL", entry_id, k.child_id)
    if done.endswith(" 0"):
        raise NotFound("entry")
    return {"shared": True}
