"""PATCH /v1/members/{id}: a member's name, email, phone and role, as the
phone app edits them. Only the fields sent change; a role moves between adult
and child as a birthday crosses eighteen, and what the other kind may not
hold is cleared so the row stays one the schema accepts."""
from familyos import db


async def patch(family, who, member, **body):
    return await family.client.patch(f"/v1/members/{member['id']}", headers=family.h(who), json=body)


async def row(member):
    return await db.pool().fetchrow("SELECT * FROM members WHERE id = $1", member["id"])


async def test_a_guardian_renames_anyone_and_only_the_name_changes(family):
    r = await patch(family, "amma", family.paati, display_name="  Paati Lakshmi ")
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Paati Lakshmi"
    after = await row(family.paati)
    assert after["email"] == "paati@example.com" and after["role"] == "adult"


async def test_a_member_edits_their_own_name_and_contact(family):
    r = await patch(family, "paati", family.paati, email="Paati.New@Example.com", phone="+91 98765 43210")
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "paati.new@example.com" and r.json()["phone"] == "919876543210"


async def test_a_member_who_is_not_a_guardian_cannot_edit_someone_else_or_any_role(family):
    assert (await patch(family, "paati", family.appa, display_name="X")).status_code == 403
    assert (await patch(family, "paati", family.paati, role="child")).status_code == 403


async def test_null_clears_an_address(family):
    r = await patch(family, "amma", family.paati, phone="98765 00001")
    assert r.status_code == 200
    r = await patch(family, "amma", family.paati, phone=None)
    assert r.status_code == 200 and r.json()["phone"] is None and r.json()["email"] == "paati@example.com"


async def test_becoming_a_child_clears_address_phone_and_circle_role(family):
    await db.pool().execute("UPDATE members SET phone = '919876500002', circle_role = 'other' WHERE id = $1", family.paati["id"])
    r = await patch(family, "amma", family.paati, role="child")
    assert r.status_code == 200, r.text
    after = await row(family.paati)
    assert after["role"] == "child" and after["email"] is None and after["phone"] is None and after["circle_role"] is None
    # A child does not sign in: the session they had no longer works.
    assert (await family.client.get("/v1/me", headers=family.h("paati"))).status_code == 401


async def test_becoming_an_adult_clears_school_and_class(family):
    r = await family.client.patch(f"/v1/members/{family.older['id']}/school", headers=family.h("amma"),
                                  json={"school": "Greenwood High", "class_label": "Grade 7"})
    assert r.status_code == 200, r.text
    r = await patch(family, "amma", family.older, role="adult")
    assert r.status_code == 200, r.text
    after = await row(family.older)
    assert after["role"] == "adult" and after["school"] is None and after["class_label"] is None


async def test_a_child_is_not_given_an_address(family):
    assert (await patch(family, "amma", family.older, email="kid@example.com")).status_code == 422
    assert (await row(family.older))["email"] is None


async def test_a_guardians_role_is_not_changed_here(family):
    assert (await patch(family, "amma", family.appa, role="adult")).status_code == 422
    assert (await row(family.appa))["role"] == "guardian"


async def test_an_address_already_in_the_household_is_refused(family):
    r = await patch(family, "amma", family.paati, email="appa@example.com")
    assert r.status_code == 422 and "already exists" in r.json()["detail"]


async def test_an_empty_request_and_an_unknown_member_are_refused(family):
    assert (await patch(family, "amma", family.paati)).status_code == 422
    assert (await patch(family, "amma", {"id": "00000000-0000-0000-0000-000000000000"}, display_name="X")).status_code == 404


async def test_the_audit_names_the_fields_never_the_values(family):
    r = await patch(family, "amma", family.paati, display_name="Secret Name", email="secret@example.com")
    assert r.status_code == 200
    audit = await db.pool().fetchrow("SELECT detail FROM audit_events WHERE action = 'member.updated' AND target_id = $1 "
                                     "ORDER BY id DESC LIMIT 1", family.paati["id"])
    assert audit["detail"] == {"fields": ["display_name", "email"]}
    assert "Secret" not in str(audit["detail"]) and "secret@" not in str(audit["detail"])
