"""The phone's own reminders: what it should schedule, with the words of the day each fires."""
import datetime as dt
import uuid

from familyos import clock, reminders
from familyos.identity import Principal

TODAY = clock.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def _obligation(family, database, title, due, status="accepted", visibility="shared", who="amma"):
    r = await family.upload(who, f"%PDF-1.4 {title} {uuid.uuid4()}".encode(), filename="n.pdf", visibility=visibility)
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    extraction_id, claim_id, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute("INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", extraction_id, household_id, artifact_id)
    await database.execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, date, quote, confidence) VALUES ($1, $2, $3, $4, 0, 'deadline', $5, $6, 'q', 0.9)", claim_id, extraction_id, household_id, artifact_id, title, due)
    await database.execute("INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, status) VALUES ($1, $2, $3, $4, 'task', 'pay', $5, $6, $7)", oid, household_id, artifact_id, claim_id, title, due, status)
    return artifact_id, oid


async def test_the_phone_is_told_each_lead_day_with_the_words_of_the_day_it_fires(family, database):
    due = TODAY + dt.timedelta(days=5)
    artifact_id, oid = await _obligation(family, database, "Pay the term fee", due)
    feed = await reminders.for_phone(_p(family))
    mine = [f for f in feed if f["obligation_id"] == oid]
    leads = reminders.lead_days()
    assert {f["key"] for f in mine} == {f"{oid}:{lead}:due" for lead in leads if TODAY <= due - dt.timedelta(days=lead)}
    on_the_day = [f for f in mine if f["fire_on"] == due]
    assert on_the_day and "is due today" in on_the_day[0]["body"] and on_the_day[0]["artifact_id"] == artifact_id
    ahead = [f for f in mine if f["fire_on"] < due]
    assert all("is due" in f["body"] and "today" not in f["body"] or f["fire_on"] == due for f in ahead)


async def test_only_what_the_member_may_see_is_offered_and_a_decided_or_far_one_is_not(family, database):
    await _obligation(family, database, "Private thing", TODAY + dt.timedelta(days=2), visibility="private", who="amma")
    await _obligation(family, database, "Dismissed thing", TODAY + dt.timedelta(days=2), status="dismissed")
    await _obligation(family, database, "Far thing", TODAY + dt.timedelta(days=90))
    mine = [f["title"] for f in await reminders.for_phone(_p(family, "amma"))]
    others = [f["title"] for f in await reminders.for_phone(_p(family, "appa"))]
    assert any("Private thing" in t for t in mine) and not any("Private thing" in t for t in others)
    assert not any("Dismissed" in t or "Far thing" in t for t in mine)


async def test_the_route_returns_the_feed_and_a_child_gets_nothing(family, database):
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=1))
    r = await family.client.get("/v1/reminders/phone", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    assert any("bus fee" in x["title"] for x in r.json())
    assert await reminders.for_phone(Principal(member_id=uuid.UUID(family.older["id"]), household_id=uuid.UUID(family.household["id"]), role="child", display_name="x")) == []
