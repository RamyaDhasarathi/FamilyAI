"""Accounts a family pays, and the bill that did not arrive."""
import datetime as dt
import uuid

import pytest

from familyos import billers, brief
from familyos.identity import Invalid, Principal
from tests.conftest import pdf

TODAY = dt.date.today()


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def _bill(database, family, *, title, quote, when=None, due=None):
    """A notice read as a payment, which is what a biller matches against."""
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload("amma", pdf(title), visibility="shared")).json()["artifact"]["id"])
    extraction_id, claim_id, obligation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)",
        extraction_id, household_id, artifact_id)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, "
        "confidence) VALUES ($1, $2, $3, $4, 0, 'payment', $5, $6, 0.9)",
        claim_id, extraction_id, household_id, artifact_id, title, quote)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, "
        "status, created_at) VALUES ($1, $2, $3, $4, 'task', 'pay', $5, $6, 'accepted', $7)",
        obligation_id, household_id, artifact_id, claim_id, title, due or TODAY + dt.timedelta(days=5),
        when or dt.datetime.now(dt.UTC))
    return obligation_id


# ----------------------------------------------------------------------------
# the consumer number is never stored
# ----------------------------------------------------------------------------

async def test_the_consumer_number_is_not_kept_anywhere(family, database):
    await billers.add(_principal(family), label="Electricity", provider="BSES Rajdhani",
                      identifier="1502 7734 0091")
    row = await database.fetchrow("SELECT * FROM billers")
    assert row["identifier_hint"] == "0091"
    assert row["identifier_mac"] is not None
    # Not in the row, and not in the audit trail.
    blob = str(dict(row)) + str([dict(r) for r in await database.fetch("SELECT * FROM audit_events")])
    assert "1502" not in blob and "150277340091" not in blob


async def test_the_digest_is_keyed_so_a_ten_digit_number_cannot_be_guessed(family, database):
    """A plain hash of a consumer number falls to a dictionary in seconds."""
    from hashlib import sha256
    await billers.add(_principal(family), label="Gas", provider="Indraprastha Gas",
                      identifier="9876543210")
    mac = await database.fetchval("SELECT identifier_mac FROM billers")
    assert mac != sha256(b"9876543210").digest()


async def test_the_same_account_is_not_tracked_twice_however_it_is_typed(family):
    me = _principal(family)
    await billers.add(me, label="Electricity", provider="BSES", identifier="1502-7734-0091")
    with pytest.raises(Invalid):
        await billers.add(me, label="Electricity again", provider="BSES", identifier="150277340091")


# ----------------------------------------------------------------------------
# matching what arrived
# ----------------------------------------------------------------------------

async def test_a_bill_that_names_the_provider_marks_it_seen(family, database):
    b = await billers.add(_principal(family), label="Electricity", provider="BSES Rajdhani")
    await _bill(database, family, title="BSES Rajdhani electricity bill",
                quote="Amount due Rs 2,410 by 20 November")
    assert await billers.note_arrivals(uuid.UUID(family.household["id"])) == 1
    assert (await database.fetchval("SELECT last_seen_at FROM billers WHERE id = $1", b["id"])) is not None


async def test_a_bill_that_names_only_the_consumer_number_still_matches(family, database):
    b = await billers.add(_principal(family), label="Gas", provider="Indraprastha Gas",
                          identifier="9876543210")
    # The notice says the number, written with spaces, and never the provider.
    await _bill(database, family, title="Your monthly statement",
                quote="Consumer no 9876 543 210, amount Rs 812 due 12 November")
    assert await billers.note_arrivals(uuid.UUID(family.household["id"])) == 1
    assert (await database.fetchval("SELECT last_seen_at FROM billers WHERE id = $1", b["id"])) is not None


async def test_an_unrelated_bill_does_not_mark_it_seen(family, database):
    """A missed match nudges; a wrong match says nothing at all, which is
    worse."""
    await billers.add(_principal(family), label="Gas", provider="Indraprastha Gas", identifier="9876543210")
    await _bill(database, family, title="School fee", quote="Term fee Rs 18,000 due 5 November")
    assert await billers.note_arrivals(uuid.UUID(family.household["id"])) == 0


# ----------------------------------------------------------------------------
# the bill that did not arrive
# ----------------------------------------------------------------------------

async def test_a_bill_later_than_usual_reaches_the_brief(family, database):
    b = await billers.add(_principal(family), label="Electricity", provider="BSES Rajdhani",
                          every_days=30, grace_days=7)
    await database.execute("UPDATE billers SET last_seen_at = NOW() - interval '45 days' WHERE id = $1", b["id"])

    late = await billers.missing(_principal(family))
    assert [r["label"] for r in late] == ["Electricity"]
    assert late[0]["days_late"] == 15

    out = await brief.today(_principal(family), limit=50)
    item = next(i for i in out["items"] if i["reason"] == "unbilled")
    assert item["title"] == "No electricity bill from BSES Rajdhani"
    assert "15 days later" in item["why"]
    assert item["biller_id"] == b["id"]


async def test_within_the_grace_period_nothing_is_said(family, database):
    b = await billers.add(_principal(family), label="Electricity", provider="BSES", every_days=30, grace_days=7)
    await database.execute("UPDATE billers SET last_seen_at = NOW() - interval '34 days' WHERE id = $1", b["id"])
    assert await billers.missing(_principal(family)) == []


async def test_an_account_never_seen_says_nothing(family, database):
    """We have no idea when its bill is due, and inventing a date would be
    worse than silence."""
    await billers.add(_principal(family), label="Water", provider="Delhi Jal Board")
    assert await billers.missing(_principal(family)) == []


async def test_muting_an_account_ends_it(family, database):
    b = await billers.add(_principal(family), label="Electricity", provider="BSES", every_days=30)
    await database.execute("UPDATE billers SET last_seen_at = NOW() - interval '60 days' WHERE id = $1", b["id"])
    assert len(await billers.missing(_principal(family))) == 1
    await billers.forget(_principal(family), b["id"])
    assert await billers.missing(_principal(family)) == []
    assert await billers.list_for(_principal(family)) == []


# ----------------------------------------------------------------------------
# who sees what
# ----------------------------------------------------------------------------

async def test_a_private_account_is_the_members_own(family, database):
    await billers.add(_principal(family), label="Life insurance", provider="LIC", visibility="private")
    assert len(await billers.list_for(_principal(family, "amma"))) == 1
    assert await billers.list_for(_principal(family, "appa")) == []


async def test_bills_are_the_payments_a_member_can_already_see(family, database):
    await _bill(database, family, title="BSES electricity bill", quote="Rs 2,410")
    rows = await billers.bills(_principal(family))
    assert [r["title"] for r in rows] == ["BSES electricity bill"]


async def test_the_whole_thing_over_http(family):
    r = await family.client.post("/v1/billers", headers=family.h("amma"), json={
        "label": "Electricity", "provider": "BSES Rajdhani", "identifier": "1502 7734 0091",
        "every_days": 30})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["identifier_hint"] == "0091" and "identifier" not in body

    listed = await family.client.get("/v1/billers", headers=family.h("amma"))
    assert [b["id"] for b in listed.json()] == [body["id"]]
    assert (await family.client.get("/v1/bills", headers=family.h("amma"))).status_code == 200
    assert (await family.client.delete(f"/v1/billers/{body['id']}", headers=family.h("amma"))).status_code == 200


def test_an_amount_is_not_mistaken_for_an_account_number():
    """The first version normalised the whole line first, which welded every
    number on the page into one run."""
    assert billers.candidates("Consumer no 9876 543 210, amount Rs 812 due 12 November") == ["9876543210"]
    assert billers.candidates("BSES 1502-7734-0091 bill") == ["150277340091"]
    assert billers.candidates("Account CA1502773400 for November") == ["ca1502773400"]
    # An amount, a date and a short reference are not account numbers.
    assert billers.candidates("Term fee Rs 18,000 due 5 November") == []
