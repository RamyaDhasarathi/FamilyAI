"""Source-backed memory: what FamilyOS holds about the household, why it holds it, and how to correct it.

Nothing is stored here. Each fact is derived at read time from where it already lives, with the trail that put it there:
- a child's school and class: set by a guardian (audit.member.school_set) or entered when the child was added;
- which phone app reads a child's school: a rule over the school's name (execution/apps.py), correctable by correcting the school;
- a document's expiry and holder: read from a notice, with the quote it was read from (documents + claims);
- whose a prescription is: read from the pad or set by a person (medications + audit.medication.patient_set).

A fact carries its source, how it is known (stated by a person, read from a notice, or a rule), who may see it, who last corrected
it, when it was last confirmed, and when to look at it again. The household can ask why, correct what is wrong, or confirm what
is right. A correction is recorded with before and after; confirming is recorded with a date, so "last verified" is a fact too.
This is a projection with controls, not a store of merged state: delete the sources and the facts go with them.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import audit, documents, identity
from familyos.db import pool
from familyos.execution import apps
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

REVIEW_AFTER_DAYS = 365          # a school year: a child's class is looked at again each year


async def _last(household_id, action_prefix: str, key: str):
    return await pool().fetchrow(
        "SELECT a.at, a.actor_member_id, a.action, (SELECT display_name FROM members m WHERE m.id = a.actor_member_id) AS who "
        "FROM audit_events a WHERE a.household_id = $1 AND a.action LIKE $2 AND a.detail->>'key' = $3 ORDER BY a.id DESC LIMIT 1", household_id, action_prefix + "%", key)


async def _verified(household_id, key: str):
    r = await _last(household_id, "memory.verified", key)
    return r["at"] if r else None


async def _corrected(household_id, key: str):
    r = await _last(household_id, "memory.corrected", key)
    return {"by": r["who"], "at": r["at"]} if r else None


def _review(at: dt.datetime | None) -> dt.date | None:
    return (at + dt.timedelta(days=REVIEW_AFTER_DAYS)).date() if at else None


async def facts(p: Principal) -> list[dict]:
    out: list[dict] = []
    if p.is_guardian:
        kids = await pool().fetch("SELECT id, display_name, school, class_label, created_at FROM members WHERE household_id = $1 AND role = 'child' ORDER BY created_at", p.household_id)
        for k in kids:
            name = k["display_name"]
            set_ev = await pool().fetchrow(
                "SELECT a.at, (SELECT display_name FROM members m WHERE m.id = a.actor_member_id) AS who FROM audit_events a "
                "WHERE a.household_id = $1 AND a.action = 'member.school_set' AND a.target_id = $2 ORDER BY a.id DESC LIMIT 1", p.household_id, k["id"])
            at = set_ev["at"] if set_ev else k["created_at"]
            skey = f"school:{k['id']}"
            ver = await _verified(p.household_id, skey)
            out.append({"key": skey, "kind": "school", "subject": name, "label": f"{name}'s school and class",
                        "value": ", ".join(x for x in (k["school"], f"class {k['class_label']}" if k["class_label"] else None) if x) or "not set",
                        "source": {"type": "person", "text": f"Entered by {set_ev['who'] if set_ev and set_ev['who'] else 'a guardian'}", "at": at, "artifact_id": None},
                        "how_known": "stated", "confidence": "high", "visible_to": "guardians", "corrected": await _corrected(p.household_id, skey),
                        "last_verified": ver, "review_by": _review(ver or at), "correctable": True})
            ak = apps.app_for_school(k["school"])
            akey = f"app:{k['id']}"
            out.append({"key": akey, "kind": "app", "subject": name, "label": f"The app that reads {name}'s school",
                        "value": apps.APPS[ak]["label"] if ak else "none registered",
                        "source": {"type": "rule", "text": (f"The school name “{k['school']}” matches the list of schools that use {apps.APPS[ak]['label']}" if ak
                                                            else (f"No registered app lists “{k['school']}”" if k["school"] else "No school is set")), "at": None, "artifact_id": None},
                        "how_known": "rule", "confidence": "medium" if ak else "n/a", "visible_to": "guardians", "corrected": None,
                        "last_verified": None, "review_by": None, "correctable": False,
                        "how_to_correct": "Correct the school above; the app follows it. A school that uses an app we do not list can be added to the list."})
    for d in await documents.list_for(p):
        dkey = f"doc:{d['id']}"
        ver = await _verified(p.household_id, dkey)
        quote = await pool().fetchval("SELECT c.quote FROM documents x JOIN claims c ON c.id = x.claim_id WHERE x.id = $1", d["id"])
        out.append({"key": dkey, "kind": "document", "subject": d["holder_name"], "label": f"{d['label'].capitalize()}" + (f" of {d['holder_name']}" if d["holder_name"] else ""),
                    "value": f"expires {d['expires_on']:%-d %b %Y}" if d["expires_on"] else "no expiry read",
                    "source": {"type": "notice", "text": "Read from a notice" + (f": “{quote}”" if quote else ""), "at": d["created_at"], "artifact_id": d["artifact_id"]},
                    "how_known": "read", "confidence": "read from a document", "visible_to": "who can see that notice", "corrected": await _corrected(p.household_id, dkey),
                    "last_verified": ver, "review_by": d["expires_on"], "correctable": False,
                    "how_to_correct": "Open the notice. If the date was misread, correct it there; this follows."})
    return out


async def why(p: Principal, key: str) -> dict:
    f = next((x for x in await facts(p) if x["key"] == key), None)
    if f is None:
        raise NotFound("fact")
    steps = [f"{f['label']}: {f['value']}.", f"How it is known: {f['how_known']}. {f['source']['text']}."]
    if f["source"].get("at"):
        steps.append(f"As of {f['source']['at']:%-d %b %Y}.")
    if f.get("corrected"):
        steps.append(f"Last corrected by {f['corrected']['by']} on {f['corrected']['at']:%-d %b %Y}.")
    steps.append(f"Last confirmed: {f['last_verified']:%-d %b %Y}." if f.get("last_verified") else "It has not been confirmed by anyone yet.")
    if f.get("review_by"):
        steps.append(f"To look at again by {f['review_by']:%-d %b %Y}.")
    return {**f, "explanation": steps}


async def correct(p: Principal, key: str, value: str | None, class_label: str | None = None) -> dict:
    if not key.startswith("school:"):
        raise Invalid("only a child's school and class can be corrected here; correct a document in its notice")
    member_id = uuid.UUID(key.split(":", 1)[1])
    before = await pool().fetchrow("SELECT school, class_label FROM members WHERE id = $1 AND household_id = $2 AND role = 'child'", member_id, p.household_id)
    if before is None:
        raise NotFound("child")
    if not p.is_guardian:
        raise NotAllowed("only a guardian can correct a child's school")
    await identity.set_school(p, member_id, value, class_label if class_label is not None else before["class_label"])
    await audit.record(p.household_id, "memory.corrected", actor_member_id=p.member_id, target_type="member", target_id=member_id,
                       detail={"key": key, "before": before["school"], "after": value})
    return await why(p, key)


async def verify(p: Principal, key: str) -> dict:
    f = await why(p, key)
    await audit.record(p.household_id, "memory.verified", actor_member_id=p.member_id, target_type="member" if key.startswith(("school:", "app:")) else "document",
                       target_id=uuid.UUID(key.split(":", 1)[1]), detail={"key": key})
    return await why(p, f["key"])
