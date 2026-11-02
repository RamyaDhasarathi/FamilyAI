"""The family key with more than one worker (FAMILYOS_MULTI_WORKER): the unlock and the failed-try count live in Postgres, so a household
unlocked through one worker is open on another, and a lock made anywhere is a lock everywhere. With one worker nothing changes."""
import uuid

import pytest

from familyos import familykey
from tests.conftest import pdf
from tests.test_familykey import _clean, _enable  # noqa: F401  (_clean is an autouse fixture there)


@pytest.fixture
def two_workers(monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "multi_worker", True)
    monkeypatch.setattr(settings, "family_key_share_unlock", True)       # the operator accepted the trade-off (see the test below for the default)
    monkeypatch.setattr(familykey, "LOCAL_TRUST_SECONDS", 0.0)          # every read asks the shared store, as another worker's would


async def test_with_one_worker_nothing_is_written_to_the_shared_store(family, database):
    await _enable(family)
    assert await database.fetchval("SELECT count(*) FROM family_key_unlocks") == 0


async def test_with_several_workers_the_unlocked_key_stays_out_of_postgres_unless_the_operator_chose_otherwise(family, database, monkeypatch):
    """The stored copy is wrapped under the server's master key, so a database snapshot plus that key would open a household the family holds the
    key to. It is written only when FAMILYOS_FAMILY_KEY_SHARE_UNLOCK says so; without it each worker holds its own unlock, in memory, as one worker does."""
    from familyos.settings import settings
    monkeypatch.setattr(settings, "multi_worker", True)
    monkeypatch.setattr(familykey, "LOCAL_TRUST_SECONDS", 0.0)
    r = await family.upload("amma", pdf("kept"), filename="kept.pdf", visibility="shared")
    aid = r.json()["artifact"]["id"]
    hid = uuid.UUID(family.household["id"])
    await _enable(family)
    assert await database.fetchval("SELECT count(*) FROM family_key_unlocks") == 0                   # nothing the operator could open
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code == 200   # and this worker still serves it
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["locked"] is False
    familykey._unlocked.clear()                                                                      # another worker has not been unlocked
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["locked"] is True
    assert hid not in familykey._unlocked


async def test_an_unlock_on_one_worker_opens_the_household_on_another_and_a_lock_closes_it_on_both(family, database, two_workers):
    r = await family.upload("amma", pdf("two"), filename="two.pdf", visibility="shared")
    aid = r.json()["artifact"]["id"]
    hid = uuid.UUID(family.household["id"])
    shares = await _enable(family)
    row = await database.fetchrow("SELECT wrapped_key, expires_at FROM family_key_unlocks WHERE household_id = $1", hid)
    assert row is not None
    key, _ = familykey._unlocked[hid]
    assert key not in bytes(row["wrapped_key"])                                       # the store alone is not the key: it is wrapped
    familykey._unlocked.clear()                                                       # the other worker has never seen this unlock
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code == 200
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["locked"] is False
    # a lock, wherever it is made, is a lock everywhere
    await database.execute("DELETE FROM family_key_unlocks WHERE household_id = $1", hid)      # the other worker locked
    assert (await family.client.get("/v1/household/family-key", headers=family.h("amma"))).json()["locked"] is True
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("amma"))).status_code != 200
    assert (await family.client.post("/v1/household/family-key/unlock", headers=family.h("paati"), json={"shares": shares[:2]})).status_code == 200
    assert await database.fetchval("SELECT count(*) FROM family_key_unlocks WHERE household_id = $1", hid) == 1
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    assert await database.fetchval("SELECT count(*) FROM family_key_unlocks WHERE household_id = $1", hid) == 0


async def test_the_shared_unlock_expires(family, database, two_workers):
    hid = uuid.UUID(family.household["id"])
    await _enable(family)
    familykey._unlocked.clear()
    await database.execute("UPDATE family_key_unlocks SET expires_at = NOW() - INTERVAL '1 second' WHERE household_id = $1", hid)
    with pytest.raises(familykey.HouseholdLocked):
        await familykey.unlocked_key(hid)


async def test_wrong_tries_are_counted_across_workers(family, database, two_workers):
    shares = await _enable(family)
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    for _ in range(familykey.MAX_ATTEMPTS_PER_HOUR):
        r = await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": ["not a share at all", "nor this"]})
        assert r.status_code in (400, 422)
        familykey._attempts.clear()                                                   # each try lands on a worker that remembers nothing
    r = await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": shares[:2]})
    assert r.status_code in (400, 422, 429) and "too many" in r.text.lower()
    await database.execute("DELETE FROM family_key_attempts")                         # the hour passes
    assert (await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": shares[:2]})).status_code == 200
    assert await database.fetchval("SELECT count(*) FROM family_key_attempts") == 0   # a success clears the member's count
