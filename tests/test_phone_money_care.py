"""The JSON the iPhone's Money and care screens decode (ios/Kit/Standing.swift, Care.swift, Handoffs.swift, Circle.swift): the keys the Swift models need,
so a server change that drops one fails here and not on a phone."""
from tests.conftest import pdf


def _has(row: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in row]
    assert not missing, f"missing {missing} in {sorted(row)}"


async def test_standing_payments_billers_and_bills_have_the_keys_the_phone_decodes(family):
    h = family.h("amma")
    made = await family.client.post("/v1/standing", headers=h, json={"title": "Rent", "payee": "Rao Estates", "amount": 20000, "day_of_month": 5})
    assert made.status_code == 201, made.text
    rows = (await family.client.get("/v1/standing", headers=h)).json()
    _has(rows[0], "id", "title", "payee", "amount", "currency", "day_of_month", "next_due", "subject_name", "visibility", "created_by")
    biller = await family.client.post("/v1/billers", headers=h, json={"label": "Electricity", "provider": "State Power", "identifier": "123456789"})
    assert biller.status_code == 201, biller.text
    _has((await family.client.get("/v1/billers", headers=h)).json()[0], "id", "label", "provider", "identifier_hint", "every_days", "grace_days", "visibility", "last_seen_at")
    _has((await family.client.get("/v1/bills", headers=h)).json()[0], "id", "title", "due_date", "status")
    assert (await family.client.delete(f"/v1/standing/{rows[0]['id']}", headers=h)).status_code == 204       # the phone sends DELETE and expects no body
    assert (await family.client.get("/v1/standing", headers=h)).json() == []


async def test_the_care_view_has_the_keys_the_phone_decodes(family):
    care = (await family.client.get(f"/v1/members/{family.appa['id']}/care", headers=family.h("amma"))).json()
    _has(care, "member", "documents", "document_checks", "bills", "appointments", "medications", "standing", "unusual", "scams", "handed_over")
    _has(care["member"], "id", "household_id", "display_name", "role")


async def test_handoffs_workload_and_load_have_the_keys_the_phone_decodes(family):
    a = (await family.upload("amma", pdf("pmc1"), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{a}/assign", headers=family.h("amma"), json={"member_id": family.appa["id"], "note": "please"})
    items = (await family.client.get("/v1/handoffs", headers=family.h("amma"))).json()["items"]
    _has(items[0], "id", "title", "with", "state", "since", "has_backup", "direction")
    assert items[0]["direction"] == "waiting_on"
    assert (await family.client.get("/v1/handoffs", headers=family.h("appa"))).json()["items"][0]["direction"] == "for_me"
    _has((await family.client.get("/v1/workload", headers=family.h("amma"))).json()[0], "member_id", "name", "open", "handled_30d")
    load = (await family.client.get("/v1/load", headers=family.h("amma"))).json()
    _has(load, "days", "total", "undecided", "missed", "members", "note")
    if load["members"]:
        _has(load["members"][0], "member_id", "display_name", "carried", "share", "noticed", "decided", "acted")


async def test_grants_and_presets_have_the_keys_the_phone_decodes_and_only_a_guardian_hands_one_out(family):
    presets = (await family.client.get("/v1/circle/presets", headers=family.h("amma"))).json()
    _has(presets[0], "key", "label", "actions", "days")
    made = await family.client.post("/v1/circle/presets/appointments", headers=family.h("amma"), json={"member_id": family.paati["id"]})
    assert made.status_code == 200, made.text
    grants = (await family.client.get("/v1/grants", headers=family.h("paati"))).json()                    # anyone may read the list
    _has(grants[0], "id", "grantee_member_id", "grantee_name", "granted_by_name", "subject_name", "actions", "reason", "expires_at")
    assert (await family.client.post("/v1/circle/presets/appointments", headers=family.h("paati"), json={"member_id": family.appa["id"]})).status_code == 403
    assert (await family.client.delete(f"/v1/grants/{grants[0]['id']}", headers=family.h("amma"))).json() == {"revoked": grants[0]["id"]}
