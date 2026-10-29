"""A suggestion Ask made can be confirmed in the chat it was made in, once, by the member it was shown to."""
import datetime as dt
import uuid

import pytest

from familyos import chat, chat_actions, clock
from familyos.db import pool
from familyos.identity import NotFound, Principal
from familyos.intake import telegram
from familyos.settings import settings
from tests.test_chat import Scripted
from tests.test_phone_reminders import _obligation
from tests.test_telegram import BOT, CHAT, SECRET, _linked, post, update

TODAY = clock.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _todo(title="Buy a gift"):
    return {"kind": "todo", "ok": True, "title": title, "due_date": TODAY + dt.timedelta(days=3), "due_time": None, "member_id": None, "member_name": None, "note": None}


async def test_a_staged_todo_is_confirmed_once_by_the_member_it_was_shown_to(family):
    staged = await chat_actions.stage(_p(family), _todo())
    assert staged and "gift" in staged["summary"].lower()
    done = await chat_actions.confirm(_p(family), staged["id"])
    assert done["kind"] == "todo" and "to-dos" in done["said"]
    assert await pool().fetchval("SELECT count(*) FROM todos WHERE household_id = $1 AND title = 'Buy a gift'", uuid.UUID(family.household["id"])) == 1
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family), staged["id"])               # once


async def test_another_member_cannot_confirm_it_and_a_cancelled_one_does_nothing(family):
    staged = await chat_actions.stage(_p(family), _todo("Not mine"))
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family, "appa"), staged["id"])
    await chat_actions.cancel(_p(family), staged["id"])
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family), staged["id"])
    assert await pool().fetchval("SELECT count(*) FROM todos WHERE title = 'Not mine'") == 0


async def test_an_expired_suggestion_is_refused(family):
    staged = await chat_actions.stage(_p(family), _todo("Old"))
    await pool().execute("UPDATE pending_actions SET expires_at = NOW() - interval '1 minute' WHERE id = $1", staged["id"])
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family), staged["id"])


async def test_only_a_resolved_ok_proposal_can_be_staged(family):
    assert await chat_actions.stage(_p(family), {"kind": "todo", "ok": False, "why": "x"}) is None
    assert await chat_actions.stage(_p(family), {"kind": "pay_everything", "ok": True}) is None


async def test_a_routine_and_a_decision_are_confirmed_through_the_same_path(family, database):
    s = await chat_actions.stage(_p(family), {"kind": "routine", "ok": True, "instruction": "Anything late?", "weekday": None, "hour": 9, "title": "Anything late?"})
    assert "Routine set" in (await chat_actions.confirm(_p(family), s["id"]))["said"]
    _, oid = await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    d = await chat_actions.stage(_p(family), {"kind": "decide", "ok": True, "obligation_id": oid, "status": "accepted", "title": "Pay the bus fee"})
    assert "calendar" in (await chat_actions.confirm(_p(family), d["id"]))["said"]
    assert await pool().fetchval("SELECT status FROM obligations WHERE id = $1", oid) == "accepted"


async def test_in_telegram_a_question_becomes_a_card_and_a_tap_does_it(family, monkeypatch):
    said = []

    async def send(chat_id, text, **kw):
        said.append((text, kw.get("buttons")))

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(telegram, "answer_callback", noop)
    monkeypatch.setattr(telegram, "edit_message", noop)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    await _linked(family)
    chat.use_model(Scripted({"say": "I can add that to your to-dos.", "proposals": [{"kind": "todo", "title": "Book the dentist", "due_date": (TODAY + dt.timedelta(days=4)).isoformat()}]}))
    r = await post(family, update(text="Remind me to book the dentist?", forwarded=False))
    assert r.json()["answered"] is True and r.json()["cards"] == 1
    buttons = [b for _, b in said if b]
    assert buttons and buttons[0][0][0][1].startswith("act:") and buttons[0][0][0][1].endswith(":y")
    press = {"update_id": 9, "callback_query": {"id": "c", "from": {"id": CHAT, "is_bot": False}, "data": buttons[0][0][0][1],
                                               "message": {"message_id": 4, "chat": {"id": CHAT, "type": "private"}}}}
    assert (await post(family, press)).json()["confirmed"] == "todo"
    assert await pool().fetchval("SELECT count(*) FROM todos WHERE title = 'Book the dentist'") == 1


async def test_decision_cards_have_buttons_in_chat_that_do_what_the_console_buttons_do(family):
    from familyos import cards, decisions
    p = _p(family)
    doc = decisions._document_card({"id": uuid.uuid4(), "artifact_id": uuid.uuid4(), "label": "Driving licence", "holder_name": "Emily", "status": "soon",
                                    "expires_on": TODAY + dt.timedelta(days=30), "days_left": 30}, TODAY)
    renew, renewed = await cards.decision_buttons(p, doc)
    assert (renew["label"], renewed["label"]) == ("Add a to-do", "Renewed")
    await chat_actions.confirm(p, uuid.UUID(renew["id"]))
    assert await pool().fetchval("SELECT count(*) FROM todos WHERE title = 'Renew Emily’s Driving licence'") == 1

    warranty = decisions._warranty_card({"artifact_id": uuid.uuid4(), "product": "Washing machine", "merchant": "Croma", "purchased_on": TODAY,
                                         "return_days": 10, "warranty_months": 24, "said": "2 years"})
    for a in warranty["actions"]:
        if a["key"] == "track":
            a["body"]["artifact_id"] = None                      # no stored invoice in this test
    track, notthis = await cards.decision_buttons(p, warranty)
    assert (await chat_actions.confirm(p, uuid.UUID(track["id"])))["said"].startswith("Tracked")
    assert await pool().fetchval("SELECT count(*) FROM warranties WHERE title = 'Washing machine'") == 1
    await chat_actions.cancel(p, uuid.UUID(notthis["id"]))              # "Not this" is remembered, as the console's is
    assert await pool().fetchval("SELECT count(*) FROM suggestion_dismissals WHERE source_key LIKE 'warranty:%'") == 1

    nudge = decisions._heads_up_card({"key": "busy:person:x:2026-42", "ref": "person:x", "title": "Emily has 4 things", "why": "a, b"})
    (got_it,) = await cards.decision_buttons(p, nudge)
    await chat_actions.confirm(p, uuid.UUID(got_it["id"]))
    assert await pool().fetchval("SELECT count(*) FROM suggestion_dismissals WHERE source_key = 'insight:busy:person:x:2026-42'") == 1


async def test_telegram_setup_walks_a_guardian_through_the_checklist(family, monkeypatch):
    said = []

    async def send(chat_id, text, **kw):
        said.append((text, kw.get("buttons")))

    async def noop(*a, **k):
        return None

    for name in ("answer_callback", "edit_message"):
        monkeypatch.setattr(telegram, name, noop)
    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    await _linked(family)
    r = await post(family, update(text="/setup", forwarded=False))
    assert r.json()["command"] == "setup" and "⬜ Name your home" in said[-1][0]
    press = {"update_id": 11, "callback_query": {"id": "c", "from": {"id": CHAT, "is_bot": False}, "data": "setup:named",
                                                "message": {"message_id": 5, "chat": {"id": CHAT, "type": "private"}}}}
    assert (await post(family, press)).json()["setup"] == "named"
    await post(family, update(text="/setup", forwarded=False))
    assert "✅ Name your home" in said[-1][0]


def _todo_for(member_id, title):
    return {**_todo(title), "member_id": str(member_id)}


async def test_buttons_offered_together_are_answered_together(family):
    group = uuid.uuid4()
    yes = await chat_actions.stage(_p(family), _todo("Pair yes"), group_id=group)
    no = await chat_actions.stage(_p(family), _todo("Pair no"), group_id=group)
    await chat_actions.confirm(_p(family), yes["id"])
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family), no["id"])              # the other button was closed with the first
    assert await pool().fetchval("SELECT count(*) FROM todos WHERE title = 'Pair no'") == 0


async def test_a_refusal_gives_back_the_action_and_its_sibling_but_an_unexpected_failure_does_not(family, monkeypatch):
    group = uuid.uuid4()
    bad = await chat_actions.stage(_p(family), _todo_for(uuid.uuid4(), "Nobody"), group_id=group)   # a member who is not in the household
    other = await chat_actions.stage(_p(family), _todo("Sibling"), group_id=group)
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family), bad["id"])
    row = await pool().fetchrow("SELECT done_at, cancelled_at FROM pending_actions WHERE id = $1", bad["id"])
    assert row["done_at"] is None
    assert await pool().fetchval("SELECT cancelled_at FROM pending_actions WHERE id = $1", other["id"]) is None   # reopened with it
    await chat_actions.confirm(_p(family), other["id"])

    from familyos import todos

    async def boom(*a, **k):
        raise RuntimeError("the database went away after the write")

    monkeypatch.setattr(todos, "add", boom)
    staged = await chat_actions.stage(_p(family), _todo("Half done"))
    with pytest.raises(RuntimeError):
        await chat_actions.confirm(_p(family), staged["id"])
    with pytest.raises(NotFound):
        await chat_actions.confirm(_p(family), staged["id"])          # used up: a tap cannot run it twice
    assert await pool().fetchval("SELECT count(*) FROM audit_events WHERE action = 'chat.action_failed'") == 1


async def test_expired_pending_rows_are_purged_by_the_reminder_sweep(family):
    from familyos import jobs, reminders
    old = await chat_actions.stage(_p(family), _todo("Long gone"))
    fresh = await chat_actions.stage(_p(family), _todo("Still live"))
    await pool().execute("UPDATE pending_actions SET expires_at = NOW() - interval '3 days' WHERE id = $1", old["id"])
    reminders.register()
    job = await reminders.ensure_scheduled()
    await jobs.attach(job["id"])
    assert await pool().fetchval("SELECT count(*) FROM pending_actions WHERE id = $1", old["id"]) == 0
    assert await pool().fetchval("SELECT count(*) FROM pending_actions WHERE id = $1", fresh["id"]) == 1


async def test_ask_proposes_a_rule_switch_and_only_a_guardian_can_confirm_it(family, database):
    hid = uuid.UUID(family.household["id"])
    await pool().execute("UPDATE households SET childrens_notices_shared = FALSE WHERE id = $1", hid)
    # the model's proposal, resolved against what the guardian is given as RULES facts
    facts = await chat.context(_p(family, "amma"), "always share the children's notices")
    assert "childrens_notices_shared = off" in "\n".join(facts.lines)
    out = chat.resolve([{"kind": "rule", "switch": "childrens_notices_shared", "on": True}], facts)
    assert out[0]["ok"] and out[0]["switch_key"] == "childrens_notices_shared" and "Children" in out[0]["title"]
    # not offered: money, where words go, a made-up key, no direction, already in that state
    for bad in ({"switch": "payments_enabled", "on": True}, {"switch": "local_models", "on": True}, {"switch": "nonsense", "on": True},
                {"switch": "childrens_notices_shared", "on": None}, {"switch": "weekly_digest", "on": True}):
        resolved = chat.resolve([{"kind": "rule", **bad}], facts)
        if bad["switch"] == "weekly_digest":
            await pool().execute("UPDATE households SET weekly_digest = TRUE WHERE id = $1", hid)
            facts2 = await chat.context(_p(family, "amma"), "x")
            resolved = chat.resolve([{"kind": "rule", **bad}], facts2)
        assert resolved[0]["ok"] is False and resolved[0]["why"], bad
    # an adult who is not a guardian is given no RULES, so nothing is offered
    nobody = await chat.context(_p(family, "paati"), "share everything")
    assert not nobody.rules and "RULES" not in "\n".join(nobody.lines)
    assert chat.resolve([{"kind": "rule", "switch": "childrens_notices_shared", "on": True}], nobody)[0]["why"] == "only a guardian can change the household's rules"
    # confirming it flips the switch from now on, and writes the activity record
    staged = await chat_actions.stage(_p(family, "amma"), out[0])
    assert staged and "Children" in staged["summary"]
    done = await chat_actions.confirm(_p(family, "amma"), staged["id"])
    assert "Turned on" in done["said"]
    assert await pool().fetchval("SELECT childrens_notices_shared FROM households WHERE id = $1", hid) is True
    assert await pool().fetchval("SELECT count(*) FROM audit_events WHERE household_id = $1 AND action = 'household.rules_set'", hid) >= 1


async def test_a_staged_rule_for_a_forbidden_switch_is_refused_at_confirm(family):
    from familyos.identity import Invalid
    s = await chat_actions.stage(_p(family, "amma"), {"kind": "rule", "ok": True, "switch_key": "payments_enabled", "on": True, "title": "Payments"})
    with pytest.raises(Invalid):
        await chat_actions.confirm(_p(family, "amma"), s["id"])
    assert await pool().fetchval("SELECT payments_enabled FROM households WHERE id = $1", uuid.UUID(family.household["id"])) is False
