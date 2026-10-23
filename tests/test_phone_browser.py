"""The phone as the errand's browser: questions go to the app, answers come
back by id, a phone that stops answering ends the run as needs_you, and an
errand bound to the phone is not picked up by the job."""
import asyncio
import uuid

import pytest

from familyos.execution import phone


class ScriptedPhone:
    """Answers like the app would, from a tiny page."""

    def __init__(self, driver_ref):
        self.driver_ref = driver_ref
        self.seen = []
        self.page = "Login  Hi, Amma  AC Service & Repair  Add  Add"

    async def send(self, message):
        self.seen.append(message)
        op = message["op"]
        result = {"goto": None, "url": "https://www.urbancompany.com/bengaluru", "text": self.page,
                  "screenshot": "/9j/4AAQ", "buttons": [{"index": 0, "near": "AC service ₹499"}, {"index": 1, "near": "AC repair ₹899"}],
                  "links": [{"text": "AC Service & Repair", "href": "https://www.urbancompany.com/bengaluru-ac"}, {"text": "bad", "href": "http://x"}],
                  "press": True, "click_text": False, "close": None}[op]
        # The app answers asynchronously, by id.
        asyncio.get_running_loop().call_soon(self.driver_ref[0].answer, {"id": message["id"], "result": result})


async def test_questions_go_to_the_phone_and_answers_come_back_by_id():
    ref = []
    scripted = ScriptedPhone(ref)
    driver = phone.attach(uuid.uuid4(), scripted.send)
    ref.append(driver)
    await driver.goto("https://www.urbancompany.com/")
    assert await driver.url() == "https://www.urbancompany.com/bengaluru"
    assert "Hi, Amma" in await driver.text()
    assert isinstance(await driver.screenshot(), bytes)
    buttons = await driver.buttons("Add")
    assert [(b["index"], b["price"]) for b in buttons] == [(0, 499.0), (1, 899.0)]
    assert await driver.links() == [{"text": "AC Service & Repair", "href": "https://www.urbancompany.com/bengaluru-ac"}]
    assert await driver.press("Add", 1) is True and await driver.click_text("View cart") is False
    assert [m["op"] for m in scripted.seen][:3] == ["goto", "url", "text"]
    assert phone.connected(driver.errand_id) is driver
    phone.detach(driver.errand_id)
    assert phone.connected(driver.errand_id) is None


async def test_a_phone_that_stops_answering_ends_the_question(monkeypatch):
    monkeypatch.setattr(phone, "ANSWER_SECONDS", 0.05)

    async def silent(message):
        pass

    driver = phone.attach(uuid.uuid4(), silent)
    with pytest.raises(phone.PhoneGone):
        await driver.text()
    driver.disconnect()
    with pytest.raises(phone.PhoneGone):
        await driver.url()


async def test_a_second_phone_replaces_the_first():
    eid = uuid.uuid4()

    async def send(message):
        pass

    first = phone.attach(eid, send)
    second = phone.attach(eid, send)
    assert first.gone and phone.connected(eid) is second
    phone.detach(eid, first)            # detaching the old one does not drop the new one
    assert phone.connected(eid) is second
    phone.detach(eid)
