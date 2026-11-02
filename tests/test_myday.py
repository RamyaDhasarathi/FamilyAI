"""My day: the signed-in member's own page, and nobody else's."""
import uuid

from familyos import clock, feedback, routines
from familyos.identity import Principal


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_my_day_has_the_whole_page_for_the_member(family):
    r = await family.client.get("/v1/me/day", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    day = r.json()
    assert day["display_name"] == family.amma["display_name"] and day["date"] == clock.today().isoformat()
    assert set(day) >= {"needs", "more", "counts", "suggestions", "routines", "reach_me", "learned", "health"}
    assert set(day["reach_me"]) == {"quiet_from", "quiet_to", "daily_cap", "morning_hour"}
    assert day["health"]["available"] is False            # the private option is off unless the deployment says so


async def test_my_day_carries_only_my_routines_and_my_counts(family):
    await routines.create(_p(family, "amma"), "List next week's school dates", 6, 18)
    await feedback.record(_p(family, "amma"), "gift", "accepted")
    mine = (await family.client.get("/v1/me/day", headers=family.h("amma"))).json()
    other = (await family.client.get("/v1/me/day", headers=family.h("appa"))).json()
    assert [x["instruction"] for x in mine["routines"]] == ["List next week's school dates"]
    assert mine["learned"] == [{"kind": "gift", "accepted": 1, "dismissed": 0, "quiet": False}]
    assert other["routines"] == [] and other["learned"] == []
    assert other["display_name"] == family.appa["display_name"]


async def test_my_day_needs_sign_in(family):
    assert (await family.client.get("/v1/me/day")).status_code in (401, 403)
