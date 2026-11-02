"""Emergency mode: a card shared by an expiring, revocable, audited link; check-ins; and nothing beyond the card."""
import datetime as dt
import uuid


async def _set_up(family):
    h = family.h("amma")
    r = await family.client.put("/v1/emergency/profile", headers=h, json={
        "contacts": [{"name": "Dr Rao", "relation": "paediatrician", "phone": "98400 00000"}],
        "pickup": [{"child": family.younger["display_name"], "name": "Paati", "relation": "grandmother", "phone": "98400 11111"}],
        "home_access": "Key with the neighbour at 4B. Gate code 4821."})
    assert r.status_code == 200, r.text
    assert (await family.client.put(f"/v1/members/{family.younger['id']}/medical", headers=h, json={"allergies": "peanuts", "blood_group": "o+"})).status_code == 200


async def test_the_card_holds_what_a_guardian_entered_and_only_a_guardian_edits_it(family):
    await _set_up(family)
    card = (await family.client.get("/v1/emergency/card", headers=family.h("amma"))).json()
    kid = next(x for x in card["people"] if x["name"] == family.younger["display_name"])
    assert kid["allergies"] == "peanuts" and kid["blood_group"] == "O+" and card["contacts"][0]["name"] == "Dr Rao"
    assert card["pickup"][0]["name"] == "Paati" and "4821" in card["home_access"]
    assert (await family.client.put("/v1/emergency/profile", headers=family.h("paati"), json={"home_access": "x"})).status_code == 403


async def test_a_link_opens_without_sign_in_shows_the_card_and_counts_every_opening(family):
    await _set_up(family)
    s = (await family.client.post("/v1/emergency/share", headers=family.h("amma"), json={"label": "Neighbour", "hours": 6})).json()
    r = await family.client.get(f"/v1/emergency/open?token={s['token']}")
    assert r.status_code == 200 and r.json()["shared_with"] == "Neighbour" and r.json()["home_access"] is None      # home access is not included by default
    page = await family.client.get(s["path"])
    assert page.status_code == 200 and "Dr Rao" in page.text and "peanuts" in page.text and "4821" not in page.text
    assert page.headers["cache-control"] == "no-store" and "noindex" in page.headers["x-robots-tag"]
    listing = (await family.client.get("/v1/emergency/shares", headers=family.h("amma"))).json()
    assert listing[0]["opened_count"] == 2 and listing[0]["active"] is True and "token" not in listing[0]


async def test_home_access_is_included_only_when_asked_for(family):
    await _set_up(family)
    s = (await family.client.post("/v1/emergency/share", headers=family.h("amma"), json={"label": "Doctor", "hours": 2, "include_home": True})).json()
    assert "4821" in (await family.client.get(s["path"])).text


async def test_revoked_expired_and_unknown_links_all_say_the_same_thing(family, database):
    await _set_up(family)
    a = (await family.client.post("/v1/emergency/share", headers=family.h("amma"), json={"label": "A", "hours": 5})).json()
    b = (await family.client.post("/v1/emergency/share", headers=family.h("amma"), json={"label": "B", "hours": 5})).json()
    assert (await family.client.delete(f"/v1/emergency/shares/{a['id']}", headers=family.h("amma"))).status_code == 204
    await database.execute("UPDATE emergency_shares SET expires_at = NOW() - interval '1 minute' WHERE id = $1", uuid.UUID(b["id"]))
    answers = [(await family.client.get(f"/v1/emergency/open?token={t}")) for t in (a["token"], b["token"], "em_" + "x" * 32)]
    assert [x.status_code for x in answers] == [404, 404, 404] and len({x.text for x in answers}) == 1
    assert (await family.client.get("/e/em_nothing")).status_code == 404


async def test_a_link_cannot_be_longer_than_72_hours_or_made_by_a_non_guardian(family):
    assert (await family.client.post("/v1/emergency/share", headers=family.h("amma"), json={"label": "x", "hours": 100})).status_code == 422
    assert (await family.client.post("/v1/emergency/share", headers=family.h("paati"), json={"label": "x", "hours": 2})).status_code == 403


async def test_opening_is_audited_and_the_link_page_shows_nothing_else(family):
    await _set_up(family)
    s = (await family.client.post("/v1/emergency/share", headers=family.h("amma"), json={"label": "Neighbour", "hours": 2})).json()
    page = (await family.client.get(s["path"])).text
    for private in ("notice", "bill", "location", "reminder"):
        assert private not in page.lower().replace("emergency", "")
    ledger = (await family.client.get("/v1/activity", headers=family.h("amma"))).json()
    assert any(x["action"] == "emergency.shared" for x in ledger)


async def test_checkins_are_seen_by_the_household_and_needing_help_tells_the_guardians(family, monkeypatch):
    from familyos import notify
    told = []

    async def member(member_id, subject, body, buttons=None):
        told.append((str(member_id), subject))
        return "test"
    monkeypatch.setattr(notify, "member", member)
    assert (await family.client.post("/v1/emergency/checkin", headers=family.h("paati"), json={"status": "safe"})).status_code == 200
    assert told == []
    await family.client.post("/v1/emergency/checkin", headers=family.h("paati"), json={"status": "need_help", "note": "fell on the stairs"})
    assert {t[0] for t in told} == {family.amma["id"], family.appa["id"]} and "needs help" in told[0][1]
    latest = (await family.client.get("/v1/emergency/checkins", headers=family.h("amma"))).json()
    assert latest[0]["status"] == "need_help" and latest[0]["name"] == family.paati["display_name"] and dt.datetime.fromisoformat(latest[0]["at"])


async def test_the_card_checkins_and_shares_have_the_shape_the_iphone_decodes(family):
    """ios/Kit/Emergency.swift decodes these keys."""
    await _set_up(family)
    h = family.h("amma")
    card = (await family.client.get("/v1/emergency/card", headers=h)).json()
    assert {"household", "people", "contacts", "pickup", "documents", "home_access"} <= set(card)
    assert {"name", "role", "allergies", "blood_group", "medicines"} <= set(card["people"][0]) and isinstance(card["people"][0]["medicines"], list)
    assert {"name", "relation", "phone"} <= set(card["contacts"][0]) and {"child", "name", "relation", "phone"} <= set(card["pickup"][0])
    assert (await family.client.post("/v1/emergency/checkin", headers=h, json={"status": "safe"})).status_code == 200
    checkin = (await family.client.get("/v1/emergency/checkins", headers=h)).json()[0]
    assert {"name", "status", "note", "at"} <= set(checkin)
    made = (await family.client.post("/v1/emergency/share", headers=h, json={"label": "Sitter", "hours": 2, "include_home": False})).json()
    assert {"id", "token", "path", "expires_at", "label"} <= set(made) and made["path"].startswith("/e/")
    listed = (await family.client.get("/v1/emergency/shares", headers=h)).json()[0]
    assert {"id", "label", "include_home", "expires_at", "opened_count", "active"} <= set(listed)
