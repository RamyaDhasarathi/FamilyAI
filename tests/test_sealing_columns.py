"""Titles and names, sealed with the quotes (sealing.py, docs/family-key.md "Sealed columns").

claims.title, claims.subject_name, claims.issuer and obligations.title are ciphertext in the database, plain through the pool every module
reads with, 423 while a family-held key is locked, and the searches that used to run on them in SQL give the same answers from Python."""
import datetime as dt
import uuid

import pytest

from familyos import clock, db, familykey, routines, scenarios, sealing, warranty_hints
from familyos.extraction import service
from familyos.extraction.claims import Amount, Claim
from familyos.identity import Principal
from familyos.settings import settings
from tests.test_loops import GROUNDED, _mail, _read

TODAY = clock.today()
SEALED = {("claims", "title"), ("claims", "subject_name"), ("claims", "issuer"), ("obligations", "title")}


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "seal_extracted_text", True)
    familykey._unlocked.clear()
    yield
    familykey._unlocked.clear()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _claim(**kw):
    return Claim(location=GROUNDED, confidence=0.9, **kw)


async def _read_notice(family, claims, *, sender="School Office <office@school.example.com>", subject="Notice"):
    artifact_id = await _mail(family, sender, subject)
    await service.save(uuid.UUID(family.household["id"]), artifact_id, _read(claims, reference=TODAY))
    return artifact_id


async def _notice_with_everything(family):
    """One notice that fills every sealed column: a named child (consented), a document with an issuer, a dated deadline and an event."""
    consent = await family.consent(family.older)
    family.consent_id = consent["id"]
    return await _read_notice(family, [
        _claim(kind="deadline", title="Pay the term fee", date=TODAY + dt.timedelta(days=6), requires=["payment"],
               amount=Amount(value=4200, currency="INR", text="Rs 4,200"), subject_name=family.older["display_name"], quote="Term fee is due on the date given"),
        _claim(kind="event", title="Parent-teacher meeting", date=TODAY + dt.timedelta(days=9), quote="PTM on the ninth"),
        _claim(kind="document", title="Passport of Ila", document_kind="passport", issuer="Passport Office, Chennai", date=TODAY - dt.timedelta(days=300),
               end_date=TODAY + dt.timedelta(days=400), identifier_tail="6543", quote="Passport number 1234567 6543")])


async def test_every_sealed_column_is_ciphertext_at_rest_and_plain_through_the_pool(family, database):
    artifact_id = await _notice_with_everything(family)
    raw = db.raw_pool()
    for table, column, _ in sealing.BACKFILL_COLUMNS:
        values = [r["v"] for r in await raw.fetch(f"SELECT {column} AS v FROM {table} WHERE household_id = $1 AND {column} IS NOT NULL", uuid.UUID(family.household["id"]))]
        assert values, f"{table}.{column} has no row, so this test would prove nothing"
        assert all(v.startswith(sealing.PREFIX) for v in values), f"{table}.{column} is stored in the clear"
    assert {(t, c) for t, c, _ in sealing.BACKFILL_COLUMNS} - {("claims", "quote")} == SEALED
    # what the application sees
    titles = {r["title"] for r in await database.fetch("SELECT title FROM obligations WHERE artifact_id = $1", artifact_id)}
    assert {"Pay the term fee", "Parent-teacher meeting"} <= titles
    row = await database.fetchrow("SELECT subject_name, issuer FROM claims WHERE artifact_id = $1 AND kind = 'document'", artifact_id)
    assert row["issuer"] == "Passport Office, Chennai"
    assert await database.fetchval("SELECT subject_name FROM claims WHERE artifact_id = $1 AND kind = 'deadline'", artifact_id) == family.older["display_name"]
    # an array built in SQL from a sealed column opens too
    assert "Pay the term fee" in await database.fetchval("SELECT array_agg(title) FROM obligations WHERE artifact_id = $1", artifact_id)


async def test_no_endpoint_hands_out_ciphertext_for_a_title_or_a_name(family, database):
    await _notice_with_everything(family)
    h = family.h("amma")
    for path in ("/v1/obligations?status=", "/v1/decisions", "/v1/brief", "/v1/me/day", "/v1/inbox?days=30", "/v1/activity", "/v1/documents", "/v1/graph/insights"):
        r = await family.client.get(path, headers=h)
        assert r.status_code == 200 and "enc:v1:" not in r.text, path
    assert "Pay the term fee" in (await family.client.get("/v1/obligations?status=", headers=h)).text


async def test_a_locked_family_held_key_answers_423_where_titles_are_read_and_unlocking_reads_them(family, database):
    await _notice_with_everything(family)
    h = family.h("amma")
    made = (await family.client.post("/v1/household/family-key/begin", headers=h, json={"threshold": 2, "count": 3})).json()
    assert (await family.client.post("/v1/household/family-key/confirm", headers=h, json={"shares": made["shares"][:2]})).status_code == 200
    await family.client.post("/v1/household/family-key/lock", headers=h)
    assert (await family.client.get("/v1/obligations?status=", headers=h)).status_code == 423
    await family.client.post("/v1/household/family-key/unlock", headers=h, json={"shares": made["shares"][1:3]})
    ok = await family.client.get("/v1/obligations?status=", headers=h)
    assert ok.status_code == 200 and "Pay the term fee" in ok.text


async def test_with_the_setting_off_nothing_new_is_sealed_and_old_plain_rows_read_and_are_sealed_by_the_sweep(family, database, monkeypatch):
    monkeypatch.setattr(settings, "seal_extracted_text", False)
    artifact_id = await _notice_with_everything(family)
    raw = db.raw_pool()
    assert await raw.fetchval("SELECT title FROM obligations WHERE artifact_id = $1 AND action = 'pay'", artifact_id) == "Pay the term fee"
    assert await raw.fetchval("SELECT issuer FROM claims WHERE artifact_id = $1 AND kind = 'document'", artifact_id) == "Passport Office, Chennai"
    assert (await family.client.get("/v1/obligations?status=", headers=family.h("amma"))).status_code == 200      # plain rows read as ever
    monkeypatch.setattr(settings, "seal_extracted_text", True)
    out = await sealing.backfill()
    assert out["sealed"] >= 5
    for table, column in SEALED:
        values = [r["v"] for r in await raw.fetch(f"SELECT {column} AS v FROM {table} WHERE household_id = $1 AND {column} IS NOT NULL", uuid.UUID(family.household["id"]))]
        assert values and all(v.startswith(sealing.PREFIX) for v in values), (table, column)
    assert await database.fetchval("SELECT title FROM obligations WHERE artifact_id = $1 AND action = 'pay'", artifact_id) == "Pay the term fee"
    assert (await sealing.backfill())["sealed"] == 0


async def test_a_sealed_value_cannot_be_moved_to_another_column_and_opened(family, database):
    artifact_id = await _notice_with_everything(family)
    raw = db.raw_pool()
    sealed_title = await raw.fetchval("SELECT title FROM claims WHERE artifact_id = $1 AND kind = 'deadline'", artifact_id)
    hid, column, blob = sealing.parse(sealed_title)
    assert column == sealing.CLAIM_TITLE
    key = await sealing.write_key(raw, hid)
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag: the column name is part of what was signed
        from familyos import crypto
        crypto.open_sealed(key, blob, sealing._aad(hid, sealing.OBLIGATION_TITLE))


# --- the searches that moved out of SQL: same answers with sealed titles ---------------------------------------------------------------

async def test_school_reopens_still_finds_the_reopening_and_the_plans_in_the_way(family, database):
    await _read_notice(family, [
        _claim(kind="event", title="School reopens after the holiday", date=TODAY + dt.timedelta(days=10), quote="School reopens"),
        _claim(kind="event", title="Family trip to Madurai", date=TODAY + dt.timedelta(days=5), quote="Trip to Madurai"),
        _claim(kind="event", title="Science exhibition", date=TODAY + dt.timedelta(days=6), quote="Science exhibition")])
    assert (await db.raw_pool().fetchval("SELECT title FROM obligations WHERE household_id = $1 AND due_date = $2", uuid.UUID(family.household["id"]), TODAY + dt.timedelta(days=5))).startswith("enc:v1:")
    out = await scenarios.school_reopens(_p(family), TODAY + dt.timedelta(days=3))
    assert [i["title"] for i in out["impacts"]] == ["Family trip to Madurai"]
    assert "1 plan" in out["headline"]
    nothing = await scenarios.school_reopens(_p(family), TODAY + dt.timedelta(days=12))
    assert nothing["impacts"] == [] and "not earlier" in nothing["headline"]


async def test_the_trip_soon_routine_still_sees_a_trip_that_starts_that_day(family, database):
    await _read_notice(family, [
        _claim(kind="event", title="Flight to Dubai", date=TODAY + dt.timedelta(days=2), quote="Flight"),
        _claim(kind="event", title="Dentist", date=TODAY + dt.timedelta(days=2), quote="Dentist")])
    local = dt.datetime.combine(TODAY, dt.time(8, 0))
    r = {"trigger": "trip_soon", "trigger_days": 2, "household_id": uuid.UUID(family.household["id"]), "member_id": uuid.UUID(family.amma["id"]),
         "created_at": dt.datetime.now(dt.UTC)}
    seen = await routines._events(r, local)
    assert len(seen) == 1 and "Flight to Dubai" in seen[0][1]


async def test_the_warranty_search_still_finds_an_invoice_that_names_a_warranty(family, database):
    await _read_notice(family, [
        _claim(kind="payment", title="Purchase of Mixer grinder", date=TODAY - dt.timedelta(days=3), quote="Invoice for the mixer grinder"),
        _claim(kind="info", title="2 year warranty on the mixer grinder", quote="Warranty: 2 years")],
        sender="Shop <bills@shop.example.com>", subject="Your invoice")
    await _read_notice(family, [_claim(kind="event", title="Sports day", date=TODAY + dt.timedelta(days=4), quote="Sports day")])
    found = await warranty_hints.waiting(_p(family))
    assert [f["product"] for f in found] == ["Mixer grinder"] and found[0]["warranty_months"] == 24


async def test_a_days_items_keep_their_order_by_time_then_title(family, database):
    from familyos import schoolday
    day = TODAY + dt.timedelta(days=1)
    await _read_notice(family, [
        _claim(kind="event", title="Zebra project", date=day, requires=["parent_attendance"], quote="z"),
        _claim(kind="event", title="Art class", date=day, requires=["parent_attendance"], quote="a"),
        _claim(kind="event", title="Maths test", date=day, time="09:00", requires=["parent_attendance"], quote="m")])
    out = await schoolday.tomorrow(_p(family), on=day)
    titles = [i["title"] for k in out["children"] for i in k["items"]]
    assert titles == ["Maths test", "Art class", "Zebra project"]


# --- export and erasure still see the words ---------------------------------------------------------------------------------------------

async def test_a_childs_export_and_a_consent_withdrawal_work_on_sealed_names(family, database):
    from familyos import jobs
    artifact_id = await _notice_with_everything(family)        # names the child on a claim, but is not tagged with the child: the notice survives a withdrawal
    child = family.older
    exported = await family.client.get(f"/v1/members/{child['id']}/export", headers=family.h("amma"))
    assert exported.status_code == 200
    import io
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(exported.content))
    assert zf.namelist()                                        # the notice that names the child was within reach: its sealed name was matched
    blob = b"".join(zf.read(n) for n in zf.namelist())
    assert b"enc:v1:" not in blob and b"Pay the term fee" in blob
    assert await database.fetchval("SELECT subject_name FROM claims WHERE artifact_id = $1 AND kind = 'deadline'", artifact_id) == child["display_name"]
    r = await family.client.post(f"/v1/consents/{family.consent_id}/withdraw", headers=family.h("appa"))
    assert r.status_code == 202, r.text
    job_id = await database.fetchval("SELECT job_id::text FROM erasure_log WHERE id = $1", r.json()["id"])
    assert (await jobs.attach(job_id.replace("-", "")))["status"] == "succeeded"
    assert await database.fetchval("SELECT subject_name FROM claims WHERE artifact_id = $1 AND kind = 'deadline'", artifact_id) is None      # the name went; the fact stays
    assert await database.fetchval("SELECT count(*) FROM claims WHERE artifact_id = $1", artifact_id) == 3


def test_no_sql_in_the_application_searches_or_sorts_a_sealed_column():
    """A sealed value is random ciphertext, so a predicate or an ORDER BY on it silently stops working. Selecting it is fine (the pool opens it)."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent / "familyos"
    column = r"\b(?:o|c|obl|claims|obligations)\.(?:title|subject_name|issuer)\b"
    bad = [re.compile(column + r"\s*(?:~\*?|!~\*?|(?:NOT\s+)?I?LIKE|=|<>|!=|IN)(?=[\s(])"),
           re.compile(r"\b(?:lower|upper|btrim|trim|left|substr|substring|length|position|initcap)\(\s*" + column),
           re.compile(r"ORDER BY[^\"'\n]*" + column), re.compile(r"GROUP BY[^\"'\n]*" + column), re.compile(r"DISTINCT\s+" + column)]
    found = []
    for path in root.rglob("*.py"):
        if path.name == "sealing.py":
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if any(rx.search(line) for rx in bad):
                found.append(f"{path.relative_to(root.parent)}:{n}: {line.strip()[:100]}")
    assert not found, "SQL on a sealed column:\n" + "\n".join(found)
