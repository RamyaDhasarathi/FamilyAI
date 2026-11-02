"""Delegation: the carer sees the pickup and never the notice."""
import datetime as dt
import json
import uuid

import pytest

from familyos import ask, brief, clock, finance, grants, graph, schoolday
from familyos.identity import Invalid, NotAllowed, NotFound

TOMORROW = clock.today() + dt.timedelta(days=1)


def _principal(family, who="amma"):
    from familyos.identity import Principal
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def _obligation(database, family, *, subject=None, action="attend", title="Sports day pickup"):
    """A private notice from Amma, and one obligation read out of it."""
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload("amma", b"%PDF-1.4 notice " + title.encode())).json()["artifact"]["id"])
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
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, "
        "title, due_date, status) VALUES ($1, $2, $3, $4, $5, 'task', $6, $7, $8, 'accepted')",
        obligation_id, household_id, artifact_id, claim_id,
        uuid.UUID(subject["id"]) if subject else None, action, title, TOMORROW)
    return obligation_id, artifact_id


async def _titles(family, who):
    """What this member's brief shows them."""
    b = await brief.today(_principal(family, who), limit=50)
    return {i["title"] for i in b["items"]}


# ----------------------------------------------------------------------------
# the rule
# ----------------------------------------------------------------------------

async def test_without_a_grant_a_member_sees_nothing_private_of_anothers(family, database):
    await _obligation(database, family, subject=family.older)
    assert await _titles(family, "paati") == set()


async def test_a_grant_shows_the_obligation_and_never_the_notice(family, database):
    _, artifact_id = await _obligation(database, family, subject=family.older)
    await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                       actions=["attend"], reason="School pickup, Tue and Thu",
                       subject_member_id=uuid.UUID(family.older["id"]))

    assert "Sports day pickup" in await _titles(family, "paati")
    # The notice itself stays out of reach: a grant never widens the artifact rule.
    r = await family.client.get(f"/v1/artifacts/{artifact_id}", headers=family.h("paati"))
    assert r.status_code == 404


async def test_a_grant_is_bounded_by_action(family, database):
    await _obligation(database, family, subject=family.older, action="pay", title="Trip fee")
    await _obligation(database, family, subject=family.older, action="attend", title="Trip pickup")
    await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                       actions=["attend"], reason="Pickup only",
                       subject_member_id=uuid.UUID(family.older["id"]))

    seen = await _titles(family, "paati")
    assert "Trip pickup" in seen
    assert "Trip fee" not in seen


async def test_a_grant_is_bounded_by_subject(family, database):
    await _obligation(database, family, subject=family.older, title="Older one pickup")
    await _obligation(database, family, subject=family.younger, title="Younger one pickup")
    await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                       actions=["attend"], reason="Only the older one",
                       subject_member_id=uuid.UUID(family.older["id"]))

    seen = await _titles(family, "paati")
    assert "Older one pickup" in seen
    assert "Younger one pickup" not in seen


async def test_an_obligation_about_nobody_matches_no_subject_scoped_grant(family, database):
    """The safe direction: a carer scoped to one child does not silently pick
    up items the extractor could not attribute."""
    await _obligation(database, family, subject=None, title="Unattributed notice")
    await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                       actions=["attend"], reason="Pickup",
                       subject_member_id=uuid.UUID(family.older["id"]))
    assert "Unattributed notice" not in await _titles(family, "paati")


# ----------------------------------------------------------------------------
# lifecycle
# ----------------------------------------------------------------------------

async def test_expiry_ends_it_without_a_sweep(family, database):
    await _obligation(database, family, subject=family.older)
    g = await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                           actions=["attend"], reason="Term time only",
                           subject_member_id=uuid.UUID(family.older["id"]), days=30)
    assert await _titles(family, "paati") != set()

    await database.execute("UPDATE grants SET expires_at = NOW() - interval '1 day' WHERE id = $1", g["id"])
    # Nothing ran. Expiry is a comparison in the read path.
    assert await _titles(family, "paati") == set()


async def test_revocation_is_instant(family, database):
    await _obligation(database, family, subject=family.older)
    g = await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                           actions=["attend"], reason="Pickup",
                           subject_member_id=uuid.UUID(family.older["id"]))
    assert await _titles(family, "paati") != set()

    r = await family.client.delete(f"/v1/grants/{g['id']}", headers=family.h("amma"))
    assert r.status_code == 200
    assert await _titles(family, "paati") == set()


async def test_only_a_guardian_grants_or_revokes(family, database):
    with pytest.raises(NotAllowed):
        await grants.issue(_principal(family, "paati"), grantee_member_id=uuid.UUID(family.appa["id"]),
                           actions=["attend"], reason="nope")
    g = await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                           actions=["attend"], reason="Pickup")
    assert (await family.client.delete(f"/v1/grants/{g['id']}", headers=family.h("paati"))).status_code == 403


async def test_a_grant_needs_actions_a_reason_and_somebody_else(family):
    me = _principal(family)
    paati = uuid.UUID(family.paati["id"])
    for bad in ({"actions": [], "reason": "x"},
                {"actions": ["attend"], "reason": "   "},
                {"actions": ["teleport"], "reason": "x"},
                {"actions": ["attend"], "reason": "x", "days": 0},
                {"actions": ["attend"], "reason": "x", "days": 400}):
        with pytest.raises(Invalid):
            await grants.issue(me, grantee_member_id=paati, **bad)
    with pytest.raises(Invalid):
        await grants.issue(me, grantee_member_id=uuid.UUID(family.amma["id"]), actions=["attend"], reason="self")


async def test_a_child_cannot_be_granted_anything(family):
    with pytest.raises(Invalid):
        await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.older["id"]),
                           actions=["attend"], reason="no")


async def test_every_member_can_read_who_holds_what(family, database):
    await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                       actions=["attend"], reason="School pickup, Tue and Thu",
                       subject_member_id=uuid.UUID(family.older["id"]))
    # Not guardians-only: who can see things about you is yours to know.
    r = await family.client.get("/v1/grants", headers=family.h("paati"))
    assert r.status_code == 200
    [row] = r.json()
    assert row["grantee_name"] == "Paati"
    assert row["subject_name"] == "Older one"
    assert row["reason"] == "School pickup, Tue and Thu"


async def test_the_audit_records_the_grant_without_the_reason_text(family, database):
    g = await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]),
                           actions=["attend"], reason="School pickup for the older one",
                           subject_member_id=uuid.UUID(family.older["id"]))
    await grants.revoke(_principal(family), g["id"])
    rows = await database.fetch(
        "SELECT action, detail FROM audit_events WHERE action LIKE 'grant.%' ORDER BY at")
    assert [r["action"] for r in rows] == ["grant.issued", "grant.revoked"]
    assert "older one" not in " ".join(str(r["detail"]) for r in rows).lower()


async def test_a_grant_in_one_household_never_shows_another_households_obligations(client, family, database):
    """A grant widens what a member sees INSIDE their own household. It must never reach across: anyone can found a household, add an adult and
    grant them everything, so a clause that forgot the household would be a read of every family's dates."""
    from tests.conftest import Family
    await _obligation(database, family, subject=family.older, action="attend", title="Other family's secret pickup")
    other = await Family(client).setup(name="Neighbours", guardian_email="neighbour@example.com")
    adult = (await client.post("/v1/household/members", headers=other.h("amma"), json={"display_name": "Visitor", "role": "adult", "email": "visitor@example.com"})).json()
    await grants.issue(_principal(other), grantee_member_id=uuid.UUID(adult["member"]["id"]), actions=list(grants.ACTIONS[:-1]), reason="all of them")
    from familyos.identity import Principal
    visitor = Principal(member_id=uuid.UUID(adult["member"]["id"]), household_id=uuid.UUID(other.household["id"]), role="adult", display_name="Visitor")
    titles = {i["title"] for i in (await brief.today(visitor, limit=50))["items"]}
    assert "Other family's secret pickup" not in titles
    # and the grant still works for what is in its own household
    own_id, _ = await _obligation(database, other, subject=None, action="attend", title="Neighbours' own date")
    assert "Neighbours' own date" in {i["title"] for i in (await brief.today(visitor, limit=50))["items"]}


# ----------------------------------------------------------------------------
# a grant reaches the obligation and nothing derived from the notice around it
# ----------------------------------------------------------------------------

async def _add_to_notice(database, family, artifact_id, *, ordinal, kind, title, action=None):
    """More read out of the same private notice: an instruction, or a second obligation (say, a fee) with its own claim."""
    household_id = uuid.UUID(family.household["id"])
    extraction_id = await database.fetchval("SELECT id FROM extractions WHERE artifact_id = $1", artifact_id)
    claim_id = uuid.uuid4()
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, 'more words', 0.9)", claim_id, extraction_id, household_id, artifact_id, ordinal, kind, title)
    if action:
        await database.execute(
            "INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, status) "
            "VALUES ($1, $2, $3, $4, NULL, 'task', $5, $6, $7, 'accepted')", uuid.uuid4(), household_id, artifact_id, claim_id, action, title, TOMORROW)


async def _granted_notice(database, family):
    """Amma's private notice (a pickup, a fee, an instruction) with Paati granted only the pickup."""
    _, artifact_id = await _obligation(database, family, subject=family.older)
    await _add_to_notice(database, family, artifact_id, ordinal=1, kind="event", title="Pay the trip fee", action="pay")
    await _add_to_notice(database, family, artifact_id, ordinal=2, kind="instruction", title="Bring a water bottle")
    await grants.issue(_principal(family), grantee_member_id=uuid.UUID(family.paati["id"]), actions=["attend"], reason="School pickup",
                       subject_member_id=uuid.UUID(family.older["id"]))
    return artifact_id


async def test_ask_cites_a_granted_obligation_without_the_notice_it_was_read_from(family, database):
    artifact_id = await _granted_notice(database, family)
    mine = [f for f in await ask.context(_principal(family)) if f.kind == "obligation" and f.text.startswith("Sports day pickup")]
    assert mine and mine[0].quote == "the words" and mine[0].artifact_id == artifact_id            # the one who may read the notice is pointed at it
    theirs = [f for f in await ask.context(_principal(family, "paati")) if f.kind == "obligation"]
    assert [f.text.split(" — ")[0] for f in theirs] == ["Sports day pickup"]                       # the grant shows the pickup, not the fee
    assert theirs[0].quote is None and theirs[0].artifact_id is None


async def test_a_granted_event_does_not_bring_the_notices_other_items_into_the_brief(family, database):
    await _granted_notice(database, family)
    seen = json.dumps(await brief.today(_principal(family, "paati"), limit=50), default=str)
    assert "Sports day pickup" in seen and "trip fee" not in seen and "water bottle" not in seen
    owner = json.dumps(await brief.today(_principal(family), limit=50), default=str)
    assert "trip fee" in owner and "water bottle" in owner                                          # the notice's own reader still hears it


async def test_a_granted_event_does_not_bring_the_notices_instructions_into_the_school_day(family, database):
    await _granted_notice(database, family)
    seen = json.dumps(await schoolday.tomorrow(_principal(family, "paati")), default=str)
    assert "Sports day pickup" in seen and "water bottle" not in seen
    assert "water bottle" in json.dumps(await schoolday.tomorrow(_principal(family)), default=str)


async def test_a_warranty_from_a_private_receipt_is_not_listed_or_closed_by_another_adult(family):
    artifact_id = uuid.UUID((await family.upload("amma", b"%PDF-1.4 receipt")).json()["artifact"]["id"])
    mine = await finance.add_warranty(_principal(family), title="Washing machine", artifact_id=artifact_id, warranty_months=24)
    await finance.add_warranty(_principal(family, "appa"), title="Kettle", warranty_months=12)       # no receipt behind it: the household's
    assert {w["title"] for w in await finance.warranties(_principal(family))} == {"Washing machine", "Kettle"}
    assert {w["title"] for w in await finance.warranties(_principal(family, "appa"))} == {"Kettle"}
    with pytest.raises(NotFound):
        await finance.close_warranty(_principal(family, "appa"), mine["id"])
    await finance.close_warranty(_principal(family), mine["id"])


async def test_the_graph_leaves_out_a_warranty_from_a_private_receipt_for_another_adult(family):
    artifact_id = uuid.UUID((await family.upload("amma", b"%PDF-1.4 receipt two")).json()["artifact"]["id"])
    await finance.add_warranty(_principal(family), title="Washing machine", artifact_id=artifact_id, warranty_months=24)
    assert await graph.find(_principal(family, "appa"), "Washing machine") == []
    assert await graph.find(_principal(family), "Washing machine") != []
