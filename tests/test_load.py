"""Who the arriving work lands on, counted rather than asked."""
import datetime as dt
import uuid

from familyos import load
from familyos.identity import Principal
from tests.conftest import pdf

TODAY = dt.date.today()


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def _arrived(database, family, *, who="amma", title="Consent form", action="sign",
                   decided_by=None, status="proposed", due=None):
    """A notice somebody brought in, and the obligation read out of it."""
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload(who, pdf(title), visibility="shared")).json()["artifact"]["id"])
    extraction_id, claim_id, obligation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)",
        extraction_id, household_id, artifact_id)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, "
        "confidence) VALUES ($1, $2, $3, $4, 0, 'event', $5, 'the words', 0.9)",
        claim_id, extraction_id, household_id, artifact_id, title)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, "
        "status, decided_by, decided_at) VALUES ($1, $2, $3, $4, 'task', $5, $6, $7, $8, $9, $10)",
        obligation_id, household_id, artifact_id, claim_id, action, title, due or TODAY + dt.timedelta(days=5),
        status, uuid.UUID(decided_by) if decided_by else None,
        dt.datetime.now(dt.UTC) if decided_by else None)
    return obligation_id


async def test_nothing_arrived_is_said_plainly(family):
    out = await load.share(_principal(family))
    assert out["total"] == 0 and out["members"] == []
    assert "not a judgement" in out["note"]


async def test_bringing_a_notice_in_counts_as_noticing_it(family, database):
    await _arrived(database, family, who="amma")
    out = await load.share(_principal(family))
    [amma] = out["members"]
    assert amma["display_name"] == "Amma"
    assert amma["noticed"] == 1 and amma["decided"] == 0 and amma["carried"] == 1
    assert amma["share"] == 100


async def test_deciding_somebody_elses_notice_divides_the_load(family, database):
    """The point of the measure: Appa forwards it, Amma is the one who deals
    with it, and both show up."""
    await _arrived(database, family, who="appa", decided_by=family.amma["id"], status="accepted")
    out = await load.share(_principal(family))
    by_name = {m["display_name"]: m for m in out["members"]}
    assert by_name["Appa"]["noticed"] == 1 and by_name["Appa"]["decided"] == 0
    assert by_name["Amma"]["decided"] == 1 and by_name["Amma"]["noticed"] == 0
    assert by_name["Appa"]["share"] == 50 and by_name["Amma"]["share"] == 50


async def test_one_member_doing_everything_shows_as_everything(family, database):
    for n in range(3):
        await _arrived(database, family, who="amma", title=f"Form {n}",
                       decided_by=family.amma["id"], status="accepted")
    await _arrived(database, family, who="appa", title="One thing")
    out = await load.share(_principal(family))
    by_name = {m["display_name"]: m for m in out["members"]}
    # Amma touched three of four; Appa one. Shares are of attended work.
    assert by_name["Amma"]["carried"] == 3 and by_name["Appa"]["carried"] == 1
    assert by_name["Amma"]["share"] == 75 and by_name["Appa"]["share"] == 25
    # And she is listed first, because the point is who is carrying it.
    assert out["members"][0]["display_name"] == "Amma"


async def test_work_nobody_touched_is_the_number_that_matters(family, database):
    """Neither competitor can report this: a pull model only knows what was
    entered, and entered work has by definition been attended to."""
    await _arrived(database, family, who="amma", title="Decided", decided_by=family.amma["id"],
                   status="accepted")
    await _arrived(database, family, who="amma", title="Ignored", status="proposed")
    await _arrived(database, family, who="amma", title="Gone past", status="proposed",
                   due=TODAY - dt.timedelta(days=3))

    out = await load.share(_principal(family))
    assert out["total"] == 3
    assert out["undecided"] == 2
    assert out["missed"] == 1


async def test_approving_a_reply_counts_as_doing_it(family, database, monkeypatch):
    from familyos import actions, mail
    from familyos.settings import settings

    sent = []

    async def fake(to, subject, body, *, ics=None):
        sent.append(to)

    monkeypatch.setattr(mail, "send", fake)
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(settings, "actions_enabled", True)

    obligation_id = await _arrived(database, family, who="amma", action="submit",
                                   decided_by=family.amma["id"], status="accepted")
    await database.execute(
        "UPDATE input_artifacts SET channel = 'gmail', "
        "source = jsonb_build_object('from', 'office@school.example.com') "
        "WHERE id = (SELECT artifact_id FROM obligations WHERE id = $1)", obligation_id)

    a = await actions.propose(_principal(family, "appa"), obligation_id, "reply", "Yes.")
    await actions.approve(_principal(family, "appa"), a["id"], a["params_sha256"])

    out = await load.share(_principal(family))
    by_name = {m["display_name"]: m for m in out["members"]}
    assert by_name["Appa"]["acted"] == 1
    assert by_name["Amma"]["decided"] == 1


async def test_only_what_a_member_may_see_is_counted(family, database):
    """Private notices stay private, including in a number about the household."""
    r = await family.upload("appa", pdf("his own"), visibility="private")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    e, c, o = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", e, household_id, artifact_id)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, "
        "confidence) VALUES ($1, $2, $3, $4, 0, 'event', 'Private thing', 'words', 0.9)",
        c, e, household_id, artifact_id)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, status) "
        "VALUES ($1, $2, $3, $4, 'task', 'sign', 'Private thing', $5, 'proposed')",
        o, household_id, artifact_id, c, TODAY)

    assert (await load.share(_principal(family, "appa")))["total"] == 1
    assert (await load.share(_principal(family, "amma")))["total"] == 0
