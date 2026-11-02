"""School copilot: what each child needs tomorrow, the forms still to come back, an absence note drafted for editing."""
import datetime as dt
import uuid

from familyos import clock
from tests.conftest import pdf
from tests.test_brief import _obligation

TOMORROW = clock.today() + dt.timedelta(days=1)


async def _notice(family, database, title, due, *, action="attend", status="accepted", child=None, instruction=None):
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=a, due=due, status=status, title=title, action=action)
    if child:
        await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid, uuid.UUID(child["id"]))
    if instruction:
        eid = await database.fetchval("SELECT id FROM extractions WHERE artifact_id = $1", uuid.UUID(a))
        await database.execute(
            "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
            "VALUES ($1, $2, $3, $4, 9, 'instruction', $5, 'the words', 0.9)", uuid.uuid4(), eid, uuid.UUID(family.household["id"]), uuid.UUID(a), instruction)
    return a, oid


async def test_tomorrow_lists_each_childs_items_and_what_to_bring(family, database):
    await _notice(family, database, "Sports day", TOMORROW, child=family.younger, instruction="Wear the house T-shirt")
    await _notice(family, database, "Library books due", TOMORROW + dt.timedelta(days=3), child=family.younger)
    day = (await family.client.get("/v1/school/tomorrow", headers=family.h("amma"))).json()
    assert day["date"] == TOMORROW.isoformat() and not day["nothing"]
    kid = next(c for c in day["children"] if c["child"] == family.younger["display_name"])
    assert [i["title"] for i in kid["items"]] == ["Sports day"] and kid["items"][0]["kind"] == "event"
    assert kid["bring"] == ["Wear the house T-shirt"]


async def test_an_untied_notice_is_kept_apart_not_given_to_a_child(family, database):
    await _notice(family, database, "School photo day", TOMORROW)
    day = (await family.client.get("/v1/school/tomorrow", headers=family.h("amma"))).json()
    assert [c["child"] for c in day["children"]] == ["Not tied to a child"]


async def test_a_quiet_day_says_so(family):
    assert (await family.client.get("/v1/school/tomorrow", headers=family.h("amma"))).json()["nothing"] is True


async def test_forms_are_tracked_from_undecided_to_returned(family, database):
    a, _ = await _notice(family, database, "Field trip consent", clock.today() + dt.timedelta(days=4), action="sign", child=family.younger)
    await _notice(family, database, "Photo release", clock.today() + dt.timedelta(days=6), action="submit", status="proposed")
    forms = (await family.client.get("/v1/school/forms", headers=family.h("amma"))).json()
    assert [(f["title"], f["state"]) for f in forms] == [("Field trip consent", "to return"), ("Photo release", "undecided")]
    assert forms[0]["child"] == family.younger["display_name"]
    await family.client.post(f"/v1/artifacts/{a}/handled", headers=family.h("amma"), json={"note": "sent with Lily"})
    forms = (await family.client.get("/v1/school/forms", headers=family.h("amma"))).json()
    assert [(f["title"], f["state"]) for f in forms] == [("Photo release", "undecided"), ("Field trip consent", "returned")]


async def test_the_absence_note_is_a_template_with_names_and_is_not_sent(family):
    r = await family.client.post("/v1/school/absence-note", headers=family.h("amma"),
                                 json={"child_id": family.younger["id"], "on": TOMORROW.isoformat(), "reason": "she has a fever"})
    assert r.status_code == 200, r.text
    n = r.json()
    assert family.younger["display_name"] in n["body"] and "she has a fever" in n["body"] and n["body"].rstrip().endswith(family.amma["display_name"])
    assert "does not send" in n["note"]
    bad = await family.client.post("/v1/school/absence-note", headers=family.h("amma"), json={"child_id": family.amma["id"], "on": TOMORROW.isoformat()})
    assert bad.status_code == 404


async def test_the_school_payloads_have_the_shape_the_iphone_decodes(family, database):
    """ios/Kit/SchoolDay.swift decodes these keys."""
    await _notice(family, database, "Sports day", TOMORROW, child=family.younger, instruction="Wear the house T-shirt")
    await _notice(family, database, "Return the slip", TOMORROW + dt.timedelta(days=2), action="sign", child=family.younger)
    day = (await family.client.get("/v1/school/tomorrow", headers=family.h("amma"))).json()
    assert {"date", "children", "nothing"} <= set(day)
    kid = day["children"][0]
    assert {"child", "class", "school", "items", "bring", "member_id"} <= set(kid)
    assert {"title", "kind", "time", "artifact_id", "undecided", "returned"} <= set(kid["items"][0])
    form = (await family.client.get("/v1/school/forms", headers=family.h("amma"))).json()[0]
    assert {"obligation_id", "artifact_id", "title", "due_date", "late", "state", "child", "child_id"} <= set(form)
    note = (await family.client.post("/v1/school/absence-note", headers=family.h("amma"),
                                     json={"child_id": family.younger["id"], "on": TOMORROW.isoformat()})).json()
    assert {"subject", "body", "school", "note"} <= set(note)
