"""Level 2: a private notice sealed with its member's key.

Until now one household key sealed everything, and privacy was the visibility
column alone. These tests are about what changes when it is not.
"""
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from familyos import artifacts, crypto
from familyos.db import pool
from tests.conftest import pdf


async def test_a_private_notice_is_sealed_with_its_members_key(family, database):
    r = await family.upload("amma", pdf("private one"))
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    blob = await database.fetchrow(
        "SELECT b.* FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1", artifact_id)
    assert blob["sealed_for"] == uuid.UUID(family.amma["id"])
    assert blob["wrapped_key"] is not None


async def test_a_shared_notice_is_sealed_with_the_households(family, database):
    r = await family.upload("amma", pdf("shared one"), visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    blob = await database.fetchrow(
        "SELECT b.* FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1", artifact_id)
    assert blob["sealed_for"] is None


async def test_the_households_key_alone_no_longer_opens_a_private_notice(family, database):
    """The property this was built for: a bug in a read path leaks a row, and
    not the document behind it."""
    r = await family.upload("amma", pdf("private one"))
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    blob = await database.fetchrow(
        "SELECT b.* FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1", artifact_id)

    household = crypto.unwrap(household_id, await database.fetchval(
        "SELECT wrapped_key FROM households WHERE id = $1", household_id))
    with pytest.raises(InvalidTag):
        crypto.open_sealed(household, blob["wrapped_key"], artifacts._aad(household_id, blob["sha256"]))

    # The member's own key does open it, and the bytes come back whole.
    async with pool().acquire() as conn:
        data = await artifacts.read_bytes(household_id, dict(
            await conn.fetchrow("SELECT * FROM input_artifacts WHERE id = $1", artifact_id)))
    assert data == pdf("private one")


async def test_one_members_sub_key_will_not_open_anothers(family, database):
    await family.upload("amma", pdf("hers"))
    await family.upload("appa", pdf("his"))
    household_id = uuid.UUID(family.household["id"])

    async with pool().acquire() as conn:
        hers = await artifacts.member_key(conn, household_id, uuid.UUID(family.amma["id"]))
        his_blob = await conn.fetchrow(
            "SELECT b.* FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id "
            "WHERE a.submitted_by = $1", uuid.UUID(family.appa["id"]))
    with pytest.raises(InvalidTag):
        crypto.open_sealed(hers, his_blob["wrapped_key"], artifacts._aad(household_id, his_blob["sha256"]))


async def test_sharing_a_notice_rewraps_without_re_encrypting_it(family, database):
    r = await family.upload("amma", pdf("later shared"))
    artifact_id = r.json()["artifact"]["id"]
    before = await database.fetchrow(
        "SELECT b.storage_key, b.wrapped_key, b.sealed_for FROM blobs b "
        "JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1", uuid.UUID(artifact_id))

    ok = await family.client.patch(f"/v1/artifacts/{artifact_id}",
                                   headers=family.h("amma"), json={"visibility": "shared"})
    assert ok.status_code == 200, ok.text

    after = await database.fetchrow(
        "SELECT b.storage_key, b.wrapped_key, b.sealed_for FROM blobs b "
        "JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1", uuid.UUID(artifact_id))
    # Same object in the store, same ciphertext: only the 32-byte key moved scope.
    assert after["storage_key"] == before["storage_key"]
    assert after["sealed_for"] is None and before["sealed_for"] is not None
    assert after["wrapped_key"] != before["wrapped_key"]

    # And Appa can read it now, which he could not before.
    seen = await family.client.get(f"/v1/artifacts/{artifact_id}/original", headers=family.h("appa"))
    assert seen.status_code == 200


async def test_erasing_a_member_destroys_their_key_before_their_rows(family, database):
    """What the sub-key is for: deleting rows leaves yesterday's backup
    readable, and destroying the key does not."""
    await family.upload("appa", pdf("his private notice"))
    household_id = uuid.UUID(family.household["id"])
    appa = uuid.UUID(family.appa["id"])

    async with pool().acquire() as conn:
        assert await artifacts.member_key(conn, household_id, appa)

    await database.execute("UPDATE members SET wrapped_sub_key = NULL WHERE id = $1", appa)

    async with pool().acquire() as conn:
        with pytest.raises(crypto.KeyUnavailable):
            await artifacts.member_key(conn, household_id, appa)


async def test_destroying_the_household_key_still_takes_every_members(family, database):
    """Sub-keys are wrapped by the household key, never by the master key, so
    household erasure remains one operation."""
    await family.upload("amma", pdf("one"))
    household_id = uuid.UUID(family.household["id"])
    # Exactly what step 0 of erasure does.
    await database.execute(
        "UPDATE households SET status = 'erasing', wrapped_key = NULL WHERE id = $1", household_id)

    async with pool().acquire() as conn:
        # HouseholdUnavailable: without the household key there is nothing to
        # unwrap a member's with, so the whole family goes at once.
        with pytest.raises(artifacts.HouseholdUnavailable):
            await artifacts.member_key(conn, household_id, uuid.UUID(family.amma["id"]))
