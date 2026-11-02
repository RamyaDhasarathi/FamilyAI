"""The decision queue: only what waits on a person, each with the way to decide it.

Not another list of dates. A card is here because someone has to choose, and it carries what a person needs to choose
well: what happened, who it affects, by when, the words it came from, what FamilyOS would do and why, what waiting
costs, and the buttons. The buttons are the existing endpoints (accept a date, confirm a revision, approve an errand or
a purchase, hand a notice on), described in the card so a client calls them and nothing new decides anything.

Rules, not a model: the recommendation and the cost of waiting are fixed sentences chosen by the kind of decision and
its facts, so they are the same every time and can be read in this file. A guardian-only decision (an errand to approve,
a purchase to approve) appears only for a guardian.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from urllib.parse import quote

from familyos import brief, clock, conflicts, documents, errands, graph, kid, payments, pointers, warranty_hints
from familyos.db import pool
from familyos.identity import Principal

# Text in a notice that is addressed to an AI assistant rather than to a family: a notice a person wrote for people never says this.
_ADDRESSED_TO_MODELS = re.compile(r"ignore (all |your )?(previous|prior|above) instructions|ai assistants?\b|\b(system|assistant) (prompt|notice|message)\b|call (the )?\w+_\w+ (tool|function)|you are now\b", re.I)


def addressed_to_models(*texts: str | None) -> bool:
    return any(t and _ADDRESSED_TO_MODELS.search(t) for t in texts)


KIND_ORDER = {"purchase": 0, "errand": 1, "kid_request": 2, "agent_proposal": 3, "revision": 4, "date": 5, "handed": 6, "pointer": 7, "warranty": 8, "document": 3, "heads_up": 9}


def _act(key: str, label: str, method: str, path: str, body: dict | None = None, *, primary: bool = False) -> dict:
    # body_json is the same body as text: a client that rewrites key names (the phone's snake-case decoder) must not touch what is sent back.
    return {"key": key, "label": label, "method": method, "path": "/v1" + path, "body": body or {}, "body_json": json.dumps(body or {}), "primary": primary}


def _link(label: str, href: str) -> dict:
    return {"key": "open", "label": label, "href": href, "primary": False}


async def _adults(p: Principal) -> list[dict]:
    rows = await pool().fetch("SELECT id, display_name FROM members WHERE household_id = $1 AND role IN ('guardian', 'adult') AND id <> $2 ORDER BY created_at",
                              p.household_id, p.member_id)
    return [{"id": str(r["id"]), "name": r["display_name"]} for r in rows]


def _delegate(artifact_id, adults: list[dict], note: str) -> dict | None:
    if not adults or artifact_id is None:
        return None
    return {"key": "delegate", "label": "Hand to…", "primary": False,
            "choices": [_act("delegate", a["name"], "POST", f"/artifacts/{artifact_id}/assign", {"member_id": a["id"], "note": note}) for a in adults]}


async def _quotes(obligation_ids: list) -> dict:
    if not obligation_ids:
        return {}
    rows = await pool().fetch("SELECT o.id, c.quote FROM obligations o JOIN claims c ON c.id = o.claim_id WHERE o.id = ANY($1::uuid[])", obligation_ids)
    return {r["id"]: r["quote"] for r in rows}


def _date_card(i: dict, quote: str | None, adults: list[dict], today: dt.date, cover: dict | None = None) -> dict:
    due: dt.date | None = i.get("due_date")
    gone = bool(due and due < today)
    who = i.get("subject_name")
    optional = bool(i.get("optional"))
    suspicious = addressed_to_models(i.get("title"), quote)
    if suspicious:
        rec = ("Dismiss it: this text is addressed to AI assistants, not to your family. Do not follow it.", "dismiss")
        cost = "Nothing is lost by dismissing it. Check who sent it."
    elif gone:
        rec = ("Dismiss it: the date has passed and nobody said yes.", "dismiss")
        cost = "It stays in Needs you as late until someone answers."
    elif optional:
        rec = ("Dismiss it unless you plan to go: the notice calls it optional.", "dismiss")
        cost = "No reminder is set and it stays off the calendar."
    else:
        rec = (f"Accept it{' for ' + who if who else ''}: it names a date and asks something of the family.", "accept")
        cost = "Nothing is put on the calendar and no reminder is set until you answer."
    conflict = None
    if i.get("clashes"):
        cost = f"It clashes with {i['clashes'][0]}; waiting leaves both standing. " + cost
        if cover:
            free = [a["name"] for a in cover["people"] if a["state"] == "free"]
            busy = [a["name"] for a in cover["people"] if a["state"] == "busy"]
            unknown = [a["name"] for a in cover["people"] if a["state"] == "unknown"]
            conflict = {"with": i["clashes"][0], "window": cover["window"], "free": free, "busy": busy, "unknown": unknown}
            if free:
                rec = (f"This clashes with {i['clashes'][0]} ({cover['window'][0]}\u2013{cover['window'][1]}). "
                       f"{' and '.join(free)} looks free then: hand it to them and they will be asked.", "delegate")
    actions = [_act("accept", "Accept", "POST", f"/obligations/{i['obligation_id']}/decision", {"status": "accepted"}, primary=rec[1] == "accept"),
               _act("dismiss", "Not this", "POST", f"/obligations/{i['obligation_id']}/decision", {"status": "dismissed"}, primary=rec[1] == "dismiss")]
    d = _delegate(i.get("artifact_id"), cover["people"] if cover else adults, f"Can you cover: {i['title']}?" if conflict else f"Can you decide: {i['title']}?")
    if d and cover:
        for ch, a in zip(d["choices"], cover["people"], strict=True):
            ch["label"] = a["name"] + {"free": " (free then)", "busy": " (busy then)", "unknown": ""}[a["state"]]
    if d:
        actions.append(d)
    if i.get("artifact_id"):
        actions.append(_link("Open the notice", f"#/notices/{i['artifact_id']}"))
    return {"id": f"date:{i['obligation_id']}", "obligation_id": i["obligation_id"], "artifact_id": i.get("artifact_id"), "time": i.get("due_time"),
            "kind": "date", "title": i["title"], "happened": i["why"],
            "affects": [who] if who else [], "deadline": due, "when": i.get("when"), "late": gone,
            "source": {"artifact_id": i.get("artifact_id"), "quote": quote},
            "conflict": conflict, "suspicious": suspicious,
            "recommendation": {"text": rec[0], "action": rec[1]}, "consequence": cost, "actions": actions}


def _handed_card(i: dict, adults: list[dict], ack: str | None = None) -> dict:
    by = i.get("assigned_by_name") or "Someone"
    actions = []
    if ack == "pending":
        # Not yet answered: say yes, or say no and, if you can, who could.
        actions.append(_act("accept", "I'll take it", "POST", f"/artifacts/{i['artifact_id']}/acknowledge", {"response": "accept"}, primary=True))
        if adults:
            actions.append({"key": "decline", "label": "Can't: suggest…", "primary": False,
                            "choices": [_act("decline", a["name"], "POST", f"/artifacts/{i['artifact_id']}/acknowledge",
                                             {"response": "decline", "propose_member_id": a["id"]}) for a in adults]})
        actions.append(_act("decline_plain", "Can't", "POST", f"/artifacts/{i['artifact_id']}/acknowledge", {"response": "decline"}))
    actions.append(_act("done", "I've done it", "POST", f"/artifacts/{i['artifact_id']}/handled", {"note": "done from the decision queue"}, primary=ack != "pending"))
    d = _delegate(i["artifact_id"], adults, i.get("note") or f"Handed on from {by}") if ack != "pending" else None
    if d:
        actions.append(d)
    if ack != "pending":
        actions.append(_act("take_back", "Not mine", "POST", f"/artifacts/{i['artifact_id']}/assign", {"member_id": None, "note": None}))
    actions.append(_link("Open the notice", f"#/notices/{i['artifact_id']}"))
    return {"id": f"handed:{i['artifact_id']}", "artifact_id": i["artifact_id"], "kind": "handed", "title": i["title"], "happened": i["why"],
            "affects": ["You"], "deadline": None, "when": i.get("when"), "late": False,
            "source": {"artifact_id": i["artifact_id"], "quote": i.get("note")},
            "recommendation": {"text": (f"Say whether you can take it: {by} is waiting on your answer." if ack == "pending"
                                        else "Do it, or hand it on to someone who can: " + by + " is waiting on an answer."), "action": "accept" if ack == "pending" else "done"},
            "consequence": (f"If nobody answers, it moves to the backup or {by} is told." if ack == "pending" else f"{by} stays waiting and it stays on your list."),
            "actions": actions}


def _revision_card(i: dict) -> dict:
    return {"id": f"revision:{i['amendment_id']}", "kind": "revision", "title": i["title"], "happened": i["why"],
            "affects": [i["subject_name"]] if i.get("subject_name") else [], "deadline": i.get("due_date"), "when": None, "late": False,
            "source": {"artifact_id": i.get("artifact_id"), "quote": None},
            "recommendation": {"text": "Read the later notice, then confirm the change if it replaces the old date.", "action": "open"},
            "consequence": "Until it is confirmed, the date shown may not be the one that holds.",
            "actions": [_link("Read the later notice", f"#/notices/{i['artifact_id']}") if i.get("artifact_id") else None,
                        _act("confirm", "It changed", "POST", f"/amendments/{i['amendment_id']}/decision", {"status": "confirmed"}),
                        _act("reject", "Keep the original", "POST", f"/amendments/{i['amendment_id']}/decision", {"status": "rejected"})]}


def _errand_card(e: dict) -> dict:
    return {"id": f"errand:{e['id']}", "kind": "errand", "title": e["title"], "happened": "FamilyOS wrote this errand down in full and is waiting for a guardian.",
            "affects": ["The household"], "deadline": None, "when": None, "late": False, "source": {"artifact_id": None, "quote": None},
            "recommendation": {"text": "Approve it only if the written details, the limit and the site are what you want.", "action": "open"},
            "consequence": "Nothing runs until a guardian approves exactly what is written.",
            "actions": [_act("approve", "Approve", "POST", f"/errands/{e['id']}/approve", primary=True),
                        _act("cancel", "Cancel", "POST", f"/errands/{e['id']}/cancel"),
                        _link("Read it in full", f"#/errands/{e['id']}")]}


def _purchase_card(pu: dict, who: str) -> dict:
    amount = f"{pu['amount']:g} {pu['currency']}"
    return {"id": f"purchase:{pu['id']}", "kind": "purchase", "title": pu["title"], "happened": f"{who} asked to buy this from {pu['merchant_name']} for {amount}.",
            "affects": [who], "deadline": pu["expires_at"].date() if pu.get("expires_at") else None, "when": None, "late": False,
            "source": {"artifact_id": None, "quote": pu.get("note")},
            "recommendation": {"text": "Approve only a purchase you recognise, at an amount you expected.", "action": "open"},
            "consequence": "The request lapses when it expires, and nothing is paid until you approve it.",
            "actions": [_act("approve", "Approve", "POST", f"/purchases/{pu['id']}/decision", {"approve": True}, primary=True),
                        _act("decline", "Decline", "POST", f"/purchases/{pu['id']}/decision", {"approve": False})]}


def _kid_card(r: dict) -> dict:
    first = r["child"].split()[0]
    return {"id": f"kid_request:{r['id']}", "kind": "kid_request", "title": f"{first} asks: {r['text']}", "happened": f"{first} asked a parent. They see your answer in their own day.",
            "affects": [r["child"]], "deadline": None, "when": None, "late": False, "source": {"artifact_id": None, "quote": r["text"]},
            "recommendation": {"text": "Answer when you can: a quick yes, no or later is enough.", "action": "later"},
            "consequence": f"{first} stays waiting; they can see it has not been answered.",
            "actions": [_act("yes", "Yes", "POST", f"/kid-requests/{r['id']}/answer", {"answer": "yes"}, primary=True),
                        _act("no", "No", "POST", f"/kid-requests/{r['id']}/answer", {"answer": "no"}),
                        _act("later", "Later", "POST", f"/kid-requests/{r['id']}/answer", {"answer": "later"})]}


def _agent_card(r: dict) -> dict:
    via = r["via"]
    return {"id": f"agent:{r['id']}", "kind": "agent_proposal", "title": f"{via} proposes: {r['summary']}", "happened": f"Your assistant {via} suggested this. Nothing happens until you confirm.",
            "affects": [], "deadline": r["expires_at"].date(), "late": False, "source": {"artifact_id": None, "quote": None},
            "recommendation": {"text": "Confirm only if it is what you want done.", "action": "open"},
            "consequence": "It lapses on its own if you leave it, and nothing is done.",
            "actions": [_act("confirm", "Confirm", "POST", f"/chat/pending/{r['id']}/confirm", primary=True), _act("cancel", "Not now", "POST", f"/chat/pending/{r['id']}/cancel")]}


def _pointer_card(x: dict) -> dict:
    headline, cands = x["headline"], x.get("candidates") or []
    one = len(cands) == 1
    reads = [_act(f"read:{c['service']}", f"Read it in {c['app']}" if not one else "Read it from the app", "POST", "/errands",
                  {"service": c["service"], "kind": "look", "title": f"Read the new announcement in {c['app']}", "spec": {"what": "Announcements"}}, primary=one) for c in cands]
    return {"id": f"pointer:{x['id']}", "kind": "pointer", "title": f"{cands[0]['app']} has something new" if one else "A school app has something new",
            "happened": f"The notification only said “{headline}”. What it says is inside the app" + ("" if one or not cands else ", and a notification does not say which one") + ".",
            "affects": [], "deadline": None, "when": None, "late": False, "source": {"artifact_id": x["id"], "quote": headline},
            "recommendation": {"text": ("Have the phone read the app, with the phone next to the Mac, or share a screenshot of the announcement from the app." if cands
                                        else "Open the app and share a screenshot of the announcement."), "action": "open"},
            "consequence": "Until it is read, any date or form in it is not on your list.",
            "actions": reads + [_act("handled", "I have seen it", "POST", f"/artifacts/{x['id']}/handled", {"note": None})]}


def _warranty_card(x: dict) -> dict:
    bits = []
    if x["warranty_months"]:
        bits.append(f"{x['warranty_months']} months of warranty")
    if x["return_days"]:
        bits.append(f"{x['return_days']} days to return it")
    body = {"title": x["product"], "merchant": x["merchant"], "purchased_on": x["purchased_on"].isoformat() if x["purchased_on"] else None,
            "return_days": x["return_days"], "warranty_months": x["warranty_months"], "artifact_id": str(x["artifact_id"])}
    return {"id": f"warranty:{x['artifact_id']}", "kind": "warranty", "title": f"Track the warranty on {x['product']}",
            "happened": "The invoice" + (f" from {x['merchant']}" if x["merchant"] else "") + " says " + " and ".join(bits) + ".",
            "affects": [], "deadline": None, "when": None, "late": False, "source": {"artifact_id": str(x["artifact_id"]), "quote": x.get("said")},
            "recommendation": {"text": "Track it, so you are told before the cover ends. Check the start date on the invoice: a warranty plan can begin after the maker's own.", "action": "accept"},
            "consequence": "Without an entry nothing warns you, and a claim missed by a day is lost.",
            "actions": [_act("track", "Track it", "POST", "/finance/warranties", body, primary=True),
                        _act("dismiss", "Not this", "POST", f"/suggestions/{quote('warranty:' + str(x['artifact_id']), safe='')}/dismiss"),
                        _link("Read the invoice", f"#/notices/{x['artifact_id']}")]}


def _document_card(d: dict, today: dt.date) -> dict:
    who = f"{d['holder_name']}’s " if d.get("holder_name") else ""
    expired = d["status"] == "expired"
    on = d["expires_on"].strftime("%-d %b %Y")
    title = f"{who}{d['label']} has expired" if expired else f"{who}{d['label']} runs out on {on}"
    renew_by = max(today, today + dt.timedelta(days=7)) if expired else max(today, d["expires_on"] - dt.timedelta(days=14))
    return {"id": f"document:{d['id']}", "kind": "document", "title": title,
            "happened": (f"It expired on {on}, {-d['days_left']} days ago." if expired else f"It expires on {on}, in {d['days_left']} days."),
            "affects": [d["holder_name"]] if d.get("holder_name") else [], "deadline": d["expires_on"] if not expired else None, "when": None, "late": expired,
            "source": {"artifact_id": str(d["artifact_id"]), "quote": None},
            "recommendation": {"text": "Renew it with the office that issued it. When you share the renewed card or PDF, this clears by itself.", "action": "accept"},
            "consequence": ("Using an expired " if expired else "Letting it lapse means an expired ") + d["label"] + " can mean a fine, a refused claim or a refused booking.",
            "actions": [_act("todo", "Add a to-do to renew it", "POST", "/todos", {"title": f"Renew {who}{d['label']}", "due_date": renew_by.isoformat(), "note": f"Expiry on the record: {on}."}, primary=True),
                        _act("renewed", "I have renewed it", "POST", f"/suggestions/{quote('doc:' + str(d['id']), safe='')}/dismiss"),
                        _link("See the document", f"#/notices/{d['artifact_id']}")]}


def _heads_up_card(x: dict) -> dict:
    return {"id": f"heads_up:{x['key']}", "kind": "heads_up", "title": x["title"], "happened": x["why"], "affects": [], "deadline": None, "when": None, "late": False,
            "source": {"artifact_id": None, "quote": None},
            "recommendation": {"text": "Nobody asked; it shows in how your record connects. Open the map to see what it touches.", "action": "open"},
            "consequence": "Nothing is wrong yet. This is a nudge, and it goes away when you say you have seen it.",
            "actions": [_link("See how it connects", f"#/map/{quote(x['ref'], safe='')}"),
                        _act("seen", "Got it", "POST", f"/suggestions/{quote('insight:' + x['key'], safe='')}/dismiss")]}


def _order(c: dict) -> tuple:
    d = c.get("deadline")
    return (0 if c.get("late") else 1, d or dt.date.max, KIND_ORDER.get(c["kind"], 9), c["title"])


async def queue(p: Principal, today: dt.date | None = None) -> list[dict]:
    today = today or clock.today()
    day = await brief.today(p, on=today, limit=-1)
    items = day["items"]
    adults = await _adults(p)
    quotes = await _quotes([i["obligation_id"] for i in items if i.get("obligation_id")])
    handed_ids = [i["artifact_id"] for i in items if i["reason"] == "assigned" and i.get("artifact_id")]
    acks = {r["id"]: r["assigned_ack"] for r in await pool().fetch("SELECT id, assigned_ack FROM input_artifacts WHERE id = ANY($1::uuid[])", handed_ids)} if handed_ids else {}
    cards: list[dict] = []
    for r in await pool().fetch("SELECT id, summary, expires_at, params FROM pending_actions WHERE member_id = $1 AND done_at IS NULL AND cancelled_at IS NULL "
                                "AND expires_at > NOW() ORDER BY created_at", p.member_id):
        params = r["params"]
        while isinstance(params, str):                    # staged params come back as text from this pool
            params = json.loads(params)
        if isinstance(params, dict) and params.get("via"):
            cards.append(_agent_card({"id": r["id"], "summary": r["summary"], "expires_at": r["expires_at"], "via": params["via"]}))
    for i in items:
        if i["reason"] in ("missed", "undecided") and i.get("status") == "proposed" and i.get("obligation_id"):
            cover = await conflicts.cover_for(p, i["due_date"], i.get("due_time"), adults) if i.get("clashes") and i.get("due_date") else None
            cards.append(_date_card(i, quotes.get(i["obligation_id"]), adults, today, cover))
        elif i["reason"] == "assigned" and i.get("artifact_id"):
            cards.append(_handed_card(i, adults, acks.get(i["artifact_id"])))
        elif i["reason"] == "amendment" and i.get("amendment_id"):
            cards.append(_revision_card(i))
    for x in await pointers.waiting(p):
        cards.append(_pointer_card(x))
    for x in await warranty_hints.waiting(p):
        cards.append(_warranty_card(x))
    for d in await documents.needing_renewal(p, today):
        cards.append(_document_card(d, today))
    noticed = await graph.insights(p, today)
    if noticed:
        gone = {r["source_key"] for r in await pool().fetch("SELECT source_key FROM suggestion_dismissals WHERE household_id = $1 AND source_key LIKE 'insight:%'", p.household_id)}
        for x in noticed:
            if f"insight:{x['key']}" not in gone:
                cards.append(_heads_up_card(x))
    if p.role == "guardian":
        for r in await kid.requests_for_guardians(p):
            cards.append(_kid_card(r))
        for e in await errands.list_for(p):
            if e["status"] == "proposed":
                cards.append(_errand_card(e))
        names = {r["id"]: r["display_name"] for r in await pool().fetch("SELECT id, display_name FROM members WHERE household_id = $1", p.household_id)}
        for pu in await payments.list_for(p):
            if pu["status"] == "requested":
                cards.append(_purchase_card(pu, names.get(pu["requested_by"], "Someone")))
    for c in cards:
        c["actions"] = [a for a in c["actions"] if a]
    cards.sort(key=_order)
    return cards


_ = uuid  # the card ids are strings built from uuids; kept importable for callers that parse them
