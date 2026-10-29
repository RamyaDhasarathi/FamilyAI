"""Cards: what the server shows in a chat, described as plain data that each client draws its own way.

The web console, the phone and Telegram all read the same list. A card is one of:

- `text`    {text}                       a line or two
- `chips`   {items: [{label, ask}]}      next questions to tap
- `action`  {title, sub, buttons: [...]} something that asks for a yes, with its source in `sub`

and a button is `confirm` {id} (run a staged action), `cancel` {id} (leave it, remembering "not now" where that applies),
`link` {url} (open the shop's own page) or `ask` {text}. The effect of a confirm button is fixed when the card is made:
the text on the card comes from the staged action, never from a model, so a card cannot say one thing and do another.
Nothing here pays, books or sends: a confirm runs the same function a button in the app would.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import brief, chat_actions, clock, ledger, medications, suggest
from familyos.identity import Principal

MAX_ACTIONS = 4


async def _pair(p: Principal, yes: dict, no_label: str, no: dict | None, *, yes_label: str, ttl: int) -> list[dict]:
    group = uuid.uuid4() if no is not None else None
    staged = await chat_actions.stage(p, yes, ttl_minutes=ttl, group_id=group)
    if staged is None:
        return []
    buttons = [{"label": yes_label, "kind": "confirm", "id": str(staged["id"])}]
    if no is not None:
        other = await chat_actions.stage(p, no, ttl_minutes=ttl, group_id=group)
        if other is not None:
            buttons.append({"label": no_label, "kind": "confirm", "id": str(other["id"])})
    return buttons


async def opening(p: Principal, today: dt.date | None = None, *, ttl_minutes: int = chat_actions.TTL_MINUTES) -> dict:
    """What a member sees when they open the chat: what needs them, with the answer one tap away."""
    today = today or clock.today()
    cards: list[dict] = []
    actions = 0
    items = (await brief.today(p, on=today)).get("items") or []

    waiting = [i for i in items if i.get("status") == "proposed" and i.get("obligation_id")]
    for i in waiting[:2]:
        yes = {"kind": "decide", "ok": True, "obligation_id": i["obligation_id"], "status": "accepted", "title": i["title"]}
        no = {"kind": "decide", "ok": True, "obligation_id": i["obligation_id"], "status": "dismissed", "title": i["title"]}
        buttons = await _pair(p, yes, "Not this", no, yes_label="Accept", ttl=ttl_minutes)
        if buttons:
            cards.append({"type": "action", "title": i["title"], "sub": " · ".join(x for x in (i.get("when"), i.get("why")) if x), "buttons": buttons})
            actions += 1

    for sg in (await suggest.for_member(p, today))[:2]:
        if actions >= MAX_ACTIONS:
            break
        # "Not now" is a cancel that records the dismissal, so the staged action carries the key for it.
        staged = await chat_actions.stage(p, {"kind": "suggestion", "ok": True, "key": sg["key"], "title": sg["title"], "due_date": sg["due_date"],
                                              "dismiss_suggestion": sg["key"]}, ttl_minutes=ttl_minutes)
        if staged is None:
            continue
        buttons = [{"label": "Add", "kind": "confirm", "id": str(staged["id"])}, {"label": "Not now", "kind": "cancel", "id": str(staged["id"])}]
        if sg.get("link"):
            buttons.append({"label": "Look", "kind": "link", "url": sg["link"]})
        cards.append({"type": "action", "title": sg["title"], "sub": sg["why"], "buttons": buttons})
        actions += 1

    low = [r for r in await ledger.running_low(p) if r["status"] in ("soon", "overdue")][:2]
    for r in low:
        if actions >= MAX_ACTIONS:
            break
        buttons = [{"label": "Reorder", "kind": "link", "url": r["reorder_url"]}] if r.get("reorder_url") else []
        if buttons:
            cards.append({"type": "action", "title": f"{r['item']} may be running low", "sub": f"Bought about every {r['every_days']} days at {r['merchant']}", "buttons": buttons})
            actions += 1

    refills = [m for m in await medications.list_for(p) if m.get("status") == "refill"][:2]
    for m in refills:
        cards.append({"type": "text", "text": f"Refill due soon: {m['drug']}" + (f" for {m['patient_name']}" if m.get("patient_name") else "") + (f" (supply to {m['ends_on'].isoformat()})" if m.get("ends_on") else "")})

    late = [i for i in items if i.get("reason") in ("overdue", "missed") and i.get("status") != "proposed"][:3]
    if late:
        cards.append({"type": "text", "text": "Late and still open: " + "; ".join(i["title"] for i in late)})

    n = len(waiting)
    say = (f"{n} thing{'s' if n != 1 else ''} waiting for your yes." if n else "Nothing is waiting for your yes.") + (" A few ideas below." if actions > min(n, 2) else "")
    cards.append({"type": "chips", "items": [{"label": q, "ask": q} for q in
                                             ("What needs someone this week?", "Which bills are due?", "What is still undecided?", "What medicines are current?")]})
    return {"say": say, "cards": cards}



def telegram_buttons(card: dict) -> list[tuple[str, str]]:
    """One row of Telegram buttons for an action card: a link opens the shop's page, the rest come back as presses."""
    row = []
    for b in card.get("buttons") or []:
        if b["kind"] == "link":
            row.append((b["label"], b["url"]))
        else:
            row.append((b["label"], f"act:{b['id']}:{'y' if b['kind'] == 'confirm' else 'n'}"))
    return row


# The decision cards that have no console-only step: what each one's buttons do, staged as confirmable actions so a press
# in Telegram runs the same thing the console button would, as the member who pressed.
CHAT_KINDS = ("heads_up", "document", "warranty", "pointer")


async def decision_buttons(p: Principal, card: dict) -> list[dict]:
    from urllib.parse import unquote
    by = {a["key"]: a for a in card.get("actions") or [] if a.get("method")}
    title = card["title"]
    plan: list[tuple[str, dict]] = []                  # (label, proposal)

    def dismissal(label: str, action: dict) -> None:
        key = unquote(action["path"].split("/suggestions/", 1)[1].rsplit("/dismiss", 1)[0])
        plan.append((label, {"kind": "ack", "ok": True, "title": title, "dismiss_suggestion": key}))

    if card["kind"] == "heads_up" and "seen" in by:
        dismissal("Got it", by["seen"])
    elif card["kind"] == "document":
        if "todo" in by:
            plan.append(("Add a to-do", {"kind": "todo", "ok": True, **{k: v for k, v in by["todo"]["body"].items() if k in ("title", "due_date", "note")}}))
        if "renewed" in by:
            dismissal("Renewed", by["renewed"])
    elif card["kind"] == "warranty":
        if "track" in by:
            plan.append(("Track it", {"kind": "warranty", "ok": True, **by["track"]["body"]}))
        if "dismiss" in by:
            dismissal("Not this", by["dismiss"])
    elif card["kind"] == "pointer":
        reads = [a for k, a in by.items() if k.startswith("read:")]
        if len(reads) == 1:
            b = reads[0]["body"]
            plan.append(("Read it", {"kind": "errand", "ok": True, "look": True, "service": b["service"], "title": b["title"], "what": "Announcements"}))
        if "handled" in by and card.get("source", {}).get("artifact_id"):
            plan.append(("Seen it", {"kind": "handled", "ok": True, "artifact_id": card["source"]["artifact_id"], "headline": card["source"].get("quote") or title}))
    out = []
    for label, proposal in plan:
        staged = await chat_actions.stage(p, proposal)
        if staged:
            out.append({"label": label, "kind": "confirm", "id": str(staged["id"])})
    return out
