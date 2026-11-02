"""The morning message: once a day, only when something needs the member, inside their budget."""
import datetime as dt
import uuid

import pytest

from familyos import morning, notify
from familyos.db import pool
from familyos.intake import telegram
from familyos.settings import settings
from tests.test_phone_reminders import _obligation
from tests.test_telegram import BOT, SECRET, _linked

TODAY = dt.date(2026, 10, 12)
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _at(hour, minute=0, day=TODAY):
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=IST).astimezone(dt.UTC)


@pytest.fixture
def wire(monkeypatch):
    out = {"telegram": [], "mail": []}

    async def send(chat_id, text, **kw):
        out["telegram"].append((chat_id, text, kw.get("buttons")))

    async def member(member_id, subject, body, buttons=None):
        out["mail"].append((member_id, subject, body))
        return "email"

    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(notify, "member", member)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    return out


async def _only_amma(family):
    """The other adults off, so the sweep's counts are about one member."""
    await pool().execute("UPDATE members SET morning_hour = NULL WHERE household_id = $1 AND id <> $2", uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]))


async def test_it_sends_the_cards_with_live_buttons_once_a_day(family, database, wire):
    await _linked(family)
    await _only_amma(family)
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    assert (await morning.sweep(_at(7, 30)))["sent"] == 0                        # before 8
    out = await morning.sweep(_at(8, 15))
    assert out["sent"] == 1
    head = wire["telegram"][0][1]
    assert head.startswith("Good morning") and "waiting for your yes" in head
    action = next(t for t in wire["telegram"] if t[2])
    assert "Pay the bus fee" in action[1] and action[2][0][0][1].startswith("act:")
    assert (await morning.sweep(_at(9, 0)))["sent"] == 0                         # once for the day
    assert await pool().fetchval("SELECT count(*) FROM proactive_log WHERE kind = 'morning'") == 1
    # the buttons are still good in the evening
    left = await pool().fetchval("SELECT min(expires_at) - NOW() FROM pending_actions")
    assert left > dt.timedelta(hours=12)


async def test_it_says_nothing_on_a_morning_when_nothing_needs_the_member(family, wire):
    await _linked(family)
    await _only_amma(family)
    # a quiet household has chips only: no action and no text card
    out = await morning.sweep(_at(8, 15))
    assert out["silent"] == 1 and wire["telegram"] == []


async def test_quiet_hours_hold_it_until_they_end_and_it_can_be_switched_off(family, database, wire):
    await _linked(family)
    await _only_amma(family)
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    await pool().execute("UPDATE members SET morning_hour = 6 WHERE id = $1", uuid.UUID(family.amma["id"]))
    assert (await morning.sweep(_at(6, 30)))["waited"] == 1 and wire["telegram"] == []         # 7 is when quiet hours end
    assert (await morning.sweep(_at(7, 10)))["sent"] == 1
    off = await family.client.put("/v1/me/interruptions", headers=family.h("amma"), json={"morning_off": True})
    assert off.status_code == 200 and off.json()["morning_hour"] is None
    back = await family.client.put("/v1/me/interruptions", headers=family.h("amma"), json={"morning_hour": 9})
    assert back.json()["morning_hour"] == 9


async def test_without_telegram_the_words_go_by_mail_with_no_buttons(family, database, wire):
    await _only_amma(family)
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    assert (await morning.sweep(_at(8, 30)))["sent"] == 1
    assert wire["telegram"] == [] and "Pay the bus fee" in wire["mail"][0][2]


async def test_a_child_gets_no_morning_message_and_the_daily_cap_applies(family, database, wire):
    await _linked(family)
    await _only_amma(family)
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    await pool().execute("UPDATE members SET proactive_daily_cap = 0 WHERE id = $1", uuid.UUID(family.amma["id"]))
    await pool().execute("UPDATE members SET morning_hour = 8 WHERE id = $1", uuid.UUID(family.older["id"]))     # even set, a child is never swept
    out = await morning.sweep(_at(8, 30))
    assert out["waited"] == 1 and out["sent"] == 0 and wire["telegram"] == [] and wire["mail"] == []
