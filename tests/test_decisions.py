"""The decision queue: only what waits on a person, each card with its source, a fixed recommendation, the cost of
waiting and buttons that are the existing endpoints."""
import datetime as dt
import uuid

from familyos import clock
from tests.conftest import pdf
from tests.test_brief import _obligation

TODAY = clock.today()


async def _queue(family, who="amma"):
    r = await family.client.get("/v1/decisions", headers=family.h(who))
    assert r.status_code == 200, r.text
    return r.json()


async def test_only_undecided_dates_are_decisions_with_their_buttons(family, database):
    a = (await family.upload("amma", pdf("q1"), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=5), status="proposed", title="Sports day form")
    await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=5), status="accepted", title="Already agreed")
    cards = await _queue(family)
    assert [c["title"] for c in cards] == ["Sports day form"]
    c = cards[0]
    assert c["kind"] == "date" and c["recommendation"]["action"] == "accept" and "calendar" in c["consequence"]
    assert c["source"]["artifact_id"] == a and c["source"]["quote"] == "the words"
    keys = [x["key"] for x in c["actions"]]
    assert keys[:2] == ["accept", "dismiss"] and "open" in keys
    accept = next(x for x in c["actions"] if x["key"] == "accept")
    assert accept["method"] == "POST" and accept["path"].startswith("/v1/obligations/") and accept["body"] == {"status": "accepted"}


async def test_a_gone_date_is_late_first_and_recommends_dismissing(family, database):
    a = (await family.upload("amma", pdf("q2"), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=3), status="proposed", title="Coming")
    await _obligation(database, family, artifact_id=a, due=TODAY - dt.timedelta(days=2), status="proposed", title="Went by")
    cards = await _queue(family)
    assert [c["title"] for c in cards] == ["Went by", "Coming"]
    assert cards[0]["late"] and cards[0]["recommendation"]["action"] == "dismiss"


async def test_a_card_can_be_decided_with_its_own_button(family, database):
    a = (await family.upload("amma", pdf("q3"), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=4), status="proposed", title="Form")
    card = (await _queue(family))[0]
    accept = next(x for x in card["actions"] if x["key"] == "accept")
    r = await family.client.request(accept["method"], accept["path"], headers=family.h("amma"), json=accept["body"])
    assert r.status_code == 200, r.text
    assert await _queue(family) == []


async def test_a_notice_handed_to_me_can_be_done_or_handed_on(family, database):
    a = (await family.upload("amma", pdf("q4"), visibility="shared")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{a}/assign", headers=family.h("amma"), json={"member_id": family.appa["id"], "note": "Please pay this"})
    assert r.status_code == 200, r.text
    mine = await _queue(family, "appa")
    assert [c["kind"] for c in mine] == ["handed"] and "Please pay this" in mine[0]["happened"]
    ack = next(x for x in mine[0]["actions"] if x["key"] == "accept")                  # a hand-off is answered first
    assert (await family.client.request(ack["method"], ack["path"], headers=family.h("appa"), json=ack["body"])).status_code == 200
    mine = await _queue(family, "appa")
    delegate = next(x for x in mine[0]["actions"] if x["key"] == "delegate")
    labels = [c["label"] for c in delegate["choices"]]
    assert family.amma["display_name"] in labels and family.appa["display_name"] not in labels
    assert await _queue(family, "amma") == []             # the one who handed it on has nothing waiting on them
    done = next(x for x in mine[0]["actions"] if x["key"] == "done")
    assert (await family.client.request(done["method"], done["path"], headers=family.h("appa"), json=done["body"])).status_code == 200
    assert await _queue(family, "appa") == []


async def test_guardian_only_decisions_do_not_reach_a_non_guardian(family, database):
    from familyos import errands
    from familyos.identity import Principal
    g = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    await errands.propose(g, service="myclassboard", kind="look", title="Read the school app", spec={"what": "Announcements"})
    kinds_guardian = [c["kind"] for c in await _queue(family, "amma")]
    kinds_adult = [c["kind"] for c in await _queue(family, "appa")]
    assert "errand" not in kinds_adult and isinstance(kinds_guardian, list)


async def test_every_button_carries_its_body_as_text_for_clients_that_rename_keys(family, database):
    import json

    from tests.conftest import pdf as _pdf
    a = (await family.upload("amma", _pdf("bj"), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=4), status="proposed", title="Form")
    card = (await _queue(family))[0]
    for act in card["actions"]:
        for a2 in act.get("choices", [act]):
            if "path" in a2:
                assert json.loads(a2["body_json"]) == a2["body"]

