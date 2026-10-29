"""Reading the chats a member names from their own WhatsApp Web, every half hour, and nothing else.

What it is: the member links WhatsApp Web (a companion device on their own number) in a browser profile on this machine
(execution/whatsapp_reader.py), names up to eight chats, and says yes to what it costs. A sweep every 30 minutes reads the newest
messages in those chats only, and hands each to the same intake every forwarded message takes (gateway.receive_whatsapp), marked as
second-hand, so dates and tasks in them come up as proposals the member accepts or not. Nothing is ever sent, replied to or
accepted on their behalf. The chat itself is not kept as a log: only the messages that reach intake, with the chat's name, the author's
name and the message id beside them, exactly like an email's headers.

What it costs, said before they say yes (CONSENT below): WhatsApp's guidelines list unofficial clients and automation among the things
not to do, so the number could be restricted; the linked browser can read every chat on the account (we open only the ones named);
opening a chat marks it read for the other person; the logged-in browser profile is a credential on this machine until forgotten; and the
text goes to whichever model reads this household's notices, which may be a hosted provider.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import uuid

from familyos import audit, jobs, modelroute, notify, origin
from familyos.db import pool
from familyos.execution import whatsapp_reader as wr
from familyos.identity import Invalid, NotAllowed, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "whatsapp_watch_sweep"
HANDLER_VERSION = "1"
SWEEP_SECONDS = 1800
CONSENT_VERSION = 1
KEEP_IDS = 300                     # message ids remembered per chat, so the same message is never taken twice

CONSENT = [
    "WhatsApp’s guidelines list unofficial clients and automation among the things not to do. Your number could be restricted.",
    "A linked WhatsApp Web can read every chat on your account. FamilyOS opens only the chats you name, and never sends, replies or reacts.",
    "Opening a chat marks its messages as read for the other person. Turn off Read receipts in WhatsApp’s privacy settings if that matters.",
    "The logged-in browser is kept on this machine until you forget it. Anyone who can read this machine’s files could use it.",
    "The words in those chats are read by the model this household uses for notices. Messages from other people in them are read too.",
]


def _require(p: Principal) -> None:
    if p.role == "child":
        raise NotAllowed("only an adult links their own WhatsApp")
    if not settings.whatsapp_watch_enabled:
        raise Invalid("reading WhatsApp is not switched on for this deployment (FAMILYOS_WHATSAPP_WATCH_ENABLED)")


async def _row(member_id: uuid.UUID) -> dict | None:
    r = await pool().fetchrow("SELECT * FROM whatsapp_watches WHERE member_id = $1", member_id)
    return dict(r) if r else None


def _cursors(row: dict | None) -> dict:
    c = (row or {}).get("cursors") or {}
    return c if isinstance(c, dict) else json.loads(c or "{}")


async def _model_note(household_id) -> dict:
    name = await modelroute.chosen(household_id, "extraction")
    return {"name": name, "trust": modelroute.trust_of(name),
            "where": "the hosted provider" if name == modelroute.DEFAULT else (modelroute.profiles()[name].where() if name in modelroute.profiles() else name)}


async def destination_ok(household_id, member_id) -> bool:
    """Whether the words in this member's chats may go where this household's notices go now. A yes given while a private model read them
    is not a yes to a hosted one: the check is made against the destination as it is at the moment of reading, in the sweep and in the
    extraction job, not once when reading was switched on."""
    row = await _row(member_id) if member_id else None
    if row is None or not row["enabled"]:
        return False
    consent = row["consent"] if isinstance(row["consent"], dict) else json.loads(row["consent"] or "{}")
    try:
        model = await _model_note(household_id)
    except Invalid:
        return False
    return model["trust"] != "cloud" or bool(consent.get("cloud_ok"))


async def requeue_waiting(member_id, household_id) -> int:
    """After a fresh yes: put back the notices whose extraction was skipped for want of consent."""
    from familyos.extraction import service as extraction
    rows = await pool().fetch(
        "SELECT a.id FROM input_artifacts a WHERE a.household_id = $1 AND a.submitted_by = $2 AND a.source->>'via' = 'whatsapp_watch' "
        "AND NOT EXISTS (SELECT 1 FROM extractions x WHERE x.artifact_id = a.id)", household_id, member_id)
    if rows:
        async with pool().acquire() as conn, conn.transaction():
            await extraction.enqueue(conn, household_id, [r["id"] for r in rows], member_id=member_id)
    return len(rows)


async def status(p: Principal) -> dict:
    available = bool(settings.whatsapp_watch_enabled)
    row = await _row(p.member_id) if available else None
    has_phone = bool(await pool().fetchval("SELECT phone FROM members WHERE id = $1", p.member_id)) if p.role != "child" else False
    needs_consent = bool(available and row and row["enabled"] and not await destination_ok(p.household_id, p.member_id)) if p.role != "child" else False
    out = {"available": available, "has_phone": has_phone, "needs_consent": needs_consent, "consent": CONSENT, "enabled": bool(row and row["enabled"]), "status": (row or {}).get("status", "off"),
           "chats": list((row or {}).get("chats") or []), "last_run_at": (row or {}).get("last_run_at"), "last_ok_at": (row or {}).get("last_ok_at"),
           "last_error": (row or {}).get("last_error"), "last_found": (row or {}).get("last_found", 0), "every_minutes": SWEEP_SECONDS // 60}
    if available and p.role != "child":
        try:
            out["model"] = await _model_note(p.household_id)
        except Invalid:
            out["model"] = None            # the choice is below the floor or its profile is gone: the card shows paused, not an error
        out["schools"] = await _schools(p)
        out["tags"] = await _tags(p, out["chats"])
    return out


def _key(chat: str) -> str:
    return f"whatsapp:group:{chat.strip().casefold()}"


async def _schools(p: Principal) -> list[dict]:
    """The schools this household's children are at, with who is there: what a chat can be said to belong to."""
    rows = await pool().fetch("SELECT school, array_agg(display_name ORDER BY display_name) AS kids FROM members WHERE household_id = $1 AND role = 'child' "
                              "AND school IS NOT NULL AND school <> '' GROUP BY school ORDER BY school", p.household_id)
    return [{"school": r["school"], "children": list(r["kids"])} for r in rows]


async def _tags(p: Principal, chats: list[str]) -> dict[str, str]:
    if not chats:
        return {}
    got = {r["source_key"]: r["school"] for r in await pool().fetch(
        "SELECT source_key, school FROM source_schools WHERE household_id = $1 AND source_key = ANY($2::text[])", p.household_id, [_key(c) for c in chats])}
    return {c: got[_key(c)] for c in chats if _key(c) in got}


async def set_chats(p: Principal, chats: list[str], tags: dict[str, str] | None = None) -> dict:
    """Name the chats. `tags` says, for a chat, which school it belongs to (so its notices are attributed to the children there); an empty
    value un-says it. Only a guardian can say it, as everywhere a source is tied to a school."""
    _require(p)
    names = wr.clean_chats(chats)
    if tags:
        if not p.is_guardian:
            raise NotAllowed("only a guardian says which school a chat belongs to")
        known = {s["school"].casefold() for s in await _schools(p)}
        for chat, school in tags.items():
            if chat not in names:
                continue
            if school:
                if school.casefold() not in known:
                    raise Invalid(f"{school} is not a school any child here is at")
                await origin.remember(p, _key(chat), school)
            else:
                await origin.forget(p, _key(chat))
    await pool().execute(
        "INSERT INTO whatsapp_watches (member_id, household_id, chats) VALUES ($1, $2, $3) ON CONFLICT (member_id) DO UPDATE SET chats = $3, cursors = '{}'::jsonb",
        p.member_id, p.household_id, names)
    await audit.record(p.household_id, "whatsapp.chats_set", actor_member_id=p.member_id, detail={"count": len(names)})
    return await status(p)


async def start_link(p: Principal) -> dict:
    """Show the code to type into WhatsApp -> Linked devices -> Link with phone number. The browser waits for it for a few minutes."""
    _require(p)
    phone = await pool().fetchval("SELECT phone FROM members WHERE id = $1", p.member_id)
    if not phone:
        raise Invalid("add your phone number to your profile first; it is the number WhatsApp links to")
    out = await wr.current_reader().start_link(p.member_id, phone)
    await pool().execute(
        "INSERT INTO whatsapp_watches (member_id, household_id, status) VALUES ($1, $2, $3) ON CONFLICT (member_id) DO UPDATE SET status = $3",
        p.member_id, p.household_id, "linked" if out.get("linked") else "needs_link")
    await audit.record(p.household_id, "whatsapp.link_started", actor_member_id=p.member_id)
    return out


async def check_link(p: Principal) -> dict:
    """Has the code been entered yet? Called by the page while it waits."""
    _require(p)
    ok = await wr.current_reader().linked(p.member_id)
    await pool().execute("UPDATE whatsapp_watches SET status = $2 WHERE member_id = $1", p.member_id, "linked" if ok else "needs_link")
    out = await status(p)
    reader = wr.current_reader()
    if not ok and hasattr(reader, "qr"):
        out["qr"] = await reader.qr(p.member_id)         # the QR rotates, so the page asks for the current one
    return out


async def enable(p: Principal, *, understood: bool, cloud_ok: bool = False) -> dict:
    """Switch the half-hourly reading on. It needs a linked browser, at least one named chat, a yes to the costs, and, when the model that
    reads notices is a hosted one, a separate yes to that."""
    _require(p)
    row = await _row(p.member_id)
    if not understood:
        raise Invalid("say that you have read what this costs")
    if not row or not row["chats"]:
        raise Invalid("name at least one chat first")
    if row["status"] != "linked":
        raise Invalid("link WhatsApp first")
    model = await _model_note(p.household_id)
    if model["trust"] == "cloud" and not cloud_ok:
        raise Invalid(f"these chats would be read by {model['where']}; say that is fine, or move this household's notices to a private model first")
    await pool().execute(
        "UPDATE whatsapp_watches SET enabled = TRUE, consented_at = NOW(), consent = $2::jsonb WHERE member_id = $1",
        p.member_id, json.dumps({"version": CONSENT_VERSION, "model": model["name"], "trust": model["trust"], "cloud_ok": bool(cloud_ok)}))
    await audit.record(p.household_id, "whatsapp.enabled", actor_member_id=p.member_id, detail={"chats": len(row["chats"]), "model_trust": model["trust"]})
    await requeue_waiting(p.member_id, p.household_id)
    return await status(p)


async def forget(p: Principal) -> dict:
    """Stop, delete the logged-in browser, and drop the chat list. Notices already read stay as the notices they became."""
    if p.role == "child":
        raise NotAllowed("not for children")
    await wr.current_reader().forget(p.member_id)
    await pool().execute("DELETE FROM whatsapp_watches WHERE member_id = $1", p.member_id)
    await audit.record(p.household_id, "whatsapp.forgotten", actor_member_id=p.member_id)
    return {**await status(p), "note": "Also remove FamilyOS from WhatsApp → Settings → Linked devices on your phone."}


def _payload(m: wr.Message, phone: str, tz: str | None = None, order: str | None = None) -> dict:
    out = {"linked_phone": phone, "id": m.id, "timestamp": wr.parse_stamp(m.stamp, tz, order, dt.datetime.now(dt.UTC)) or "", "is_group": m.is_group, "chat_name": m.chat,
           "author_name": m.author, "text": m.text}
    if m.media_b64:
        out["media"] = {"mimetype": m.media_type or "image/jpeg", "filename": "whatsapp-picture", "data_base64": m.media_b64, "caption": m.text}
    return out


async def run_for(member_id: uuid.UUID) -> dict:
    """One pass for one member: read, take what is new, hand it to intake. A lapsed link is said once and the reading stops until relinked."""
    from familyos.intake import gateway, wa_bridge
    row = await _row(member_id)
    if row is None or not row["enabled"]:
        return {"skipped": "off"}
    m = await pool().fetchrow("SELECT id, household_id, role, display_name, phone FROM members WHERE id = $1", member_id)
    if m is None or m["role"] == "child" or not m["phone"]:
        return {"skipped": "no member or phone"}
    now = dt.datetime.now(dt.UTC)
    cursors = _cursors(row)
    taken = 0
    from familyos import artifacts
    from familyos.familykey import HouseholdLocked
    try:
        async with pool().acquire() as conn:
            await artifacts.household_key(conn, m["household_id"])
    except HouseholdLocked:
        return {"paused": "locked"}          # opening chats marks them read for the sender, and nothing could be stored: leave them alone until unlocked
    tz = await pool().fetchval("SELECT timezone FROM households WHERE id = $1", m["household_id"]) or settings.timezone
    if not await destination_ok(m["household_id"], member_id):
        # The connection is fine; only the consent is stale. Status stays what it is, so the card can offer "resume", which is enable() again.
        await pool().execute("UPDATE whatsapp_watches SET last_run_at = $2, last_error = $3 WHERE member_id = $1", member_id, now,
                             "Paused: this household's notices are now read by a hosted model, and you said yes only to a private one. Say yes to that on the card to resume.")
        return {"paused": "consent"}
    try:
        got = await wr.current_reader().read(member_id, list(row["chats"]), cursors)
        # The account's day/month order is learned from the stamps (a 29 can only be a day) and kept, so a message whose own stamp is ambiguous
        # (9/1/2026) is still read against the right day.
        order = wr.date_order([m_.stamp for m_ in got.messages]) or cursors.get("_date_order")
        if order:
            cursors["_date_order"] = order
        for msg in got.messages:
            seen = cursors.setdefault(msg.chat, [])
            if msg.id in seen:
                continue
            seen.append(msg.id)
            del seen[:-KEEP_IDS]
            try:
                payload = _payload(msg, m["phone"], tz, order)
                parsed, extra = wa_bridge.parse(payload)
                # A message whose own time could not be told says so, rather than quietly counting as arrived today: its relative dates
                # ("tomorrow") are then proposed as uncertain, to be checked (extraction/service.py).
                stored = await gateway.receive_whatsapp(parsed, fetch=wa_bridge.media_fetcher(payload),
                                                        extra_source={**extra, "via": "whatsapp_watch", **({"sent_at_unknown": True} if not payload["timestamp"] else {})})
                taken += sum(1 for _a, dup in stored if not dup)
            except gateway.Rejected:
                continue
        ambiguous = list(getattr(got, "ambiguous", []) or [])
        error = "; ".join(x for x in (f"not found on this account: {', '.join(got.missing)}" if got.missing else "",
                                      f"more than one chat has this name, so none was read (rename the one you mean): {', '.join(ambiguous)}" if ambiguous else "") if x) or None
        await pool().execute(
            "UPDATE whatsapp_watches SET cursors = $2::jsonb, status = 'linked', last_run_at = $3, last_ok_at = $3, last_error = $4, last_found = $5 WHERE member_id = $1",
            member_id, json.dumps(cursors), now, error, taken)
        return {"read": len(got.messages), "taken": taken, "missing": got.missing, "ambiguous": ambiguous}
    except wr.NeedsLink as exc:
        await pool().execute("UPDATE whatsapp_watches SET status = 'lapsed', last_run_at = $2, last_error = $3 WHERE member_id = $1", member_id, now, str(exc)[:300])
        if row["status"] != "lapsed":
            await notify.member(member_id, "WhatsApp needs linking again",
                                "FamilyOS can no longer read your WhatsApp chats because the link ended. Open WhatsApp reading in FamilyOS and link again; nothing was sent or changed.")
        return {"lapsed": True}
    except Exception as exc:  # noqa: BLE001 - one person's page changing is not everyone's
        logger.warning("whatsapp read failed for %s", member_id, exc_info=True)
        await pool().execute("UPDATE whatsapp_watches SET status = 'error', last_run_at = $2, last_error = $3 WHERE member_id = $1", member_id, now, str(exc)[:300])
        return {"failed": True}


async def read_now(p: Principal) -> dict:
    _require(p)
    row = await _row(p.member_id)
    if row and row["last_run_at"] and (dt.datetime.now(dt.UTC) - row["last_run_at"]).total_seconds() < 300:
        raise Invalid("it just ran; try again in a few minutes")
    return {"result": await run_for(p.member_id), **await status(p)}


async def sweep() -> dict[str, int]:
    out = {"members": 0, "taken": 0, "lapsed": 0, "failed": 0}
    if not settings.whatsapp_watch_enabled:
        return out
    for r in await pool().fetch("SELECT w.member_id FROM whatsapp_watches w JOIN households h ON h.id = w.household_id WHERE w.enabled AND h.status = 'active' AND w.status <> 'lapsed'"):
        res = await run_for(r["member_id"])
        out["members"] += 1
        out["taken"] += res.get("taken", 0)
        out["lapsed"] += 1 if res.get("lapsed") else 0
        out["failed"] += 1 if res.get("failed") else 0
    return out


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    try:
        result = await sweep()
    except Exception:  # noqa: BLE001 - the sweep must come back
        logger.warning("the WhatsApp sweep failed; it will run again", exc_info=True)
        result = {"failed_pass": 1}
    return {**result, "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled() -> dict | None:
    if not settings.whatsapp_watch_enabled:
        return None
    return await jobs.ensure_recurring(KIND)


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("whatsapp_watch_enabled",))


def describe() -> str:
    return f"WhatsApp reading: the chats a member names, from their own linked WhatsApp Web, every {SWEEP_SECONDS // 60} minutes; off by default, consent per member, read only"
