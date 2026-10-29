"""The Family Activity Ledger: every action FamilyOS took or a person took through it, as a receipt, with undo where it
can honestly be undone.

Built on the audit trail (audit.py), which already records who did what to what. This adds what a person wants from a
receipt: what was observed (the notice), what was inferred (the date or the claim read from it, with its quote), which
rule or tap applied, who approved it, what changed, and whether it can be undone. A guardian sees the household's
ledger; anyone else sees only their own actions. Nothing here is a second source of truth: undoing calls the same
function that did the thing, so the same checks apply, and the undo is itself recorded.

What can be undone is deliberately short and checked against the current state: an undo is offered only if nothing
has changed since, so it never reverses a later person's decision.
"""
from __future__ import annotations

import uuid

from familyos import audit, calendar, inbox, todos
from familyos.db import pool
from familyos.identity import NotAllowed, NotFound, Principal

UNDOABLE = ("obligation.accepted", "obligation.dismissed", "artifact.handled", "artifact.assigned", "todo.added")

_RULE = {
    "obligation.accepted": "A date proposed from a notice, accepted by a person",
    "obligation.dismissed": "A date proposed from a notice, waved away by a person",
    "obligation.filed": "A rule: an optional or note-only date that has passed is filed away",
    "artifact.handled": "A person marked the notice handled",
    "artifact.reopened": "A person reopened a handled notice",
    "artifact.assigned": "A person handed the notice to someone",
    "artifact.unassigned": "A person took a handed notice back",
    "todo.added": "A to-do added by a person, or from a suggestion they accepted",
    "todo.removed": "A person removed a to-do",
    "todo.done": "A person ticked a to-do",
    "chat.action_confirmed": "A card shown in chat, confirmed by the person it was shown to",
    "calendar.event_written": "The calendar followed an accepted date",
    "calendar.event_removed": "The calendar followed a dismissed or changed date",
    "amendment.confirmed": "A person confirmed that a later notice changed a date",
    "amendment.rejected": "A person kept the original date",
    "purchase.approved": "A guardian approved this one purchase",
    "purchase.declined": "A guardian declined this purchase",
    "errand.approved": "A guardian approved exactly what was written",
    "reminder.sent": "A reminder sent by the schedule you set",
    "activity.undone": "A person undid an earlier action",
}


async def _latest(action_prefix: str, target_id) -> int | None:
    return await pool().fetchval("SELECT max(id) FROM audit_events WHERE target_id = $1 AND action LIKE $2", target_id, action_prefix + "%")


async def _undoable(p: Principal, e: dict) -> dict | None:
    """The undo for this row if it still can be, else None. Offered only when nothing has changed since."""
    if e["action"] not in UNDOABLE or not e.get("target_id"):
        return None
    if not (p.is_guardian or e.get("actor_member_id") == p.member_id):
        return None
    if e.get("actor_kind") == "system":
        return None
    tid = e["target_id"]
    if e["action"] in ("obligation.accepted", "obligation.dismissed"):
        want = e["action"].split(".")[1]
        row = await pool().fetchrow("SELECT status FROM obligations WHERE id = $1 AND household_id = $2", tid, p.household_id)
        if not row or row["status"] != want or await _latest("obligation.", tid) != e["id"]:
            return None
        return {"label": "Put it back to undecided"}
    if e["action"] == "artifact.handled":
        row = await pool().fetchrow("SELECT handled_at FROM input_artifacts WHERE id = $1 AND household_id = $2", tid, p.household_id)
        if not row or row["handled_at"] is None or await _latest("artifact.handled", tid) < e["id"] or await _latest("artifact.reopened", tid) and await _latest("artifact.reopened", tid) > e["id"]:
            return None
        return {"label": "Reopen the notice"}
    if e["action"] == "artifact.assigned":
        row = await pool().fetchrow("SELECT assigned_to FROM input_artifacts WHERE id = $1 AND household_id = $2", tid, p.household_id)
        latest = await pool().fetchval("SELECT max(id) FROM audit_events WHERE target_id = $1 AND action IN ('artifact.assigned', 'artifact.unassigned')", tid)
        if not row or row["assigned_to"] is None or latest != e["id"]:
            return None
        return {"label": "Take it back"}
    if e["action"] == "todo.added":
        row = await pool().fetchrow("SELECT done_at FROM todos WHERE id = $1 AND household_id = $2", tid, p.household_id)
        if not row or row["done_at"] is not None:
            return None
        return {"label": "Remove the to-do"}
    return None


async def _inferred(p: Principal, e: dict) -> str | None:
    if e["action"].startswith("obligation.") and e.get("target_id"):
        r = await pool().fetchrow(
            "SELECT o.title, o.due_date, c.quote FROM obligations o LEFT JOIN claims c ON c.id = o.claim_id WHERE o.id = $1 AND o.household_id = $2",
            e["target_id"], p.household_id)
        if r:
            when = f" on {r['due_date']:%a %-d %b}" if r["due_date"] else ""
            return f"Read “{r['title']}”{when}" + (f" from the words “{r['quote']}”" if r["quote"] else "")
    return None


async def ledger(p: Principal, limit: int = 50, before_id: int | None = None) -> list[dict]:
    """The household's receipts for a guardian, a member's own for anyone else, newest first."""
    rows = await audit.describe_for(p, limit=max(1, min(limit, 200)), before_id=before_id)
    out = []
    for e in rows:
        if not p.is_guardian and e.get("actor_member_id") != p.member_id:
            continue
        undo = await _undoable(p, e)
        approver = e["who"] if e.get("actor_kind") != "system" else "no one: a rule ran"
        out.append({
            "id": e["id"], "at": e["at"], "who": e["who"], "said": e["said"], "action": e["action"],
            "target": {"type": e.get("target_type"), "id": e.get("target_id")},
            "receipt": {
                "observed": e.get("about"),
                "inferred": await _inferred(p, e),
                "rule": _RULE.get(e["action"]),
                "approved_by": approver,
                "changed": e["said"],
                "external": ({"event_id": e["detail"].get("event_id")} if e["action"].startswith("calendar.") and e.get("detail") else None),
            },
            "undo": ({"available": True, **undo, "method": "POST", "path": f"/v1/activity/{e['id']}/undo"} if undo else None),
        })
    return out


async def undo(p: Principal, event_id: int) -> dict:
    e = await pool().fetchrow("SELECT * FROM audit_events WHERE id = $1 AND household_id = $2", event_id, p.household_id)
    if e is None:
        raise NotFound("activity")
    e = dict(e)
    if await _undoable(p, e) is None:
        raise NotAllowed("this can no longer be undone: something changed since, or it is not yours to undo")
    tid = e["target_id"]
    if e["action"] in ("obligation.accepted", "obligation.dismissed"):
        async with pool().acquire() as conn, conn.transaction():
            await conn.execute("UPDATE obligations SET status = 'proposed', decided_by = NULL, decided_at = NULL WHERE id = $1 AND household_id = $2", tid, p.household_id)
            await calendar.enqueue_obligations(conn, p.household_id, [tid], force=True)
    elif e["action"] == "artifact.handled":
        await inbox.reopen(p, tid)
    elif e["action"] == "artifact.assigned":
        await inbox.assign(p, tid, None, None)
    elif e["action"] == "todo.added":
        await todos.remove(p, tid)
    await audit.record(p.household_id, "activity.undone", actor_member_id=p.member_id, target_type=e["target_type"], target_id=tid,
                       detail={"event_id": event_id, "undid": e["action"]})
    return {"undone": e["action"], "event_id": event_id}


_ = uuid
