"""Audit events: an append-only record of who did what to which record.

Rules: write the event in the same transaction as the change it describes,
and put ids, counts, sizes and hashes in `detail`, never user content
(filenames, subjects, text). The table rejects UPDATE and DELETE; only an
erasure may purge it (see erasure.py).
"""
from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from familyos.db import pool


async def record(
    household_id: uuid.UUID,
    action: str,
    *,
    actor_member_id: uuid.UUID | None = None,
    actor_kind: str = "member",
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    conn: asyncpg.Connection | None = None,
) -> None:
    sql = ("INSERT INTO audit_events (household_id, actor_kind, actor_member_id, action, target_type, target_id, detail) "
           "VALUES ($1, $2, $3, $4, $5, $6, $7)")
    args = (household_id, actor_kind, actor_member_id, action, target_type, target_id, detail or {})
    if conn is not None:
        await conn.execute(sql, *args)
    else:
        await pool().execute(sql, *args)


async def list_for(household_id: uuid.UUID, limit: int = 100, before_id: int | None = None) -> list[dict]:
    rows = await pool().fetch(
        "SELECT * FROM audit_events WHERE household_id = $1 AND ($2::bigint IS NULL OR id < $2) ORDER BY id DESC LIMIT $3",
        household_id, before_id, limit)
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# saying an event in words
# ----------------------------------------------------------------------------
#
# The row keeps ids, counts and hashes. A guardian reading the trail wants a
# sentence: who did what, to which notice, with what outcome. The sentence
# is composed at read time from the row and from names the reader may see;
# a notice the reader cannot see is "a private notice", never its headline.

def _n(d: dict, key: str, one: str, many: str | None = None) -> str | None:
    v = d.get(key)
    if v in (None, 0, False, [], ""):
        return None
    if isinstance(v, list):
        v = len(v)
    if isinstance(v, bool):
        return one
    many = many or one + "s"
    return f"{v} {one if v == 1 else many}"


def _join(parts: list[str | None]) -> str:
    return ", ".join(p for p in parts if p)


def _money(d: dict) -> str | None:
    if d.get("amount") is None:
        return None
    from familyos import country
    return country.money(float(d["amount"]), d.get("currency") or "")


RULE_WORDS = {"childrens_notices_shared": "children's notices are shared", "weekly_digest": "the weekly digest",
              "calendar_follows_decisions": "the calendar follows decisions", "local_models": "the household's own model",
              "holidays_accepted": "holidays are accepted", "receipts_close_bills": "receipts close bills",
              "investments_quiet": "investments are quiet", "pictures_by_model": "pictures are read by the model",
              "bills_handed_to": "bills are handed to"}
REASON_WORDS = {"optional_passed": "an optional date that has passed", "investments_quiet": "investments are quiet",
                "holidays_accepted": "holidays are accepted"}
SERVICE_WORDS = {"urbancompany": "Urban Company", "swiggy": "Swiggy", "instamart": "Instamart", "zomato": "Zomato"}
EXTRACTOR_WORDS = {"local": "the household's own model", "rules": "the rules", "openai": "the cloud model", "anthropic": "the cloud model"}


def _rule(name) -> str:
    return RULE_WORDS.get(str(name), str(name).replace("_", " "))


def _service(name) -> str:
    return SERVICE_WORDS.get(str(name or "").lower(), str(name or "a site"))


def _rules_set(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{_rule(k)} {'on' if v is True else 'off' if v is False else v}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(_rule(v) for v in value)
    return _rule(value)


def say(e: dict, *, who: str, about: str | None, names: dict) -> str:
    """One sentence for an audit row. `who` is the actor's name or
    "FamilyOS"; `about` is the target's name or headline when the reader may
    see it; `names` maps member ids to display names."""
    a, d = e["action"], e.get("detail") or {}
    kind, _, verb = a.partition(".")
    t = about or {"artifact": "a notice", "obligation": "a date", "todo": "a to-do", "plan": "a plan", "errand": "an errand",
                  "member": "a member", "session": "a site session", "sign_in": "a site sign-in", "google_account": "a mailbox",
                  "consent": "a consent", "watch": "a watch", "school": "a school", "household": "the household"}.get(e.get("target_type") or "", "a record")
    name = lambda key: names.get(str(d.get(key)), "someone") if d.get(key) else None  # noqa: E731 - a one-line lookup
    if a == "artifact.received":
        where = {"gmail": "by mail", "gmail_attachment": "as a mail attachment", "share": "from a phone", "telegram": "from Telegram",
                 "whatsapp": "from WhatsApp", "email": "by mail", "upload": "by upload", "errand": "from an errand"}.get(d.get("channel"), d.get("channel") or "")
        return _join([f"{t[0].upper() + t[1:]} arrived {where}".strip(), d.get("visibility") == "shared" and "shared with the household" or None,
                      d.get("reason") and f"held: {d['reason']}" or None])
    if a == "artifact.duplicate":
        return f"{t[0].upper() + t[1:]} arrived again; the first copy stands"
    if a == "artifact.duplicate_merged":
        return _join([f"{t[0].upper() + t[1:]} was merged with its earlier copy", _n(d, "obligations_superseded", "date", "dates") and _n(d, "obligations_superseded", "date", "dates") + " superseded"])
    if a == "artifact.original_read":
        return f"{who} opened the original of {t}"
    if a == "artifact.originals_read":
        return f"{who} read {_n(d, 'artifacts', 'original') or 'originals'}"
    if a == "artifact.handled":
        if d.get("by") == "receipt":
            return _join([f"{t[0].upper() + t[1:]} was marked paid by a receipt", _money(d) and f"for {_money(d)}", _n(d, "reminders_cancelled", "reminder") and _n(d, "reminders_cancelled", "reminder") + " cancelled"])
        return _join([f"{who} marked {t} handled", d.get("with_note") and "with a note", _n(d, "reminders_cancelled", "reminder") and _n(d, "reminders_cancelled", "reminder") + " cancelled"])
    if a == "artifact.reopened":
        return f"{who} reopened {t}"
    if a == "artifact.assigned":
        to = name("member_id")
        return _join([f"{who} handed {t} to {to}" if to else f"{who} took {t} back", d.get("with_note") and "with a note"])
    if a == "artifact.subjects_set":
        kids = [names.get(str(m), "someone") for m in d.get("member_ids") or []]
        return f"{who} tagged {t} as about {', '.join(kids)}" if kids else f"{who} cleared who {t} is about"
    if a == "artifact.visibility_changed":
        how = f" by the rule that {_rule(d['rule'])}" if d.get("rule") else (f" via {d['via']}" if d.get("via") else "")
        return f"{who} made {t} {d.get('to', 'shared')}{how}"
    if a == "artifact.shared":
        return f"{t[0].upper() + t[1:]} was shared with the household" + (f" via {d['via']}" if d.get("via") else "")
    if a in ("artifact.quarantined", "intake.rejected"):
        return _join([f"{t[0].upper() + t[1:]} was held in quarantine" if a == "artifact.quarantined" else "A message was refused at the door", d.get("reason") and f"reason: {d['reason']}"])
    if a == "artifact.quarantine_accepted":
        return f"{who} let {t} in from quarantine"
    if a == "extraction.completed":
        bits = [f"{t[0].upper() + t[1:]} was read" + (f" by {EXTRACTOR_WORDS.get(d['extractor'], d['extractor'])}" if d.get("extractor") else ""),
                _n(d, "claims", "claim"), _n(d, "obligations", "date", "dates") and _n(d, "obligations", "date", "dates") + " proposed",
                _n(d, "documents", "document"), d.get("category") and f"filed under {d['category']}",
                _n(d, "loops_closed", "bill") and _n(d, "loops_closed", "bill") + " closed by it", d.get("handed_to") and "handed on by a rule",
                d.get("holidays_accepted") and "holiday accepted by a rule", d.get("hearsay") and "read as a forward", d.get("from_ocr") and "from OCR"]
        return _join(bits) if any(bits[1:]) else bits[0] + (", nothing to do" if d.get("actionable") is False else "")
    if a == "obligation.accepted":
        return f"{who} accepted {t}"
    if a == "obligation.dismissed":
        return f"{who} dismissed {t}" + (f" by the rule that {_rule(d['rule'])}" if d.get("rule") else "")
    if a == "obligation.filed":
        return f"{t[0].upper() + t[1:]} was filed without asking" + (f": {REASON_WORDS.get(d['reason'], str(d['reason']).replace('_', ' '))}" if d.get("reason") else "")
    if a == "reminder.sent":
        return _join([f"A reminder went to {name('member_id') or 'a member'} about {t}", d.get("channel") and ("to the log" if d["channel"] == "log" else f"by {d['channel']}"), d.get("lead_days") and f"{d['lead_days']} days ahead" or None])
    if a == "calendar.event_written":
        return f"{t[0].upper() + t[1:]} was written to the calendar"
    if a == "calendar.event_removed":
        return f"{t[0].upper() + t[1:]} was taken off the calendar"
    if a == "calendar.synced":
        return _join(["The calendar was read", _n(d, "kept", "event"), _n(d, "dropped", "old event", "old events") and _n(d, "dropped", "old event", "old events") + " dropped"])
    if a == "todo.added":
        to = name("assigned_to")
        return _join([f"{who} added {t}", to and f"for {to}", d.get("dated") and "with a date" or None])
    if a == "todo.done":
        return f"{who} ticked off {t}"
    if a == "todo.removed":
        return f"{who} removed {t}"
    if a == "plan.requested":
        return f"{who} asked for a plan"
    if a == "plan.drafted":
        return _join([f"{t[0].upper() + t[1:]} was drafted", _n(d, "options", "option"), _n(d, "todos", "to-do")])
    if a == "plan.dropped":
        return _join([f"{who} dropped {t}", _n(d, "todos_removed", "to-do") and _n(d, "todos_removed", "to-do") + " removed"])
    if a == "plan.done":
        return f"{who} marked {t} done"
    if a == "plan.failed":
        return f"{t[0].upper() + t[1:]} could not be written"
    if a == "plan.option_booked":
        return f"{who} marked an option of {t} booked"
    if a == "plan.evidence_read":
        return f"A public page on {d.get('host', 'a site')} was read for {t}"
    if a == "errand.proposed":
        return _join([f"{who} proposed an errand on {_service(d.get('service'))}", d.get("kind"), _money({"amount": d.get("max_amount"), "currency": d.get("currency")}) and f"up to {_money({'amount': d.get('max_amount'), 'currency': d.get('currency')})}", d.get("payment") and f"paid {d['payment'].replace('_', ' ')}"])
    if a == "errand.approved":
        return f"{who} approved the errand on {_service(d.get('service'))}"
    if a == "errand.needs_you":
        return _join([f"The errand on {_service(d.get('service'))} stopped and needs a person", _n(d, "steps", "step") and f"after {_n(d, 'steps', 'step')}"])
    if a == "errand.done":
        return f"The errand on {_service(d.get('service'))} finished" + (" by hand" if d.get("finished_by_person") else "")
    if a == "errand.cancelled":
        return f"{who} cancelled the errand on {_service(d.get('service'))}"
    if a == "member.signed_in":
        return f"{who} signed in" + (" with Google" if d.get("via") == "google" else f" by {d['via']}" if d.get("via") else "")
    if a == "member.added":
        return f"{who} added {t}" + (f" as a {d['role']}" if d.get("role") else "")
    if a == "member.invited":
        return f"{who} invited {t}"
    if a == "member.school_set":
        return f"{who} {'set' if d.get('set') else 'cleared'} the school and class of {t}" + (" (changed)" if d.get("changed") else "")
    if a == "member.birthday_set":
        return f"{who} {'set' if d.get('set') else 'cleared'} the birthday of {t}"
    if a in ("member.telegram_linked", "member.telegram_unlinked"):
        return f"{t[0].upper() + t[1:]} {'linked' if a.endswith('linked') and not a.endswith('unlinked') else 'unlinked'} Telegram"
    if a == "consent.granted":
        return f"{who} recorded consent for {name('subject_member_id') or 'a child'}" + (f" ({d['purpose']})" if d.get("purpose") else "")
    if a == "consent.withdrawn":
        return f"{who} withdrew consent for {name('subject_member_id') or 'a child'}"
    if a == "household.created":
        return f"{who} started the household"
    if a == "household.rules_set":
        return f"{who} changed the household's rules" + (f": {_rules_set(d['set'])}" if d.get("set") else "")
    if a == "household.locale_set":
        return f"{who} set where the household lives: {d.get('country', '')} {d.get('timezone', '')} {d.get('currency', '')}".rstrip()
    if a == "household.handle_set":
        return f"{who} named the household's address"
    if a == "school.updated":
        return f"{who} {'renamed' if d.get('renamed') else 'updated'} {t}" + (" and set its portal" if d.get("portal") else "")
    if a == "source.school_set":
        return f"{who} said which school a source belongs to"
    if a == "device.added":
        return f"{who} added a phone or shortcut token" + (f" ({d['label']})" if d.get("label") else "")
    if a == "device.revoked":
        return f"{who} revoked a phone or shortcut token"
    if a == "mailbox.connected":
        return f"{who} connected a mailbox" + (" with calendar" if any("calendar" in s for s in d.get("scopes") or []) else "")
    if a == "mailbox.disconnected":
        return f"{who} disconnected a mailbox"
    if a == "mailbox.needs_reconnect":
        return "A mailbox needs reconnecting" + (f": {d['reason']}" if d.get("reason") else "")
    if a == "export.created":
        return _join([f"{who} exported the record ({d.get('scope', 'household')})", _n(d, "notices", "notice"), _n(d, "originals", "original")])
    if a in ("erasure.requested", "erasure.completed"):
        return f"{who} asked for an erasure" if a.endswith("requested") else "An erasure completed"
    if a == "sign_in.began":
        return f"{who} began signing in to {_service(d.get('service'))}"
    if a == "sign_in.sealed":
        return f"{who} sealed the sign-in to {_service(d.get('service'))}"
    if a == "sign_in.abandoned":
        return f"The sign-in to {_service(d.get('service'))} was abandoned"
    if a == "session.opened":
        return f"A browser session on {_service(d.get('service'))} opened" + (f" for {d['reason']}" if d.get("reason") else "")
    if a == "session.closed":
        return f"The browser session on {_service(d.get('service'))} closed"
    if a == "session.stored":
        return f"The sign-in to {_service(d.get('service'))} was sealed and stored"
    if a in ("session.revoked", "session.signed_out"):
        return f"{who} {'revoked' if a.endswith('revoked') else 'signed out'} a session"
    if a == "watch.created":
        return f"{who} set a watch on {d.get('host', 'a page')}" + (f" every {d['every_hours']} hours" if d.get("every_hours") else "")
    if a == "watch.notified":
        return "A watched page changed and the household was told"
    if a == "reply.sent":
        return f"{who} sent a reply about {t}" + (f" by {'mail' if d.get('channel') == 'email' else d.get('channel')}" if d.get("channel") else "")
    if a == "grant.issued":
        return f"{who} granted {t} something"
    if a == "grant.revoked":
        return f"{who} revoked a grant"
    if a.startswith("action."):
        return f"{who} {verb} an action on {t}"
    if a.startswith("harvest."):
        return f"{who} {verb.replace('_', ' ')} a collection from a site"
    if a.startswith("amendment"):
        return f"A revision was proposed for {t}"
    if a.startswith("intake.gap"):
        return f"{who} {'reported' if verb.endswith('reported') else 'closed'} a gap in what arrives"
    return f"{who} {verb.replace('_', ' ')} {t}"


async def describe_for(p, limit: int = 100, before_id: int | None = None) -> list[dict]:
    """The trail with each row said in words, for a guardian. Names come
    from the household; headlines only for notices the reader may see."""
    from familyos.artifacts import VISIBLE_TO_MEMBER
    from familyos.inbox import HEADLINE
    rows = await list_for(p.household_id, limit, before_id)
    names = {str(r["id"]): r["display_name"] for r in await pool().fetch("SELECT id, display_name FROM members WHERE household_id = $1", p.household_id)}
    by_type: dict[str, set] = {}
    for r in rows:
        if r.get("target_id") and r.get("target_type"):
            by_type.setdefault(r["target_type"], set()).add(r["target_id"])
    labels: dict[tuple, str] = {}
    if by_type.get("artifact"):
        for r in await pool().fetch(f"SELECT a.id, {HEADLINE} AS headline FROM input_artifacts a WHERE {VISIBLE_TO_MEMBER} AND a.id = ANY($3::uuid[])",
                                    p.household_id, p.member_id, list(by_type["artifact"])):
            labels[("artifact", r["id"])] = f"“{r['headline']}”" if r["headline"] else "a notice"
    if by_type.get("obligation"):
        for r in await pool().fetch("SELECT o.id, o.title FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id "
                                    f"WHERE {VISIBLE_TO_MEMBER} AND o.id = ANY($3::uuid[])", p.household_id, p.member_id, list(by_type["obligation"])):
            labels[("obligation", r["id"])] = f"“{r['title']}”"
    for ttype, table, col in (("todo", "todos", "title"), ("plan", "plans", "title"), ("errand", "errands", "title"), ("school", "schools", "name")):
        if by_type.get(ttype):
            for r in await pool().fetch(f"SELECT id, {col} AS label FROM {table} WHERE household_id = $1 AND id = ANY($2::uuid[])", p.household_id, list(by_type[ttype])):
                labels[(ttype, r["id"])] = f"“{r['label']}”"
    for r in rows:
        who = names.get(str(r["actor_member_id"]), "someone") if r.get("actor_member_id") else "FamilyOS"
        about = None
        if r.get("target_type") == "member" and r.get("target_id"):
            about = names.get(str(r["target_id"]))
        elif r.get("target_type") == "artifact" and r.get("target_id"):
            about = labels.get(("artifact", r["target_id"]), "a private notice")
        elif r.get("target_id"):
            about = labels.get((r["target_type"], r["target_id"]))
        r["who"] = who
        r["about"] = about
        try:
            r["said"] = say(r, who=who, about=about, names=names)
        except Exception:  # noqa: BLE001 - a sentence is a convenience; the row is the record
            r["said"] = f"{who} {r['action']}"
    return rows
