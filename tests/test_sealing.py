"""The text read out of notices, sealed under the household key, opened on read, and unreadable without it."""
import datetime as dt
import uuid

import pytest

from familyos import clock, crypto, db, familykey, sealing
from familyos.settings import settings
from tests.conftest import pdf
from tests.test_brief import _obligation

TODAY = clock.today()


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "seal_extracted_text", True)
    familykey._unlocked.clear()
    yield
    familykey._unlocked.clear()


def test_a_sealed_value_is_bound_to_its_household_and_column():
    hid = uuid.uuid4()
    key = crypto.AESGCM.generate_key(bit_length=256) if hasattr(crypto, "AESGCM") else b"\x01" * 32
    sealed = sealing.seal(key, hid, "quote", "Last date for fee payment is 19 October")
    assert sealed.startswith("enc:v1:") and "fee payment" not in sealed
    parsed_hid, column, blob = sealing.parse(sealed)
    assert parsed_hid == hid and column == "quote"
    assert crypto.open_sealed(key, blob, sealing._aad(hid, "quote")) == b"Last date for fee payment is 19 October"
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag: the column is part of what was signed
        crypto.open_sealed(key, blob, sealing._aad(hid, "title"))
    assert sealing.seal(key, hid, "quote", None) is None and sealing.seal(key, hid, "quote", sealed) == sealed


def test_when_the_setting_is_off_nothing_is_sealed(monkeypatch):
    monkeypatch.setattr(settings, "seal_extracted_text", False)
    assert sealing.seal(b"\x01" * 32, uuid.uuid4(), "quote", "plain") == "plain"


async def test_a_quote_is_stored_sealed_and_every_reader_still_sees_the_words(family, database):
    aid = (await family.upload("amma", pdf("fees"), filename="fees.pdf", visibility="shared")).json()["artifact"]["id"]
    from tests.test_brief import _claim
    await _claim(database, family, aid, title="Term 2 fee", date=TODAY + dt.timedelta(days=4))
    raw_db = db.raw_pool()
    raw = await raw_db.fetchval("SELECT quote FROM claims WHERE artifact_id = $1", uuid.UUID(aid))
    assert raw == "the words"                                   # a direct insert, as the test helpers do: plain until sealed
    out = await sealing.backfill()
    assert out["sealed"] >= 1
    raw = await raw_db.fetchval("SELECT quote FROM claims WHERE artifact_id = $1", uuid.UUID(aid))
    assert raw.startswith("enc:v1:") and "the words" not in raw
    # the shared pool opens it, by name, by position and as a dict
    from familyos.db import pool
    row = await pool().fetchrow("SELECT quote, title FROM claims WHERE artifact_id = $1", uuid.UUID(aid))
    assert row["quote"] == "the words" and row[0] == "the words" and dict(row)["quote"] == "the words" and row.get("title") == "Term 2 fee"
    assert await pool().fetchval("SELECT quote FROM claims WHERE artifact_id = $1", uuid.UUID(aid)) == "the words"
    async with pool().acquire() as conn:
        assert (await conn.fetch("SELECT quote FROM claims WHERE artifact_id = $1", uuid.UUID(aid)))[0]["quote"] == "the words"
    again = await sealing.backfill()
    assert again["sealed"] == 0                                 # done once


async def test_no_endpoint_ever_hands_out_ciphertext(family, database):
    aid = (await family.upload("amma", pdf("ptm"), filename="ptm.pdf", visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=3), title="Parent-teacher meeting", status="proposed")
    await sealing.backfill()
    assert (await db.raw_pool().fetchval("SELECT quote FROM claims c JOIN obligations o ON o.claim_id = c.id WHERE o.id = $1", oid)).startswith("enc:v1:")
    h = family.h("amma")
    for path in ("/v1/decisions", "/v1/brief", "/v1/me/day", "/v1/graph/insights", f"/v1/graph/touches?ref=obligation:{oid}&depth=2", "/v1/inbox?days=30", "/v1/activity"):
        r = await family.client.get(path, headers=h)
        assert r.status_code == 200 and "enc:v1:" not in r.text, path
    cards = (await family.client.get("/v1/decisions", headers=h)).json()
    assert any("the words" in str(c["source"]) for c in cards if c["kind"] == "date")


async def test_a_family_held_key_that_is_locked_cannot_open_the_text_and_unlocking_can(family, database):
    aid = (await family.upload("amma", pdf("rc"), filename="rc.pdf", visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=3), title="Pay the premium")
    await sealing.backfill()
    made = (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).json()
    assert (await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": made["shares"][:2]})).status_code == 200
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    locked = await family.client.get("/v1/decisions", headers=family.h("amma"))
    assert locked.status_code == 423
    assert (await db.raw_pool().fetchval("SELECT quote FROM claims c JOIN obligations o ON o.claim_id = c.id WHERE o.id = $1", oid)).startswith("enc:v1:")
    await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": made["shares"][1:3]})
    ok = await family.client.get("/v1/decisions", headers=family.h("amma"))
    assert ok.status_code == 200 and "enc:v1:" not in ok.text


async def test_the_backfill_skips_a_locked_household_and_erasing_the_key_ends_the_text(family, database):
    aid = (await family.upload("amma", pdf("x"), filename="x.pdf", visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=2))
    made = (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).json()
    await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": made["shares"][:2]})
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    out = await sealing.backfill()
    assert out["sealed"] == 0 and out["skipped_locked"] >= 1
    await family.client.post("/v1/household/family-key/unlock", headers=family.h("amma"), json={"shares": made["shares"][1:3]})
    assert (await sealing.backfill())["sealed"] >= 1
    # destroying the household key: the sealed text can never be opened again
    sealed = await db.raw_pool().fetchval("SELECT quote FROM claims WHERE household_id = $1 AND quote LIKE 'enc:v1:%' LIMIT 1", uuid.UUID(family.household["id"]))
    await database.execute("UPDATE households SET status = 'erasing' WHERE id = $1", uuid.UUID(family.household["id"]))
    familykey._unlocked.clear()
    from familyos.db import pool
    with pytest.raises(Exception):  # noqa: B017 - the household is gone: nothing opens it
        await pool().fetchval("SELECT $1::text", sealed)


async def test_many_rows_of_a_locked_household_do_not_starve_an_open_one(client, family, database):
    from tests.conftest import Family
    from tests.test_brief import _claim
    other = await Family(client).setup(name="Neighbours", guardian_email="n@example.com")
    locked_aid = (await family.upload("amma", pdf("locked"), filename="l.pdf", visibility="shared")).json()["artifact"]["id"]
    open_aid = (await other.upload("amma", pdf("open"), filename="o.pdf", visibility="shared")).json()["artifact"]["id"]
    for i in range(6):
        await _claim(database, family, locked_aid, title=f"Locked {i}")
    await _claim(database, other, open_aid, title="Open one")
    made = (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).json()
    await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": made["shares"][:2]})
    await family.client.post("/v1/household/family-key/lock", headers=family.h("amma"))
    out = await sealing.backfill(limit=3)                       # fewer rows per pass than the locked household has
    assert out["sealed"] == 2 and out["skipped_locked"] == 12      # the open household's one claim: its quote and its title; the locked one's six, twice
    assert (await db.raw_pool().fetchval("SELECT quote FROM claims WHERE artifact_id = $1", uuid.UUID(open_aid))).startswith("enc:v1:")


async def test_a_write_that_lands_during_the_backfill_wins(family, database, monkeypatch):
    from tests.test_brief import _claim
    aid = (await family.upload("amma", pdf("race"), filename="r.pdf", visibility="shared")).json()["artifact"]["id"]
    await _claim(database, family, aid)
    seen = {"n": 0}
    real_raw_pool = db.raw_pool

    class _Conn:
        def __init__(self, ctx):
            self.ctx = ctx

        async def __aenter__(self):
            self.c = await self.ctx.__aenter__()
            return self

        async def __aexit__(self, *e):
            return await self.ctx.__aexit__(*e)

        def __getattr__(self, n):
            return getattr(self.c, n)

        async def execute(self, sql, *a):
            if sql.startswith("UPDATE claims SET quote") and not seen["n"]:
                seen["n"] += 1      # a newer write lands after the pass read the row and before it writes
                await database.execute("UPDATE claims SET quote = 'a newer quote' WHERE artifact_id = $1", uuid.UUID(aid))
            return await self.c.execute(sql, *a)

    class _Hook:
        def __init__(self, raw):
            self.raw = raw

        def acquire(self):
            return _Conn(self.raw.acquire())

    monkeypatch.setattr(db, "raw_pool", lambda: _Hook(real_raw_pool()))
    out = await sealing.backfill()
    assert out["sealed"] == 1                                    # the claim's title; its quote lost the race
    assert await real_raw_pool().fetchval("SELECT quote FROM claims WHERE artifact_id = $1", uuid.UUID(aid)) == "a newer quote"
    monkeypatch.setattr(db, "raw_pool", real_raw_pool)
    assert (await sealing.backfill())["sealed"] == 1             # the next pass seals the newer value
