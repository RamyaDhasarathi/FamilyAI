"""The household's rule: a notice tagged with a child is every adult's.
Applied wherever subjects are written; off for the household by a guardian;
a notice made private by hand afterwards stays so."""
import uuid

from tests.conftest import pdf


async def _device(family, who="amma"):
    r = await family.client.post("/v1/devices", headers=family.h(who), json={"label": "phone"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


async def test_tagging_a_private_notice_with_a_child_shares_it_with_the_household(family, database):
    await family.consent(family.older)
    r = await family.upload("amma", pdf("circular"), visibility="private")
    aid = r.json()["artifact"]["id"]
    assert r.json()["artifact"]["visibility"] == "private"
    assert (await family.client.get(f"/v1/artifacts/{aid}", headers=family.h("appa"))).status_code == 404
    r = await family.client.put(f"/v1/artifacts/{aid}/subjects", headers=family.h("amma"), json=[family.older["id"]])
    assert r.status_code == 200, r.text
    assert r.json()["visibility"] == "shared"
    # The other parent can open it and read the original: the blob was re-wrapped to the household.
    assert (await family.client.get(f"/v1/artifacts/{aid}", headers=family.h("appa"))).status_code == 200
    assert (await family.client.get(f"/v1/artifacts/{aid}/original", headers=family.h("appa"))).status_code == 200
    assert await database.fetchval("SELECT sealed_for FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1",
                                   uuid.UUID(aid)) is None
    row = await database.fetchrow("SELECT detail FROM audit_events WHERE action = 'artifact.visibility_changed' AND target_id = $1",
                                  uuid.UUID(aid))
    assert row["detail"]["rule"] == "childrens_notices_shared" and row["detail"]["via"] == "subjects"


async def test_a_notice_that_arrives_naming_a_child_is_shared_on_arrival(family, database):
    await family.consent(family.older)
    r = await family.upload("amma", pdf("ptm"), visibility="private", subjects=[family.older])
    assert r.status_code == 201, r.text
    assert r.json()["artifact"]["visibility"] == "shared"
    # And from the phone, with the child's name sent alongside.
    token = await _device(family)
    r = await family.client.post("/v1/inbound/share", headers={"Authorization": f"Bearer {token}"},
                                 data={"text": "Sports day on Friday.", "tag": "Older one"})
    assert r.status_code == 201, r.text
    assert r.json()["artifact"]["visibility"] == "shared"
    listed = (await family.client.get("/v1/artifacts", headers=family.h("appa"))).json()
    assert r.json()["artifact"]["id"] in {a["id"] for a in listed}


async def test_an_untagged_notice_stays_private_and_an_adult_tag_does_not_share(family, database):
    r = await family.upload("amma", pdf("salary"), visibility="private")
    aid = r.json()["artifact"]["id"]
    r = await family.client.put(f"/v1/artifacts/{aid}/subjects", headers=family.h("amma"), json=[family.appa["id"]])
    assert r.status_code == 200 and r.json()["visibility"] == "private"
    assert (await family.client.get(f"/v1/artifacts/{aid}", headers=family.h("appa"))).status_code == 404


async def test_a_guardian_turns_the_rule_off_and_tagging_then_keeps_it_private(family, database):
    await family.consent(family.older)
    assert (await family.client.get("/v1/household", headers=family.h("amma"))).json()["childrens_notices_shared"] is True
    r = await family.client.put("/v1/household/rules", headers=family.h("paati"), json={"childrens_notices_shared": False})
    assert r.status_code == 403
    r = await family.client.put("/v1/household/rules", headers=family.h("appa"), json={"childrens_notices_shared": False})
    assert r.status_code == 200, r.text
    assert next(x for x in r.json()["rules"] if x["key"] == "childrens_notices_shared")["on"] is False
    assert (await family.client.get("/v1/household", headers=family.h("amma"))).json()["childrens_notices_shared"] is False
    r = await family.upload("amma", pdf("circular"), visibility="private", subjects=[family.older])
    assert r.json()["artifact"]["visibility"] == "private"
    assert await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'household.rules_set'") == 1


async def test_made_private_by_hand_afterwards_it_stays_private_until_tagged_again(family, database):
    await family.consent(family.older)
    r = await family.upload("amma", pdf("circular"), visibility="private", subjects=[family.older])
    aid = r.json()["artifact"]["id"]
    assert r.json()["artifact"]["visibility"] == "shared"
    r = await family.client.patch(f"/v1/artifacts/{aid}", headers=family.h("amma"), json={"visibility": "private"})
    assert r.status_code == 200 and r.json()["visibility"] == "private"
    assert (await family.client.get(f"/v1/artifacts/{aid}", headers=family.h("appa"))).status_code == 404
    # Only the submitter could have done that; and it is sealed to them again.
    assert await database.fetchval("SELECT sealed_for FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1",
                                   uuid.UUID(aid)) == uuid.UUID(family.amma["id"])
