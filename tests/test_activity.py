"""The activity ledger: receipts, and undo only where nothing has changed since."""
import datetime as dt

from familyos import clock
from tests.conftest import pdf
from tests.test_brief import _obligation

TODAY = clock.today()


async def _ledger(family, who="amma"):
    r = await family.client.get("/v1/activity", headers=family.h(who))
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_decision_leaves_a_receipt_and_can_be_put_back(family, database):
    a = (await family.upload("amma", pdf("act1"), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=4), status="proposed", title="Return the slip")
    r = await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert r.status_code == 200
    rows = await _ledger(family)
    row = next(x for x in rows if x["action"] == "obligation.accepted")
    assert row["receipt"]["approved_by"] == family.amma["display_name"] and "accepted" in row["receipt"]["rule"]
    assert "the words" in row["receipt"]["inferred"] and row["undo"]["available"] is True
    done = await family.client.post(row["undo"]["path"], headers=family.h("amma"))
    assert done.status_code == 200, done.text
    assert await database.fetchval("SELECT status FROM obligations WHERE id = $1", oid) == "proposed"
    again = await _ledger(family)
    assert any(x["action"] == "activity.undone" for x in again)
    assert next(x for x in again if x["action"] == "obligation.accepted")["undo"] is None       # already undone
    assert (await family.client.post(row["undo"]["path"], headers=family.h("amma"))).status_code == 403


async def test_an_undo_is_refused_after_something_else_changed_it(family, database):
    a = (await family.upload("amma", pdf("act2"), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=4), status="proposed", title="Form")
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    first = next(x for x in await _ledger(family) if x["action"] == "obligation.accepted")
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "dismissed"})
    assert (await family.client.post(first["undo"]["path"] if first["undo"] else f"/v1/activity/{first['id']}/undo", headers=family.h("amma"))).status_code == 403
    latest = next(x for x in await _ledger(family) if x["action"] == "obligation.dismissed")
    assert latest["undo"]["available"] is True


async def test_handing_a_notice_on_and_taking_it_back_through_undo(family):
    a = (await family.upload("amma", pdf("act3"), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{a}/assign", headers=family.h("amma"), json={"member_id": family.appa["id"], "note": "please"})
    row = next(x for x in await _ledger(family) if x["action"] == "artifact.assigned")
    assert row["undo"]["label"] == "Take it back"
    assert (await family.client.post(row["undo"]["path"], headers=family.h("amma"))).status_code == 200
    assert (await family.client.get("/v1/decisions", headers=family.h("appa"))).json() == []


async def test_a_todo_added_can_be_removed_unless_it_is_done(family):
    r = await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Buy chart paper"})
    assert r.status_code == 201, r.text
    row = next(x for x in await _ledger(family) if x["action"] == "todo.added")
    assert row["undo"]["label"] == "Remove the to-do"
    await family.client.patch(f"/v1/todos/{r.json()['id']}", headers=family.h("amma"), json={"done": True})
    row = next(x for x in await _ledger(family) if x["action"] == "todo.added")
    assert row["undo"] is None


async def test_only_a_guardian_sees_the_households_ledger_and_others_their_own(family):
    await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Amma's thing"})
    await family.client.post("/v1/todos", headers=family.h("paati"), json={"title": "Paati's thing"})
    mine = await _ledger(family, "paati")
    assert mine and all(x["who"] == family.paati["display_name"] for x in mine)
    assert {x["who"] for x in await _ledger(family, "amma")} >= {family.amma["display_name"], family.paati["display_name"]}
    amma_row = next(x for x in await _ledger(family, "amma") if x["who"] == family.amma["display_name"] and x["action"] == "todo.added")
    assert (await family.client.post(f"/v1/activity/{amma_row['id']}/undo", headers=family.h("paati"))).status_code in (403, 404)


async def test_the_ledger_has_the_shape_the_iphone_decodes(family, database):
    """ios/Kit/Activity.swift decodes exactly these keys: id (int), at, who, said, action, receipt{...}, undo{label} or null."""
    a = (await family.upload("amma", pdf("act-shape"), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=4), status="proposed", title="Shape check")
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    rows = await _ledger(family)
    for row in rows:
        assert isinstance(row["id"], int) and isinstance(row["who"], str) and isinstance(row["said"], str) and isinstance(row["action"], str)
        assert dt.datetime.fromisoformat(row["at"].replace("Z", "+00:00")).tzinfo is not None
        assert set(row["receipt"]) >= {"observed", "inferred", "rule", "approved_by", "changed"}
        assert row["undo"] is None or isinstance(row["undo"]["label"], str)
    assert (await family.client.get("/v1/activity?limit=1", headers=family.h("amma"))).json().__len__() == 1
    oldest = rows[-1]["id"]
    older = (await family.client.get(f"/v1/activity?before={oldest}", headers=family.h("amma"))).json()
    assert all(r["id"] < oldest for r in older)
