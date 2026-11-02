"""today, needs and help in a member's own Telegram chat, and the Accept and Not this buttons."""
import datetime as dt

from familyos import clock
from familyos.db import pool
from familyos.intake import telegram
from familyos.settings import settings
from tests.test_phone_reminders import _obligation
from tests.test_telegram import BOT, CHAT, SECRET, _linked, post, update

TODAY = clock.today()


async def _setup(monkeypatch):
    said, answered = [], []

    async def send(chat_id, text, **kw):
        said.append((chat_id, text, kw.get("buttons")))

    async def answer(callback_id, text, **kw):
        answered.append(text)

    async def edit(chat_id, message_id, text, **kw):
        answered.append("edited: " + text)

    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(telegram, "answer_callback", answer)
    monkeypatch.setattr(telegram, "edit_message", edit)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    return said, answered


def _cmd(text, sender=CHAT):
    return update(sender_id=sender, text=text, forwarded=False)


async def test_help_and_today_answer_in_the_members_own_chat(family, database, monkeypatch):
    said, _ = await _setup(monkeypatch)
    await _linked(family)
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=1), status="proposed")
    assert (await post(family, _cmd("help"))).json()["command"] == "help"
    assert "needs:" in said[-1][1]
    assert (await post(family, _cmd("/today"))).json()["command"] == "today"
    assert "bus fee" in said[-1][1].lower()


async def test_needs_offers_accept_and_not_this_and_a_press_decides_as_that_member(family, database, monkeypatch):
    said, answered = await _setup(monkeypatch)
    await _linked(family)
    artifact_id, oid = await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=1), status="proposed")
    assert (await post(family, _cmd("needs"))).json()["command"] == "needs"
    buttons = [b for _, _, b in said if b]
    assert buttons and buttons[0][0][0][1] == f"ob:{oid}:y"
    press = {"update_id": 7, "callback_query": {"id": "c", "from": {"id": CHAT, "is_bot": False}, "data": f"ob:{oid}:y",
                                               "message": {"message_id": 3, "chat": {"id": CHAT, "type": "private"}}}}
    assert (await post(family, press)).json().get("decided") == "y"
    assert await pool().fetchval("SELECT status FROM obligations WHERE id = $1", oid) == "accepted"


async def test_commands_are_for_a_linked_member_only(family, monkeypatch):
    await _setup(monkeypatch)
    r = await post(family, _cmd("today", sender=999))
    assert r.json()["refused"] == 1
