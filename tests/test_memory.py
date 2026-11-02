"""Source-backed memory: why, correct, verify, and who sees what."""
import datetime as dt
import uuid

import pytest

from familyos import clock
from tests.conftest import pdf

pytestmark = pytest.mark.usefixtures("school_apps")


async def _school(family, child, school, cls="KG-1"):
    r = await family.client.patch(f"/v1/members/{child['id']}/school", headers=family.h("amma"), json={"school": school, "class_label": cls})
    assert r.status_code in (200, 204), r.text


async def test_a_childs_school_and_its_app_come_with_their_sources(family, database):
    await _school(family, family.younger, "Bright Start")
    facts = (await family.client.get("/v1/memory", headers=family.h("amma"))).json()
    school = next(f for f in facts if f["kind"] == "school" and f["subject"] == family.younger["display_name"])
    assert school["value"].startswith("Bright Start") and school["how_known"] == "stated" and school["correctable"] is True
    assert family.amma["display_name"] in school["source"]["text"] and school["last_verified"] is None and school["review_by"]
    app = next(f for f in facts if f["key"] == f"app:{family.younger['id']}")
    assert app["how_known"] == "rule" and "Bright Start" in app["value"] and "matches" in app["source"]["text"]


async def test_why_explains_in_steps_and_correcting_changes_the_fact_and_the_app(family):
    await _school(family, family.younger, "Some Other School")
    key = f"school:{family.younger['id']}"
    why = (await family.client.get("/v1/memory/why", headers=family.h("amma"), params={"key": key})).json()
    assert any("not been confirmed" in s for s in why["explanation"])
    fixed = (await family.client.post("/v1/memory/correct", headers=family.h("amma"), json={"key": key, "value": "Bright Start Intellitots"})).json()
    assert fixed["value"].startswith("Bright Start Intellitots") and fixed["corrected"]["by"] == family.amma["display_name"]
    facts = (await family.client.get("/v1/memory", headers=family.h("amma"))).json()
    assert "Bright Start" in next(f for f in facts if f["key"] == f"app:{family.younger['id']}")["value"]


async def test_confirming_sets_last_verified_and_moves_the_review_date(family):
    await _school(family, family.younger, "Bright Start")
    key = f"school:{family.younger['id']}"
    done = (await family.client.post("/v1/memory/verify", headers=family.h("amma"), json={"key": key})).json()
    assert done["last_verified"] is not None and any("Last confirmed" in s for s in done["explanation"])
    assert dt.date.fromisoformat(done["review_by"]) > clock.today() + dt.timedelta(days=300)


async def test_only_a_guardian_sees_or_corrects_a_childs_facts(family):
    await _school(family, family.younger, "Bright Start")
    assert [f for f in (await family.client.get("/v1/memory", headers=family.h("paati"))).json() if f["kind"] in ("school", "app")] == []
    key = f"school:{family.younger['id']}"
    r = await family.client.post("/v1/memory/correct", headers=family.h("paati"), json={"key": key, "value": "Elsewhere"})
    assert r.status_code in (403, 404)


async def test_a_document_fact_carries_its_quote_and_cannot_be_corrected_here(family, database):
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    eid = uuid.uuid4()
    hid = uuid.UUID(family.household["id"])
    await database.execute("INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) VALUES ($1,$2,$3,'rules','v1','v1',true,1)", eid, hid, uuid.UUID(a))
    cid = uuid.uuid4()
    await database.execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, date, quote, confidence) VALUES ($1,$2,$3,$4,0,'document','Passport',$5,'Date of expiry 12 MAR 2029',0.9)", cid, eid, hid, uuid.UUID(a), dt.date(2029, 3, 12))
    did = uuid.uuid4()
    await database.execute("INSERT INTO documents (id, household_id, artifact_id, claim_id, kind, title, holder_member_id, expires_on) VALUES ($1,$2,$3,$4,'passport','Passport',$5,$6)", did, hid, uuid.UUID(a), cid, uuid.UUID(family.amma["id"]), dt.date(2029, 3, 12))
    f = next(x for x in (await family.client.get("/v1/memory", headers=family.h("amma"))).json() if x["key"] == f"doc:{did}")
    assert "Date of expiry 12 MAR 2029" in f["source"]["text"] and f["source"]["artifact_id"] == a and f["correctable"] is False
    r = await family.client.post("/v1/memory/correct", headers=family.h("amma"), json={"key": f"doc:{did}", "value": "x"})
    assert r.status_code == 422 or r.status_code == 400


async def test_memory_has_the_shape_the_iphone_decodes(family):
    """ios/Kit/Memory.swift decodes these keys, on the list and on why / verify / correct."""
    await _school(family, family.younger, "Bright Start")
    key = f"school:{family.younger['id']}"
    keys = {"key", "kind", "subject", "label", "value", "source", "how_known", "confidence", "corrected", "last_verified", "review_by", "correctable"}
    facts = (await family.client.get("/v1/memory", headers=family.h("amma"))).json()
    assert all(keys <= set(f) and {"type", "text", "at", "artifact_id"} <= set(f["source"]) for f in facts)
    why = (await family.client.get(f"/v1/memory/why?key={key}", headers=family.h("amma"))).json()
    assert keys <= set(why) and isinstance(why["explanation"], list) and all(isinstance(s, str) for s in why["explanation"])
    done = (await family.client.post("/v1/memory/verify", headers=family.h("amma"), json={"key": key})).json()
    assert done["last_verified"] is not None
    fixed = (await family.client.post("/v1/memory/correct", headers=family.h("amma"), json={"key": key, "value": "Another School", "class_label": "2-B"})).json()
    assert fixed["value"].startswith("Another School") and fixed["corrected"] and {"by", "at"} <= set(fixed["corrected"])
