"""A Shamir share kept sealed to a member's passkey, and unlocking by tapping t members' devices. The server holds only ciphertext the browser
made under a passkey-derived secret; the shares members give are held in memory until enough have come, then dropped."""
import uuid

import pytest

from familyos import familykey
from familyos.settings import settings
from tests import test_passkeys as pk
from tests.test_familykey import _enable
from tests.test_private_mode import _passkey_headers

SALT = familykey._b64(b"\x22" * 32)
BLOB = familykey._b64(b"\x33" * 60)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    familykey._unlocked.clear()
    familykey._attempts.clear()
    familykey._contributions.clear()
    monkeypatch.setattr(settings, "webauthn_origins", pk.ORIGIN)
    yield
    familykey._unlocked.clear()
    familykey._contributions.clear()


async def _cred(database, family, who):
    raw = await database.fetchval("SELECT credential_id FROM member_passkeys WHERE member_id = $1 AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1",
                                  uuid.UUID(getattr(family, who)["id"]))
    return familykey._b64(bytes(raw))


async def test_a_member_keeps_a_share_in_their_passkey_and_the_server_holds_only_ciphertext(family, database):
    shares = await _enable(family)
    h = await _passkey_headers(family, "amma")
    cred = await _cred(database, family, "amma")
    r = await family.client.post("/v1/household/family-key/share-seals", headers=h, json={"credential_id": cred, "salt": SALT, "wrapped": BLOB})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["display_name"] for x in body["holders"]] == [family.amma["display_name"]] and body["mine"]["wrapped"] == BLOB and body["threshold"] == 2
    # another member sees who holds one, never anyone's ciphertext
    other = (await family.client.get("/v1/household/family-key/share-seals", headers=family.h("appa"))).json()
    assert other["mine"] is None and len(other["holders"]) == 1 and BLOB not in str(other)
    assert not any(sh in str(body) for sh in shares)
    # a new one replaces the old; removing it leaves the words valid
    await family.client.post("/v1/household/family-key/share-seals", headers=h, json={"credential_id": cred, "salt": SALT, "wrapped": familykey._b64(b"\x44" * 60)})
    assert await database.fetchval("SELECT count(*) FROM family_key_share_seals WHERE revoked_at IS NULL") == 1
    gone = await family.client.delete("/v1/household/family-key/share-seals", headers=h)
    assert gone.status_code == 200 and gone.json()["holders"] == []
    assert familykey.combine(shares[:2])


async def test_a_share_cannot_be_sealed_to_somebody_elses_passkey_or_in_a_household_without_shares(family, database):
    await _enable(family)
    h = await _passkey_headers(family, "amma")
    await pk._add(family, "paati")
    theirs = await _cred(database, family, "paati")
    r = await family.client.post("/v1/household/family-key/share-seals", headers=h, json={"credential_id": theirs, "salt": SALT, "wrapped": BLOB})
    assert r.status_code in (400, 422) and "not one of yours" in r.text
    mine = await _cred(database, family, "amma")
    short = await family.client.post("/v1/household/family-key/share-seals", headers=h, json={"credential_id": mine, "salt": familykey._b64(b"x" * 8), "wrapped": BLOB})
    assert short.status_code in (400, 422)


async def test_t_members_giving_their_shares_open_the_household_and_the_shares_are_dropped(family, database):
    shares = await _enable(family)
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    ha, hp = await _passkey_headers(family, "amma"), await _passkey_headers(family, "appa")
    first = await family.client.post("/v1/household/family-key/contribute", headers=ha, json={"share": shares[0]})
    assert first.status_code == 200 and first.json()["locked"] is True and first.json()["contributed"] == 1
    again = await family.client.post("/v1/household/family-key/contribute", headers=ha, json={"share": shares[0]})
    assert again.json()["locked"] is True and again.json()["contributed"] == 1             # the same member twice is still one
    second = await family.client.post("/v1/household/family-key/contribute", headers=hp, json={"share": shares[1]})
    assert second.status_code == 200 and second.json()["locked"] is False
    assert familykey._contributions == {}                                                      # nothing kept


async def test_contributing_needs_a_recent_passkey_a_readable_share_and_shares_of_the_same_set(family, database):
    shares = await _enable(family)
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    no_passkey = await family.client.post("/v1/household/family-key/contribute", headers=family.h("amma"), json={"share": shares[0]})
    assert no_passkey.status_code == 403 and "passkey" in no_passkey.text
    ha, hp = await _passkey_headers(family, "amma"), await _passkey_headers(family, "appa")
    junk = await family.client.post("/v1/household/family-key/contribute", headers=ha, json={"share": "these are not twenty words of a share at all"})
    assert junk.status_code in (400, 422)
    stranger = familykey.split(b"\x09" * 32, 2, 3)
    await family.client.post("/v1/household/family-key/contribute", headers=ha, json={"share": shares[0]})
    wrong = await family.client.post("/v1/household/family-key/contribute", headers=hp, json={"share": stranger[0]})
    assert wrong.status_code in (400, 422)
    assert familykey._contributions == {}                                                      # a failed attempt keeps nothing either
    status = (await family.client.get("/v1/household/family-key", headers=ha)).json()
    assert status["locked"] is True and status["contributed"] == 0


async def test_with_several_workers_tapping_to_unlock_is_refused_so_no_share_rests_in_the_database(family, monkeypatch):
    shares = await _enable(family)
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    ha = await _passkey_headers(family, "amma")
    monkeypatch.setattr(settings, "multi_worker", True)
    r = await family.client.post("/v1/household/family-key/contribute", headers=ha, json={"share": shares[0]})
    assert r.status_code in (400, 422) and "single worker" in r.text
