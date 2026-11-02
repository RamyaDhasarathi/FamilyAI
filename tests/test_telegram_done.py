"""Done under a Telegram reminder: the button on the message marks the notice handled, as the member who pressed it."""
import datetime as dt

from familyos import clock
from familyos.db import pool
from familyos.intake import telegram
from familyos.settings import settings
from tests.test_phone_reminders import _obligation
from tests.test_telegram import BOT, CHAT, SECRET, _linked, post

TODAY = clock.today()


def _press(data, sender=CHAT, chat=CHAT):
    return {"update_id": 1, "callback_query": {"id": "cb1", "from": {"id": sender, "is_bot": False}, "data": data,
                                              "message": {"message_id": 77, "chat": {"id": chat, "type": "private"}}}}


async def _capture(monkeypatch):
    calls = []

    async def answer(callback_id, text, **kw):
        calls.append(("answer", text))

    async def edit(chat_id, message_id, text, **kw):
        calls.append(("edit", text))

    monkeypatch.setattr(telegram, "answer_callback", answer)
    monkeypatch.setattr(telegram, "edit_message", edit)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    return calls


async def test_the_reminder_carries_a_done_button_for_its_obligation():
    sent = []

    async def post_(chat_id, text, markup=None):
        sent.append(markup)

    await telegram.send_message(1, "hi", bot_token="t", api_base="x", post=post_, buttons=[[("Done", "done:abc")]])
    assert sent == [{"inline_keyboard": [[{"text": "Done", "callback_data": "done:abc"}]]}]


async def test_pressing_done_marks_the_notice_handled_and_says_so(family, database, monkeypatch):
    calls = await _capture(monkeypatch)
    await _linked(family)
    artifact_id, oid = await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=1))
    r = await post(family, _press(f"done:{oid}"))
    assert r.status_code == 202 and r.json().get("handled") is True
    assert await pool().fetchval("SELECT handled_at IS NOT NULL FROM input_artifacts WHERE id = $1", artifact_id)
    assert ("answer", "Marked done.") in calls and any(k == "edit" for k, _ in calls)


async def test_a_press_from_an_account_nobody_linked_does_nothing(family, database, monkeypatch):
    await _capture(monkeypatch)
    artifact_id, oid = await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=1))
    r = await post(family, _press(f"done:{oid}", sender=999, chat=999))
    assert r.json()["refused"] == 1
    assert not await pool().fetchval("SELECT handled_at IS NOT NULL FROM input_artifacts WHERE id = $1", artifact_id)


async def test_a_member_cannot_mark_done_what_they_cannot_see(family, database, monkeypatch):
    calls = await _capture(monkeypatch)
    await _linked(family, "appa", chat_id=CHAT)
    artifact_id, oid = await _obligation(family, database, "Amma's private thing", TODAY + dt.timedelta(days=1), visibility="private", who="amma")
    r = await post(family, _press(f"done:{oid}"))
    assert r.json()["refused"] == 1
    assert not await pool().fetchval("SELECT handled_at IS NOT NULL FROM input_artifacts WHERE id = $1", artifact_id)
    assert ("answer", "I could not mark that done.") in calls


async def test_an_unknown_button_is_refused_and_a_bad_id_does_not_crash(family, monkeypatch):
    await _capture(monkeypatch)
    await _linked(family)
    assert (await post(family, _press("snooze:1"))).json()["reason"] == "unknown_button"
    assert (await post(family, _press("done:not-a-uuid"))).json()["reason"] == "unknown_button"
