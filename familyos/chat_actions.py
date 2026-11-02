"""One place where a confirmed proposal becomes an action, for every chat surface.

Ask only proposes. A proposal that passed `chat.resolve` (the person may see what it names, the fields are valid) can be
staged: stored for this member for half an hour under an id. Confirming the id runs the same service function a button
runs, as that member, so permissions, audit and limits are the ordinary ones. Only the member it was staged for can
confirm it, once.

Actions that spend money or reach outside (a purchase, a booking that needs a guardian) are not run here: an errand
is written down for a guardian's approval exactly as before, and nothing here pays.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import uuid

from familyos import audit, chat, inbox, plans, routines, todos
from familyos.db import pool
from familyos.extraction import service as extraction
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)
TTL_MINUTES = 30
KINDS = ("assign", "todo", "handled", "decide", "plan", "errand", "routine", "suggestion", "warranty", "ack", "rule")


def _plain(x):
    return str(x) if isinstance(x, (uuid.UUID, dt.date, dt.time)) else x


async def stage(p: Principal, proposal: dict, *, ttl_minutes: int = TTL_MINUTES, group_id: uuid.UUID | None = None) -> dict | None:
    """Store a resolved, ok proposal. None when it is not one that can be confirmed. Proposals staged with one `group_id` are
    offered together: answering any of them closes the rest."""
    if not proposal.get("ok") or proposal.get("kind") not in KINDS:
        return None
    params = {k: _plain(v) for k, v in proposal.items() if v is not None and k not in ("ok", "why")}
    summary = chat._offer(proposal)
    row = dict(await pool().fetchrow(
        "INSERT INTO pending_actions (id, household_id, member_id, kind, params, summary, expires_at, group_id) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8) RETURNING id, summary, expires_at",
        uuid.uuid4(), p.household_id, p.member_id, proposal["kind"], json.dumps(params), summary[:300],
        dt.datetime.now(dt.UTC) + dt.timedelta(minutes=ttl_minutes), group_id))
    return row


async def _claim(p: Principal, action_id: uuid.UUID, *, cancel: bool = False, choice: bool | None = None) -> dict:
    """Take a pending row once. `choice` keeps the two kinds apart: an action cannot be taken as a choice, nor a choice confirmed
    as an action, and refusing one does not use it up."""
    col = "cancelled_at" if cancel else "done_at"
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            f"UPDATE pending_actions SET {col} = NOW() WHERE id = $1 AND member_id = $2 AND done_at IS NULL AND cancelled_at IS NULL AND expires_at > NOW() "
            "AND ($3::boolean IS NULL OR (kind = 'ask') = $3) RETURNING *",
            action_id, p.member_id, choice)
        if row is None:
            raise NotFound("that suggestion has expired or was already answered")
        if row["group_id"] is not None:
            # The buttons offered with it are answered too (NOW() is this transaction's, so _unclaim can find exactly these).
            await conn.execute("UPDATE pending_actions SET cancelled_at = NOW() WHERE group_id = $1 AND id <> $2 AND done_at IS NULL AND cancelled_at IS NULL",
                               row["group_id"], action_id)
    return dict(row)


async def _unclaim(row: dict) -> None:
    """Give a claimed row, and the buttons that were closed with it, back. Only for a refusal that changed nothing."""
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("UPDATE pending_actions SET done_at = NULL WHERE id = $1", row["id"])
        if row["group_id"] is not None:
            await conn.execute("UPDATE pending_actions SET cancelled_at = NULL WHERE group_id = $1 AND id <> $2 AND cancelled_at = $3 AND done_at IS NULL",
                               row["group_id"], row["id"], row["done_at"])


async def purge_expired(older_than: dt.timedelta = dt.timedelta(days=1)) -> int:
    """Delete pending rows whose time ran out (answered or not) at least `older_than` ago. They only ever matter before they expire."""
    done = await pool().execute("DELETE FROM pending_actions WHERE expires_at < $1", dt.datetime.now(dt.UTC) - older_than)
    return int(done.rsplit(" ", 1)[-1])


async def cancel(p: Principal, action_id: uuid.UUID) -> None:
    row = await _claim(p, action_id, cancel=True)
    params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
    if params.get("dismiss_suggestion"):
        # "Not now" on a suggestion is remembered, so the same one is not offered again.
        from familyos import suggest
        await suggest.dismiss(p, params["dismiss_suggestion"])


async def confirm(p: Principal, action_id: uuid.UUID) -> dict:
    """Run it, as the member who was shown it. Returns what to tell them."""
    row = await _claim(p, action_id, choice=False)
    params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
    try:
        said = await _run(p, row["kind"], params)
    except (Invalid, NotAllowed, NotFound) as exc:
        # A refusal is raised before anything is written, so it is safe to try again once fixed; the person is told why in a sentence.
        await _unclaim(row)
        raise exc
    except Exception:
        # Anything else may have half happened (a write, a send): the row stays used up, so a tap can never run it twice.
        logger.error("a confirmed chat action failed after it was claimed: %s %s", row["kind"], action_id, exc_info=True)
        try:
            await audit.record(p.household_id, "chat.action_failed", actor_member_id=p.member_id, target_type="member", target_id=p.member_id,
                               detail={"kind": row["kind"]})
        except Exception:  # noqa: BLE001 - the original error is the one to raise
            logger.warning("could not record the failed chat action", exc_info=True)
        raise
    await audit.record(p.household_id, "chat.action_confirmed", actor_member_id=p.member_id, target_type="member", target_id=p.member_id,
                       detail={"kind": row["kind"]})
    return {"kind": row["kind"], "said": said, "summary": row["summary"]}


def _id(v):
    return uuid.UUID(v) if v else None


async def _run(p: Principal, kind: str, a: dict) -> str:
    if kind == "todo":
        due = dt.date.fromisoformat(a["due_date"]) if a.get("due_date") else None
        at = dt.time.fromisoformat(a["due_time"]) if a.get("due_time") else None
        await todos.add(p, a["title"], due_date=due, due_time=at, assigned_to=_id(a.get("member_id")), note=a.get("note"))
        return "Added to your to-dos."
    if kind == "assign":
        await inbox.assign(p, _id(a["artifact_id"]), _id(a.get("member_id")), a.get("note"))
        return "Handed over."
    if kind == "handled":
        await inbox.mark_handled(p, _id(a["artifact_id"]), a.get("note"))
        return "Marked handled."
    if kind == "decide":
        await extraction.decide(p, _id(a["obligation_id"]), a["status"])
        return "Accepted. It is on the calendar." if a["status"] == "accepted" else "Set aside."
    if kind == "plan":
        await plans.start(p, a["brief"], shape=a.get("shape") or "trip")
        return "Planning started. Open it in the app to see the plan; nothing is booked."
    if kind == "suggestion":
        from familyos import suggest
        await suggest.accept(p, a["key"])
        return "Added to your to-dos."
    if kind == "warranty":
        from familyos import finance
        bought = dt.date.fromisoformat(a["purchased_on"]) if a.get("purchased_on") else None
        await finance.add_warranty(p, title=a["title"], merchant=a.get("merchant"), purchased_on=bought, return_days=a.get("return_days"),
                                   warranty_months=a.get("warranty_months"), artifact_id=_id(a.get("artifact_id")))
        return "Tracked. You will be told before the cover ends."
    if kind == "ack":
        from familyos import suggest
        await suggest.dismiss(p, a["dismiss_suggestion"])
        return "Noted."
    if kind == "rule":
        from familyos import rules
        if a.get("switch_key") not in rules.ASKABLE or not isinstance(a.get("on"), bool):
            raise Invalid("that rule cannot be changed from here")
        await rules.set_switches(p, {a["switch_key"]: a["on"]})                    # guardians only, audited, from now on
        return f"Turned {'on' if a['on'] else 'off'}: {a.get('title') or a['switch_key']}."
    if kind == "routine":
        made = await routines.create(p, a["instruction"], a.get("weekday"), a["hour"])
        return f"Routine set: {made['when']}."
    if kind == "errand":
        from familyos import errands
        spec = {"what": a.get("what") or a.get("title"), "details": a.get("details"), "bundle": a.get("bundle"),
                "when": {"date": a.get("due_date"), "time": (a.get("due_time") or "")[:5] or None, "part": a.get("part") or "any"},
                "max_amount": a.get("max_amount"), "currency": a.get("currency") or "INR", "payment": "pay_after_service"}
        made = await errands.propose(p, service=a["service"], kind="look" if a.get("look") else "booking", title=a.get("title") or a.get("what"), spec=spec)
        return ("Started. It reads and reports." if a.get("look") else "Written down for a guardian to approve. Nothing runs until they do.") + f" ({made['status']})"
    raise Invalid("that kind of suggestion cannot be confirmed here")


async def stage_choice(p: Principal, text: str, *, ttl_minutes: int = TTL_MINUTES) -> uuid.UUID:
    """A choice offered when Ask asked back: pressing it sends this text as the person's next message."""
    return await pool().fetchval(
        "INSERT INTO pending_actions (id, household_id, member_id, kind, params, summary, expires_at) VALUES ($1, $2, $3, 'ask', $4::jsonb, $5, $6) RETURNING id",
        uuid.uuid4(), p.household_id, p.member_id, json.dumps({"text": text}), text[:300], dt.datetime.now(dt.UTC) + dt.timedelta(minutes=ttl_minutes))


async def take_choice(p: Principal, choice_id: uuid.UUID) -> str:
    """The text of a choice, once, for the member it was offered to."""
    row = await _claim(p, choice_id, choice=True)
    params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
    return params["text"]
