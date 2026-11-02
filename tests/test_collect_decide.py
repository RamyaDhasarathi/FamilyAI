"""The decision layer (familyos/collect/decide.py, ported from the collector app's decisionLayer.js, decided 30 Oct 2026):
for each phone app switched on, which methods may collect from it, in a fixed priority. Qwen3.5 proposes; every status
comes from the registry -- what is really configured and collected for that member -- never from the model. Email is
checked against real mail. Without the model the registry alone decides. Kept in the local cache only."""
import asyncio

import pytest

from familyos.collect import decide, store
from familyos.intake import google
from familyos.settings import settings

ORDER = ["api", "mcp", "email", "phone_data", "mobile_use", "browser_use"]


@pytest.fixture(autouse=True)
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(decide, "_running", {})


def model_says(monkeypatch, *candidates):
    asked = []

    async def fake(body):
        asked.append(body)
        return list(candidates)
    monkeypatch.setattr(decide, "_ask_model", fake)
    return asked


def no_model(monkeypatch):
    async def down(body):
        raise ConnectionError("model server is not running")
    monkeypatch.setattr(decide, "_ask_model", down)


async def settle():
    await asyncio.gather(*decide._running.values())


def by_method(methods):
    return {m["method"]: m for m in methods}


def test_apps_are_put_in_a_category_by_package_then_name():
    assert decide.classify("in.swiggy.android") == "Food and Grocery"
    assert decide.classify("com.example.neighbourhoodbank", "Neighbourhood Bank") == "Bank"
    assert decide.classify("com.example.torch", "Torch") == "Other"


async def test_without_the_model_the_registry_alone_decides_in_the_fixed_order(monkeypatch):
    no_model(monkeypatch)
    found = await decide.analyze("amma@example.com", {"package": "in.swiggy.android", "label": "Swiggy", "collect": True})
    assert found["model"] is None and found["category"] == "Food and Grocery"
    assert [m["method"] for m in found["methods"]] == ORDER
    assert [m["priority"] for m in found["methods"]] == [1, 2, 3, 4, 5, 6]
    status = {m["method"]: m["status"] for m in found["methods"]}
    assert status == {"api": "unsupported", "mcp": "unsupported", "email": "requires_connection",
                      "phone_data": "requires_permission", "mobile_use": "available", "browser_use": "requires_connection"}
    assert "Swiggy" in by_method(found["methods"])["browser_use"]["reason"]


async def test_the_model_cannot_set_a_status_invent_a_method_or_a_data_type(monkeypatch):
    store.set_apps("amma@example.com", [{"package": "in.swiggy.android", "label": "Swiggy", "collect": True}])
    store.upsert("notifications", "amma@example.com", [
        {"id": "n1", "package": "in.swiggy.android", "app_label": "Swiggy", "title": "Order", "text": "On the way", "posted_at": "2026-10-30T10:00:00+00:00"}])
    asked = model_says(monkeypatch,
                       {"method": "api", "supported_data_types": ["food.order_history"], "reason": "Swiggy has a partner API."},
                       {"method": "teleport", "reason": "x"},
                       {"method": "phone_data", "supported_data_types": ["bank.balance", "app.notifications"],
                        "reason": "Order updates arrive as <b>notifications</b>.\n```rm -rf```"})
    found = await decide.analyze("amma@example.com", {"package": "in.swiggy.android", "label": "Swiggy", "collect": True})
    assert found["model"] == "qwen3.5"
    assert asked[0]["app"] == {"package_name": "in.swiggy.android", "display_name": "Swiggy", "category": "Food and Grocery"}
    m = by_method(found["methods"])
    assert set(m) == set(ORDER)
    assert m["api"]["status"] == "unsupported" and m["api"]["reason"] == "No service API is configured for this app."
    assert m["phone_data"]["status"] == "available"
    assert m["phone_data"]["supported_data_types"] == ["app.notifications"]
    assert m["phone_data"]["reason"] == "Order updates arrive as bnotifications/b."


async def test_email_is_available_only_with_real_mail_from_the_senders(monkeypatch):
    store.keep_google("amma@example.com", "1//refresh", google.SIGN_IN_SCOPES + (google.GMAIL_SCOPE,))
    store.upsert("gmail", "amma@example.com", [
        {"id": "g1", "thread_id": "t", "sender": "Swiggy <noreply@swiggy.in>", "recipients": "amma@example.com",
         "subject": "Your order", "snippet": "", "sent_at": "2026-10-29T10:00:00+00:00", "labels": "[]"}])
    asked_gmail = []

    async def gmail(email, senders, transport=None):
        asked_gmail.append(senders)
        return 0
    monkeypatch.setattr(decide, "_gmail_count", gmail)
    model_says(monkeypatch, {"method": "email", "email_senders": ["@zomato.com", "not a domain"]})

    swiggy = by_method((await decide.analyze("amma@example.com", {"package": "in.swiggy.android", "label": "Swiggy", "collect": True}))["methods"])
    assert swiggy["email"]["status"] == "available"                 # in the local cache: Gmail is not asked
    assert asked_gmail == []

    zomato = by_method((await decide.analyze("amma@example.com", {"package": "com.application.zomato", "label": "Zomato", "collect": True}))["methods"])
    assert zomato["email"]["status"] == "unverified"
    assert zomato["email"]["reason"] == "No emails from zomato.com in the last 90 days."
    assert asked_gmail == [["zomato.com"]]


async def test_switching_an_app_on_decides_for_it_and_each_member_sees_only_their_own(family, monkeypatch):
    no_model(monkeypatch)
    r = await family.client.put("/v1/collect/device/apps", headers=family.h("amma"), json={"apps": [
        {"package": "com.flipkart.android", "label": "Flipkart", "collect": True},
        {"package": "com.example.torch", "label": "Torch", "collect": False},
    ]})
    assert r.status_code == 200 and r.json()["deciding"] == 1
    await settle()
    got = (await family.client.get("/v1/collect/decide", headers=family.h("amma"))).json()
    assert [(a["package"], a["status"], a["category"]) for a in got["apps"]] == [("com.flipkart.android", "completed", "Shopping")]
    assert [m["method"] for m in got["apps"][0]["methods"]] == ORDER
    # The same list again: nothing new to decide.
    r = await family.client.put("/v1/collect/device/apps", headers=family.h("amma"), json={"apps": [
        {"package": "com.flipkart.android", "label": "Flipkart", "collect": True}]})
    assert r.json()["deciding"] == 0
    assert (await family.client.get("/v1/collect/decide", headers=family.h("appa"))).json()["apps"] == []
    assert (await family.client.get("/v1/collect/decide")).status_code == 401


async def test_deciding_again_for_one_app_or_all(family, monkeypatch):
    no_model(monkeypatch)
    await family.client.put("/v1/collect/device/apps", headers=family.h("amma"), json={"apps": [
        {"package": "com.flipkart.android", "label": "Flipkart", "collect": True}]})
    await settle()
    r = await family.client.post("/v1/collect/decide/com.flipkart.android", headers=family.h("amma"))
    assert r.status_code == 202 and r.json() == {"started": True}
    await settle()
    assert (await family.client.post("/v1/collect/decide", headers=family.h("amma"))).json() == {"started": 1}
    await settle()
    assert (await family.client.post("/v1/collect/decide/com.not.there", headers=family.h("amma"))).status_code == 404


async def test_a_decision_that_breaks_is_kept_as_failed(monkeypatch):
    store.set_apps("amma@example.com", [{"package": "com.flipkart.android", "label": "Flipkart", "collect": True}])

    def broken(*a, **k):
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(decide, "capabilities", broken)
    assert decide.start("amma@example.com", "com.flipkart.android") is True
    await settle()
    [app] = decide.results("amma@example.com")
    assert app["status"] == "failed" and app["error"] == "registry unreadable"
