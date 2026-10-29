"""Purchases: nothing is bought unless payments are on, within the limits, and a guardian approves that one purchase."""
import decimal
import uuid

from familyos import payments
from familyos.db import pool
from familyos.settings import settings


class Fake:
    name = "fake"

    def __init__(self):
        self.made, self.revoked = [], []

    async def create_allowance(self, **kw):
        self.made.append(kw)
        return {"ref": "oi_" + str(len(self.made)), "state": {"status": "active"}}

    async def revoke(self, ref, **kw):
        self.revoked.append(ref)

    async def get_allowance(self, ref, **kw):
        return {'orderIntentId': ref, 'rails': [{'rail': 'agentic-token', 'status': 'active'}]}

    async def register_card(self, **kw):
        self.registered = getattr(self, 'registered', []) + [kw['payment_method_id']]


async def _on(family, monkeypatch, card=True):
    fake = Fake()
    payments.use_provider(fake)
    monkeypatch.setattr(settings, "payments_provider", "fake")
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"payments_enabled": True})
    assert r.status_code == 200, r.text
    if card:
        await pool().execute("UPDATE members SET payment_method_id = 'pm_test' WHERE id = $1", uuid.UUID(family.amma["id"]))
    return fake


def _body(amount=500, **kw):
    return {"title": "Lunch order", "merchant_name": "Swiggy Instamart", "merchant_url": "https://www.swiggy.com/instamart",
            "amount": amount, "currency": "INR", **kw}


async def _currency(family):
    return await pool().fetchval("SELECT currency FROM households WHERE id = $1", uuid.UUID(family.household["id"]))


def teardown_function(_fn):
    payments.use_provider(None)


async def test_nothing_can_be_asked_for_while_payments_are_off(family):
    r = await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())
    assert r.status_code == 403 and "off" in r.text


async def test_a_purchase_is_asked_then_a_guardian_approves_it_and_an_allowance_is_made(family, monkeypatch):
    fake = await _on(family, monkeypatch)
    assert (await _currency(family)).strip() == "INR"
    r = await family.client.post("/v1/purchases", headers=family.h("paati"), json=_body(500))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["status"] == "requested" and fake.made == []
    assert (await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("paati"), json={"approve": True})).status_code == 403
    assert fake.made == []
    done = await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "ready" and done.json()["provider"] == "fake"
    assert len(fake.made) == 1 and fake.made[0]["payment_method_id"] == "pm_test" and fake.made[0]["amount"] == decimal.Decimal("500.00")
    assert "pm_test" not in str(done.json()) and "payment_method" not in str(done.json())


async def test_limits_stop_a_purchase_before_anyone_is_asked(family, monkeypatch):
    await _on(family, monkeypatch)
    assert (await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"payment_limit": 1000, "payment_month_limit": 1500})).status_code == 200
    assert (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body(1200))).status_code == 403
    first = await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body(900))
    assert first.status_code == 201
    assert (await family.client.post(f"/v1/purchases/{first.json()['id']}/decision", headers=family.h("amma"), json={"approve": True})).status_code == 200
    again = await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body(900))
    assert again.status_code == 403 and "month" in again.text


async def test_declined_and_cancelled_purchases_make_no_allowance_and_cancel_revokes_one(family, monkeypatch):
    fake = await _on(family, monkeypatch)
    a = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    assert (await family.client.post(f"/v1/purchases/{a}/decision", headers=family.h("amma"), json={"approve": False})).json()["status"] == "declined"
    assert fake.made == []
    b = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    await family.client.post(f"/v1/purchases/{b}/decision", headers=family.h("amma"), json={"approve": True})
    c = await family.client.delete(f"/v1/purchases/{b}", headers=family.h("amma"))
    assert c.json()["status"] == "cancelled" and fake.revoked == ["oi_1"]
    assert (await family.client.post(f"/v1/purchases/{b}/decision", headers=family.h("amma"), json={"approve": True})).status_code == 403


async def test_without_a_saved_card_approval_waits_and_says_so(family, monkeypatch):
    fake = await _on(family, monkeypatch, card=False)
    pid = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    r = await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert r.json()["status"] == "approved" and "save a card" in r.json()["note"] and fake.made == []


async def test_a_member_sees_only_their_own_requests_and_a_provider_error_is_said_in_words(family, monkeypatch):
    fake = await _on(family, monkeypatch)

    async def boom(**kw):
        raise RuntimeError("secret detail")

    fake.create_allowance = boom
    pid = (await family.client.post("/v1/purchases", headers=family.h("paati"), json=_body())).json()["id"]
    await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())
    assert len((await family.client.get("/v1/purchases", headers=family.h("paati"))).json()) == 1
    assert len((await family.client.get("/v1/purchases", headers=family.h("amma"))).json()) == 2
    done = await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert done.json()["status"] == "failed" and "secret detail" not in done.json()["note"]


async def test_a_provider_that_needs_the_cardholders_browser_leaves_the_purchase_approved_and_says_so(family, monkeypatch):
    fake = await _on(family, monkeypatch)

    async def browser_only(**kw):
        raise payments.NeedsCardholder("x")

    fake.create_allowance = browser_only
    pid = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    r = await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert r.json()["status"] == "approved" and "cardholder's own browser" in r.json()["note"]


async def test_a_purchase_needs_the_merchants_address(family, monkeypatch):
    await _on(family, monkeypatch)
    body = _body()
    del body["merchant_url"]
    assert (await family.client.post("/v1/purchases", headers=family.h("amma"), json=body)).status_code == 422


async def test_saving_a_card_registers_it_with_the_provider_and_the_merchant_country_defaults_to_the_households(family, monkeypatch):
    fake = await _on(family, monkeypatch, card=False)
    r = await family.client.put("/v1/payments/card", headers=family.h("amma"), json={"payment_method_id": "pm_new"})
    assert r.status_code == 200 and r.json()["has_card"] is True and fake.registered == ["pm_new"]
    pid = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert fake.made[0]["merchant_country"] == "IN"


async def test_the_providers_own_words_are_kept_when_it_refuses(family, monkeypatch):
    fake = await _on(family, monkeypatch)

    async def refuse(**kw):
        raise payments.ProviderRefused("merchant.countryCode: Invalid input")

    fake.create_allowance = refuse
    pid = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    r = await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert r.json()["status"] == "failed" and "merchant.countryCode" in r.json()["note"]


async def test_refresh_keeps_the_providers_latest_record_of_the_allowance(family, monkeypatch):
    await _on(family, monkeypatch)
    pid = (await family.client.post("/v1/purchases", headers=family.h("amma"), json=_body())).json()["id"]
    await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    r = await family.client.post(f"/v1/purchases/{pid}/refresh", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["provider_state"]["order_intent"]["rails"][0]["status"] == "active"
    assert (await family.client.post(f"/v1/purchases/{pid}/refresh", headers=family.h("paati"))).status_code == 403


async def test_a_guardian_approves_or_declines_from_telegram_and_a_plain_adult_cannot(family, monkeypatch):
    from familyos.intake import telegram
    from tests.test_telegram import BOT, CHAT, SECRET, _linked, post
    fake = await _on(family, monkeypatch)
    sent, answers = [], []

    async def send(chat_id, text, **kw):
        sent.append((chat_id, kw.get("buttons")))

    async def answer(callback_id, text, **kw):
        answers.append(text)

    async def edit(chat_id, message_id, text, **kw):
        pass

    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(telegram, "answer_callback", answer)
    monkeypatch.setattr(telegram, "edit_message", edit)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    await _linked(family, "amma", chat_id=CHAT)
    await _linked(family, "paati", chat_id=CHAT + 1)
    pid = (await family.client.post("/v1/purchases", headers=family.h("paati"), json=_body(250))).json()["id"]
    buttons = [b for _, b in sent if b]
    assert buttons and buttons[0][0][0][1] == f"buy:{pid}:y"        # the guardians were sent Approve and Decline

    def press(data, sender):
        return {"update_id": 5, "callback_query": {"id": "c1", "from": {"id": sender, "is_bot": False}, "data": data,
                                                  "message": {"message_id": 9, "chat": {"id": sender, "type": "private"}}}}
    nope = await post(family, press(f"buy:{pid}:y", CHAT + 1))      # Paati is not a guardian
    assert nope.json()["refused"] == 1 and fake.made == []
    yes = await post(family, press(f"buy:{pid}:y", CHAT))
    assert yes.json().get("decided") in ("ready", "approved") and (await family.client.get("/v1/purchases", headers=family.h("amma"))).json()[0]["status"] in ("ready", "approved")
