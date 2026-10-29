"""Adding a member from the phone: the app's Add member sends a name, a role
and a birthday, never an address. A guardian still needs one (they sign in
and can act for the household); an adult may be added without one and gets
no session until they have one; a child never has one."""


async def test_an_adult_can_be_added_without_an_address_and_gets_no_session(family):
    r = await family.client.post("/v1/household/members", headers=family.h("amma"),
                                 json={"display_name": "Grandma", "role": "adult", "date_of_birth": "1950-03-03"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token" not in body and body["role"] == "adult" and body["email"] is None


async def test_an_adult_with_an_address_still_gets_a_session(family):
    r = await family.client.post("/v1/household/members", headers=family.h("amma"),
                                 json={"display_name": "Uncle", "role": "adult", "email": "uncle@example.com"})
    assert r.status_code == 201, r.text
    assert r.json()["token"] and r.json()["member"]["email"] == "uncle@example.com"


async def test_a_guardian_still_needs_an_address(family):
    r = await family.client.post("/v1/household/members", headers=family.h("amma"),
                                 json={"display_name": "Second guardian", "role": "guardian"})
    assert r.status_code == 422 and "guardian needs an email" in r.json()["detail"]


async def test_a_child_still_has_no_address(family):
    r = await family.client.post("/v1/household/members", headers=family.h("amma"),
                                 json={"display_name": "Baby", "role": "child", "email": "baby@example.com"})
    assert r.status_code == 422


async def test_only_a_guardian_adds_members(family):
    r = await family.client.post("/v1/household/members", headers=family.h("paati"),
                                 json={"display_name": "Friend", "role": "adult"})
    assert r.status_code == 403
