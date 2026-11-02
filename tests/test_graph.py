"""The household graph: what touches what, only what this person may see, every link citing its notice."""
import datetime as dt
import uuid

from familyos import clock
from tests.conftest import pdf
from tests.test_brief import _obligation

TODAY = clock.today()


async def _notice(family, text, who="amma", visibility="shared"):
    r = await family.upload(who, pdf(text), filename=text[:24] + ".pdf", visibility=visibility)
    return r.json()["artifact"]["id"]


async def _touches(family, ref, who="amma", depth=1):
    r = await family.client.get("/v1/graph/touches", headers=family.h(who), params={"ref": ref, "depth": depth})
    return r


async def test_a_child_with_consent_is_connected_to_the_date_and_the_notice_it_came_from(family, database):
    await family.consent(family.younger)
    aid = await _notice(family, "School trip circular")
    oid = await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=5), title="Field trip form")
    await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid, uuid.UUID(family.younger["id"]))
    r = await _touches(family, f"person:{family.younger['id']}")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["entity"]["label"] == "Younger one"
    hit = next(c for c in got["connections"] if c["node"]["ref"] == f"obligation:{oid}")
    assert hit["distance"] == 1 and hit["path"][0]["relation"] == "about" and hit["path"][0]["source_artifact_id"] == aid
    assert "is about" in hit["path"][0]["phrase"]
    # two steps out reaches the notice that date came from
    deep = (await _touches(family, f"person:{family.younger['id']}", depth=2)).json()
    assert f"artifact:{aid}" in [c["node"]["ref"] for c in deep["connections"]]


async def test_a_child_without_consent_is_not_in_the_graph_at_all(family, database):
    aid = await _notice(family, "Circular")
    oid = await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=3))
    await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid, uuid.UUID(family.older["id"]))
    assert (await _touches(family, f"person:{family.older['id']}")).status_code == 404
    found = (await family.client.get("/v1/graph/find", headers=family.h("amma"), params={"q": "older"})).json()
    assert found == []
    # the date itself is still there, just not tied to a person who has not been consented
    obl = (await _touches(family, f"obligation:{oid}")).json()
    assert [c["node"]["type"] for c in obl["connections"]] == ["artifact"]


async def test_a_warranty_connects_a_shop_and_its_invoice_and_a_name_finds_it(family, database):
    aid = await _notice(family, "Croma invoice")
    w = (await family.client.post("/v1/finance/warranties", headers=family.h("amma"),
                                  json={"title": "Bosch washing machine", "merchant": "Croma", "warranty_months": 12, "artifact_id": aid})).json()
    hits = (await family.client.get("/v1/graph/find", headers=family.h("amma"), params={"q": "croma"})).json()
    assert [h["ref"] for h in hits] == ["org:croma"]
    shop = (await _touches(family, "org:croma")).json()
    assert [c["node"]["label"] for c in shop["connections"]] == ["Bosch washing machine"]
    machine = (await _touches(family, f"warranty:{w['id']}", depth=2)).json()
    labels = {c["node"]["type"] for c in machine["connections"]}
    assert {"org", "artifact"} <= labels


async def test_a_private_notice_and_what_hangs_off_it_stay_out_of_another_adults_graph(family, database):
    aid = await _notice(family, "Private clinic letter", who="amma", visibility="private")
    oid = await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=4), title="Book the scan")
    assert (await _touches(family, f"obligation:{oid}", who="amma")).status_code == 200
    assert (await _touches(family, f"obligation:{oid}", who="paati")).status_code == 404
    assert (await _touches(family, f"artifact:{aid}", who="paati")).status_code == 404


async def test_bad_references_are_refused_plainly_and_depth_is_capped(family):
    assert (await _touches(family, "nonsense")).status_code in (400, 422)
    assert (await _touches(family, "person:not-a-uuid")).status_code in (400, 422)
    assert (await _touches(family, f"person:{family.amma['id']}", depth=9)).status_code == 200      # capped to two, not refused
    assert (await family.client.get("/v1/graph/find", headers=family.h("amma"), params={"q": "a"})).status_code in (400, 422)


async def _open_things(family, database, who_id, titles, aid=None):
    aid = aid or await _notice(family, "Week circular " + titles[0])
    for i, t in enumerate(titles):
        title, day = (t if isinstance(t, tuple) else (t, 1 + i))
        oid = await _obligation(database, family, artifact_id=aid, due=TODAY + dt.timedelta(days=day), title=title)
        await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid, uuid.UUID(who_id))
    return aid


async def test_a_pile_of_dated_things_for_one_child_is_said_once_and_a_reworded_date_counts_once(family, database):
    await family.consent(family.younger)
    await _open_things(family, database, family.younger["id"], ["Field trip form", "Cetirizine refill", ("Book fair", 3), ("Book Fair", 3)])
    got = (await family.client.get("/v1/graph/insights", headers=family.h("amma"))).json()
    busy = [i for i in got if i["kind"] == "busy_person"]
    assert len(busy) == 1 and busy[0]["title"] == "Younger has 3 things in the next 7 days" and len(busy[0]["items"]) == 3
    # it is a card in Needs you, opens on the map, and "Got it" keeps it quiet
    cards = [c for c in (await family.client.get("/v1/decisions", headers=family.h("amma"))).json() if c["kind"] == "heads_up"]
    assert len(cards) == 1 and cards[0]["actions"][0]["href"].startswith("#/map/person%3A")
    seen = next(a for a in cards[0]["actions"] if a["key"] == "seen")
    assert (await family.client.post(seen["path"], headers=family.h("amma"))).status_code == 204
    assert [c for c in (await family.client.get("/v1/decisions", headers=family.h("amma"))).json() if c["kind"] == "heads_up"] == []


async def test_two_things_are_not_a_pile_and_other_peoples_children_are_not_counted_without_consent(family, database):
    await family.consent(family.younger)
    await _open_things(family, database, family.younger["id"], ["Field trip form", "Book fair"])
    assert [i for i in (await family.client.get("/v1/graph/insights", headers=family.h("amma"))).json() if i["kind"] == "busy_person"] == []
    await _open_things(family, database, family.older["id"], ["A", "B", "C", "D"])          # never consented
    assert [i for i in (await family.client.get("/v1/graph/insights", headers=family.h("amma"))).json() if i["kind"] == "busy_person"] == []


async def test_a_prescription_tied_to_no_one_and_a_warranty_about_to_end_are_noticed(family, database):
    aid = await _notice(family, "Clinic sheet")
    hid = uuid.UUID(family.household["id"])
    for drug in ("Cetirizine", "ORS", "Vitamin D"):
        await database.execute("INSERT INTO medications (id, household_id, artifact_id, drug, dose_text, times_per_day, starts_on) VALUES ($1, $2, $3, $4, '5 ml', 1, $5)",
                               uuid.uuid4(), hid, uuid.UUID(aid), drug, TODAY)
    await family.client.post("/v1/finance/warranties", headers=family.h("amma"),
                             json={"title": "Bosch washing machine", "merchant": "Croma", "purchased_on": (TODAY - dt.timedelta(days=335)).isoformat(), "warranty_months": 12})
    got = (await family.client.get("/v1/graph/insights", headers=family.h("amma"))).json()
    sheet = [i for i in got if i["kind"] == "unattached"]
    assert len(sheet) == 1 and sheet[0]["title"] == "Whose is this prescription (3 medicines)?" and "Cetirizine" in sheet[0]["why"]
    ending = [i for i in got if i["kind"] == "warranty_ending"]
    assert len(ending) == 1 and "Bosch washing machine" in ending[0]["title"]


async def test_a_prescription_or_document_of_a_child_without_consent_is_not_asked_about_as_if_it_belonged_to_nobody(family, database):
    """The child is not in the graph, so their things have no edge to them. That is hiding, not "tied to no one": nobody is asked whose it is."""
    aid = await _notice(family, "Clinic sheet for the younger one")
    hid = uuid.UUID(family.household["id"])
    younger = uuid.UUID(family.younger["id"])                                    # no consent given: the child is hidden
    for drug in ("Cetirizine", "ORS"):
        await database.execute("INSERT INTO medications (id, household_id, artifact_id, patient_member_id, drug, dose_text, times_per_day, starts_on) VALUES ($1, $2, $3, $4, $5, '5 ml', 1, $6)",
                               uuid.uuid4(), hid, uuid.UUID(aid), younger, drug, TODAY)
    await database.execute("INSERT INTO documents (id, household_id, artifact_id, kind, title, holder_member_id) VALUES ($1, $2, $3, 'passport', 'Passport', $4)",
                           uuid.uuid4(), hid, uuid.UUID(aid), younger)
    got = (await family.client.get("/v1/graph/insights", headers=family.h("amma"))).json()
    assert [i for i in got if i["kind"] == "unattached"] == []
    # with consent the same rows are visible and tied to the child, so still nothing to ask; and a document with no holder at all IS asked about
    await family.consent(family.younger)
    await database.execute("INSERT INTO documents (id, household_id, artifact_id, kind, title) VALUES ($1, $2, $3, 'passport', 'Another passport')", uuid.uuid4(), hid, uuid.UUID(aid))
    got = (await family.client.get("/v1/graph/insights", headers=family.h("amma"))).json()
    assert [i["title"] for i in got if i["kind"] == "unattached"] == ["Whose is this passport?"]
