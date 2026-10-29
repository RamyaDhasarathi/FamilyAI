"""Emergency mode: the one card someone needs when it matters, shared on purpose, for a short time, and recorded.

What it holds is typed in by a guardian (contacts, who may collect each child, home access instructions, each member's
allergies and blood group) or read from what FamilyOS already knows (current medicines, insurance and travel documents).
A guardian shares it as a link that expires (up to 72 hours), can be revoked at once, can include home access or not (not
by default), and counts and dates every time it is opened. Whoever opens it needs no account and sees nothing else: no
notices, no money, no messages, no location. The household can also post an "I'm safe" check-in that only the household sees.

It is a surface over data, not a store of new facts: nothing here is guessed, and a field left empty is shown empty.
"""
from __future__ import annotations

import datetime as dt
import html
import secrets
import uuid

from familyos import audit, clock
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal, _hash

MAX_HOURS = 72
CRITICAL_DOCS = ("insurance", "passport", "visa")


def _j(v) -> list:
    """A jsonb column comes back as text from this pool."""
    import json
    return json.loads(v) if isinstance(v, str) else list(v or [])


def _clean_list(items: list[dict], keys: tuple[str, ...], limit: int = 12) -> list[dict]:
    out = []
    for it in (items or [])[:limit]:
        row = {k: " ".join(str(it.get(k) or "").split())[:120] for k in keys}
        if row.get(keys[0]):
            out.append(row)
    return out


async def set_profile(p: Principal, *, contacts: list[dict] | None, pickup: list[dict] | None, home_access: str | None) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian edits the emergency card")
    cur = await pool().fetchrow("SELECT contacts, pickup, home_access FROM emergency_profile WHERE household_id = $1", p.household_id)
    new_contacts = _clean_list(contacts, ("name", "relation", "phone")) if contacts is not None else (_j(cur["contacts"]) if cur else [])
    new_pickup = _clean_list(pickup, ("child", "name", "relation", "phone")) if pickup is not None else (_j(cur["pickup"]) if cur else [])
    access = ((home_access or "").strip()[:600] or None) if home_access is not None else (cur["home_access"] if cur else None)
    import json
    await pool().execute(
        "INSERT INTO emergency_profile (household_id, contacts, pickup, home_access, updated_by, updated_at) VALUES ($1, $2::jsonb, $3::jsonb, $4, $5, NOW()) "
        "ON CONFLICT (household_id) DO UPDATE SET contacts = EXCLUDED.contacts, pickup = EXCLUDED.pickup, home_access = EXCLUDED.home_access, "
        "updated_by = EXCLUDED.updated_by, updated_at = NOW()", p.household_id, json.dumps(new_contacts), json.dumps(new_pickup), access, p.member_id)
    await audit.record(p.household_id, "emergency.profile_set", actor_member_id=p.member_id, detail={"contacts": len(new_contacts), "pickup": len(new_pickup), "home_access": bool(access)})
    return await card(p, include_home=True)


async def set_member_medical(p: Principal, member_id: uuid.UUID, allergies: str | None, blood_group: str | None) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian edits a member's emergency details")
    done = await pool().execute("UPDATE members SET allergies = $3, blood_group = $4 WHERE id = $1 AND household_id = $2",
                                member_id, p.household_id, (allergies or "").strip()[:300] or None, (blood_group or "").strip().upper()[:5] or None)
    if done.endswith(" 0"):
        raise NotFound("member")
    await audit.record(p.household_id, "emergency.member_set", actor_member_id=p.member_id, target_type="member", target_id=member_id)
    return {"member_id": member_id, "allergies": allergies, "blood_group": blood_group}


async def _card(household_id: uuid.UUID, include_home: bool, p: Principal | None = None) -> dict:
    prof = await pool().fetchrow("SELECT contacts, pickup, home_access FROM emergency_profile WHERE household_id = $1", household_id)
    members = await pool().fetch("SELECT id, display_name, role, allergies, blood_group FROM members WHERE household_id = $1 ORDER BY created_at", household_id)
    today = clock.today()
    meds = await pool().fetch(
        "SELECT patient_member_id, drug, dose_text, times_per_day FROM medications WHERE household_id = $1 AND superseded_at IS NULL "
        "AND (ends_on IS NULL OR ends_on >= $2) AND (starts_on IS NULL OR starts_on <= $2)", household_id, today)
    docs = await pool().fetch(
        "SELECT kind, holder_member_id, holder_text, issuer, identifier_tail, expires_on FROM documents WHERE household_id = $1 AND superseded_at IS NULL AND kind = ANY($2::text[]) "
        "ORDER BY expires_on NULLS LAST", household_id, list(CRITICAL_DOCS))
    by_med: dict = {}
    for m in meds:
        by_med.setdefault(m["patient_member_id"], []).append(f"{m['drug']}" + (f" {m['dose_text']}" if m["dose_text"] else "") + (f", {m['times_per_day']} a day" if m["times_per_day"] else ""))
    names = {m["id"]: m["display_name"] for m in members}
    out = {
        "household": await pool().fetchval("SELECT name FROM households WHERE id = $1", household_id),
        "people": [{"name": m["display_name"], "role": m["role"], "allergies": m["allergies"], "blood_group": m["blood_group"], "medicines": by_med.get(m["id"], [])} for m in members],
        "contacts": _j(prof["contacts"]) if prof else [],
        "pickup": _j(prof["pickup"]) if prof else [],
        "documents": [{"kind": d["kind"], "holder": names.get(d["holder_member_id"]) or d["holder_text"], "issuer": d["issuer"],
                       "identifier_tail": d["identifier_tail"], "expires_on": d["expires_on"]} for d in docs],
        "home_access": (prof["home_access"] if prof and include_home else None),
        "includes_home_access": bool(include_home),
    }
    return out


async def card(p: Principal, include_home: bool = True) -> dict:
    from familyos import circle
    if not await circle.may_open_emergency_card(p):
        raise NotAllowed("a guardian has not handed you the emergency card")
    return await _card(p.household_id, include_home and p.role != "child")


async def share(p: Principal, label: str, hours: int = 24, include_home: bool = False) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian shares the emergency card")
    label = " ".join((label or "").split())[:80]
    if not label:
        raise Invalid("say who it is for, so you can tell the links apart")
    if not 1 <= hours <= MAX_HOURS:
        raise Invalid(f"a link lasts from 1 to {MAX_HOURS} hours")
    token = "em_" + secrets.token_urlsafe(24)
    expires = dt.datetime.now(dt.UTC) + dt.timedelta(hours=hours)
    sid = await pool().fetchval("INSERT INTO emergency_shares (household_id, token_hash, label, include_home, created_by, expires_at) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                                p.household_id, _hash(token), label, include_home, p.member_id, expires)
    await audit.record(p.household_id, "emergency.shared", actor_member_id=p.member_id, target_type="emergency", target_id=sid,
                       detail={"label": label, "hours": hours, "home_access": include_home})
    return {"id": sid, "token": token, "path": f"/e/{token}", "expires_at": expires, "label": label, "include_home": include_home}


async def shares(p: Principal) -> list[dict]:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sees the emergency links")
    rows = await pool().fetch("SELECT id, label, include_home, created_at, expires_at, revoked_at, opened_count, last_opened_at FROM emergency_shares WHERE household_id = $1 ORDER BY created_at DESC LIMIT 30", p.household_id)
    now = dt.datetime.now(dt.UTC)
    return [{**dict(r), "active": r["revoked_at"] is None and r["expires_at"] > now} for r in rows]


async def revoke(p: Principal, share_id: uuid.UUID) -> None:
    if not p.is_guardian:
        raise NotAllowed("only a guardian revokes an emergency link")
    done = await pool().execute("UPDATE emergency_shares SET revoked_at = NOW() WHERE id = $1 AND household_id = $2 AND revoked_at IS NULL", share_id, p.household_id)
    if done.endswith(" 0"):
        raise NotFound("link")
    await audit.record(p.household_id, "emergency.revoked", actor_member_id=p.member_id, target_type="emergency", target_id=share_id)


async def open_shared(token: str) -> dict:
    """What a link shows. Unknown, expired and revoked links all say the same thing, so a guess learns nothing."""
    row = await pool().fetchrow(
        "UPDATE emergency_shares SET opened_count = opened_count + 1, last_opened_at = NOW() "
        "WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > NOW() RETURNING id, household_id, include_home, label, expires_at", _hash(token or ""))
    if row is None:
        raise NotFound("link")
    await audit.record(row["household_id"], "emergency.opened", actor_kind="system", target_type="emergency", target_id=row["id"], detail={"label": row["label"]})
    return {**await _card(row["household_id"], row["include_home"]), "shared_with": row["label"], "link_expires_at": row["expires_at"]}


def page(card_: dict) -> str:
    """A plain, readable page for the link, every value escaped."""
    e = html.escape

    def li(items) -> str:
        return "".join(f"<li>{e(str(i))}</li>" for i in items) or "<li>None recorded</li>"
    people = "".join(
        f"<section><h2>{e(x['name'])} <small>({e(x['role'])})</small></h2><p>Allergies: {e(x['allergies'] or 'none recorded')}. Blood group: {e(x['blood_group'] or 'not recorded')}.</p>"
        f"<p>Medicines now:</p><ul>{li(x['medicines'])}</ul></section>" for x in card_["people"])
    contacts = li(f"{c['name']} ({c['relation']}) {c['phone']}" for c in card_["contacts"])
    pickup = li(f"{c['child']}: {c['name']} ({c['relation']}) {c['phone']}" for c in card_["pickup"])
    docs = li(f"{d['kind']} of {d['holder'] or 'someone'}" + (f", ends in {d['identifier_tail']}" if d.get("identifier_tail") else "") + (f", expires {d['expires_on']}" if d.get("expires_on") else "") for d in card_["documents"])
    home = f"<h2>Home access</h2><p>{e(card_['home_access'])}</p>" if card_.get("home_access") else ""
    return ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content=noindex>"
            f"<title>Emergency card</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:0 auto;padding:16px}}h1{{font-size:22px}}h2{{font-size:17px;margin:18px 0 4px}}small{{color:#666}}</style>"
            f"<h1>Emergency card: {e(card_['household'] or 'household')}</h1><p><small>Shared with {e(card_['shared_with'])}. This link expires and every opening is recorded.</small></p>"
            f"<h2>Call</h2><ul>{contacts}</ul><h2>Who may collect the children</h2><ul>{pickup}</ul>{people}<h2>Insurance and travel documents</h2><ul>{docs}</ul>{home}</html>")


async def checkin(p: Principal, status: str, note: str | None = None) -> dict:
    if status not in ("safe", "need_help"):
        raise Invalid("safe or need_help")
    await pool().execute("INSERT INTO safe_checkins (member_id, household_id, status, note) VALUES ($1, $2, $3, $4)", p.member_id, p.household_id, status, (note or "").strip()[:200] or None)
    await audit.record(p.household_id, "emergency.checkin", actor_member_id=p.member_id, detail={"status": status})
    if status == "need_help":
        from familyos import notify
        for g in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role = 'guardian' AND id <> $2", p.household_id, p.member_id):
            await notify.member(g["id"], f"{p.display_name} needs help", f"{p.display_name} checked in as needing help." + (f" “{note}”" if note else "") + " Call them now.")
    return {"status": status}


async def checkins(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        "SELECT DISTINCT ON (c.member_id) c.member_id, m.display_name, c.status, c.note, c.at FROM safe_checkins c JOIN members m ON m.id = c.member_id "
        "WHERE c.household_id = $1 ORDER BY c.member_id, c.at DESC", p.household_id)
    return sorted(({"name": r["display_name"], "status": r["status"], "note": r["note"], "at": r["at"]} for r in rows), key=lambda x: x["at"], reverse=True)
