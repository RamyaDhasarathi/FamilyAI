"""Implied to-dos: a party asks for a gift, a trip for passports. Suggested,
never added on their own; Add makes a to-do that remembers its source, the
cross is remembered too."""
import datetime as dt
import uuid

import pytest

from familyos import notify, suggest
from familyos.db import pool
from familyos.identity import Principal
from tests.conftest import pdf


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    async def member(member_id, subject, body):
        return "test"
    monkeypatch.setattr(notify, "member", member)


def test_events_imply_the_right_to_do_with_the_right_lead():
    today = dt.date(2026, 10, 7)
    events = [
        {"key_id": "o1", "summary": "Kabir's birthday party", "on_date": dt.date(2026, 10, 17), "subject_name": None},
        {"key_id": "o2", "summary": "1st Parent-Teacher Meeting", "on_date": dt.date(2026, 10, 9), "subject_name": "Meera"},
        {"key_id": "o3", "summary": "Dentist", "on_date": dt.date(2026, 10, 8), "subject_name": None},
        {"key_id": "o4", "summary": "Annual trip to Fort Warangal", "on_date": dt.date(2026, 10, 29), "subject_name": None},
        {"key_id": "o5", "summary": "Pay the term fee", "on_date": dt.date(2026, 10, 20), "subject_name": None},
        {"key_id": "o6", "summary": "Birthday", "on_date": dt.date(2026, 10, 1), "subject_name": None},   # gone by
    ]
    out = {s["event"]: s for s in suggest.implied_from(events, today)}
    gift = out["Kabir's birthday party"]
    assert gift["title"] == "Gift for Kabir" and gift["due_date"] == dt.date(2026, 10, 13) and "amazon.in" in gift["link"]
    assert out["1st Parent-Teacher Meeting"]["title"].startswith("Questions for the teacher") and out["1st Parent-Teacher Meeting"]["due_date"] == dt.date(2026, 10, 7)
    assert out["Dentist"]["due_date"] == dt.date(2026, 10, 7)          # never before today
    assert out["Annual trip to Fort Warangal"]["title"].startswith("Passports, tickets and packing")
    assert "Pay the term fee" not in out and "Birthday" not in out


async def _accepted(family, title, on):
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload("amma", pdf(title), visibility="shared")).json()["artifact"]["id"])
    xid, cid, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'event', $5, $5, 0.9)", cid, xid, household_id, artifact_id, title)
    await pool().execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, status) "
        "VALUES ($1, $2, $3, $4, 'calendar', 'note', $5, $6, 'accepted')", oid, household_id, artifact_id, cid, title, on)
    return oid


async def test_a_suggestion_is_offered_added_once_and_a_dismissal_is_remembered(family, database):
    today = dt.date.today()
    await _accepted(family, "Aarav's birthday party", today + dt.timedelta(days=10))
    await _accepted(family, "Sports day", today + dt.timedelta(days=12))
    r = await family.client.get("/v1/suggestions", headers=family.h("amma"))
    assert r.status_code == 200
    by_title = {s["title"]: s for s in r.json()}
    assert "Gift for Aarav" in by_title and "Costume or kit for Sports day" in by_title
    # Add the gift: a to-do with the source remembered; the suggestion is gone.
    gift = by_title["Gift for Aarav"]
    r = await family.client.post(f"/v1/suggestions/{gift['key']}/accept", headers=family.h("amma"),
                                 json={"assigned_to": family.appa["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Gift for Aarav" and r.json()["assigned_to"] == family.appa["id"] and r.json()["source_key"] == gift["key"]
    titles = [s["title"] for s in (await family.client.get("/v1/suggestions", headers=family.h("amma"))).json()]
    assert "Gift for Aarav" not in titles and "Costume or kit for Sports day" in titles
    # Dismiss the other: remembered, for everyone in the household.
    kit = by_title["Costume or kit for Sports day"]
    assert (await family.client.post(f"/v1/suggestions/{kit['key']}/dismiss", headers=family.h("appa"))).status_code == 204
    assert (await family.client.get("/v1/suggestions", headers=family.h("amma"))).json() == []
    # Accepting it again is not possible.
    assert (await family.client.post(f"/v1/suggestions/{kit['key']}/accept", headers=family.h("amma"), json={})).status_code == 404
