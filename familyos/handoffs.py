"""Hand-offs that close the loop.

Handing a notice to someone is a request, not a drop. The person it goes to says yes, or says they cannot and may suggest
someone; if nobody answers within the household's wait (24 hours by default) it moves to the backup the sender named, or
the sender is told. What a person is waiting on, and what is handed to them, is one view. Counts of open hand-offs per
adult are visible to the adults, as plain numbers, so an uneven load can be seen and talked about; nothing is scored.

Everything here changes the same columns `inbox.assign` does, through it where possible, so the visibility rules, the
audit rows and the notifications stay in one place.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from familyos import audit, inbox, jobs, notify
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)

KIND = "handoffs_sweep"
HANDLER_VERSION = "1"
SWEEP_SECONDS = 900


async def acknowledge(p: Principal, artifact_id: uuid.UUID, response: str, propose_member_id: uuid.UUID | None = None, note: str | None = None) -> dict:
    row = await pool().fetchrow(
        "SELECT a.id, a.assigned_to, a.assigned_by, a.assigned_ack, a.assigned_backup, a.handled_at, "
        "(SELECT m.display_name FROM members m WHERE m.id = a.assigned_by) AS by_name "
        "FROM input_artifacts a WHERE a.id = $1 AND a.household_id = $2 AND a.parent_id IS NULL", artifact_id, p.household_id)
    if row is None:
        raise NotFound("artifact")
    if row["assigned_to"] != p.member_id:
        raise NotAllowed("this was not handed to you")
    if row["handled_at"] is not None:
        raise NotAllowed("this is already handled")
    if row["assigned_ack"] != "pending":
        raise NotAllowed(f"you already answered ({row['assigned_ack']})")
    headline = await _headline(artifact_id)
    sender = row["assigned_by"]
    if response == "accept":
        await pool().execute("UPDATE input_artifacts SET assigned_ack = 'accepted', assigned_ack_at = NOW() WHERE id = $1", artifact_id)
        await audit.record(p.household_id, "handoff.accepted", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id)
        if sender and sender != p.member_id:
            await notify.member(sender, f"{p.display_name} has it", f"{p.display_name} took what you handed over: {headline}.")
        return {"state": "accepted"}
    # declined
    await pool().execute("UPDATE input_artifacts SET assigned_ack = 'declined', assigned_ack_at = NOW() WHERE id = $1", artifact_id)
    await audit.record(p.household_id, "handoff.declined", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id,
                       detail={"proposed": str(propose_member_id) if propose_member_id else None})
    if propose_member_id is not None and propose_member_id not in (p.member_id, sender):
        # They suggest someone: it goes to them, from the original sender, waiting for that person's answer.
        sender_p = await _as_member(sender, p.household_id) if sender else p
        moved = await inbox.assign(sender_p, artifact_id, propose_member_id, (note or "") + (f" (suggested by {p.display_name})" if p.display_name else ""),
                                   row["assigned_backup"])
        if sender and sender != p.member_id:
            await notify.member(sender, f"{p.display_name} can't, and suggested someone", f"{p.display_name} can't take: {headline}. It is now with {await _name(propose_member_id)}, who has to answer.")
        return {"state": "moved", "to": str(propose_member_id), "assigned_ack": moved.get("assigned_ack")}
    # No one suggested: it goes back to the sender, who is told.
    if sender:
        await notify.member(sender, f"{p.display_name} can't take it", f"{p.display_name} can't take: {headline}." + (f" “{note}”" if note else "") + " It is back with you.")
    await pool().execute("UPDATE input_artifacts SET assigned_to = assigned_by, assigned_ack = 'accepted', assigned_ack_at = NOW(), assigned_backup = NULL WHERE id = $1 AND assigned_by IS NOT NULL", artifact_id)
    return {"state": "returned"}


async def _headline(artifact_id) -> str:
    return await pool().fetchval(f"SELECT {inbox.HEADLINE} FROM input_artifacts a WHERE a.id = $1", artifact_id) or "a notice"


async def _name(member_id) -> str:
    return await pool().fetchval("SELECT display_name FROM members WHERE id = $1", member_id) or "someone"


async def _as_member(member_id, household_id) -> Principal:
    m = await pool().fetchrow("SELECT id, role, display_name FROM members WHERE id = $1 AND household_id = $2", member_id, household_id)
    if m is None:
        raise Invalid("the sender is no longer in the household")
    return Principal(member_id=m["id"], household_id=household_id, role=m["role"], display_name=m["display_name"])


async def waiting(p: Principal) -> dict:
    """What the member handed over and is waiting on, and what is handed to them and unanswered or open."""
    base = ("SELECT a.id, a.assigned_to, a.assigned_by, a.assigned_ack, a.assigned_at, a.assigned_note, a.assigned_backup, "
            f"{inbox.HEADLINE} AS headline, "
            "(SELECT display_name FROM members m WHERE m.id = a.assigned_to) AS to_name, "
            "(SELECT display_name FROM members m WHERE m.id = a.assigned_by) AS by_name "
            "FROM input_artifacts a WHERE a.household_id = $1 AND a.parent_id IS NULL AND a.assigned_to IS NOT NULL AND a.handled_at IS NULL ")
    out = []
    for r in await pool().fetch(base + "AND a.assigned_by = $2 AND a.assigned_to <> $2 ORDER BY a.assigned_at DESC LIMIT 50", p.household_id, p.member_id):
        out.append({"id": r["id"], "title": r["headline"], "with": r["to_name"], "state": r["assigned_ack"] or "pending", "since": r["assigned_at"], "has_backup": r["assigned_backup"] is not None, "direction": "waiting_on"})
    for r in await pool().fetch(base + "AND a.assigned_to = $2 ORDER BY a.assigned_at DESC LIMIT 50", p.household_id, p.member_id):
        out.append({"id": r["id"], "title": r["headline"], "with": r["by_name"], "state": r["assigned_ack"] or "accepted", "since": r["assigned_at"], "has_backup": False, "direction": "for_me"})
    return {"items": out}


async def workload(p: Principal) -> list[dict]:
    """Open hand-offs and what was handled in the last 30 days, per adult. Plain counts for the adults to see together."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=30)
    rows = await pool().fetch(
        "SELECT m.id, m.display_name, "
        " (SELECT count(*) FROM input_artifacts a WHERE a.assigned_to = m.id AND a.handled_at IS NULL AND a.parent_id IS NULL) AS open, "
        " (SELECT count(*) FROM input_artifacts a WHERE a.handled_by = m.id AND a.handled_at >= $2) AS handled "
        "FROM members m WHERE m.household_id = $1 AND m.role IN ('guardian', 'adult') ORDER BY m.created_at", p.household_id, since)
    return [{"member_id": r["id"], "name": r["display_name"], "open": r["open"], "handled_30d": r["handled"]} for r in rows]


async def sweep(now: dt.datetime | None = None) -> dict[str, int]:
    """Escalate hand-offs nobody answered: to the backup if one was named, else tell the sender. Once each."""
    out = {"to_backup": 0, "told_sender": 0}
    rows = await pool().fetch(
        "SELECT a.id, a.household_id, a.assigned_to, a.assigned_by, a.assigned_backup, a.assigned_note, "
        f"{inbox.HEADLINE} AS headline "
        "FROM input_artifacts a JOIN households h ON h.id = a.household_id "
        "WHERE a.assigned_ack = 'pending' AND a.handled_at IS NULL AND a.assigned_escalated_at IS NULL "
        "AND a.assigned_at < NOW() - make_interval(hours => h.handoff_escalate_hours)")
    for r in rows:
        who = await _name(r["assigned_to"])
        if r["assigned_backup"] is not None and r["assigned_backup"] != r["assigned_to"]:
            await pool().execute(
                "UPDATE input_artifacts SET assigned_to = $2, assigned_ack = 'pending', assigned_at = NOW(), assigned_backup = NULL, assigned_escalated_at = NOW() WHERE id = $1",
                r["id"], r["assigned_backup"])
            await audit.record(r["household_id"], "handoff.escalated", actor_kind="system", target_type="artifact", target_id=r["id"],
                               detail={"from": str(r["assigned_to"]), "to": str(r["assigned_backup"])})
            await notify.member(r["assigned_backup"], f"For you: {r['headline']}", f"{who} did not answer in time, so this is now with you: {r['headline']}.")
            if r["assigned_by"]:
                await notify.member(r["assigned_by"], "Moved to the backup", f"{who} did not answer, so {r['headline']} went to {await _name(r['assigned_backup'])}.")
            out["to_backup"] += 1
        else:
            await pool().execute("UPDATE input_artifacts SET assigned_escalated_at = NOW() WHERE id = $1", r["id"])
            await audit.record(r["household_id"], "handoff.escalated", actor_kind="system", target_type="artifact", target_id=r["id"], detail={"from": str(r["assigned_to"]), "to": None})
            if r["assigned_by"]:
                await notify.member(r["assigned_by"], f"No answer from {who}", f"{who} has not answered about {r['headline']}. Take it back, or hand it to someone else.")
            await notify.member(r["assigned_to"], f"Still for you: {r['headline']}", f"{await _name(r['assigned_by']) if r['assigned_by'] else 'Someone'} is waiting on your answer about {r['headline']}.")
            out["told_sender"] += 1
    return out


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    return {**await sweep(now), "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled() -> dict | None:
    return await jobs.ensure_recurring(KIND)


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=())
