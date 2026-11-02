"""When a request could mean more than one thing, Ask asks back with choices and proposes nothing until one is picked."""
import uuid

import pytest

from familyos import chat, chat_actions, clock
from familyos.db import pool
from familyos.identity import NotFound, Principal
from familyos.intake import telegram
from familyos.settings import settings
from tests.test_chat import Scripted
from tests.test_telegram import BOT, CHAT, SECRET, _linked, post, update

TODAY = clock.today()
ASK = {"question": "Which prescription do you mean?", "choices": ["The August one", "The September one"]}


def test_a_clarifying_question_is_trimmed_and_replaces_any_proposal():
    answer = {"say": "I can move one of them.", "proposals": [{"kind": "todo", "title": "x"}],
              "clarify": {"question": "  Which   prescription do you mean?  ", "choices": ["The August one", "the august one", "The September one", "", "Third", "Fourth", "Fifth"]}}
    out = chat._finish(answer, chat.Facts(), "move the prescription")
    assert out["proposals"] == []                                              # unsure means no action
    assert out["clarify"] == {"question": "Which prescription do you mean?", "choices": ["The August one", "The September one", "Third", "Fourth"]}
    assert "Which prescription do you mean?" in out["say"]                     # the question is always shown


def test_fewer_than_two_choices_or_no_question_is_not_a_clarification():
    for bad in ({"question": "Which?", "choices": ["only one"]}, {"question": "", "choices": ["a", "b"]}, None, "text", {}):
        out = chat._finish({"say": "Done.", "proposals": [], "clarify": bad}, chat.Facts(), "q")
        assert out["clarify"] is None and out["say"] == "Done."


def test_the_strict_schema_lets_the_model_ask_back_and_propose_a_routine():
    props = chat.OUTPUT_SCHEMA["properties"]
    assert "clarify" in props and "clarify" in chat.OUTPUT_SCHEMA["required"]
    item = props["proposals"]["items"]
    assert "routine" in item["properties"]["kind"]["enum"]
    assert set(item["properties"]) <= set(item["required"])                    # strict mode needs every property required
    assert {"instruction", "weekday", "hour", "bundle"} <= set(item["properties"])


async def test_the_turn_carries_the_question_to_the_client(family):
    chat.use_model(Scripted({"say": "More than one fits.", "proposals": [], "clarify": ASK}))
    try:
        m = family.amma
        turn = await chat.turn(Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"]),
                               "move the prescription to Lily")
        assert turn["clarify"]["choices"] == ASK["choices"] and turn["proposals"] == []
    finally:
        chat.use_model(chat.RefusingModel())


async def test_in_telegram_the_choices_are_buttons_and_a_pick_asks_that_text(family, monkeypatch):
    said, answers = [], []

    async def send(chat_id, text, **kw):
        said.append((text, kw.get("buttons")))

    async def answer(callback_id, text, **kw):
        answers.append(text)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(telegram, "answer_callback", answer)
    monkeypatch.setattr(telegram, "edit_message", noop)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    await _linked(family)
    first = Scripted({"say": "More than one fits.", "proposals": [], "clarify": ASK})
    chat.use_model(first)
    try:
        r = await post(family, update(text="Move the prescription to Lily?", forwarded=False))
        assert r.json()["answered"] is True
        rows = [b for _, b in said if b][-1]
        assert [row[0][0] for row in rows] == ASK["choices"] and all(row[0][1].startswith("pick:") for row in rows)
        chat.use_model(Scripted({"say": "Moved the August one.", "proposals": [], "clarify": None}))
        press = {"update_id": 11, "callback_query": {"id": "c", "from": {"id": CHAT, "is_bot": False}, "data": rows[0][0][1],
                                                    "message": {"message_id": 5, "chat": {"id": CHAT, "type": "private"}}}}
        assert (await post(family, press)).json().get("picked") is True
        assert said[-1][0].startswith("Moved the August one")                    # the pick became the next question
        again = await post(family, press)                                        # a choice is used once
        assert again.json()["refused"] == 1
    finally:
        chat.use_model(chat.RefusingModel())


async def test_a_choice_cannot_be_taken_by_another_member_or_as_an_action(family):
    m = family.amma
    p = Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])
    other = Principal(member_id=uuid.UUID(family.appa["id"]), household_id=p.household_id, role="guardian", display_name="Appa")
    cid = await chat_actions.stage_choice(p, "The August one")
    with pytest.raises(NotFound):
        await chat_actions.take_choice(other, cid)
    assert await chat_actions.take_choice(p, cid) == "The August one"
    cid2 = await chat_actions.stage_choice(p, "x")
    with pytest.raises(NotFound):
        await chat_actions.confirm(p, cid2)                                      # a choice is not an action
    assert await pool().fetchval("SELECT count(*) FROM pending_actions WHERE kind = 'ask' AND done_at IS NOT NULL") >= 1
