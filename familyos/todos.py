"""To-dos the family wrote themselves.

A notice proposes; a person decides. A to-do is the other direction: a person
says "book the dentist by the 20th, Maya's on it", and it is simply so.
Shared across the household's adults, handed to one of them with a note,
done when somebody says so. Nothing here reads a document or sends anything
on anyone's behalf; the assignee is told, the same way a handed-over notice
tells them.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import audit, calendar, notify
from familyos.db import pool
from familyos.identity import Invalid, NotFound, Principal

TITLE_MAX, NOTE_MAX = 200, 500

_ROW = """
SELECT t.id, t.title, t.note, t.due_date, t.due_time, t.assigned_to, t.created_by, t.done_at, t.done_by, t.created_at,
       t.source_key, t.calendar_event_id
FROM todos t WHERE t.household_id = $1
"""


async def with_clashes(p: Principal, rows: list[dict]) -> list[dict]:
    """Adds `clashes` (the summaries of calendar entries at the same time) to each open, timed to-do. Said, not enforced."""
    slots = [(str(r["id"]), r["due_date"], r["due_time"]) for r in rows if r.get("due_date") and r.get("due_time") and not r.get("done_at")]
    found = await calendar.clashes_for_slots(p, slots) if slots else {}
    for r in rows:
        r["clashes"] = [c["summary"] for c in found.get(str(r["id"]), [])] or None
    return rows


async def list_for(p: Principal, *, include_done: bool = False, limit: int = 100) -> list[dict]:
    from familyos import circle
    # A caregiver sees the to-dos given to them and the ones they made, not the household's.
    own = " AND (t.assigned_to = $3 OR t.created_by = $3)" if await circle.is_caregiver(p.member_id) else ""
    sql = _ROW + own + ("" if include_done else " AND t.done_at IS NULL") + \
        " ORDER BY t.done_at IS NOT NULL, t.due_date NULLS LAST, t.created_at LIMIT $2"
    args = [p.household_id, max(1, min(limit, 300))] + ([p.member_id] if own else [])
    return await with_clashes(p, [dict(r) for r in await pool().fetch(sql, *args)])


async def add(p: Principal, title: str, *, due_date: dt.date | None = None, due_time: dt.time | None = None,
              assigned_to: uuid.UUID | None = None, note: str | None = None) -> dict:
    title = " ".join((title or "").split())[:TITLE_MAX]
    note = " ".join((note or "").split())[:NOTE_MAX] or None
    if not title:
        raise Invalid("a to-do needs a few words")
    async with pool().acquire() as conn, conn.transaction():
        assignee = None
        if assigned_to is not None:
            assignee = await conn.fetchrow(
                "SELECT id, display_name, role FROM members WHERE id = $1 AND household_id = $2", assigned_to, p.household_id)
            if assignee is None:
                raise NotFound("member")
            if assignee["role"] == "child":
                raise Invalid("a child does not sign in, so a to-do cannot be handed to them")
        row = await conn.fetchrow(
            "INSERT INTO todos (id, household_id, created_by, assigned_to, title, note, due_date, due_time) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id, title, note, due_date, due_time, assigned_to, created_by, "
            "done_at, done_by, created_at, calendar_event_id",
            uuid.uuid4(), p.household_id, p.member_id, assigned_to, title, note, due_date, due_time if due_date else None)
        await audit.record(p.household_id, "todo.added", actor_member_id=p.member_id, target_type="todo",
                           target_id=row["id"], detail={"assigned_to": str(assigned_to) if assigned_to else None,
                                                        "dated": due_date is not None}, conn=conn)
        if due_date:
            await calendar.enqueue_todos(conn, p.household_id, [row["id"]])
    if assigned_to and assigned_to != p.member_id:
        when = (f" by {due_date.strftime('%-d %b')}" + (f" {due_time.strftime('%H:%M')}" if due_time else "")) if due_date else ""
        await notify.member(assigned_to, f"To do: {title}",
                            f"{p.display_name} added a to-do for you: {title}{when}\n\n"
                            + (f"“{note}”\n\n" if note else "") + "Open FamilyOS to see it.")
    return (await with_clashes(p, [dict(row)]))[0]


async def set_done(p: Principal, todo_id: uuid.UUID, done: bool) -> dict:
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "UPDATE todos SET done_at = CASE WHEN $3 THEN NOW() ELSE NULL END, "
            "done_by = CASE WHEN $3 THEN $4::uuid ELSE NULL END WHERE id = $1 AND household_id = $2 "
            "RETURNING id, title, note, due_date, due_time, assigned_to, created_by, done_at, done_by, created_at, calendar_event_id",
            todo_id, p.household_id, done, p.member_id)
        if row is None:
            raise NotFound("todo")
        await audit.record(p.household_id, "todo.done" if done else "todo.reopened", actor_member_id=p.member_id,
                           target_type="todo", target_id=todo_id, conn=conn)
        if row["due_date"]:
            await calendar.enqueue_todos(conn, p.household_id, [todo_id])
    return dict(row)


async def remove(p: Principal, todo_id: uuid.UUID) -> None:
    async with pool().acquire() as conn, conn.transaction():
        gone = await conn.fetchrow("DELETE FROM todos WHERE id = $1 AND household_id = $2 "
                                   "RETURNING id, calendar_event_id, calendar_account_id", todo_id, p.household_id)
        if gone is None:
            raise NotFound("todo")
        await audit.record(p.household_id, "todo.removed", actor_member_id=p.member_id, target_type="todo",
                           target_id=todo_id, conn=conn)
        if gone["calendar_event_id"] and gone["calendar_account_id"]:
            # The row is gone, so the event's own ids ride in the job.
            await calendar.enqueue_event_removal(conn, p.household_id, gone["calendar_account_id"], gone["calendar_event_id"])
