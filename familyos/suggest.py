"""Implied to-dos: what an event quietly asks for.

The "47 things before anyone else realises" are mostly this: a party on
the calendar means a gift, a trip means passports, a PTM means the
questions you meant to raise, a clinic visit means the reports. The event
is already in the record -- a circular read, a date accepted, a calendar
synced. The to-do is implied, and nobody writes it down.

So FamilyOS writes it down as a *suggestion*: a line with a date, why, and
an Add button. Never added on its own -- a suggestion a family did not want
is noise, and noise is how a reminder product gets muted. Added, it is an
ordinary to-do that remembers its source, so the same event never suggests
it twice; dismissed, the cross is remembered for the same reason.

The rules are words, not a model: a handful of event kinds a family has,
each with what it asks for and how many days before. Cheap, explainable,
and wrong in an obvious way when it is wrong.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from urllib.parse import quote_plus

from familyos import calendar, grants
from familyos.db import pool
from familyos.identity import NotFound, Principal

HORIZON_DAYS = 21

# (id, pattern, what it asks for, days before, a link that helps, why)
_RULES: list[tuple[str, re.Pattern[str], str, int, str | None, str]] = [
    ("gift", re.compile(r"\b(birthday|b'?day|bday)\b", re.I), "Gift for {who}", 4,
     "https://www.amazon.in/s?k={q}", "{event} is on {when}; a gift takes a few days to arrive."),
    ("occasion", re.compile(r"\b(wedding|reception|engagement|housewarming|anniversary)\b", re.I), "Gift and outfit for {event}", 7,
     "https://www.amazon.in/s?k={q}", "{event} is on {when}."),
    ("travel", re.compile(r"\b(trip|flight|travel|holiday|vacation|tour)\b", re.I), "Passports, tickets and packing for {event}", 5,
     None, "{event} starts {when}."),
    ("ptm", re.compile(r"\b(ptm|parent[- ]teacher|open house|parents' meeting)\b", re.I), "Questions for the teacher before {event}", 2,
     None, "{event} is on {when}."),
    ("clinic", re.compile(r"\b(doctor|dentist|clinic|hospital|vaccin|check[- ]?up|appointment)\b", re.I), "Reports and insurance card for {event}", 1,
     None, "{event} is on {when}."),
    ("exam", re.compile(r"\b(exam|test|assessment|olympiad)\b", re.I), "Revision plan for {event}", 7,
     None, "{event} is on {when}."),
    ("kit", re.compile(r"\b(sports day|annual day|concert|recital|performance|fancy dress)\b", re.I), "Costume or kit for {event}", 4,
     None, "{event} is on {when}."),
    ("outing", re.compile(r"\b(picnic|field trip|excursion|camp)\b", re.I), "Consent form, snacks and kit for {event}", 3,
     None, "{event} is on {when}."),
]

_EVENTS = f"""
SELECT o.id::text AS key_id, o.title AS summary, o.due_date AS on_date, o.subject_member_id, c.subject_name
FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id LEFT JOIN claims c ON c.id = o.claim_id
WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed')
  AND o.due_date BETWEEN $3::date AND $4::date AND a.handled_at IS NULL
"""


def _who(summary: str, subject_name: str | None) -> str:
    if subject_name:
        return subject_name
    m = re.search(r"\b([A-Z][a-z]+)'s\b", summary)
    return m.group(1) if m else "them"


def implied_from(events: list[dict], today: dt.date) -> list[dict]:
    """Pure: suggestions from events. Each event: key_id, summary, on_date,
    subject_name (optional)."""
    out = []
    for e in events:
        on: dt.date = e["on_date"]
        if on < today:
            continue
        for rule_id, pattern, what, before, link, why in _RULES:
            if not pattern.search(e["summary"] or ""):
                continue
            due = max(today, on - dt.timedelta(days=before))
            who = _who(e["summary"], e.get("subject_name"))
            title = what.format(who=who, event=e["summary"].strip()[:60])
            out.append({
                "key": f"{e['key_id']}:{rule_id}",
                "title": title[:200], "due_date": due,
                "why": why.format(event=e["summary"].strip()[:60], when=on.strftime("%a %-d %b")),
                "event": e["summary"], "event_on": on,
                "link": link.format(q=quote_plus(f"{who} {e['summary']}".strip())) if link else None,
            })
            break
    out.sort(key=lambda s: (s["due_date"], s["event_on"]))
    return out


async def for_member(p: Principal, today: dt.date | None = None) -> list[dict]:
    """Suggestions this member can act on, minus what was already added or
    waved away."""
    today = today or dt.date.today()
    until = today + dt.timedelta(days=HORIZON_DAYS)
    events = [dict(r) for r in await pool().fetch(_EVENTS, p.household_id, p.member_id, today, until)]
    for ev in await calendar.upcoming(p, days=HORIZON_DAYS):
        events.append({"key_id": f"cal:{ev['id']}", "summary": ev["summary"], "on_date": ev["starts_at"].date(),
                       "subject_name": None})
    found = implied_from(events, today)
    if not found:
        return []
    keys = [s["key"] for s in found]
    taken = {r["source_key"] for r in await pool().fetch(
        "SELECT source_key FROM todos WHERE household_id = $1 AND source_key = ANY($2::text[]) "
        "UNION SELECT source_key FROM suggestion_dismissals WHERE household_id = $1 AND source_key = ANY($2::text[])",
        p.household_id, keys)}
    return [s for s in found if s["key"] not in taken]


async def dismiss(p: Principal, key: str) -> None:
    await pool().execute(
        "INSERT INTO suggestion_dismissals (household_id, source_key, dismissed_by) VALUES ($1, $2, $3) "
        "ON CONFLICT DO NOTHING", p.household_id, key, p.member_id)


async def accept(p: Principal, key: str, *, assigned_to: uuid.UUID | None = None) -> dict:
    """Add the suggested to-do, remembering its source so it is not suggested again."""
    from familyos import todos
    match = next((s for s in await for_member(p) if s["key"] == key), None)
    if match is None:
        raise NotFound("suggestion")
    made = await todos.add(p, match["title"], due_date=match["due_date"], assigned_to=assigned_to,
                           note=match["why"] + (f" {match['link']}" if match["link"] else ""))
    await pool().execute("UPDATE todos SET source_key = $2 WHERE id = $1", made["id"], key)
    return {**made, "source_key": key}
