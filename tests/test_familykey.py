"""A key the family holds: begin, confirm, lock, unlock, reshare, disable, and what a locked household cannot do."""
import time
import uuid

import pytest

from familyos import familykey
from familyos.identity import Invalid
from tests.conftest import pdf


@pytest.fixture(autouse=True)
def _clean():
    familykey._unlocked.clear()
    familykey._attempts.clear()
    yield
    familykey._unlocked.clear()


async def _begin(family, threshold=2, count=3):
    r = await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": threshold, "count": count})
    assert r.status_code == 200, r.text
    return r.json()


async def _enable(family, threshold=2, count=3):
    made = await _begin(family, threshold, count)
    r = await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": made["shares"][:threshold]})
    assert r.status_code == 200, r.text
    return made["shares"]


def test_shares_split_and_recombine_and_a_wrong_set_is_refused_in_plain_words():
    secret = b"\x07" * 32
    shares = familykey.split(secret, 2, 3)
    assert len(shares) == 3 and all(len(s.split()) == 33 for s in shares)
    assert familykey.combine(shares[:2]) == secret and familykey.combine([shares[2], shares[0]]) == secret
    with pytest.raises(Invalid, match="do not fit"):
        familykey.combine(shares[:1])
    other = familykey.split(b"\x09" * 32, 2, 3)
    with pytest.raises(Invalid):
        familykey.combine([shares[0], other[1]])
    typo = shares[0].split()
    typo[2] = typo[3]
    with pytest.raises(Invalid, match="checksum"):
        familykey.combine([" ".join(typo), shares[1]])
    with pytest.raises(Invalid):
        familykey.split(secret, 4, 3)


async def test_nothing_changes_until_the_shares_are_given_back_and_a_wrong_set_does_not_switch_it(family, database):
    made = await _begin(family)
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["mode"] == "server"
    assert await database.fetchval("SELECT wrapped_key IS NOT NULL FROM households WHERE id = $1", uuid.UUID(family.household["id"]))
    bad = familykey.split(b"\x01" * 32, 2, 3)
    r = await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": bad[:2]})
    assert r.status_code in (400, 422) and "do not open" in r.text
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["mode"] == "server"
    ok = await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": made["shares"][1:3]})
    assert ok.status_code == 200 and ok.json()["mode"] == "family" and ok.json()["locked"] is False
    # the server's own wrapped copy is gone
    assert await database.fetchval("SELECT wrapped_key IS NULL FROM households WHERE id = $1", uuid.UUID(family.household["id"]))


async def test_a_locked_household_cannot_read_what_was_sealed_and_unlocking_brings_it_back(family):
    r = await family.upload("amma", pdf("policy"), filename="policy.pdf", visibility="shared")
    aid = r.json()["artifact"]["id"]
    shares = await _enable(family)
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code == 200      # unlocked after confirming
    lock = await family.client.post("/v1/household/family-key/lock", headers=family.h("paati"))
    assert lock.status_code == 200 and lock.json()["locked"] is True
    locked = await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))
    assert locked.status_code == 423 and "household_locked" in locked.text
    too_few = await family.client.post("/v1/household/family-key/unlock", headers=family.h("paati"), json={"shares": shares[:1]})
    assert too_few.status_code in (400, 422)
    up = await family.client.post("/v1/household/family-key/unlock", headers=family.h("paati"), json={"shares": [shares[2], shares[0]]})
    assert up.status_code == 200 and up.json()["locked"] is False
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code == 200


async def test_the_unlock_expires_and_a_restart_forgets_it(family, monkeypatch):
    shares = await _enable(family)
    hid = uuid.UUID(family.household["id"])
    assert await familykey.unlocked_key(hid)
    key, _ = familykey._unlocked[hid]
    familykey._unlocked[hid] = (key, time.monotonic() - 1)
    with pytest.raises(familykey.HouseholdLocked):
        await familykey.unlocked_key(hid)
    familykey._unlocked.clear()                                                       # a restart
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["locked"] is True
    assert (await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": shares[:2]})).status_code == 200


async def test_reshare_makes_the_old_shares_useless_without_touching_data_and_disable_goes_back(family, database):
    r = await family.upload("amma", pdf("rc"), filename="rc.pdf", visibility="shared")
    aid = r.json()["artifact"]["id"]
    old = await _enable(family)
    new = (await family.client.post("/v1/household/family-key/reshare", headers=family.h("amma"), json={"shares": old[:2], "threshold": 3, "count": 4})).json()
    assert new["threshold"] == 3 and len(new["shares"]) == 4
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    assert (await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": old[:2]})).status_code in (400, 422)
    assert (await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": new["shares"][:3]})).status_code == 200
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code == 200
    off = await family.client.post("/v1/household/family-key/disable", headers=family.h("amma"), json={"shares": new["shares"][1:4]})
    assert off.status_code == 200 and off.json()["mode"] == "server"
    assert await database.fetchval("SELECT wrapped_key IS NOT NULL FROM households WHERE id = $1", uuid.UUID(family.household["id"]))
    familykey._unlocked.clear()
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code == 200      # the server holds it again


async def test_only_a_guardian_changes_it_and_a_child_cannot_unlock(family):
    forbidden = await family.client.post("/v1/household/family-key/begin", headers=family.h("paati"), json={"threshold": 2, "count": 3})
    assert forbidden.status_code == 403
    await _enable(family)
    assert (await family.client.post("/v1/household/family-key/disable", headers=family.h("paati"), json={"shares": ["x"]})).status_code == 403
    assert (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).status_code in (400, 422)   # already on


async def test_guessing_is_slowed(family):
    await _enable(family)
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    bad = familykey.split(b"\x05" * 32, 2, 3)[:2]
    codes = [(await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": bad})).status_code for _ in range(12)]
    assert codes[-1] in (400, 422) and "too many" in (await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": bad})).text


async def test_successful_unlocks_do_not_use_up_the_guessing_allowance(family):
    made = await _enable(family)
    for _ in range(familykey.MAX_ATTEMPTS_PER_HOUR + 3):
        await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
        ok = await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": made[:2]})
        assert ok.status_code == 200, ok.text


async def test_one_members_wrong_guesses_do_not_lock_the_others_out(family):
    made = await _enable(family)
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    bad = familykey.split(b"\x05" * 32, 2, 3)[:2]
    for _ in range(familykey.MAX_ATTEMPTS_PER_HOUR):
        await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": bad})
    blocked = await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": made[:2]})
    assert blocked.status_code in (400, 422) and "too many" in blocked.text
    appa = await family.client.post("/v1/household/family-key/unlock", headers=family.h("appa"), json={"shares": made[:2]})
    assert appa.status_code == 200, appa.text


async def test_reshare_and_a_new_phrase_say_so_when_no_row_was_changed(family, monkeypatch):
    from familyos.identity import Invalid, Principal

    made = await _enable(family)

    class Zero:
        def __init__(self, real):
            self.real = real

        def __getattr__(self, name):
            return getattr(self.real, name)

        async def execute(self, sql, *a):
            return "UPDATE 0" if sql.startswith("UPDATE family_keys SET") and "rotated_at" in sql else await self.real.execute(sql, *a)

    real_pool = familykey.pool
    monkeypatch.setattr(familykey, "pool", lambda: Zero(real_pool()))
    amma = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    with pytest.raises(Invalid):
        await familykey.reshare(amma, made[:2], 2, 3)
    monkeypatch.setattr(familykey, "pool", real_pool)
    await database_simple_flag(family, True)
    monkeypatch.setattr(familykey, "pool", lambda: Zero(real_pool()))
    with pytest.raises(Invalid):
        await familykey.new_phrase(amma)


async def database_simple_flag(family, value):
    from familyos.db import pool
    await pool().execute("UPDATE family_keys SET simple = $2 WHERE household_id = $1", uuid.UUID(family.household["id"]), value)
