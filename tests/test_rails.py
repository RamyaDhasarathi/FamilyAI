"""Outcome-scored rails: each school notice is recorded with the rail it came
by and whether it was first or an echo; the score per rail is computed from
those rows, and the family is shown the numbers."""
import datetime as dt
import uuid

import pytest

from familyos import notify, offers, rails
from familyos.db import pool
from familyos.identity import Principal

TODAY = dt.date(2026, 10, 11)


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    async def member(member_id, subject, body):
        return "test"
    monkeypatch.setattr(notify, "member", member)


@pytest.mark.parametrize("channel,source,rail", [
    ("share", {"via": "share", "note": "read from MyClassBoard school app by the phone"}, "school_app"),
    ("share", {"via": "share", "headline": "screen 1 of MyClassBoard school app, taken by the phone"}, "school_app"),
    ("share", {"via": "share"}, "share"),
    ("whatsapp", {"from_name": "Priya"}, "whatsapp"),
    ("whatsapp_media", {}, "whatsapp"),
    ("gmail", {"from": "office@school.example"}, "mail"),
    ("gmail_attachment", {}, "mail"),
    ("telegram", {}, "telegram"),
    ("harvest", {}, "portal"),
    ("upload", {}, "console"),
    ("errand", {"errand_id": "x"}, None),
])
def test_the_rail_is_read_off_how_the_notice_arrived(channel, source, rail):
    assert rails.rail_of(channel, source) == rail


def test_the_score_is_beta_smoothed_so_an_unseen_rail_sits_at_the_prior():
    assert rails.score(0, 0, 0) == 0.5
    assert rails.score(9, 0, 0) == round(10 / 11, 3)
    assert rails.score(1, 8, 0) < rails.score(1, 0, 0)
    assert rails.similar("PTM on Friday for Grade 4", "Parent-Teacher Meeting (PTM) Friday, Grade 4") is True
    assert rails.similar("Term 2 fee", "Diwali holidays") is False


async def _school_notice(database, family, *, channel, source, title, due, received, school_id, child_id):
    """A notice for a child of the school, with one dated obligation, arrived by a rail."""
    household_id = uuid.UUID(family.household["id"])
    aid = uuid.UUID((await family.upload("amma", b"%PDF-1.4 " + title.encode() + received.isoformat().encode(), visibility="shared")).json()["artifact"]["id"])
    await database.execute("UPDATE input_artifacts SET channel = $2, source = $3, received_at = $4 WHERE id = $1",
                           aid, channel, source, dt.datetime.combine(received, dt.time(9), tzinfo=dt.UTC))
    await database.execute("INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, TRUE) ON CONFLICT DO NOTHING", aid, child_id)
    extraction_id, claim_id, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) "
        "VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", extraction_id, household_id, aid)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'event', $5, 'the words', 0.9)", claim_id, extraction_id, household_id, aid, title)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, status) "
        "VALUES ($1, $2, $3, $4, $5, 'calendar', 'attend', $6, $7, 'proposed')", oid, household_id, aid, claim_id, child_id, title, due)
    row = dict(await database.fetchrow("SELECT * FROM input_artifacts WHERE id = $1", aid))
    async with pool().acquire() as conn, conn.transaction():
        out = await rails.record(conn, household_id, row, [child_id], [(oid, household_id, aid, claim_id, child_id, "calendar", "attend", title, due, None, None, False, None)])
    return aid, out


async def test_the_first_rail_to_carry_a_date_is_first_and_the_rest_are_echoes(family, database):
    household_id = uuid.UUID(family.household["id"])
    school_id = uuid.uuid4()
    await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Aachi Global School')", school_id, household_id)
    child_id = uuid.UUID(family.older["id"])
    await database.execute("UPDATE members SET school_id = $2 WHERE id = $1", child_id, school_id)
    app = {"via": "share", "note": "read from MyClassBoard school app by the phone"}
    # The app read brings the PTM first; the WhatsApp forward the next day says the same thing.
    a1, out1 = await _school_notice(database, family, channel="share", source=app, title="Parent-Teacher Meeting (PTM) on Friday",
                                    due=dt.date(2026, 10, 9), received=dt.date(2026, 10, 6), school_id=school_id, child_id=child_id)
    a2, out2 = await _school_notice(database, family, channel="whatsapp", source={"from_name": "Priya"}, title="PTM this Friday, Grade 4",
                                    due=dt.date(2026, 10, 9), received=dt.date(2026, 10, 7), school_id=school_id, child_id=child_id)
    assert out1 == {"rail": "school_app", "outcome": "first", "school_id": school_id, "echo_of": None}
    assert out2["rail"] == "whatsapp" and out2["outcome"] == "echo" and out2["echo_of"] == a1
    # A different date on the same rail is first again; a notice with nothing dated is empty.
    _, out3 = await _school_notice(database, family, channel="whatsapp", source={}, title="Diwali holidays 20 to 24 October",
                                   due=dt.date(2026, 10, 20), received=dt.date(2026, 10, 8), school_id=school_id, child_id=child_id)
    assert out3["outcome"] == "first"
    scored = await rails.for_school(_p(family), school_id)
    by = {r["rail"]: r for r in scored}
    assert by["school_app"]["first"] == 1 and by["whatsapp"]["first"] == 1 and by["whatsapp"]["echo"] == 1
    assert by["school_app"]["score"] > by["whatsapp"]["score"]
    # The summary says it in a sentence, and the route serves it.
    summary = (await family.client.get("/v1/rails", headers=family.h("amma"))).json()
    assert summary[0]["school"] == "Aachi Global School" and summary[0]["notices"] == 3 and summary[0]["first"] == 2
    assert summary[0]["said"].startswith("For Aachi Global School, the school app, read by the phone brought 1 of 3 notices first")
    assert "WhatsApp echoed 1" in summary[0]["said"]


async def test_a_notice_that_belongs_to_no_school_is_not_a_rail_delivery(family, database):
    household_id = uuid.UUID(family.household["id"])
    aid = uuid.UUID((await family.upload("amma", b"%PDF-1.4 bill", visibility="shared")).json()["artifact"]["id"])
    row = dict(await database.fetchrow("SELECT * FROM input_artifacts WHERE id = $1", aid))
    async with pool().acquire() as conn, conn.transaction():
        assert await rails.record(conn, household_id, row, [], []) is None
    assert await database.fetchval("SELECT count(*) FROM rail_deliveries") == 0


async def test_once_a_school_has_enough_notices_the_family_is_told_where_they_come_from(family, database):
    household_id = uuid.UUID(family.household["id"])
    school_id = uuid.uuid4()
    await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Aachi Global School')", school_id, household_id)
    child_id = uuid.UUID(family.older["id"])
    await database.execute("UPDATE members SET school_id = $2 WHERE id = $1", child_id, school_id)
    app = {"via": "share", "note": "read from MyClassBoard school app by the phone"}
    for i in range(4):
        await _school_notice(database, family, channel="share", source=app, title=f"Circular {i} on sports day",
                             due=dt.date(2026, 10, 12 + i), received=dt.date(2026, 10, 1 + i), school_id=school_id, child_id=child_id)
    found = await offers.for_member(_p(family), today=TODAY)
    card = next(o for o in found if o["key"] == f"rails:{school_id}:2026-10")
    assert card["fyi"] and card["title"].startswith("For Aachi Global School, the school app, read by the phone brought 4 of 4 notices first")
