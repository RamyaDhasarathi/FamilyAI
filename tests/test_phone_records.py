"""The JSON the iPhone's Records screens decode (ios/Kit/Records.swift): consent, the digest, what-if and notices that did not arrive."""
import datetime as dt


def _has(row: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in row]
    assert not missing, f"missing {missing} in {sorted(row)}"


async def test_consent_has_the_keys_the_phone_decodes_and_withdrawing_names_what_it_erases(family):
    h = family.h("amma")
    kid = (await family.client.post("/v1/household/members", headers=h, json={"display_name": "Ila", "role": "child", "date_of_birth": "2019-07-01"})).json()
    body = {"subject_member_id": kid["id"], "purpose": "household_records", "notice_version": "2026-10", "verification_method": "account_holder", "declares_guardian": True}
    made = await family.client.post("/v1/consents", headers=h, json=body)
    assert made.status_code == 201, made.text
    rows = (await family.client.get("/v1/consents", headers=h)).json()
    _has(rows[0], "id", "subject_member_id", "purpose", "notice_version", "verification_method", "guardian_declared_at", "granted_at", "withdrawn_at")
    assert rows[0]["guardian_declared_at"] is not None
    assert (await family.client.post(f"/v1/consents/{rows[0]['id']}/withdraw", headers=family.h("paati"))).status_code == 403
    out = await family.client.post(f"/v1/consents/{rows[0]['id']}/withdraw", headers=h)
    assert out.status_code == 202, out.text
    _has(out.json(), "id", "scope", "status")


async def test_the_digest_preview_and_send_have_the_keys_the_phone_decodes(family):
    preview = (await family.client.get("/v1/digest", headers=family.h("amma"))).json()
    _has(preview, "subject", "body", "sends_on")
    _has((await family.client.post("/v1/digest/send", headers=family.h("amma"))).json(), "sent", "channel", "why")


async def test_every_scenario_has_the_keys_the_phone_decodes_and_changes_nothing(family):
    h, today = family.h("amma"), dt.date.today()
    for body in ({"kind": "member_away", "member_id": family.appa["id"], "start": str(today), "end": str(today + dt.timedelta(days=5))},
                 {"kind": "spend", "amount": 15000}, {"kind": "school_reopens", "reopens_on": str(today + dt.timedelta(days=9))}):
        out = (await family.client.post("/v1/scenarios", headers=h, json=body)).json()
        _has(out, "scenario", "headline", "impacts", "changes_nothing")
        assert out["changes_nothing"] is True
        for impact in out["impacts"]:
            _has(impact, "kind", "title")


async def test_intake_gaps_and_their_summary_have_the_keys_the_phone_decodes(family):
    h = family.h("amma")
    made = await family.client.post("/v1/intake-gaps", headers=h, json={"title": "Sports day note", "lived_where": "whatsapp_group", "also_emailed": False, "had_date": True})
    assert made.status_code == 201, made.text
    _has((await family.client.get("/v1/intake-gaps", headers=h)).json()[0], "id", "title", "lived_where", "also_emailed", "had_date", "arrived_as", "created_at")
    summary = (await family.client.get("/v1/intake-gaps/summary", headers=h)).json()
    _has(summary, "captured", "missed_reported", "capture_rate", "missed_by_where", "caveat")
    _has(summary["missed_by_where"][0], "lived_where", "count", "means")
