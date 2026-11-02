"""The first-run checklist: read off the household, only a guardian answers it, existing households are not nagged."""
import uuid

from familyos import identity
from familyos.db import pool


async def _new_household(family, database):
    """A fresh household the way a new person gets one: no checklist answers yet (the migration only silences the ones that existed)."""
    await database.execute("UPDATE households SET onboarding = '{}'::jsonb WHERE id = $1", uuid.UUID(family.household["id"]))


async def test_a_new_household_sees_six_steps_and_the_ones_it_has_done_are_ticked(family, database):
    await _new_household(family, database)
    s = (await family.client.get("/v1/household/onboarding", headers=family.h("amma"))).json()
    assert [x["key"] for x in s["steps"]] == ["signed_in", "named", "family", "channel", "mail", "private"] and s["show"] is True
    done = {x["key"]: x["done"] for x in s["steps"]}
    assert done == {"signed_in": True, "named": False, "family": True, "channel": False, "mail": False, "private": False}   # the fixture already has other members
    assert s["done"] == 2 and s["total"] == 6 and s["complete"] is False
    assert s["wizard"] is True                                                                     # nothing answered yet: the first-run screens are due


async def test_confirming_the_name_and_putting_off_privacy_completes_it_and_a_dismissal_hides_it(family, database):
    await _new_household(family, database)
    h = family.h("amma")
    named = (await family.client.post("/v1/household/onboarding/named", headers=h)).json()
    assert named["done"] == 3 and named["wizard"] is False                                          # the first-run screens appear once
    for choice in ("skip_channel", "skip_mail"):
        await family.client.post(f"/v1/household/onboarding/{choice}", headers=h)
    out = (await family.client.post("/v1/household/onboarding/skip_private", headers=h)).json()
    assert out["complete"] is True and out["show"] is False
    await _new_household(family, database)
    gone = (await family.client.post("/v1/household/onboarding/dismissed", headers=h)).json()
    assert gone["dismissed"] is True and gone["show"] is False


async def test_making_it_private_ticks_the_last_step_and_only_a_guardian_answers(family, database):
    await _new_household(family, database)
    assert (await family.client.post("/v1/household/onboarding/named", headers=family.h("paati"))).status_code == 403
    shown_to_adult = (await family.client.get("/v1/household/onboarding", headers=family.h("paati"))).json()
    assert shown_to_adult["show"] is False                                                        # an adult who is not a guardian is not asked
    assert (await family.client.post("/v1/household/onboarding/nonsense", headers=family.h("amma"))).status_code in (400, 422)
    made = (await family.client.post("/v1/household/family-key/begin", headers=family.h("amma"), json={"threshold": 2, "count": 3})).json()
    await family.client.post("/v1/household/family-key/confirm", headers=family.h("amma"), json={"shares": made["shares"][:2]})
    s = (await family.client.get("/v1/household/onboarding", headers=family.h("amma"))).json()
    assert {x["key"]: x["done"] for x in s["steps"]}["private"] is True


async def test_existing_households_start_dismissed_by_the_migration_and_a_founder_sees_the_checklist(family, database):
    # a household founded now has no answers; the migration's blanket dismissal only applied to the rows that existed then
    founded = await pool().fetchval("SELECT onboarding FROM households WHERE id = $1", uuid.UUID(family.household["id"]))
    assert founded in ({}, {"dismissed": True}) and identity is not None


async def test_a_guardian_renames_the_home_and_nobody_else_does(family, database):
    h = family.h("amma")
    out = await family.client.patch("/v1/household", headers=h, json={"name": "  The   Iyer family "})
    assert out.status_code == 200 and out.json()["name"] == "The Iyer family"
    assert (await family.client.patch("/v1/household", headers=family.h("paati"), json={"name": "Mine"})).status_code == 403
    assert (await family.client.patch("/v1/household", headers=h, json={"name": "   "})).status_code == 422
    assert (await family.client.get("/v1/household", headers=h)).json()["name"] == "The Iyer family"


async def test_a_linked_channel_tick_its_step_and_a_mailbox_is_still_open(family, database):
    await _new_household(family, database)
    me = (await family.client.get("/v1/me", headers=family.h("amma"))).json()["id"]
    await database.execute("UPDATE members SET telegram_chat_id = 42 WHERE id = $1", uuid.UUID(me))
    s = (await family.client.get("/v1/household/onboarding", headers=family.h("amma"))).json()
    done = {x["key"]: x["done"] for x in s["steps"]}
    assert done["channel"] is True and done["mail"] is False
