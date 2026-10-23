"""The inbox: every notice a member can see, as a row they can act on, and
who is handling it.

Two things live here that the artifact record does not carry on its own.

**A headline.** A notice arrives as bytes with a filename, and "pasted.txt"
is not a title. The headline is the email subject when there is one, else
the first thing the extractor read from it ("1st Parent-Teacher Meeting"),
else the filename. Derived, never stored: it follows a re-read.

**An assignee.** Whom a notice is *about* is `artifact_subjects`, and it
decides visibility and consent. Who is *handling* it is a different
question, with a note attached ("can you let them know who is on
pickup?"), and it changes nothing about who may see it: a member can only
be handed a notice they can already see. A private notice is shared first,
by its owner, on purpose -- never widened by an assignment on the quiet.

A row's state is derived too: to do while any date on it is undecided,
done once every date is decided, and info when it asked for nothing.

**Handled.** The answer to a hand-over. "Paid, ref 4471" closes the notice
for the person who asked -- told the same way the assignee was -- and makes
it done whatever its dates say, because accepting a date is "remind me",
not "I did it". Its pending reminders are cancelled: nothing nags about a
thing somebody has said is finished. A
message and its attachments are one row: the dates a PDF asks about belong
to the mail it arrived in.
"""
from __future__ import annotations

import logging
import uuid
from email.utils import parseaddr

from familyos import audit, categories, notify
from familyos.artifacts import VISIBLE_TO_MEMBER
from familyos.db import pool
from familyos.identity import Invalid, NotFound, Principal

logger = logging.getLogger(__name__)

NOTE_MAX = 500


class NotVisibleToAssignee(Invalid):
    """The member cannot see the notice, so it cannot be handed to them."""


# The headline, as SQL, so the list and the single read agree.
HEADLINE = ("COALESCE(NULLIF(a.source->>'subject', ''), "
            "(SELECT c.title FROM claims c JOIN extractions x ON x.id = c.extraction_id "
            " WHERE c.artifact_id = a.id AND x.superseded_at IS NULL ORDER BY c.ordinal LIMIT 1), "
            "NULLIF(a.source->>'headline', ''), CASE WHEN a.media_type LIKE 'image/%' THEN 'A photo' END, a.filename, a.channel)")

# A message and its attachments are one notice to the family: the dates in
# the PDF count for the mail it came in, as does a reason nothing was read.
_OWN = "(o.artifact_id = a.id OR o.artifact_id IN (SELECT c.id FROM input_artifacts c WHERE c.parent_id = a.id))"

_FEED = f"""
SELECT a.id, a.channel, a.visibility, a.submitted_by, a.received_at, a.filename, a.media_type, a.source,
       a.assigned_to, a.assigned_note, a.assigned_by, a.assigned_at,
       a.handled_at, a.handled_by, a.handled_note,
       {HEADLINE} AS headline,
       COALESCE((SELECT array_agg(s.member_id) FROM artifact_subjects s WHERE s.artifact_id = a.id), '{{}}') AS subject_member_ids,
       (SELECT count(*) FROM obligations o WHERE {_OWN} AND o.superseded_at IS NULL) AS dates,
       (SELECT count(*) FROM obligations o WHERE {_OWN} AND o.superseded_at IS NULL AND o.status = 'proposed') AS open,
       (SELECT count(*) FROM input_artifacts c WHERE c.parent_id = a.id) AS attachments,
       COALESCE((SELECT array_agg(o.title ORDER BY o.due_date NULLS LAST, o.created_at)
                 FROM (SELECT o.title, o.due_date, o.created_at FROM obligations o
                       WHERE {_OWN} AND o.superseded_at IS NULL
                       ORDER BY o.due_date NULLS LAST, o.created_at LIMIT 3) o), '{{}}') AS preview,
       (SELECT min(o.due_date) FROM obligations o WHERE {_OWN} AND o.superseded_at IS NULL
        AND o.status <> 'dismissed' AND o.due_date >= CURRENT_DATE) AS next_date,
       (SELECT x.non_actionable_reason FROM extractions x
        WHERE (x.artifact_id = a.id OR x.artifact_id IN (SELECT c.id FROM input_artifacts c WHERE c.parent_id = a.id))
          AND x.superseded_at IS NULL AND x.non_actionable_reason IS NOT NULL
        ORDER BY (x.artifact_id = a.id) DESC, x.created_at DESC LIMIT 1) AS reason
FROM input_artifacts a
WHERE {VISIBLE_TO_MEMBER} AND a.parent_id IS NULL
  AND a.channel <> 'errand'   -- a run's step pictures belong to the errand page, not the Inbox
  AND a.received_at > NOW() - make_interval(days => $3)
ORDER BY a.received_at DESC
LIMIT $4
"""


def from_label(channel: str, source: dict | None) -> str:
    """Who it came from, as a person would say it: the sender's name or
    domain for mail, the forwarder for a chat, the channel otherwise."""
    source = source or {}
    if channel.startswith(("email", "gmail")):
        name, address = parseaddr(source.get("from") or "")
        if name:
            return name
        if address and "@" in address:
            return address.rsplit("@", 1)[-1]
        return "email"
    if channel.startswith("telegram") or channel.startswith("whatsapp"):
        return source.get("from_name") or "forwarded"
    if channel == "harvest":
        return "collected"
    if channel == "share":
        return "your phone"
    return "you"


def state_of(row: dict) -> str:
    """Handled is done, whatever its dates say; else to do while any date is
    undecided; done once every date is decided; info when nothing was asked."""
    if row.get("handled_at"):
        return "done"
    if row["open"]:
        return "todo"
    return "done" if row["dates"] else "info"


async def feed(p: Principal, *, days: int = 30, limit: int = 100) -> list[dict]:
    rows = await pool().fetch(_FEED, p.household_id, p.member_id, max(1, min(days, 365)), max(1, min(limit, 300)))
    out = []
    for r in rows:
        row = dict(r)
        row["from_label"] = from_label(row["channel"], row["source"])
        row["category"] = categories.category_of(row["channel"], row["source"])
        row["state"] = state_of(row)
        row["preview"] = list(row["preview"] or [])
        out.append(row)
    return out


async def assign(p: Principal, artifact_id: uuid.UUID, member_id: uuid.UUID | None, note: str | None) -> dict:
    """Hand a notice to a member, with a note, or take it back (member_id
    None). Anyone who can see the notice may; the assignee must be able to
    see it too, and must be someone who signs in."""
    note = " ".join((note or "").split())[:NOTE_MAX] or None
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            f"SELECT a.id, a.visibility, a.submitted_by, a.assigned_to FROM input_artifacts a "
            f"WHERE {VISIBLE_TO_MEMBER} AND a.id = $3 AND a.parent_id IS NULL FOR UPDATE",
            p.household_id, p.member_id, artifact_id)
        if row is None:
            raise NotFound("artifact")
        assignee = None
        if member_id is not None:
            assignee = await conn.fetchrow(
                "SELECT id, display_name, role FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id)
            if assignee is None:
                raise NotFound("member")
            if assignee["role"] == "child":
                raise Invalid("a child does not sign in, so a notice cannot be handed to them")
            if row["visibility"] != "shared" and row["submitted_by"] != member_id:
                # Said plainly, with the fix: the owner shares it, then hands it over.
                raise NotVisibleToAssignee(
                    f"{assignee['display_name']} cannot see this notice. Share it with the household first.")
        updated = await conn.fetchrow(
            "UPDATE input_artifacts SET assigned_to = $2, assigned_note = $3, assigned_by = $4, "
            "assigned_at = CASE WHEN $2::uuid IS NULL THEN NULL ELSE NOW() END WHERE id = $1 "
            "RETURNING id, assigned_to, assigned_note, assigned_by, assigned_at",
            artifact_id, member_id, note if member_id else None, p.member_id if member_id else None)
        headline = await conn.fetchval(f"SELECT {HEADLINE} FROM input_artifacts a WHERE a.id = $1", artifact_id)
        await audit.record(p.household_id, "artifact.assigned" if member_id else "artifact.unassigned",
                           actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id,
                           # Who, never the note: the note is the family's words.
                           detail={"member_id": str(member_id) if member_id else None,
                                   "previous": str(row["assigned_to"]) if row["assigned_to"] else None,
                                   "with_note": bool(note)}, conn=conn)
    if member_id and member_id != p.member_id:
        body = (f"{p.display_name} handed you a notice: {headline}\n\n"
                + (f"“{note}”\n\n" if note else "")
                + "Open FamilyOS to see what it asks for.")
        await notify.member(member_id, f"For you: {headline}", body)
    out = dict(updated)
    out["headline"] = headline
    return out


async def mark_handled(p: Principal, artifact_id: uuid.UUID, note: str | None) -> dict:
    """Say a notice is dealt with. Anyone who can see it may; the note is for
    whoever handed it over, and they are told."""
    note = " ".join((note or "").split())[:NOTE_MAX] or None
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            f"SELECT a.id, a.assigned_to, a.assigned_by, a.handled_at FROM input_artifacts a "
            f"WHERE {VISIBLE_TO_MEMBER} AND a.id = $3 AND a.parent_id IS NULL FOR UPDATE",
            p.household_id, p.member_id, artifact_id)
        if row is None:
            raise NotFound("artifact")
        updated = await conn.fetchrow(
            "UPDATE input_artifacts SET handled_at = NOW(), handled_by = $2, handled_note = $3 WHERE id = $1 "
            "RETURNING id, handled_at, handled_by, handled_note, assigned_to, assigned_by",
            artifact_id, p.member_id, note)
        cancelled = await conn.fetch(
            "UPDATE reminders r SET status = 'cancelled' FROM obligations o "
            "WHERE o.id = r.obligation_id AND o.artifact_id = $1 AND r.status = 'pending' RETURNING r.id", artifact_id)
        headline = await conn.fetchval(f"SELECT {HEADLINE} FROM input_artifacts a WHERE a.id = $1", artifact_id)
        await _calendar_follows(conn, p.household_id, artifact_id)
        await audit.record(p.household_id, "artifact.handled", actor_member_id=p.member_id, target_type="artifact",
                           target_id=artifact_id,
                           detail={"with_note": bool(note), "reminders_cancelled": len(cancelled),
                                   "assigned_by": str(row["assigned_by"]) if row["assigned_by"] else None}, conn=conn)
    # Whoever is on the other end of the hand-over hears it was done.
    for other in {row["assigned_by"], row["assigned_to"]} - {None, p.member_id}:
        await notify.member(other, f"Handled: {headline}",
                            f"{p.display_name} handled a notice: {headline}\n\n"
                            + (f"\u201c{note}\u201d\n\n" if note else "") + "Nothing more to do on it.")
    out = dict(updated)
    out["headline"] = headline
    return out


async def reopen(p: Principal, artifact_id: uuid.UUID) -> dict:
    """Take back "handled". The dates come back as they were; reminders are
    made again by the next sweep."""
    async with pool().acquire() as conn, conn.transaction():
        updated = await conn.fetchrow(
            f"UPDATE input_artifacts a SET handled_at = NULL, handled_by = NULL, handled_note = NULL "
            f"WHERE {VISIBLE_TO_MEMBER} AND a.id = $3 AND a.parent_id IS NULL "
            f"RETURNING id, handled_at, handled_by, handled_note, assigned_to, assigned_by",
            p.household_id, p.member_id, artifact_id)
        if updated is None:
            raise NotFound("artifact")
        headline = await conn.fetchval(f"SELECT {HEADLINE} FROM input_artifacts a WHERE a.id = $1", artifact_id)
        await _calendar_follows(conn, p.household_id, artifact_id)
        await audit.record(p.household_id, "artifact.reopened", actor_member_id=p.member_id, target_type="artifact",
                           target_id=artifact_id, conn=conn)
    out = dict(updated)
    out["headline"] = headline
    return out


async def _calendar_follows(conn, household_id: uuid.UUID, artifact_id: uuid.UUID) -> None:
    """Handled takes the notice's accepted dates off the member's calendar;
    reopening puts them back. The reconciler decides which."""
    from familyos import calendar
    ids = [r["id"] for r in await conn.fetch(
        "SELECT id FROM obligations WHERE artifact_id = $1 AND status = 'accepted' AND superseded_at IS NULL", artifact_id)]
    await calendar.enqueue_obligations(conn, household_id, ids)
