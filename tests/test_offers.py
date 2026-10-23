"""Offers: what FamilyOS could start doing, said in the family's names.
Derived from the record each time; Accept flips the switch or hands Ask the
question; Not now is remembered."""
import datetime as dt
import uuid

import pytest

from familyos import notify, offers
from familyos.identity import Principal

TODAY = dt.date(2026, 10, 10)


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    async def member(member_id, subject, body):
        return "test"
    monkeypatch.setattr(notify, "member", member)


async def _bill(database, family, title, due, *, handled_by=None, status="accepted", visibility="shared", kind="task", action="pay"):
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload("amma", b"%PDF-1.4 " + title.encode(), visibility=visibility)).json()["artifact"]["id"])
    if handled_by:
        await database.execute("UPDATE input_artifacts SET handled_by = $2, handled_at = NOW() WHERE id = $1", artifact_id, uuid.UUID(handled_by))
    extraction_id, claim_id, obligation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) "
        "VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", extraction_id, household_id, artifact_id)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'payment', $5, 'the words', 0.9)", claim_id, extraction_id, household_id, artifact_id, title)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, due_time, status) "
        "VALUES ($1, $2, $3, $4, $8, $9, $5, $6, NULL, $7)", obligation_id, household_id, artifact_id, claim_id, title, due, status, kind, action)
    return obligation_id


async def test_the_adult_who_handles_the_bills_is_offered_them_by_default(family, database):
    for i, due in enumerate([TODAY - dt.timedelta(days=40), TODAY - dt.timedelta(days=10), TODAY + dt.timedelta(days=20)]):
        await _bill(database, family, f"Airtel bill {i}", due, handled_by=family.appa["id"])
    found = await offers.for_member(_p(family), today=TODAY)
    bills = next(o for o in found if o["key"].startswith("bills_to:"))
    assert bills["kind"] == "rule" and "Appa handled the last 3 bills" in bills["title"] and bills["accept_label"] == "Hand bills to Appa"
    assert "Nothing is paid" in bills["limit"]
    # Accepting sets the household's rule, and the offer is gone.
    r = await family.client.post(f"/v1/offers/{bills['key']}/accept", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    assert r.json()["done"].endswith(": on.")
    assert str(await database.fetchval("SELECT bills_handed_to FROM households WHERE id = $1", uuid.UUID(family.household["id"]))) == family.appa["id"]
    assert not any(o["key"].startswith("bills_to:") for o in await offers.for_member(_p(family), today=TODAY))
    # The rule is a guardian's to set: an adult who is not one is not offered it.
    assert not any(o["key"].startswith("bills_to:") for o in await offers.for_member(_p(family, "paati"), today=TODAY))


async def test_a_bill_due_soon_is_told_once_that_its_receipt_will_close_it(family, database):
    oid = await _bill(database, family, "Pay the electricity bill", TODAY + dt.timedelta(days=5))
    found = await offers.for_member(_p(family), today=TODAY)
    fyi = next(o for o in found if o["key"] == f"closes:{oid}")
    assert fyi["fyi"] and fyi["accept_label"] is None and "stop reminding" in fyi["title"]
    r = await family.client.post(f"/v1/offers/{fyi['key']}/dismiss", headers=family.h("amma"))
    assert r.status_code == 204
    assert f"closes:{oid}" not in [o["key"] for o in await offers.for_member(_p(family), today=TODAY)]
    # With the switch off it is an offer to switch it on, and accepting does.
    await database.execute("UPDATE households SET receipts_close_bills = FALSE WHERE id = $1", uuid.UUID(family.household["id"]))
    oid2 = await _bill(database, family, "Pay the water bill", TODAY + dt.timedelta(days=3))
    ask = next(o for o in await offers.for_member(_p(family), today=TODAY) if o["key"] == f"closes:{oid2}")
    assert not ask["fyi"] and ask["accept_label"]
    r = await family.client.post(f"/v1/offers/{ask['key']}/accept", headers=family.h("amma"))
    assert r.status_code == 200 and await database.fetchval("SELECT receipts_close_bills FROM households WHERE id = $1", uuid.UUID(family.household["id"]))


async def test_a_plan_on_an_accepted_date_is_offered_a_check_in_ask(family, database):
    household_id = uuid.UUID(family.household["id"])
    await _bill(database, family, "Reopening of School", TODAY + dt.timedelta(days=11), kind="calendar", action="attend")
    await _bill(database, family, "Pay the fee", TODAY + dt.timedelta(days=10))   # a bill that week is not a clash
    await database.execute(
        "INSERT INTO plans (id, household_id, created_by, title, brief, status, shape, starts_on, ends_on) "
        "VALUES ($1, $2, $3, 'Five Days in Madurai', 'a trip', 'draft', 'trip', $4, $5)",
        uuid.uuid4(), household_id, uuid.UUID(family.amma["id"]), TODAY + dt.timedelta(days=8), TODAY + dt.timedelta(days=12))
    found = await offers.for_member(_p(family), today=TODAY)
    over = next(o for o in found if o["key"].startswith("overlap:"))
    assert "Five Days in Madurai" in over["title"] and "Reopening of School" in over["title"] and over["kind"] == "ask"
    assert "Pay the fee" not in over["title"]
    r = await family.client.post(f"/v1/offers/{over['key']}/accept", headers=family.h("amma"))
    assert r.status_code == 200 and "clash with Reopening of School" in r.json()["ask"]
    assert not any(o["key"].startswith("overlap:") for o in await offers.for_member(_p(family), today=TODAY))


async def test_a_sender_gone_quiet_is_said_once(family, database):
    household_id = uuid.UUID(family.household["id"])
    for i in range(5):
        aid = uuid.UUID((await family.upload("amma", b"%PDF-1.4 circular " + str(i).encode(), visibility="shared")).json()["artifact"]["id"])
        await database.execute("UPDATE input_artifacts SET channel = 'gmail', source = $2, received_at = $3 WHERE id = $1",
                               aid, {"from": "office@school.example"}, dt.datetime.combine(TODAY - dt.timedelta(days=60 - 7 * i), dt.time(9), tzinfo=dt.UTC))
    found = await offers.for_member(_p(family), today=TODAY)
    quiet = next(o for o in found if o["key"].startswith("rhythm:school.example:"))
    assert quiet["fyi"] and "every 7 days" in quiet["title"] and "say so once" in quiet["limit"]
    assert len(found) <= offers.MOST
    assert (await family.client.get("/v1/offers", headers=family.h("amma"))).status_code == 200
