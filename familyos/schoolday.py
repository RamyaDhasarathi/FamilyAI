"""School copilot, the parts that answer a parent's three daily questions without a model.

- What does each child need tomorrow? Everything dated tomorrow for that child, plus what the same notices say to bring
  or wear, in one short list per child, each line pointing at its notice.
- Which forms are still to come back? Every sign or submit date, per child, with whether it is undecided, open, or
  already returned (the notice marked handled).
- An absence note, drafted from a fixed template with the child's name, class and school; the parent edits it and sends it
  themselves. FamilyOS does not send it.

Everything is read from dates a family accepted or has not decided yet, through the same visibility rules as the brief, so a
caregiver sees only what was shared with them. Nothing here is a guess: a line exists because a notice says it.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import artifacts, clock, grants
from familyos.db import pool
from familyos.identity import NotFound, Principal

_DAY = f"""
SELECT o.id, o.artifact_id, o.title, o.action, o.due_date, o.due_time, o.status, o.subject_member_id, o.optional,
       c.requires, a.handled_at
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
LEFT JOIN claims c ON c.id = o.claim_id
WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed')
  AND o.due_date = $3::date
ORDER BY o.due_time NULLS LAST
"""

_FORMS = f"""
SELECT o.id, o.artifact_id, o.title, o.action, o.due_date, o.status, o.subject_member_id, a.handled_at
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed')
  AND o.action IN ('sign', 'submit') AND o.due_date IS NOT NULL
  AND (a.handled_at IS NULL OR a.handled_at > NOW() - interval '14 days')
  AND o.due_date >= $3::date
ORDER BY o.due_date
"""


async def _children(p: Principal) -> list[dict]:
    rows = await pool().fetch("SELECT id, display_name, school, class_label FROM members WHERE household_id = $1 AND role = 'child' ORDER BY created_at", p.household_id)
    return [dict(r) for r in rows]


async def _instructions(p: Principal, artifact_ids: list) -> dict:
    """What the same notices say to bring, wear or do, per notice, for the notices this member may read: a grant to one event does not open its notice."""
    if not artifact_ids:
        return {}
    rows = await pool().fetch(
        f"SELECT COALESCE(a.parent_id, a.id) AS top, c.title FROM claims c JOIN input_artifacts a ON a.id = c.artifact_id "
        f"JOIN extractions x ON x.id = c.extraction_id WHERE {artifacts.VISIBLE_TO_MEMBER} AND c.kind = 'instruction' AND x.superseded_at IS NULL "
        f"AND COALESCE(a.parent_id, a.id) = ANY($3::uuid[]) ORDER BY c.ordinal", p.household_id, p.member_id, artifact_ids)
    out: dict = {}
    for r in rows:
        out.setdefault(r["top"], []).append(r["title"])
    return out


async def tomorrow(p: Principal, on: dt.date | None = None) -> dict:
    day = on or (clock.today() + dt.timedelta(days=1))
    kids = await _children(p)
    rows = [dict(r) for r in await pool().fetch(_DAY, p.household_id, p.member_id, day)]
    rows.sort(key=lambda r: (r["due_time"] is None, str(r["due_time"] or ""), r["title"] or ""))      # the title tie-break is made here: titles are sealed
    tops = await pool().fetch("SELECT id, COALESCE(parent_id, id) AS top FROM input_artifacts WHERE id = ANY($1::uuid[])", [r["artifact_id"] for r in rows]) if rows else []
    top_of = {r["id"]: r["top"] for r in tops}
    bring = await _instructions(p, list({top_of.get(r["artifact_id"], r["artifact_id"]) for r in rows}))
    per: dict = {k["id"]: {"child": k["display_name"], "class": k["class_label"], "school": k["school"], "items": [], "bring": [], "member_id": k["id"]} for k in kids}
    per[None] = {"child": "Not tied to a child", "class": None, "school": None, "items": [], "bring": [], "member_id": None}
    for r in rows:
        key = r["subject_member_id"] if r["subject_member_id"] in per else None
        kind = "form" if r["action"] in ("sign", "submit") else "pay" if r["action"] in ("pay", "payment") else "event" if r["action"] == "attend" else "note"
        per[key]["items"].append({"title": r["title"], "kind": kind, "time": r["due_time"], "artifact_id": r["artifact_id"], "undecided": r["status"] == "proposed",
                                  "returned": r["handled_at"] is not None})
        for line in bring.get(top_of.get(r["artifact_id"], r["artifact_id"]), []):
            if line not in per[key]["bring"]:
                per[key]["bring"].append(line)
        if "items_to_bring" in (r["requires"] or []) and not bring.get(top_of.get(r["artifact_id"], r["artifact_id"])):
            if "bring what the notice lists" not in per[key]["bring"]:
                per[key]["bring"].append("bring what the notice lists")
    kids_out = [v for k, v in per.items() if k is not None and (v["items"] or v["bring"])]
    if per[None]["items"] or per[None]["bring"]:
        kids_out.append(per[None])
    return {"date": day, "children": kids_out, "nothing": not kids_out}


async def forms(p: Principal, today: dt.date | None = None) -> list[dict]:
    today = today or clock.today()
    names = {k["id"]: k["display_name"] for k in await _children(p)}
    out = []
    for r in await pool().fetch(_FORMS, p.household_id, p.member_id, today - dt.timedelta(days=14)):
        state = "returned" if r["handled_at"] is not None else "undecided" if r["status"] == "proposed" else "to return"
        out.append({"obligation_id": r["id"], "artifact_id": r["artifact_id"], "title": r["title"], "due_date": r["due_date"], "late": r["due_date"] < today and state != "returned",
                    "state": state, "child": names.get(r["subject_member_id"]), "child_id": r["subject_member_id"]})
    out.sort(key=lambda f: ({"to return": 0, "undecided": 1, "returned": 2}[f["state"]], f["due_date"], f["title"] or ""))
    return out


def _fmt(d: dt.date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


async def absence_note(p: Principal, child_id: uuid.UUID, on: dt.date, reason: str | None = None, until: dt.date | None = None) -> dict:
    kid = await pool().fetchrow("SELECT id, display_name, school, class_label FROM members WHERE id = $1 AND household_id = $2 AND role = 'child'", child_id, p.household_id)
    if kid is None:
        raise NotFound("child")
    when = _fmt(on) if not until or until <= on else f"{_fmt(on)} to {_fmt(until)}"
    cls = f", class {kid['class_label']}" if kid["class_label"] else ""
    why = " ".join((reason or "").split())[:200]
    body = (f"Dear Class Teacher,\n\n{kid['display_name']}{cls} will be absent on {when}"
            + (f" because {why}" if why else "") + ".\nKindly excuse the absence. Please let us know if there is any classwork or homework to catch up on.\n\n"
            f"Thank you,\n{p.display_name}")
    school = kid["school"]
    return {"subject": f"Absence: {kid['display_name']}, {when}", "body": body, "school": school, "note": "A draft to edit and send yourself. FamilyOS does not send it."}
