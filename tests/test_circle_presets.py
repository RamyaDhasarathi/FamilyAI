"""Care circles: narrow, short scopes for the people who are not the household."""
from tests.conftest import pdf


async def _caregiver(family, who="paati"):
    r = await family.client.put(f"/v1/members/{family[who]['id'] if isinstance(family, dict) else getattr(family, who)['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    assert r.status_code == 200, r.text


async def test_a_pickup_preset_needs_a_child_and_grants_only_attending(family):
    await _caregiver(family)
    no_child = await family.client.post("/v1/circle/presets/pickup", headers=family.h("amma"), json={"member_id": family.paati["id"]})
    assert no_child.status_code in (400, 422)
    r = await family.client.post("/v1/circle/presets/pickup", headers=family.h("amma"), json={"member_id": family.paati["id"], "subject_member_id": family.younger["id"]})
    assert r.status_code in (200, 201), r.text
    grant = r.json()
    assert grant["actions"] == ["attend"] and "Pickups and drop-offs only" in grant["reason"]


async def test_the_scopes_are_listed_and_only_a_guardian_hands_them_out(family):
    keys = [x["key"] for x in (await family.client.get("/v1/circle/presets", headers=family.h("amma"))).json()]
    assert {"pickup", "medicines", "while_we_travel", "emergency_only", "school_one_child"} <= set(keys)
    assert (await family.client.post("/v1/circle/presets/medicines", headers=family.h("paati"), json={"member_id": family.appa["id"]})).status_code == 403


async def test_a_caregiver_cannot_open_the_emergency_card_until_it_is_handed_to_them(family):
    await _caregiver(family)
    assert (await family.client.get("/v1/emergency/card", headers=family.h("paati"))).status_code == 403
    r = await family.client.post("/v1/circle/presets/emergency_only", headers=family.h("amma"), json={"member_id": family.paati["id"], "days": 3})
    assert r.status_code in (200, 201), r.text
    assert (await family.client.get("/v1/emergency/card", headers=family.h("paati"))).status_code == 200
    gid = r.json()["id"]
    assert (await family.client.delete(f"/v1/grants/{gid}", headers=family.h("amma"))).status_code in (200, 204)
    assert (await family.client.get("/v1/emergency/card", headers=family.h("paati"))).status_code == 403


async def test_the_emergency_scope_gives_no_notice_or_date(family):
    await _caregiver(family)
    await family.client.post("/v1/circle/presets/emergency_only", headers=family.h("amma"), json={"member_id": family.paati["id"]})
    a = (await family.upload("amma", pdf("circle-x"), visibility="shared")).json()["artifact"]["id"]
    assert (await family.client.get("/v1/decisions", headers=family.h("paati"))).json() == []
    assert a
