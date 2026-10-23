"""Offers: what FamilyOS could start doing, said in the family's own names,
switched on with a tap or waved away.

An offer is derived from the record each time it is asked for, never
stored: a standing behaviour the household has not switched on but the
record suggests ("Archana handled the last three bills: hand bills to her
as they arrive?"), or a thing FamilyOS is already going to do, said once so
nobody is surprised ("when Airtel's receipt lands I'll mark the bill
handled"). Each says what it will do and what it will not. Accept turns a
switch or opens Ask with the question; Not now is remembered in
suggestion_dismissals under the offer's key, as suggestions are.
"""
from __future__ import annotations

import datetime as dt
import statistics
import uuid

from familyos import rules
from familyos.db import pool
from familyos.identity import NotFound, Principal

MOST = 3                 # offers shown at once: three is a card, more is a list
CLOSES_WITHIN_DAYS = 14  # a bill due this soon gets the "I'll close it" line
RHYTHM_MIN_NOTICES = 4   # a sender needs this many before it has a rhythm
RHYTHM_MAX_GAP_DAYS = 10


def _first(name: str) -> str:
    return (name or "").split()[0] if (name or "").split() else name


async def _switches(household_id: uuid.UUID) -> dict:
    return dict(await pool().fetchrow(
        "SELECT receipts_close_bills, bills_handed_to, holidays_accepted FROM households WHERE id = $1", household_id))


async def _bills_to(p: Principal, sw: dict) -> dict | None:
    """One adult has handled most of the bills and nobody is named: offer
    to hand bills to them as they arrive. Guardians only: it sets a rule."""
    if sw.get("bills_handed_to") or not p.is_guardian:
        return None
    rows = await pool().fetch(
        "SELECT m.id, m.display_name, count(*) AS n FROM obligations o "
        "JOIN input_artifacts a ON a.id = o.artifact_id "
        "JOIN members m ON m.id = COALESCE(a.handled_by, a.assigned_to) "
        "WHERE o.household_id = $1 AND o.action = 'pay' AND o.superseded_at IS NULL AND m.role <> 'child' "
        "GROUP BY m.id, m.display_name ORDER BY n DESC", p.household_id)
    if not rows or rows[0]["n"] < 2 or (len(rows) > 1 and rows[1]["n"] == rows[0]["n"]):
        return None
    who, n = rows[0], rows[0]["n"]
    name = _first(who["display_name"]) if who["id"] != p.member_id else "you"
    return {"key": f"bills_to:{who['id']}", "kind": "rule",
            "title": f"{name.capitalize()} handled the last {n} bills. Hand bills to {name} as they arrive?",
            "body": f"Each bill goes to {name} as it is read, with its pay link beside it. Anyone can still take one over.",
            "limit": "Nothing is paid. The bill is handed over, not settled.",
            "fyi": False, "accept_label": f"Hand bills to {name}", "ask": None,
            "member_id": str(who["id"])}


async def _closes(p: Principal, sw: dict, today: dt.date) -> list[dict]:
    """Bills due soon: say once that the receipt will close them, or offer
    to switch that on."""
    rows = await pool().fetch(
        "SELECT o.id, o.title, o.due_date FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id "
        "WHERE o.household_id = $1 AND o.action = 'pay' AND o.status = 'accepted' AND o.superseded_at IS NULL "
        "AND o.due_date BETWEEN $2 AND $3 AND a.handled_at IS NULL ORDER BY o.due_date LIMIT 3",
        p.household_id, today, today + dt.timedelta(days=CLOSES_WITHIN_DAYS))
    out = []
    on = bool(sw.get("receipts_close_bills", True))
    for r in rows:
        when = r["due_date"].strftime("%-d %b")
        out.append({"key": f"closes:{r['id']}", "kind": "fyi" if on else "rule",
                    "title": (f"When the receipt for “{r['title']}” lands, I'll mark it handled and stop reminding."
                              if on else f"When the receipt for “{r['title']}” lands, shall I mark it handled?"),
                    "body": f"Due {when}. A receipt or a bank's UPI alert with the same biller and amount, around that date, closes it; "
                            "whoever was holding it is told.",
                    "limit": "Strictly on the record: nothing is paid, and a receipt that does not match changes nothing.",
                    "fyi": on, "accept_label": None if on else "Yes, close bills from receipts", "ask": None})
    return out


async def _rhythms(p: Principal, today: dt.date) -> list[dict]:
    """A sender that writes on a rhythm and has gone quiet: say so once."""
    rows = await pool().fetch(
        "SELECT split_part(a.source->>'from', '@', 2) AS sender, array_agg(a.received_at::date ORDER BY a.received_at) AS days "
        "FROM input_artifacts a WHERE a.household_id = $1 AND a.channel LIKE 'gmail%' AND a.parent_id IS NULL "
        "AND a.visibility <> 'private' AND a.source->>'from' LIKE '%@%' GROUP BY 1 HAVING count(*) >= $2",
        p.household_id, RHYTHM_MIN_NOTICES)
    out = []
    for r in rows:
        days = sorted(set(r["days"]))
        if len(days) < RHYTHM_MIN_NOTICES:
            continue
        gaps = [(b - a).days for a, b in zip(days, days[1:], strict=False)]
        usual = statistics.median(gaps)
        if not 3 <= usual <= RHYTHM_MAX_GAP_DAYS:
            continue
        quiet = (today - days[-1]).days
        if quiet <= usual * 1.5 + 2:
            continue
        sender = r["sender"].strip(".")
        out.append({"key": f"rhythm:{sender}:{days[-1].isoformat()}", "kind": "fyi",
                    "title": f"{sender} usually writes every {int(round(usual))} days. Nothing since {days[-1].strftime('%-d %b')}.",
                    "body": "If something was sent and did not arrive, the mailbox or the forwarding is where to look. "
                            "Say Noted and this will not be raised again for this gap.",
                    "limit": "I'll say so once. Nothing is fetched and nobody is written to.",
                    "fyi": True, "accept_label": None, "ask": None})
    return out


async def _overlaps(p: Principal, today: dt.date) -> list[dict]:
    """A trip whose dates sit on an accepted event of the family's (a school
    day, a reopening, a visit): offer the check in Ask, where the answer
    cites both. A meals plan is not a trip, and a bill due that week is not
    a clash, so neither is raised."""
    plans = await pool().fetch(
        "SELECT id, title, starts_on, ends_on FROM plans WHERE household_id = $1 AND status IN ('draft', 'active') "
        "AND shape = 'trip' AND starts_on IS NOT NULL AND ends_on >= $2 ORDER BY starts_on LIMIT 5", p.household_id, today)
    out = []
    for pl in plans:
        hits = await pool().fetch(
            "SELECT o.title, o.due_date FROM obligations o WHERE o.household_id = $1 AND o.status = 'accepted' "
            "AND o.superseded_at IS NULL AND o.kind = 'calendar' AND o.due_date BETWEEN $2 AND $3 ORDER BY o.due_date LIMIT 3",
            p.household_id, pl["starts_on"], pl["ends_on"])
        if not hits:
            continue
        span = f"{pl['starts_on'].strftime('%-d %b')} to {pl['ends_on'].strftime('%-d %b')}"
        named = ", ".join(f"{h['title']} ({h['due_date'].strftime('%-d %b')})" for h in hits)
        question = f"Does the plan “{pl['title']}” ({span}) clash with {named}? What would have to move?"
        out.append({"key": f"overlap:{pl['id']}:{hits[0]['due_date'].isoformat()}", "kind": "ask",
                    "title": f"“{pl['title']}” ({span}) overlaps {named}. Want it checked?",
                    "body": "Ask lays the plan's days against the accepted dates and says what would have to move, with the notices beside it.",
                    "limit": "A question, not a change: nothing is moved, booked or cancelled.",
                    "fyi": False, "accept_label": "Check it in Ask", "ask": question})
    return out


async def _rails(p: Principal, today: dt.date) -> list[dict]:
    """Where each school's notices come from, said once a month, once a
    school has enough notices for the numbers to mean something."""
    from familyos import rails
    out = []
    for s in await rails.summary(p):
        if s["notices"] < 4 or not s["said"]:
            continue
        out.append({"key": f"rails:{s['school_id']}:{today.strftime('%Y-%m')}", "kind": "fyi",
                    "title": s["said"],
                    "body": "That rail is the source; the others are echoes. If it goes quiet for longer than usual I'll say so once, "
                            "and a read of the school app is a tap away on the phone.",
                    "limit": "Nothing is fetched or changed because of this; it says where the notices come from.",
                    "fyi": True, "accept_label": None, "ask": None})
    return out


async def for_member(p: Principal, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    sw = await _switches(p.household_id)
    found: list[dict] = []
    if one := await _bills_to(p, sw):
        found.append(one)
    found += await _rails(p, today)
    found += await _overlaps(p, today)
    found += await _closes(p, sw, today)
    found += await _rhythms(p, today)
    if not found:
        return []
    keys = [o["key"] for o in found]
    gone = {r["source_key"] for r in await pool().fetch(
        "SELECT source_key FROM suggestion_dismissals WHERE household_id = $1 AND source_key = ANY($2::text[])", p.household_id, keys)}
    return [o for o in found if o["key"] not in gone][:MOST]


async def dismiss(p: Principal, key: str) -> None:
    await pool().execute(
        "INSERT INTO suggestion_dismissals (household_id, source_key, dismissed_by) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
        p.household_id, key, p.member_id)


async def accept(p: Principal, key: str) -> dict:
    """Do what the offer said: set the switch, or hand back the question for
    Ask. Either way the offer is not shown again."""
    match = next((o for o in await for_member(p) if o["key"] == key), None)
    if match is None:
        raise NotFound("offer")
    done = "Noted."
    if match["kind"] == "rule" and key.startswith("bills_to:"):
        await rules.set_switches(p, {"bills_handed_to": uuid.UUID(match["member_id"])})
        done = match["accept_label"] + ": on."
    elif match["kind"] == "rule" and key.startswith("closes:"):
        await rules.set_switches(p, {"receipts_close_bills": True})
        done = "Receipts close bills from now on."
    await dismiss(p, key)
    return {"key": key, "done": done, "ask": match.get("ask")}


def describe() -> str:
    return "offers: standing behaviours the record suggests, said in the family's names, switched on with a tap or waved away; derived, never stored"
