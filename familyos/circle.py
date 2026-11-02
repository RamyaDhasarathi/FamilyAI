"""The circle around a parent: who is who, what each may see, and what the
household has decided in words.

Three things live here, none of them a new permission system:

* **A label.** `members.circle_role` says a member is the parent, a sibling,
  a spouse, a caregiver or other. It words the page and orders the family; it
  grants nothing. The one exception is deliberate and small: a *caregiver*
  does not see what the household shares (artifacts.VISIBLE_TO_MEMBER and its
  inline copies say so), only what they themselves send and what a guardian
  hands them with a grant (grants.py). That is the delegation design already
  here -- "a carer sees the pickup and nothing else" -- made a role a family
  can name.

* **The constitution.** The household's authority, in sentences: what is
  fixed and nobody can change, the rules a guardian has set, and for each
  person what they see and why, read from the rows that decide it. A sentence
  is never written by hand about a person: it is derived, so it cannot drift
  from what the code does.

* **The care view.** One person's papers, bills, appointments and the
  messages that looked wrong, read through the same rules as every other
  read: it shows a member only what they could already see.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import audit, clock, documents, grants, rules, scamguard
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

ROLES = ("parent", "sibling", "spouse", "caregiver", "other")
ROLE_WORDS = {"parent": "the parent", "sibling": "a sibling", "spouse": "a spouse", "caregiver": "a caregiver", "other": "in the circle"}

# What a guardian may hand to someone, in the words the page uses.
PRESETS = [
    {"key": "appointments", "label": "Appointments and what to prepare", "actions": ["attend", "prepare", "note"], "days": 30},
    {"key": "bills", "label": "Bills to pay and prepare", "actions": ["pay", "prepare"], "days": 30},
    {"key": "everything_dated", "label": "Everything dated", "actions": [a for a in grants.ACTIONS if a != "emergency"], "days": 30},
    # Narrow and short, for the people who are not the household: a driver, a nanny, a neighbour, a grandparent who is staying.
    {"key": "pickup", "label": "Pickups and drop-offs only", "actions": ["attend"], "days": 14, "needs_child": True},
    {"key": "school_one_child", "label": "One child's school notices", "actions": ["attend", "submit", "sign", "prepare", "note"], "days": 30, "needs_child": True},
    {"key": "medicines", "label": "Medicine reminders only", "actions": ["medication"], "days": 14, "needs_child": False},
    {"key": "while_we_travel", "label": "While we are away", "actions": ["attend", "prepare", "submit", "note"], "days": 7, "needs_child": False},
    {"key": "emergency_only", "label": "The emergency card, nothing else", "actions": ["emergency"], "days": 7, "needs_child": False},
]

# Fixed: no setting changes these, which is why they are said first.
WALLS = [
    "FamilyOS never holds a card, a UPI PIN or a bank login, and never pays. It prepares a payment and opens the biller’s own page; a person pays.",
    "Every date, task and errand is a suggestion until a person accepts it.",
    "What a member keeps private, nobody else sees, the guardians included.",
    "A message is said to match a scam, never to be one. Nothing is blocked, deleted or reported on its own.",
    "Everything FamilyOS does is written to a record a guardian can read, and that record is only ever added to.",
]

ACTION_WORDS = {"sign": "forms to sign", "pay": "bills to pay", "attend": "things to attend", "submit": "things to submit",
                "prepare": "what to prepare", "note": "notes", "medication": "medicine reminders", "emergency": "the emergency card"}


async def grant_preset(actor: Principal, key: str, grantee_member_id: uuid.UUID, *, subject_member_id: uuid.UUID | None = None, days: int | None = None) -> dict:
    """Hand someone one of the named, narrow scopes, for a short while, with the reason written from the scope itself."""
    preset = next((x for x in PRESETS if x["key"] == key), None)
    if preset is None:
        raise NotFound("preset")
    if preset.get("needs_child") and subject_member_id is None:
        raise Invalid("say which child this is about")
    span = days or preset["days"]
    return await grants.issue(actor, grantee_member_id=grantee_member_id, actions=preset["actions"], reason=f"{preset['label']}, for {span} days",
                              subject_member_id=subject_member_id, days=span)


async def may_open_emergency_card(p: Principal) -> bool:
    """Everyone in the household sees the card; a caregiver only while a guardian has handed them the emergency card."""
    if not await is_caregiver(p.member_id):
        return True
    return bool(await pool().fetchval(
        "SELECT 1 FROM grants WHERE grantee_member_id = $1 AND household_id = $2 AND revoked_at IS NULL AND expires_at > NOW() AND 'emergency' = ANY(actions)",
        p.member_id, p.household_id))


async def set_role(actor: Principal, member_id: uuid.UUID, role: str | None) -> dict:
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can say who is who in the circle")
    if role is not None and role not in ROLES:
        raise Invalid(f"a circle role is one of: {', '.join(ROLES)}")
    async with pool().acquire() as conn, conn.transaction():
        m = await conn.fetchrow("SELECT id, role, circle_role FROM members WHERE id = $1 AND household_id = $2 FOR UPDATE", member_id, actor.household_id)
        if m is None:
            raise NotFound("member")
        if m["role"] == "child":
            raise Invalid("a child has no place in the circle; they are who it is for")
        if role == "caregiver" and m["role"] == "guardian":
            raise Invalid("a guardian cannot be a caregiver: a caregiver sees only what is handed to them")
        row = await conn.fetchrow("UPDATE members SET circle_role = $2 WHERE id = $1 RETURNING *", member_id, role)
        await audit.record(actor.household_id, "member.circle_role_set", actor_member_id=actor.member_id, target_type="member",
                           target_id=member_id, detail={"role": role, "was": m["circle_role"]}, conn=conn)
    return dict(row)


def _date(d) -> str:
    return d.strftime("%-d %b %Y") if hasattr(d, "strftime") else str(d)


def _grant_sentence(g: dict) -> str:
    what = " and ".join(ACTION_WORDS.get(a, a) for a in g["actions"])
    about = g.get("subject_name") or "anyone"
    return f"Also sees {what} about {about}, until {_date(g['expires_at'])}, because {g['reason'].rstrip('.')}."


def sees(member: dict, held: list[dict]) -> list[str]:
    """What this member sees and may do, read from the rows that decide it."""
    out = []
    role, circle = member["role"], member.get("circle_role")
    if role == "child":
        return ["Is someone the household keeps records for. Has no sign-in and no private notices."]
    if circle == "caregiver":
        out.append("Sees only what they send themselves and what a guardian hands them below. What the household shares is not shown to them.")
        out.append("Sees the to-dos given to them, and no plans, errands, bills or money.")
    else:
        out.append("Sees everything shared with the household, and what they keep private themselves.")
        out.append("Decides dates, hands things over and changes these rules." if role == "guardian" else "Decides dates and hands things over; cannot change these rules.")
    out += [_grant_sentence(g) for g in held]
    if circle == "caregiver" and not held:
        out.append("Nothing has been handed to them yet.")
    return out


async def constitution(p: Principal) -> dict:
    members = [dict(r) for r in await pool().fetch(
        "SELECT id, display_name, role, circle_role FROM members WHERE household_id = $1 ORDER BY (role = 'guardian') DESC, "
        "(circle_role = 'parent') DESC, created_at", p.household_id)]
    live = await grants.list_for(p)
    people = [{"member_id": m["id"], "display_name": m["display_name"], "role": m["role"], "circle_role": m["circle_role"],
               "circle_words": ROLE_WORDS.get(m["circle_role"] or ""),
               "sees": sees(m, [g for g in live if g["grantee_member_id"] == m["id"]]),
               "grants": [g for g in live if g["grantee_member_id"] == m["id"]]} for m in members]
    return {"walls": WALLS, "rules": (await rules.list_for(p))["rules"], "people": people, "presets": PRESETS}


async def is_caregiver(member_id: uuid.UUID) -> bool:
    return bool(await pool().fetchval("SELECT circle_role = 'caregiver' FROM members WHERE id = $1", member_id))


async def care(p: Principal, member_id: uuid.UUID, today: dt.date | None = None) -> dict:
    """One person's papers, bills, appointments and worrying messages."""
    from familyos import brief
    today = today or clock.today()
    m = await pool().fetchrow("SELECT id, household_id, display_name, role, circle_role, email, phone, date_of_birth, created_at "
                              "FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id)
    if m is None:
        raise NotFound("member")
    docs = [d for d in await documents.list_for(p, today) if d["holder_member_id"] == member_id]
    doc_checks = [c for c in await documents.checks(p, docs, today) if c.get("document_id") in {d["id"] for d in docs}]
    about = {r["id"] for r in await pool().fetch(
        "SELECT a.id FROM input_artifacts a WHERE a.household_id = $1 AND a.parent_id IS NULL AND (a.submitted_by = $2 OR EXISTS "
        "(SELECT 1 FROM artifact_subjects s WHERE s.artifact_id = a.id AND s.member_id = $2))", p.household_id, member_id)}
    obligations = [dict(r) for r in await pool().fetch(
        f"SELECT o.id, o.title, o.action, o.due_date, o.due_time, o.status, o.pay_url, o.artifact_id FROM obligations o "
        f"JOIN input_artifacts a ON a.id = o.artifact_id WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL "
        "AND o.subject_member_id = $3 AND o.status IN ('accepted', 'proposed') AND o.due_date >= $4 ORDER BY o.due_date, o.created_at",
        p.household_id, p.member_id, member_id, today - dt.timedelta(days=30))]
    bills = [o for o in obligations if o["action"] == "pay"]
    appointments = [o for o in obligations if o["action"] in ("attend", "prepare") and o["due_date"] >= today
                    and o["due_date"] <= today + dt.timedelta(days=45)]
    try:
        unusual = [i for i in await brief._money_watch(p, today) if i.get("artifact_id") in about]
    except Exception:  # noqa: BLE001 - the ledger is a reading
        unusual = []
    scams = [dict(r) for r in await pool().fetch(
        f"SELECT a.id AS artifact_id, a.received_at, a.suspicion, a.handled_at, {_headline()} AS headline FROM input_artifacts a "
        f"WHERE {_visible()} AND a.parent_id IS NULL AND a.suspicion IS NOT NULL AND a.received_at > NOW() - INTERVAL '60 days' "
        "AND a.id = ANY($3::uuid[]) ORDER BY a.received_at DESC LIMIT 10", p.household_id, p.member_id, list(about))]
    held = [g for g in await grants.list_for(p) if g.get("subject_member_id") == member_id]
    from familyos import medications, standing
    meds = await medications.list_for(p, today, member_id)
    rhythm = [r for r in await standing.list_for(p) if r.get("subject_member_id") == member_id]
    return {"member": dict(m), "documents": docs, "document_checks": doc_checks, "bills": bills, "appointments": appointments,
            "medications": meds, "standing": rhythm, "unusual": unusual, "scams": scams, "handed_over": held}


def _headline() -> str:
    from familyos.inbox import HEADLINE
    return HEADLINE


def _visible() -> str:
    from familyos import artifacts
    return artifacts.VISIBLE_TO_MEMBER


async def report_scam(p: Principal, text: str, *, caller: str | None = None, about_member_id: uuid.UUID | None = None) -> dict:
    """A parent's (or anyone's) word that something looked wrong: filed as a
    shared notice so the household can see it, read at once, and answered
    with what to do whatever the reading says. Always answered: a call that
    matches nothing still gets the one thing worth saying."""
    from familyos.intake import gateway
    body = " ".join((text or "").split())
    if len(body) < 8:
        raise Invalid("say what they said, in a few words")
    country = await pool().fetchval("SELECT country FROM households WHERE id = $1", p.household_id)
    filed_text = (f"Reported call from {caller.strip()[:40]}: " if caller and caller.strip() else "Reported call or message: ") + body[:3000]
    if about_member_id is not None and await pool().fetchval("SELECT 1 FROM members WHERE id = $1 AND household_id = $2", about_member_id, p.household_id) is None:
        raise NotFound("member")
    result = await gateway.receive_share(p, text=filed_text, visibility="shared", note="reported as suspicious")
    artifact = result.get("artifact") or {}
    artifact_id = artifact.get("id")
    found = scamguard.assess(filed_text, channel="share", source={"via": "share"}, category=None, country=country)
    if artifact_id is not None:
        await scamguard.keep(artifact_id, found)
        if about_member_id is not None:
            await pool().execute("INSERT INTO artifact_subjects (artifact_id, member_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", artifact_id, about_member_id)
        if found and found["level"] == "high":
            await scamguard.alert(p.household_id, artifact_id, found)
    reading = found or {"level": "none", "score": 0, "reasons": [], "advice": scamguard.advice("medium", country)[-2:]}
    reading = {**{k: v for k, v in reading.items() if k != "assessed_at"}, "artifact_id": artifact_id}
    await audit.record(p.household_id, "scam.reported", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id,
                       detail={"level": reading["level"]})
    return reading
