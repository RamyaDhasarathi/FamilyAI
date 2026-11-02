"""What the collecting layer adds to what the phone sends (decided 2 Nov 2026, ported from the collector app): the one-time
code pulled out of a message (otp.py, from otp.js), Qwen's category and summary for each SMS and notification
(categorize.py, from categorize.js + deviceDataWorker.js) and a place name for a location (geocode.py, from geocode.js).
Driven here by a stand-in model server and a stand-in OpenStreetMap."""
import pytest

from familyos.collect import categorize, device, geocode, store
from familyos.collect.otp import extract_otp
from familyos.settings import settings

EMAIL = "amma@example.com"


@pytest.fixture(autouse=True)
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    monkeypatch.setattr(categorize, "start", lambda email: False)
    monkeypatch.setattr(geocode, "start", lambda email: False)
    monkeypatch.setattr(geocode.asyncio, "sleep", _no_wait)


async def _no_wait(_):
    return None


@pytest.mark.parametrize("body, code", [
    ("123456 is your OTP to log in. Do not share it.", "123456"),
    ("Your verification code is 4821", "4821"),
    ("Use 492 013 as your one-time password for Amazon", "492013"),
    ("OTP 0042 17 for txn of Rs 1,299 at Swiggy", "004217"),          # leading zeros kept; the amount is not the code
    ("Your code: 12-34-56. Valid till 2026.", "123456"),                # a year is never the code
    ("Rs 2,500 debited from a/c 123456 on 30 Oct", None),               # no OTP word: never guessed
    ("Order #45821 shipped, track with code ABC", None),                # an order number after '#' is not a code
    ("", None),
])
def test_a_code_is_pulled_out_conservatively_as_the_collector_app_does(body, code):
    assert extract_otp(body) == code


def test_a_notification_carrying_a_code_keeps_it_too(monkeypatch):
    store.set_apps(EMAIL, [{"package": "com.google.android.apps.messaging", "label": "Messages", "collect": True}])
    out = device.keep("notifications", EMAIL, [{"package": "com.google.android.apps.messaging", "title": "AX-ICICIB",
                                                "text": "Your OTP is 778899 for login", "postTime": 1761800000000}])
    assert out == {"kept": 1, "dropped": 0}
    assert store.items("notifications", EMAIL)[0]["otp"] == "778899"


async def test_qwen_sorts_each_sms_and_notification_and_never_echoes_a_code(monkeypatch):
    device.keep("sms", EMAIL, [
        {"id": "1", "sender": "VM-HDFCBK", "body": "Rs 2,500 debited at BigBasket from a/c XX12", "date": 1761800000000},
        {"id": "2", "sender": "AD-SWIGGY", "body": "123456 is your OTP", "date": 1761800100000},
        {"id": "3", "sender": "Mom", "body": "Call me", "date": 1761800200000}])
    asked = []

    async def fake(items):
        asked.append(items)
        out = {"1": {"category": "bank_debit", "summary": "Rs 2,500 debited at BigBasket",
                     "extracted": {"amount": "2500", "merchant": "BigBasket", "account": "XX12"}},
               "2": {"category": "otp", "summary": "Swiggy login code 123456"}}
        return [{"id": i["id"], **out[i["id"]]} for i in items if i["id"] in out]       # "3" not answered: a try is counted
    monkeypatch.setattr(categorize, "_ask", fake)
    assert await categorize.run(EMAIL) == 2
    assert len(asked[0]) == 3 and {i["kind"] for i in asked[0]} == {"sms"}
    rows = {r["id"]: r for r in store.items("sms", EMAIL)}
    assert rows["1"]["category"] == "bank_debit" and '"merchant": "BigBasket"' in rows["1"]["extracted"]
    assert rows["2"]["summary"] == "Swiggy login code ••••" and rows["2"]["otp"] == "123456"      # the code stays in its own field
    assert rows["3"]["category"] is None and rows["3"]["categorize_tries"] >= 1


async def test_with_the_model_server_down_nothing_counts_as_a_try(monkeypatch):
    device.keep("sms", EMAIL, [{"id": "1", "sender": "X", "body": "hello", "date": 1761800000000}])

    async def down(items):
        raise categorize.Unavailable("connection refused")
    monkeypatch.setattr(categorize, "_ask", down)
    assert await categorize.run(EMAIL) == 0
    assert store.items("sms", EMAIL)[0]["categorize_tries"] == 0


async def test_a_location_gets_a_place_name_and_an_unnamed_one_is_tried_three_times_at_most(monkeypatch):
    device.keep("locations", EMAIL, [{"lat": 12.97, "lng": 77.64, "accuracy": 20, "time": 1761800000000},
                                     {"lat": 0.0, "lng": 0.0, "accuracy": 20, "time": 1761800100000}])

    async def reverse(lat, lon):
        return "Indiranagar" if lat else None
    monkeypatch.setattr(geocode, "reverse", reverse)
    for _ in range(4):
        await geocode.run(EMAIL)
    places = {r["id"]: r for r in store.items("locations", EMAIL)}
    assert places["1761800000000"]["place"] == "Indiranagar"
    assert places["1761800100000"]["place"] is None and places["1761800100000"]["geocode_tries"] == 3
