"""What if: impact maps that read the record and change nothing."""
import datetime as dt
import uuid

from familyos import clock
from tests.conftest import pdf
from tests.test_brief import _obligation

TODAY = clock.today()


async def _scenario(family, body, who="amma"):
    r = await family.client.post("/v1/scenarios", headers=family.h(who), json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_member_away_lists_what_they_hold_and_who_could_cover(family, database):
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{a}/assign", headers=family.h("amma"), json={"member_id": family.appa["id"], "note": "school fees"})
    b = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=b, due=TODAY + dt.timedelta(days=5), status="accepted", title="PTM", action="attend")
    await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid, uuid.UUID(family.appa["id"]))
    out = await _scenario(family, {"kind": "member_away", "member_id": family.appa["id"], "start": TODAY.isoformat(), "end": (TODAY + dt.timedelta(days=9)).isoformat()})
    kinds = sorted(i["kind"] for i in out["impacts"])
    assert kinds == ["date", "handoff"] and out["changes_nothing"] is True and "2 things touched" in out["headline"]
    handoff = next(i for i in out["impacts"] if i["kind"] == "handoff")
    assert family.appa["display_name"] not in handoff["cover"] and family.amma["display_name"] in handoff["cover"]
    # nothing changed: the hand-off is still with the same person
    assert (await family.client.get("/v1/handoffs", headers=family.h("appa"))).json()["items"][0]["direction"] == "for_me"


async def test_a_stay_longer_than_120_days_is_refused(family):
    r = await family.client.post("/v1/scenarios", headers=family.h("amma"),
                                 json={"kind": "member_away", "member_id": family.appa["id"], "start": TODAY.isoformat(), "end": (TODAY + dt.timedelta(days=200)).isoformat()})
    assert r.status_code in (400, 422)


async def test_a_purchase_is_set_beside_what_is_already_expected_and_the_budget(family):
    await family.client.put("/v1/finance/budgets", headers=family.h("amma"), json={"category": "shopping", "monthly_limit": 10000})
    await family.client.post("/v1/finance/goals", headers=family.h("amma"), json={"title": "Trip", "target_amount": 30000})
    out = await _scenario(family, {"kind": "spend", "amount": 12000, "category": "shopping"})
    titles = [i["title"] for i in out["impacts"]]
    assert any("with this: 12,000" in t for t in titles) and any("-2,000 after this" in t or "after this" in t for t in titles)
    assert any(i["note"] == "over the budget after this" for i in out["impacts"]) and any("Trip" in t for t in titles)


async def test_an_earlier_reopening_names_the_plans_in_the_way(family, database):
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=20), status="accepted", title="School reopening", action="note")
    b = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=b, due=TODAY + dt.timedelta(days=15), status="accepted", title="Trip to Ooty", action="attend")
    out = await _scenario(family, {"kind": "school_reopens", "reopens_on": (TODAY + dt.timedelta(days=12)).isoformat()})
    assert [i["title"] for i in out["impacts"]] == ["Trip to Ooty"] and "1 plan in the way" in out["headline"]
    later = await _scenario(family, {"kind": "school_reopens", "reopens_on": (TODAY + dt.timedelta(days=30)).isoformat()})
    assert later["impacts"] == [] and "not earlier" in later["headline"]


async def test_no_reopening_recorded_says_so(family):
    out = await _scenario(family, {"kind": "school_reopens", "reopens_on": TODAY.isoformat()})
    assert out["impacts"] == [] and "No reopening date" in out["headline"]
