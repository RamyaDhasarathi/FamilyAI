"""What Ask is shown. A recent window alone cannot answer a question about the past, so a question pulls matching
older notices into the facts, from what the asker may see and nothing else. No model is involved here."""
import datetime as dt
import uuid

import pytest

from familyos import chat, clock
from familyos.db import pool
from familyos.identity import Principal
from familyos.settings import settings
from tests.conftest import pdf


def _p(family, who="amma", role="guardian"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


@pytest.fixture(autouse=True)
def words_only(monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "")      # deterministic: no embedding model in the suite


async def _notice(family, who, name, tag, visibility="shared"):
    r = await family.upload(who, pdf(f"{tag}-{uuid.uuid4()}"), filename=name, visibility=visibility)
    assert r.status_code in (200, 201), r.text
    return uuid.UUID(r.json()["artifact"]["id"])


async def _history(family, oldest="Annual Day sports circular.pdf", n=70):
    """One old notice, then more than the recent window of newer ones."""
    first = await _notice(family, "amma", oldest, "old")
    await pool().execute("UPDATE input_artifacts SET received_at = $2 WHERE id = $1", first, dt.datetime.now(dt.UTC) - dt.timedelta(days=50))
    for i in range(n):
        await _notice(family, "amma", f"Bus route note {i}.pdf", f"new{i}")
    return first


async def test_a_question_pulls_in_an_older_notice_the_recent_window_leaves_out(family):
    await _history(family)
    plain = await chat.context(_p(family))
    assert not any("Annual Day" in line for line in plain.lines)             # beyond the newest window
    asked = await chat.context(_p(family), "What did the school send about Annual Day?")
    found = [line for line in asked.lines if "older notice found by search" in line and "Annual Day" in line]
    assert found, "the old notice was not retrieved"
    key = found[0].split("]")[0].lstrip("[")
    assert asked.notices[key]["headline"].startswith("Annual Day")           # it can be cited, like any other


async def test_a_question_with_no_match_adds_nothing(family):
    await _history(family, n=3)
    asked = await chat.context(_p(family), "zzzz qqqq nothing like this")
    assert not any("older notice found by search" in line for line in asked.lines)


async def test_retrieval_never_shows_another_members_private_notice(family):
    first = await _notice(family, "amma", "Private clinic letter Annual Day.pdf", "priv", visibility="private")
    await pool().execute("UPDATE input_artifacts SET received_at = $2 WHERE id = $1", first, dt.datetime.now(dt.UTC) - dt.timedelta(days=50))
    for i in range(70):
        await _notice(family, "amma", f"Bus route note {i}.pdf", f"n{i}")
    other = await chat.context(_p(family, "appa"), "Annual Day clinic letter")
    assert not any("Private clinic letter" in line for line in other.lines)
    mine = await chat.context(_p(family), "Annual Day clinic letter")
    assert any("Private clinic letter" in line for line in mine.lines)


async def test_the_medicines_documents_and_standing_payments_are_in_the_facts(family, database):
    p = _p(family)
    r = await family.upload("amma", pdf("rx"), filename="rx.pdf", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    today = clock.today()
    await database.execute(
        "INSERT INTO medications (id, household_id, artifact_id, drug, dose_text, patient_member_id, starts_on, ends_on) VALUES ($1, $2, $3, 'Cetrizine', '5 ml', $4, $5, $6)",
        uuid.uuid4(), p.household_id, artifact_id, uuid.UUID(family.younger["id"]), today, today + dt.timedelta(days=4))
    made = await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "Rent", "payee": "Landlord", "amount": 25000, "currency": "INR", "day_of_month": 5})
    assert made.status_code in (200, 201), made.text
    facts = await chat.context(p)
    assert any(line.startswith("[m1]") and "Cetrizine 5 ml" in line and family.younger["display_name"] in line for line in facts.lines)
    assert any(line.startswith("[y1]") and "Rent to Landlord" in line for line in facts.lines)


def test_references_to_medicines_documents_and_standing_payments_are_recognised_as_citations():
    facts = chat.Facts()
    facts.plain["m1"] = ("medicine", "medicine for Younger one: Cetrizine 5 ml")
    facts.plain["y1"] = ("standing", "standing payment: Rent to Landlord")
    facts.plain["d1"] = ("document", "document: Passport")
    done = chat._finish({"say": "Cetrizine [m1]. Rent goes to the landlord [y1]. The passport is held [d1].", "proposals": []}, facts, "q")
    assert {c["ref"] for c in done["citations"]} == {"m1", "y1", "d1"}
