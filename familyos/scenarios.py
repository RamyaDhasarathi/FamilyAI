""""What if": an impact map for three questions a family actually asks, computed from the record and changing nothing.

- A member is away between two dates: what they hold in that window (hand-offs, dated items about them, what is in their own
  calendar as busy), and who looks free to cover each timed one.
- A purchase of some amount: what is already expected to go out, the budgets, the goals, and the school fees, with and without it.
- School reopens on another date: which dated items (trips, holidays, plans) fall in the days that would be lost.

Every line comes from something already recorded; a scenario that has nothing to say says so. It proposes nothing and writes
nothing. Acting on an impact is a separate step: the decision queue, a hand-off, a budget.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid

from familyos import clock, conflicts, finance, grants
from familyos.db import pool
from familyos.identity import Invalid, NotFound, Principal


async def member_away(p: Principal, member_id: uuid.UUID, start: dt.date, end: dt.date) -> dict:
    if end < start or (end - start).days > 120:
        raise Invalid("a stay away is up to 120 days, with the end not before the start")
    m = await pool().fetchrow("SELECT id, display_name, role FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id)
    if m is None or m["role"] == "child":
        raise NotFound("member")
    adults = [{"id": str(r["id"]), "name": r["display_name"]} for r in await pool().fetch(
        "SELECT id, display_name FROM members WHERE household_id = $1 AND role IN ('guardian', 'adult') AND id <> $2 ORDER BY created_at", p.household_id, member_id)]
    impacts: list[dict] = []
    for r in await pool().fetch(
        "SELECT a.id, COALESCE(a.note, a.filename, 'a notice') AS title, a.assigned_at FROM input_artifacts a WHERE a.household_id = $1 AND a.assigned_to = $2 AND a.handled_at IS NULL AND a.parent_id IS NULL", p.household_id, member_id):
        impacts.append({"kind": "handoff", "title": r["title"], "date": None, "note": "handed to them and still open", "artifact_id": r["id"], "cover": [a["name"] for a in adults]})
    for r in await pool().fetch(
        f"SELECT o.id, o.artifact_id, o.title, o.due_date, o.due_time FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id WHERE {grants.VISIBLE_OBLIGATION} "
        "AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed') AND o.subject_member_id = $3 AND o.due_date BETWEEN $4 AND $5 ORDER BY o.due_date",
        p.household_id, p.member_id, member_id, start, end):
        cover = await conflicts.cover_for(p, r["due_date"], r["due_time"], adults)
        impacts.append({"kind": "date", "title": r["title"], "date": r["due_date"], "note": "a dated item about them", "artifact_id": r["artifact_id"],
                        "cover": [a["name"] for a in (cover["people"] if cover else adults) if a.get("state", "free") != "busy"]})
    tz = await conflicts._tz(p.household_id)
    lo, hi = dt.datetime.combine(start, dt.time.min, tzinfo=tz).astimezone(dt.UTC), dt.datetime.combine(end, dt.time.max, tzinfo=tz).astimezone(dt.UTC)
    busy = await pool().fetchval("SELECT count(*) FROM calendar_events WHERE household_id = $1 AND member_id = $2 AND starts_at < $4 AND ends_at > $3", p.household_id, member_id, lo, hi)
    if busy:
        impacts.append({"kind": "calendar", "title": f"{busy} thing{'s' if busy != 1 else ''} in their own calendar", "date": None, "note": "busy; what they are is theirs to share", "artifact_id": None, "cover": []})
    days = (end - start).days + 1
    return {"scenario": "member_away", "headline": f"{m['display_name']} away {start:%-d %b} to {end:%-d %b} ({days} day{'s' if days != 1 else ''}): {len(impacts)} thing{'s' if len(impacts) != 1 else ''} touched",
            "impacts": impacts, "changes_nothing": True}


async def spend(p: Principal, amount: float, currency: str = "INR", category: str | None = None, today: dt.date | None = None) -> dict:
    if amount <= 0:
        raise Invalid("an amount above zero")
    today = today or clock.today()
    tl = await finance.timeline(p, 30, today)
    out_now = tl["totals"].get(currency.upper(), 0.0)
    impacts = [{"kind": "cash", "title": f"Already expected to go out in the next 30 days: {out_now:,.0f} {currency.upper()}; with this: {out_now + amount:,.0f}", "date": None, "note": "from bills, subscriptions and standing payments"}]
    fees = [i for d in tl["days"] for i in d["items"] if i["amount"] is not None and any(w in i["title"].lower() for w in ("fee", "tuition", "school"))]
    for f in fees:
        impacts.append({"kind": "fee", "title": f"{f['title']}: {f['amount']:,.0f} {f['currency']}", "date": f["date"], "note": "a school payment already expected, which this does not change but sits beside"})
    for b in await finance.budgets(p, today):
        if b["currency"] == currency.upper() and (category is None or b["category"] == category.lower()):
            left = b["left"] - (amount if category else 0)
            impacts.append({"kind": "budget", "title": f"{b['category']} budget: {b['left']:,.0f} left" + (f", {left:,.0f} after this" if category else ""), "date": None,
                            "note": "over the budget after this" if left < 0 else "still inside it"})
    for g in await finance.goals(p):
        if g["currency"] == currency.upper():
            impacts.append({"kind": "goal", "title": f"{g['title']}: {g['left']:,.0f} still to save", "date": g["by_date"], "note": "this purchase does not change the target; it is money not put toward it"})
    return {"scenario": "spend", "headline": f"Spending {amount:,.0f} {currency.upper()}: what it sits beside", "impacts": impacts, "changes_nothing": True}


# The words were a Postgres regex on the title (`\m...`); titles are sealed now, so the match is made here, after the rows are opened.
_REOPENS = re.compile(r"\b(reopen|re-open|reopening|school reopens)", re.I)
_PLANS = re.compile(r"\b(trip|flight|travel|holiday|vacation|tour|camp|visit)\b", re.I)


async def school_reopens(p: Principal, new_date: dt.date) -> dict:
    row = next((r for r in await pool().fetch(
        f"SELECT o.due_date, o.title FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL "
        f"AND o.status IN ('accepted', 'proposed') AND o.due_date >= {clock.sql_date()} - 30 ORDER BY o.due_date", p.household_id, p.member_id)
        if _REOPENS.search(r["title"] or "")), None)
    if row is None:
        return {"scenario": "school_reopens", "headline": "No reopening date is recorded, so there is nothing to compare with", "impacts": [], "changes_nothing": True}
    old = row["due_date"]
    if new_date >= old:
        return {"scenario": "school_reopens", "headline": f"{new_date:%-d %b} is not earlier than the recorded reopening, {old:%-d %b}", "impacts": [], "changes_nothing": True}
    impacts = []
    for r in await pool().fetch(
        f"SELECT o.artifact_id, o.title, o.due_date FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL "
        "AND o.status IN ('accepted', 'proposed') AND o.due_date >= $3 AND o.due_date < $4 ORDER BY o.due_date", p.household_id, p.member_id, new_date, old):
        if not _PLANS.search(r["title"] or ""):
            continue
        impacts.append({"kind": "date", "title": r["title"], "date": r["due_date"], "note": "falls in the days school would no longer be off", "artifact_id": r["artifact_id"]})
    return {"scenario": "school_reopens", "headline": f"School reopening {new_date:%-d %b} instead of {old:%-d %b}: {len(impacts)} plan{'s' if len(impacts) != 1 else ''} in the way", "impacts": impacts, "changes_nothing": True}
