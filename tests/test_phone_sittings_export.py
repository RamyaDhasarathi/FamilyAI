"""The JSON the iPhone's rails, sittings, export and erasure screens decode (ios/Kit/Sittings.swift)."""
import datetime as dt
import hashlib
import uuid

from familyos.execution import disposable, harvest
from familyos.identity import Principal
from tests.conftest import pdf


def _has(row: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in row]
    assert not missing, f"missing {missing} in {sorted(row)}"


async def test_rails_have_the_keys_the_phone_decodes(family, database):
    hid = uuid.UUID(family.household["id"])
    school = await database.fetchval("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Oakridge') RETURNING id", uuid.uuid4(), hid)
    a = (await family.upload("amma", pdf("rails1"), visibility="shared")).json()["artifact"]["id"]
    await database.execute("INSERT INTO rail_deliveries (artifact_id, household_id, school_id, rail, outcome, delivered_at) VALUES ($1, $2, $3, 'email', 'first', $4)",
                           uuid.UUID(a), hid, school, dt.datetime.now(dt.UTC))
    rows = (await family.client.get("/v1/rails", headers=family.h("amma"))).json()
    _has(rows[0], "school_id", "school", "notices", "rails", "said")
    _has(rows[0]["rails"][0], "rail", "label", "first", "echo", "empty", "deliveries")


async def test_a_sitting_and_its_pages_have_the_keys_the_phone_decodes(family):
    h = family.h("amma")
    begun = (await family.client.post("/v1/harvests", headers=h, json={"label": "School portal", "allow_hosts": ["portal.example.com"], "minutes": 30})).json()
    _has(begun, "id", "label", "live_url", "allow_hosts", "state", "expires_at")
    text = "Sports day on 14 November."
    p = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    await harvest.offer(p, uuid.UUID(begun["id"]), disposable.Page(url="https://portal.example.com/c/1", title="Circular", text=text,
                                                                   sha256=hashlib.sha256(text.encode()).hexdigest(), bytes=len(text), truncated=False))
    _has((await family.client.get("/v1/harvests", headers=h)).json()[0], "id", "label", "allow_hosts", "state", "expires_at")
    page = (await family.client.get(f"/v1/harvests/{begun['id']}/candidates", headers=h)).json()[0]
    _has(page, "id", "url", "title", "text", "bytes", "decision")
    assert (await family.client.delete(f"/v1/harvest-candidates/{page['id']}", headers=h)).status_code == 200      # the phone sends DELETE and ignores the body
    assert (await family.client.post(f"/v1/harvests/{begun['id']}/finish", headers=h)).status_code == 200


async def test_an_export_is_a_zip_with_a_filename_the_phone_can_read(family):
    r = await family.client.get("/v1/export", headers=family.h("amma"))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="' in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    kid = (await family.client.post("/v1/household/members", headers=family.h("amma"), json={"display_name": "Ila", "role": "child", "date_of_birth": "2019-07-01"})).json()
    assert (await family.client.get(f"/v1/members/{kid['id']}/export", headers=family.h("amma"))).status_code == 200
    assert (await family.client.get(f"/v1/members/{kid['id']}/export", headers=family.h("paati"))).status_code == 403


async def test_erasing_is_a_guardians_alone_and_a_household_needs_its_name_typed(family):
    kid = (await family.client.post("/v1/household/members", headers=family.h("amma"), json={"display_name": "Ila", "role": "child", "date_of_birth": "2019-07-01"})).json()
    assert (await family.client.post(f"/v1/members/{kid['id']}/erase", headers=family.h("paati"))).status_code == 403
    assert (await family.client.post("/v1/household/erase", headers=family.h("paati"), json={"confirm_name": family.household["name"]})).status_code in (403, 422)
    assert (await family.client.post("/v1/household/erase", headers=family.h("amma"), json={"confirm_name": "not the name"})).status_code == 422
    started = await family.client.post(f"/v1/members/{kid['id']}/erase", headers=family.h("amma"))
    assert started.status_code == 202, started.text
    _has(started.json(), "id", "scope", "status")
