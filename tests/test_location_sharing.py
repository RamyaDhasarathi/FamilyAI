"""Location sharing: each adult's own choice, the latest point only, and arrivals said once."""
import uuid

from familyos import notify
from familyos.db import pool

HOME = (12.9716, 77.5946)
FAR = (13.2000, 77.7000)


async def _set_home(family):
    await pool().execute("UPDATE households SET home_place = 'Home', home_lat = $2, home_lon = $3 WHERE id = $1",
                         uuid.UUID(family.household["id"]), *HOME)


async def _share(family, who, on=True):
    r = await family.client.put("/v1/location/sharing", headers=family.h(who), json={"sharing": on})
    assert r.status_code == 200, r.text


async def _fix(family, who, where, at=None):
    body = {"lat": where[0], "lon": where[1], "accuracy_m": 20}
    if at:
        body["at"] = at
    return await family.client.post("/v1/location", headers=family.h(who), json=body)


async def test_sharing_is_off_by_default_and_a_fix_is_refused_until_it_is_on(family):
    assert (await family.client.get("/v1/location/sharing", headers=family.h("amma"))).json() == {"sharing": False}
    assert (await _fix(family, "amma", HOME)).status_code == 403


async def test_nobody_sees_anyone_unless_they_share_too(family):
    await _share(family, "amma")
    await _fix(family, "amma", HOME)
    assert (await family.client.get("/v1/location/family", headers=family.h("appa"))).json() == {"sharing": False, "people": []}
    await _share(family, "appa")
    people = (await family.client.get("/v1/location/family", headers=family.h("appa"))).json()["people"]
    assert {p["name"] for p in people} >= {family.amma["display_name"]}


async def test_only_the_latest_point_is_kept_and_stopping_deletes_it(family):
    await _share(family, "amma")
    await _fix(family, "amma", HOME, at="2026-10-10T08:00:00Z")
    await _fix(family, "amma", FAR, at="2026-10-10T09:00:00Z")
    assert await pool().fetchval("SELECT count(*) FROM member_locations WHERE member_id = $1", uuid.UUID(family.amma["id"])) == 1
    older = await _fix(family, "amma", HOME, at="2026-10-10T07:00:00Z")
    assert older.json() == {"kept": False}
    await _share(family, "amma", on=False)
    assert await pool().fetchval("SELECT count(*) FROM member_locations WHERE member_id = $1", uuid.UUID(family.amma["id"])) == 0


async def test_an_arrival_at_home_is_said_once_to_the_other_sharing_adults(family, monkeypatch):
    await _set_home(family)
    told = []

    async def member(member_id, subject, body):
        told.append((member_id, subject))

    monkeypatch.setattr(notify, "member", member)
    await _share(family, "amma")
    await _share(family, "appa")
    await _fix(family, "amma", FAR, at="2026-10-10T08:00:00Z")
    assert told == []
    await _fix(family, "amma", HOME, at="2026-10-10T09:00:00Z")
    await _fix(family, "amma", HOME, at="2026-10-10T09:05:00Z")
    assert len(told) == 1 and told[0][0] == uuid.UUID(family.appa["id"]) and "reached home" in told[0][1]
    people = (await family.client.get("/v1/location/family", headers=family.h("appa"))).json()["people"]
    assert next(p for p in people if p["name"] == family.amma["display_name"])["place"] == "home"


async def test_someone_who_is_not_sharing_is_not_told_and_a_bad_point_is_refused(family, monkeypatch):
    await _set_home(family)
    told = []

    async def member(member_id, subject, body):
        told.append(member_id)

    monkeypatch.setattr(notify, "member", member)
    await _share(family, "amma")
    await _fix(family, "amma", FAR, at="2026-10-10T08:00:00Z")
    await _fix(family, "amma", HOME, at="2026-10-10T09:00:00Z")
    assert told == []
    bad = await family.client.post("/v1/location", headers=family.h("amma"), json={"lat": 120, "lon": 0})
    assert bad.status_code == 422
