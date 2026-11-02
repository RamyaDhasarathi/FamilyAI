"""Make it private in one tap: one recovery phrase, trusted devices, and a recent passkey sign-in to open the household on a device."""
import uuid

import pytest

from familyos import familykey
from familyos.settings import settings
from tests import test_passkeys as pk
from tests.conftest import pdf
from tests.test_familykey import _enable


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    familykey._unlocked.clear()
    familykey._attempts.clear()
    monkeypatch.setattr(settings, "webauthn_origins", pk.ORIGIN)
    yield
    familykey._unlocked.clear()


async def _simple(family):
    r = await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "Emily's laptop"})
    assert r.status_code == 200, r.text
    made = r.json()
    done = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                    json={"device_id": made["device"]["id"], "device_secret": made["device"]["secret"]})
    assert done.status_code == 200, done.text
    return made, done.json()


async def _passkey_headers(family, who="amma"):
    phone, _ = await pk._add(family, who)
    r = await pk._sign_in(family, phone)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_a_recovery_phrase_is_one_33_word_share():
    secret = b"\x05" * 32
    phrase = familykey.phrase_of(secret)
    assert len(phrase.split()) == 33 and familykey.combine([phrase]) == secret


async def test_make_it_private_in_one_tap_shows_the_phrase_once_and_the_server_keeps_no_copy_of_the_key(family, database):
    hid = uuid.UUID(family.household["id"])
    made = (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={})).json()
    assert len(made["phrase"].split()) == 33 and made["device"]["secret"]
    # begun, not switched: the server still holds the key, so a lost phrase cannot lock anyone out yet
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["mode"] == "server"
    # a device that did not keep its secret cannot switch it on
    bad = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                   json={"device_id": made["device"]["id"], "device_secret": familykey._b64(b"x" * 32)})
    assert bad.status_code in (400, 422)
    done = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                    json={"device_id": made["device"]["id"], "device_secret": made["device"]["secret"]})
    assert done.status_code == 200 and done.json()["mode"] == "family" and done.json()["simple"] is True and done.json()["locked"] is False
    assert await database.fetchval("SELECT wrapped_key IS NULL FROM households WHERE id = $1", hid)
    # the phrase and the device secret are in no key table and no ledger line
    stored = " ".join(str(v) for r in await database.fetch("SELECT * FROM family_keys") for v in r.values())
    stored += " ".join(str(v) for r in await database.fetch("SELECT * FROM family_key_devices") for v in r.values())
    stored += " ".join(str(v) for r in await database.fetch("SELECT detail FROM audit_events") for v in r.values())
    assert made["phrase"] not in stored and made["device"]["secret"] not in stored
    # a second begin on a family-held household is refused
    assert (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={})).status_code in (400, 422)


async def test_after_a_restart_the_household_is_locked_and_only_the_phrase_opens_it_without_a_device(family):
    aid = (await family.upload("amma", pdf("policy"), filename="policy.pdf", visibility="shared")).json()["artifact"]["id"]
    original = f"/v1/artifacts/{aid}/original"
    made, _ = await _simple(family)
    familykey._unlocked.clear()                                                                  # a restart
    assert (await family.client.get(original, headers=family.h("amma"))).status_code == 423
    wrong = familykey.phrase_of(b"\x01" * 32)
    assert (await family.client.post("/v1/household/family-key/recover", headers=family.h("amma"), json={"phrase": wrong})).status_code in (400, 422)
    assert (await family.client.get(original, headers=family.h("amma"))).status_code == 423
    ok = await family.client.post("/v1/household/family-key/recover", headers=family.h("amma"), json={"phrase": made["phrase"]})
    assert ok.status_code == 200 and ok.json()["locked"] is False
    assert (await family.client.get(original, headers=family.h("amma"))).status_code == 200
    # the phrase opens it in any case and spacing, as it is copied from a page or a printout
    familykey._unlocked.clear()
    messy = "  " + made["phrase"].upper().replace(" ", "\n ") + " "
    assert (await family.client.post("/v1/household/family-key/recover", headers=family.h("amma"), json={"phrase": messy})).status_code == 200


async def test_a_trusted_device_opens_it_only_with_a_recent_passkey_sign_in(family, database):
    made, _ = await _simple(family)
    dev = {"device_id": made["device"]["id"], "device_secret": made["device"]["secret"]}
    familykey._unlocked.clear()
    # an ordinary session is refused, with a reason the console can act on
    r = await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=family.h("amma"), json=dev)
    assert r.status_code == 403 and "passkey_needed" in r.text
    h = await _passkey_headers(family)
    wrong = await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h, json={**dev, "device_secret": familykey._b64(b"y" * 32)})
    assert wrong.status_code in (400, 422)
    ok = await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h, json=dev)
    assert ok.status_code == 200 and ok.json()["locked"] is False
    # a passkey sign-in that is no longer recent is refused again
    familykey._unlocked.clear()
    await database.execute("UPDATE member_tokens SET passkey_at = NOW() - INTERVAL '2 hours' WHERE passkey_at IS NOT NULL")
    assert (await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h, json=dev)).status_code == 403
    # another member's device secret is not theirs to use
    await database.execute("UPDATE member_tokens SET passkey_at = NOW() WHERE passkey_at IS NOT NULL")
    other_h = await _passkey_headers(family, "paati")
    other = await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=other_h, json=dev)
    assert other.status_code in (400, 422)


async def test_another_device_can_be_trusted_while_open_and_a_lost_one_can_be_removed(family):
    await _simple(family)
    added = (await family.client.post("/v1/household/family-key/devices", headers=family.h("amma"), json={"label": "Emily's phone"})).json()
    assert added["secret"] and added["label"] == "Emily's phone"
    listed = (await family.client.get("/v1/household/family-key/devices", headers=family.h("amma"))).json()
    assert [d["label"] for d in listed] == ["Emily's laptop", "Emily's phone"] and "secret" not in str(listed)
    h = await _passkey_headers(family)
    familykey._unlocked.clear()
    assert (await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h, json={"device_id": added["id"], "device_secret": added["secret"]})).status_code == 200
    assert (await family.client.delete(f"/v1/household/family-key/devices/{added['id']}", headers=family.h("amma"))).status_code == 204
    familykey._unlocked.clear()
    assert (await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h, json={"device_id": added["id"], "device_secret": added["secret"]})).status_code in (400, 422)
    # a locked household cannot trust a new device: someone has to prove a factor first
    assert (await family.client.post("/v1/household/family-key/devices", headers=family.h("amma"), json={})).status_code in (400, 423)


async def test_a_new_phrase_retires_the_old_one(family):
    made, _ = await _simple(family)
    fresh = (await family.client.post("/v1/household/family-key/new-phrase", headers=family.h("amma"))).json()
    assert fresh["phrase"] != made["phrase"]
    familykey._unlocked.clear()
    assert (await family.client.post("/v1/household/family-key/recover", headers=family.h("amma"), json={"phrase": made["phrase"]})).status_code in (400, 422)
    assert (await family.client.post("/v1/household/family-key/recover", headers=family.h("amma"), json={"phrase": fresh["phrase"]})).status_code == 200
    # reshare is the several-people mode's
    assert (await family.client.post("/v1/household/family-key/reshare", headers=family.h("amma"), json={"shares": [fresh["phrase"]], "threshold": 2, "count": 3})).status_code in (400, 422)


async def test_a_guardian_can_go_back_with_the_phrase_and_the_several_people_mode_still_works(family, database):
    made, _ = await _simple(family)
    off = await family.client.post("/v1/household/family-key/disable", headers=family.h("amma"), json={"shares": [made["phrase"]]})
    assert off.status_code == 200 and off.json()["mode"] == "server"
    assert await database.fetchval("SELECT count(*) FROM family_key_devices") == 0
    shares = await _enable(family)
    familykey._unlocked.clear()
    assert (await family.client.post("/v1/household/family-key/unlock", headers=family.h("paati"), json={"shares": shares[:2]})).status_code == 200


async def test_only_a_guardian_makes_it_private(family):
    r = await family.client.post("/v1/household/family-key/simple", headers=family.h("paati"), json={})
    assert r.status_code == 403


async def test_a_second_setup_cannot_be_confirmed_by_the_first_and_the_saved_phrase_stays_the_one_that_works(family, database):
    first = (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "one"})).json()
    second = (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "two"})).json()
    stale = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                     json={"device_id": first["device"]["id"], "device_secret": first["device"]["secret"]})
    assert stale.status_code in (400, 422)                                   # the first device row was replaced with the second setup
    assert await database.fetchval("SELECT key_mode FROM households WHERE id = $1", uuid.UUID(family.household["id"])) == "server"
    ok = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                  json={"device_id": second["device"]["id"], "device_secret": second["device"]["secret"]})
    assert ok.status_code == 200
    # and the phrase that came with the setup that was confirmed is the one that opens it
    familykey._unlocked.clear()
    again = await family.client.post("/v1/household/family-key/recover", headers=family.h("amma"), json={"phrase": second["phrase"]})
    assert again.status_code == 200, again.text
    # a new begin on a household that already switched is refused outright
    assert (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "three"})).status_code in (400, 422)


async def test_switching_between_the_one_tap_and_the_shares_setup_cannot_activate_the_wrong_one(family, database):
    hid = uuid.UUID(family.household["id"])
    first = (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "one"})).json()
    adv = (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).json()
    stale = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                     json={"device_id": first["device"]["id"], "device_secret": first["device"]["secret"]})
    assert stale.status_code in (400, 422)
    assert await database.fetchval("SELECT key_mode FROM households WHERE id = $1", hid) == "server"
    assert await database.fetchval("SELECT simple FROM family_keys WHERE household_id = $1", hid) is False
    assert await database.fetchval("SELECT count(*) FROM family_key_devices WHERE household_id = $1", hid) == 0
    ok = await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": adv["shares"][:2]})
    assert ok.status_code == 200, ok.text
    # and the other way round: the shares setup is replaced by a one-tap one, so its confirmation must refuse
    await family.client.post("/v1/household/family-key/disable", headers=family.h("amma"), json={"shares": adv["shares"][:2]})
    adv2 = (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).json()
    (await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "two"})).json()
    stale2 = await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": adv2["shares"][:2]})
    assert stale2.status_code in (400, 422) and await database.fetchval("SELECT key_mode FROM households WHERE id = $1", hid) == "server"
