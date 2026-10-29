"""Ask, judged by a real model on an invented household. Off by default: it needs a model and costs a few cents.

    scripts/ask_eval.sh                 # all cases
    scripts/ask_eval.sh -k bill         # one

It never touches your data: the household is built fresh in the test database from invented people and notices.
A failing case is a finding, not necessarily a bug in the code: models vary, so run it twice before believing a miss.
"""
import datetime as dt
import os
import uuid

import pytest

from familyos import chat, clock
from familyos.identity import Principal
from familyos.settings import settings
from tests.ask_eval_cases import CASES
from tests.conftest import pdf
from tests.test_phone_reminders import _obligation

pytestmark = pytest.mark.skipif(not os.environ.get("FAMILYOS_ASK_EVAL"), reason="set by scripts/ask_eval.sh; needs a model")
TODAY = clock.today()


def _p(family, who):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


@pytest.fixture
async def household(family, database):
    hid = uuid.UUID(family.household["id"])
    if settings.local_model:
        await database.execute("UPDATE households SET local_models = TRUE WHERE id = $1", hid)
    chat.configure()
    await _obligation(family, database, "Pay the Airtel bill", TODAY + dt.timedelta(days=3))
    _, ptm = await _obligation(family, database, "Parent-Teacher Meeting", TODAY + dt.timedelta(days=5), status="accepted")
    ptm_day = TODAY + dt.timedelta(days=5)
    # an old notice, then more than the recent window of newer ones
    old = await family.upload("amma", pdf("old"), filename="Annual Day sports circular.pdf", visibility="shared")
    await database.execute("UPDATE input_artifacts SET received_at = $2 WHERE id = $1", uuid.UUID(old.json()["artifact"]["id"]), dt.datetime.now(dt.UTC) - dt.timedelta(days=50))
    for i in range(65):
        await family.upload("amma", pdf(f"bus{i}"), filename=f"Bus route note {i}.pdf", visibility="shared")
    private = await family.upload("amma", pdf("private"), filename="Private clinic letter blood test results.pdf", visibility="private")
    assert private.status_code in (200, 201)
    rx = await family.upload("amma", pdf("rx"), filename="prescription.pdf", visibility="shared")
    await database.execute(
        "INSERT INTO medications (id, household_id, artifact_id, drug, dose_text, patient_member_id, starts_on, ends_on) VALUES ($1, $2, $3, 'Cetrizine', '5 ml', $4, $5, $6)",
        uuid.uuid4(), hid, uuid.UUID(rx.json()["artifact"]["id"]), uuid.UUID(family.younger["id"]), TODAY, TODAY + dt.timedelta(days=4))
    await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "Rent", "payee": "Landlord", "amount": 25000, "currency": "INR", "day_of_month": 5})
    return {"ptm_day": f"{ptm_day.day} {ptm_day.strftime('%b').lower()}", "ptm_iso": ptm_day.isoformat(), "younger": family.younger["display_name"]}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_ask_case(case, family, household):
    fill = lambda s: s.format(**household)       # noqa: E731
    turn = await chat.turn(_p(family, case["who"]), fill(case["q"]))
    said = turn["say"].lower().replace("\u2019", "'")      # a model writes curly apostrophes
    if case.get("contains_any"):
        assert any(fill(w).lower() in said for w in case["contains_any"]), f"expected one of {case['contains_any']} in: {turn['say']}"
    for bad in case.get("not_contains", []):
        assert bad.lower() not in said, f"must not say {bad!r}: {turn['say']}"
    if case.get("cited"):
        assert turn["citations"], f"no fact cited: {turn['say']}"
    if case.get("proposal"):
        assert any(x["kind"] == case["proposal"] and x["ok"] for x in turn["proposals"]), f"no {case['proposal']} proposed: {turn['proposals']}"
    if "clarify" in case:
        assert bool(turn.get("clarify")) is case["clarify"], f"clarify should be {case['clarify']}: {turn}"
    if case.get("not_proposal"):
        assert not any(x["kind"] == case["not_proposal"] for x in turn["proposals"]), f"must not propose {case['not_proposal']}: {turn['proposals']}"
