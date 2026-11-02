"""The shapes the iPhone's first-run screens decode (ios/Kit/FirstRun.swift, Setup.swift, Models.swift): a key renamed here breaks the
phone quietly, so each is pinned."""
import uuid


async def _new_household(family, database):
    await database.execute("UPDATE households SET onboarding = '{}'::jsonb WHERE id = $1", uuid.UUID(family.household["id"]))


async def test_the_onboarding_status_has_what_the_phone_decodes(family, database):
    await _new_household(family, database)
    s = (await family.client.get("/v1/household/onboarding", headers=family.h("amma"))).json()
    assert {"steps", "done", "total", "complete", "dismissed", "show", "wizard"} <= set(s)
    assert isinstance(s["wizard"], bool) and s["wizard"] is True
    for step in s["steps"]:
        assert {"key", "title", "detail", "done", "optional"} <= set(step)                  # SetupStep: key, title, detail?, done, optional, on?
    assert [x["key"] for x in s["steps"]][:3] == ["signed_in", "named", "family"]


async def test_renaming_the_home_answers_with_the_name(family):
    out = (await family.client.patch("/v1/household", headers=family.h("amma"), json={"name": "The Rao family"})).json()
    assert out["name"] == "The Rao family"                                                   # the phone reads only `name`


async def test_adding_a_child_answers_with_a_member_the_phone_can_read(family):
    body = {"display_name": "Kavi", "role": "child", "date_of_birth": "2018-07-01"}
    r = await family.client.post("/v1/household/members", headers=family.h("amma"), json=body)
    assert r.status_code == 201
    m = r.json()
    assert {"id", "household_id", "display_name", "role", "date_of_birth"} <= set(m) and m["role"] == "child"   # AddedMember reads `id`


async def test_adding_an_adult_answers_with_credentials_whose_member_has_an_id(family):
    body = {"display_name": "Meena", "role": "adult", "email": "meena@example.com"}
    r = await family.client.post("/v1/household/members", headers=family.h("amma"), json=body)
    assert r.status_code == 201
    out = r.json()
    assert "token" in out and "id" in out["member"]                                           # AddedMember falls back to `member.id`
    invited = await family.client.post(f"/v1/members/{out['member']['id']}/invite", headers=family.h("amma"))
    assert invited.status_code == 202 and {"member_id", "token", "emailed"} <= set(invited.json())     # Invitation
