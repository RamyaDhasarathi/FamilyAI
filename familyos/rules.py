"""The household's rules: a short list of sentences, each with a switch.

Not a workflow builder. A family will accept a default and perhaps flip a
switch once; it will not wire flows. So every rule is named here, said in
one sentence a parent would say, and either switchable by a guardian or
built in and shown as such. Alongside them, the things the household has
taught by a tap -- "this group is that school" -- listed read-only.
"""
from __future__ import annotations

import uuid

from familyos import audit, origin
from familyos.db import pool
from familyos.identity import NotAllowed, Principal
from familyos.settings import settings

SWITCHES = ("childrens_notices_shared", "weekly_digest", "calendar_follows_decisions", "local_models", "holidays_accepted", "receipts_close_bills", "investments_quiet", "pictures_by_model",
            "weather_lines", "travel_time", "public_holidays", "exam_dates")
WHO = ("bills_handed_to",)
TEXT = ("home_place", "work_place")   # places a guardian types or picks on the map; kept with a point
POINT = {"home_place": ("home_lat", "home_lon"), "work_place": ("work_lat", "work_lon")}


def _catalogue(h: dict, adults: list[dict] | None = None) -> list[dict]:
    adults = adults or []
    handed = next((m for m in adults if m["id"] == h.get("bills_handed_to")), None)
    digest_possible = bool(settings.digest_enabled)
    calendar_possible = bool(settings.calendar_write_enabled)
    local_possible = bool(settings.local_model)
    return [
        {"key": "childrens_notices_shared", "title": "Children’s notices",
         "sentence": "A notice tagged with a child is shared with every adult of the household the moment it is tagged. "
                     "A notice made private afterwards stays private until it is tagged again.",
         "on": bool(h["childrens_notices_shared"]), "fixed": False, "why_fixed": None},
        {"key": "weekly_digest", "title": "Weekly digest",
         "sentence": "Every adult gets the week ahead as one plain message on Sunday morning: what is due, what is waiting "
                     "on them, to-dos, what comes out of the account. Over Telegram, else email. Only what they can see.",
         "on": bool(h["weekly_digest"]) and digest_possible, "fixed": not digest_possible,
         "why_fixed": None if digest_possible else "off for this deployment"},
        {"key": "calendar_follows_decisions", "title": "Calendar",
         "sentence": "A date you accept, and a to-do with a date, go to your Google Calendar when you have connected one. "
                     "Dismissed, handled or done, it comes off again.",
         "on": bool(h["calendar_follows_decisions"]) and calendar_possible, "fixed": not calendar_possible,
         "why_fixed": None if calendar_possible else "off for this deployment"},
        {"key": "local_models", "title": "Local model",
         "sentence": "Notices are read and questions answered by the household’s own model"
                     + (f" ({settings.local_model})" if local_possible else "") + ", on this machine or a server you run, "
                     "instead of the cloud provider. Errands on sites without a runbook need a cloud model and stay off while this is on.",
         "on": bool(h["local_models"]) and local_possible, "fixed": not local_possible,
         "why_fixed": None if local_possible else "no local model on this deployment"},
        {"key": "pictures_by_model", "title": "Pictures read by your model",
         "sentence": "A photographed notice \u2014 a circular on a wall, a stamped scan, a passport page \u2014 is read by the household\u2019s own model"
                     + (f" ({settings.local_model})" if local_possible else "") + ", which sees the picture itself; it needs a model that reads "
                     "pictures. Off, the picture is read by the OCR on this machine, which sees text only.",
         "on": bool(h.get("pictures_by_model")) and local_possible, "fixed": not local_possible,
         "why_fixed": None if local_possible else "no local model on this deployment"},
        {"key": "holidays_accepted", "title": "Holidays",
         "sentence": "A holiday, a closure or a reopening read from a school\u2019s notice is accepted the moment it is read and goes "
                     "to the calendar; nobody is asked. Fees, forms, events to attend and anything optional are still asked.",
         "on": bool(h.get("holidays_accepted")), "fixed": False, "why_fixed": None},
        {"key": "receipts_close_bills", "title": "Receipts settle bills",
         "sentence": "A receipt, or a bank\u2019s UPI alert, that matches an open bill \u2014 same biller, same amount, around its due date \u2014 "
                     "marks the bill paid, and whoever was holding it is told.",
         "on": bool(h.get("receipts_close_bills", True)), "fixed": False, "why_fixed": None},
        {"key": "bills_handed_to", "title": "Bills go to",
         "sentence": ("A bill that arrives is handed to " + handed["display_name"] + " as it is read, with its pay link."
                      if handed else "A bill that arrives can be handed to one adult as it is read, with its pay link. Nobody is named yet."),
         "on": bool(handed), "fixed": False, "why_fixed": None,
         "member_id": handed["id"] if handed else None,
         "options": [{"id": m["id"], "name": m["display_name"]} for m in adults]},
        {"key": "investments_quiet", "title": "Investments ask nothing",
         "sentence": "E-votes, ballots, AGM notices, contract notes and statements are filed in Investments and ask nothing of anyone. "
                     "Turn it off and their dates are proposed like any other.",
         "on": bool(h.get("investments_quiet", True)), "fixed": False, "why_fixed": None},
        {"key": "promos_never_obligate", "title": "Promotions",
         "sentence": "A promotion, newsletter or developer mail never becomes something to do. It is filed and nothing is asked.",
         "on": True, "fixed": True, "why_fixed": "built in"},
        {"key": "receipts_feed_meals", "title": "Receipts",
         "sentence": "Grocery receipts feed the week’s meals plan and the running-low list; restaurant orders are left out of the rhythm.",
         "on": True, "fixed": True, "why_fixed": "built in"},
        # Public context: read without any credential, each off until turned on.
        {"key": "home_place", "title": "Where home is",
         "sentence": ("Home is " + h["home_place"] + ". The weather and travel-time lines below are read for it; nothing of the family's is sent, only the place."
                      if h.get("home_place") else "A town, an address or a pasted Google Maps link, picked once on the Household card, for the weather and travel-time lines below. Nothing of the family's is sent, only the place."),
         "on": h.get("home_lat") is not None, "fixed": False, "why_fixed": None, "kind": "place", "text": h.get("home_place")},
        {"key": "work_place", "title": "Where the office is",
         "sentence": ("The office is " + h["work_place"] + ". The commute from home is on Today's day tile, live on a weekday morning when traffic is read live."
                      if h.get("work_place") else "The office, picked once on the Household card, so the commute from home sits beside the school run on Today."),
         "on": h.get("work_lat") is not None, "fixed": False, "why_fixed": None, "kind": "place", "text": h.get("work_place")},
        {"key": "weather_lines", "title": "The weather",
         "sentence": "A line on the brief for today and tomorrow (33°, showers likely), from a public forecast for home, with no key and nothing of the family's in the request.",
         "on": bool(h.get("weather_lines")), "fixed": h.get("home_lat") is None, "why_fixed": None if h.get("home_lat") is not None else "needs home"},
        {"key": "travel_time", "title": "Leave by",
         "sentence": "A dated thing with a place gets a drive time from home and a leave-by time, from public maps; the school run too, with a leave-by from the school's timings. "
                     "Only the place's own words and the home town leave the house"
                     + (", except the school run on a school morning, which goes to TomTom with the two points under the deployment's key for live traffic; "
                        "a guardian is told when the drive is markedly worse than usual." if settings.tomtom_api_key else "."),
         "on": bool(h.get("travel_time")), "fixed": h.get("home_lat") is None, "why_fixed": None if h.get("home_lat") is not None else "needs home"},
        {"key": "public_holidays", "title": "Public holidays",
         "sentence": "The country's public holidays in the next two weeks on the brief, from a public calendar, so the week reads right before the school's circular arrives.",
         "on": bool(h.get("public_holidays")), "fixed": False, "why_fixed": None},
        {"key": "exam_dates", "title": "Exam date sheets",
         "sentence": "A board's date-sheet page, set per school on the Household card, is read once a day without any sign-in and handed in as a notice when it changes, so its dates are proposed like any other.",
         "on": bool(h.get("exam_dates")), "fixed": False, "why_fixed": None},
    ]


def _learned_label(key: str) -> str:
    if key.startswith("telegram:chat:"):
        return "a Telegram group"
    if key.startswith("email:"):
        return "mail from " + key[len("email:"):]
    if key.startswith("whatsapp:"):
        return "the WhatsApp group “" + key[len("whatsapp:"):].split(":", 1)[-1] + "”"
    return key


async def list_for(p: Principal) -> dict:
    h = await pool().fetchrow("SELECT * FROM households WHERE id = $1", p.household_id)
    adults = [dict(r) for r in await pool().fetch(
        "SELECT id, display_name FROM members WHERE household_id = $1 AND role <> 'child' ORDER BY created_at", p.household_id)]
    learned = [{"kind": "source_school", "source_key": r["source_key"], "label": _learned_label(r["source_key"]),
                "says": f"is {r['school']}’s: every notice from it is attributed on arrival", "created_at": r["created_at"]}
               for r in await origin.list_for(p)]
    return {"rules": _catalogue(dict(h), adults), "learned": learned}


def _plain(v):
    return str(v) if isinstance(v, uuid.UUID) else v


async def set_switches(actor: Principal, changes: dict[str, bool]) -> None:
    """A guardian flips one or more switches. Changing one changes what
    happens from now; nothing already done is undone."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can change the household's rules")
    who = {k: v for k, v in changes.items() if k in WHO and k in changes}
    text = {k: v for k, v in changes.items() if k in TEXT}
    changes = {k: v for k, v in changes.items() if k in SWITCHES and v is not None}
    if text:
        # Home, the office: words typed here are kept as typed and placed once
        # (a town by the weather geocoder, an address or a pasted map link by
        # the map search); a place nothing knows keeps the words and no point,
        # and the lines that need a point stay off. A point picked on the map
        # search arrives through set_place instead, exact.
        from familyos import publiccontext
        for key, raw in text.items():
            place = " ".join(str(raw or "").split())[:200] or None
            point = None
            if place:
                point = await publiccontext.geocode(place) if key == "home_place" and "," not in place and not place.startswith("http") else None
                if point is None:
                    try:
                        found = await publiccontext.resolve(place)
                    except Exception:  # noqa: BLE001
                        found = []
                    if found:
                        point = found[0]
                        if place.startswith(("http://", "https://")):
                            place = found[0]["label"][:200]
            lat_key, lon_key = POINT[key]
            changes = {**changes, key: place, lat_key: point["lat"] if point else None, lon_key: point["lon"] if point else None}
    if who:
        # A bill goes to an adult of this household, or to nobody.
        for _key, member_id in who.items():
            if member_id is not None:
                m = await pool().fetchrow("SELECT role FROM members WHERE id = $1 AND household_id = $2", member_id, actor.household_id)
                if m is None or m["role"] == "child":
                    raise NotAllowed("a bill can only be handed to an adult of this household")
        changes = {**changes, **who}
    if not changes:
        return
    async with pool().acquire() as conn, conn.transaction():
        before = dict(await conn.fetchrow(f"SELECT {', '.join(SWITCHES + WHO + TEXT + ('home_lat', 'home_lon', 'work_lat', 'work_lon'))} FROM households WHERE id = $1 FOR UPDATE",
                                          actor.household_id))
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(changes))
        await conn.execute(f"UPDATE households SET {sets} WHERE id = $1", actor.household_id, *changes.values())
        if "local_models" in changes:
            from familyos import chat
            chat.forget_local_choice(actor.household_id)
        if changes.get("investments_quiet"):
            # What is already waiting from investment mail is filed now too.
            from familyos import categories
            rows = await conn.fetch(
                "SELECT o.id, a.channel, a.source FROM obligations o JOIN input_artifacts own ON own.id = o.artifact_id "
                "JOIN input_artifacts a ON a.id = COALESCE(own.parent_id, own.id) WHERE o.household_id = $1 AND o.status = 'proposed' "
                "AND o.superseded_at IS NULL", actor.household_id)
            quiet = [r["id"] for r in rows if categories.category_of(r["channel"], r["source"]) == "trading"]
            if quiet:
                await conn.execute("UPDATE obligations SET status = 'dismissed', decided_by = NULL, decided_at = NOW() WHERE id = ANY($1::uuid[])", quiet)
                for oid in quiet:
                    await audit.record(actor.household_id, "obligation.dismissed", actor_member_id=actor.member_id, target_type="obligation",
                                       target_id=oid, detail={"rule": "investments_quiet"}, conn=conn)
        await audit.record(actor.household_id, "household.rules_set", actor_member_id=actor.member_id,
                           target_type="household", target_id=actor.household_id,
                           detail={"set": {k: _plain(v) for k, v in changes.items()}, "was": {k: _plain(before[k]) for k in changes}}, conn=conn)
    if "travel_time" in changes or "home_place" in changes:
        # The morning's traffic check follows the switch and where home is.
        from familyos import publiccontext
        await publiccontext.ensure_run_scheduled(actor.household_id)


async def set_place(actor: Principal, key: str, label: str | None, lat: float | None, lon: float | None) -> None:
    """A place picked on the map search: home or the office, the words and
    the exact point together. Guardians only. Null clears both."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can change the household's places")
    if key not in POINT:
        raise NotAllowed("a place is home or work")
    if (lat is None) != (lon is None) or (label is None and lat is not None):
        raise NotAllowed("a place is its words and a point together")
    lat_key, lon_key = POINT[key]
    label = " ".join((label or "").split())[:200] or None
    async with pool().acquire() as conn, conn.transaction():
        before = await conn.fetchrow(f"SELECT {key}, {lat_key}, {lon_key} FROM households WHERE id = $1 FOR UPDATE", actor.household_id)
        await conn.execute(f"UPDATE households SET {key} = $2, {lat_key} = $3, {lon_key} = $4 WHERE id = $1", actor.household_id, label, lat, lon)
        await audit.record(actor.household_id, "household.place_set", actor_member_id=actor.member_id, target_type="household",
                           target_id=actor.household_id, detail={"place": key, "set": lat is not None, "was_set": before[lat_key] is not None}, conn=conn)
    if key == "home_place":
        from familyos import publiccontext
        await publiccontext.ensure_run_scheduled(actor.household_id)
