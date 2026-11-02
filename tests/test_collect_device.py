"""Our data collecting layer, phone part: what the Android app collects (SMS, call log, notifications, location, photo
names, the installed apps with their collect switch) is sent to /v1/collect/device/… and kept in the local cache for the
signed-in member only. Every SMS is kept, one-time codes included (decided 2 Nov 2026), with the code pulled out;
notifications from an app switched off are never kept."""
import pytest

from familyos.collect import categorize, device, geocode
from familyos.settings import settings


@pytest.fixture(autouse=True)
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    # Sorting and place names run on their own (test_collect_enrich.py); not against the real model or OpenStreetMap here.
    monkeypatch.setattr(categorize, "start", lambda email: False)
    monkeypatch.setattr(geocode, "start", lambda email: False)


async def post(family, who, kind, items):
    return await family.client.post(f"/v1/collect/device/{kind}", headers=family.h(who), json={"items": items})


async def test_every_sms_is_kept_one_time_codes_included_with_every_field_and_the_code_pulled_out(family):
    r = await post(family, "amma", "sms", [
        {"id": "11", "sender": "VM-HDFCBK", "body": "Rs 2,500 debited from a/c XX12 for school fee", "date": 1761800000000,
         "dateSent": 1761799990000, "type": 1, "read": 0, "seen": 1, "subject": None, "serviceCenter": "+919845000000",
         "person": None, "protocol": 0, "threadId": "7"},
        {"id": "12", "sender": "AD-SWIGGY", "body": "123456 is your OTP to log in. Do not share it.", "date": 1761800100000},
    ])
    assert r.status_code == 200, r.text
    assert r.json() == {"kept": 2, "dropped": 0}
    got = {m["id"]: m for m in (await family.client.get("/v1/collect/device/sms", headers=family.h("amma"))).json()}
    assert got["12"]["otp"] == "123456" and got["11"]["otp"] is None
    assert got["11"]["service_center"] == "+919845000000" and got["11"]["seen"] == 1 and got["11"]["date_sent"].startswith("2025-10-30")
    # The same message again is not kept twice.
    await post(family, "amma", "sms", [{"id": "11", "sender": "VM-HDFCBK", "body": "Rs 2,500 debited", "date": 1761800000000}])
    assert len((await family.client.get("/v1/collect/device/sms", headers=family.h("amma"))).json()) == 2


async def test_each_member_sees_only_their_own(family):
    await post(family, "amma", "calls", [{"number": "+919845012345", "type": "incoming", "date": 1761800000000, "duration": 62}])
    assert len((await family.client.get("/v1/collect/device/calls", headers=family.h("amma"))).json()) == 1
    assert (await family.client.get("/v1/collect/device/calls", headers=family.h("appa"))).json() == []
    assert (await family.client.get("/v1/collect/device/calls")).status_code == 401


async def test_the_app_list_keeps_each_switch_and_notifications_follow_it(family):
    r = await family.client.put("/v1/collect/device/apps", headers=family.h("amma"), json={"apps": [
        {"package": "com.whatsapp", "label": "WhatsApp", "collect": True},
        {"package": "com.supercell.clashofclans", "label": "Clash of Clans", "collect": False},
    ]})
    assert r.status_code == 200, r.text
    apps = (await family.client.get("/v1/collect/device/apps", headers=family.h("amma"))).json()
    assert {a["package"]: a["collect"] for a in apps} == {"com.whatsapp": True, "com.supercell.clashofclans": False}
    r = await post(family, "amma", "notifications", [
        {"package": "com.whatsapp", "title": "Class 4 parents", "text": "PTM moved to Saturday", "postTime": 1761800000000},
        {"package": "com.supercell.clashofclans", "title": "Your troops", "text": "are ready", "postTime": 1761800000500},
        {"package": "com.unknown.app", "title": "x", "text": "y", "postTime": 1761800001000},
    ])
    assert r.json() == {"kept": 1, "dropped": 2}
    kept = (await family.client.get("/v1/collect/device/notifications", headers=family.h("amma"))).json()
    assert [(n["package"], n["app_label"]) for n in kept] == [("com.whatsapp", "WhatsApp")]


async def test_location_and_photo_names(family):
    assert (await post(family, "amma", "locations", [{"lat": 12.97, "lng": 77.64, "accuracy": 20.5, "time": 1761800000000}])).json()["kept"] == 1
    assert (await post(family, "amma", "files", [{"id": "img1", "name": "IMG_2026.jpg", "size": 204800, "mimeType": "image/jpeg", "date": 1761800000}])).json()["kept"] == 1
    loc = (await family.client.get("/v1/collect/device/locations", headers=family.h("amma"))).json()
    assert loc[0]["lat"] == 12.97 and loc[0]["accuracy"] == 20.5
    assert (await family.client.get("/v1/collect/device/files", headers=family.h("amma"))).json()[0]["name"] == "IMG_2026.jpg"


async def test_status_counts_what_the_phone_sent(family):
    await post(family, "amma", "sms", [{"id": "1", "sender": "VM-HDFCBK", "body": "Your bill is due", "date": 1761800000000}])
    s = (await family.client.get("/v1/collect/status", headers=family.h("amma"))).json()
    assert s["device"]["sms"] == 1 and s["device"]["calls"] == 0


async def test_an_unknown_kind_is_not_found_and_a_bad_body_is_refused(family):
    assert (await post(family, "amma", "contacts", [])).status_code == 404
    r = await family.client.post("/v1/collect/device/sms", headers=family.h("amma"), json={"nope": 1})
    assert r.status_code == 422


def test_kinds_are_the_ones_the_phone_sends():
    assert set(device.KINDS) == {"sms", "calls", "notifications", "locations", "files"}
