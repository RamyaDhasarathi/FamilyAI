"""A person's profile: their own work place and usual start, who may read or change it, and the commute built from it."""
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest

from familyos import profile, publiccontext
from familyos.identity import Invalid, Principal

IST = ZoneInfo("Asia/Kolkata")


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_a_person_sets_and_clears_their_own_work_place_and_a_guardian_can_too(family):
    h = family.h("appa")
    r = await family.client.put(f"/v1/members/{family.appa['id']}/work", headers=h, json={"label": "Riverside Tower", "lat": 13.058, "lon": 80.25, "starts": "09:30"})
    assert r.status_code == 200 and r.json()["work"] == {"place": "Riverside Tower", "lat": 13.058, "lon": 80.25, "starts": "09:30"}
    got = await family.client.get(f"/v1/members/{family.appa['id']}/profile", headers=family.h("amma"))     # a guardian reads it
    assert got.status_code == 200 and got.json()["work"]["place"] == "Riverside Tower" and got.json()["reach"] is None      # their reach settings are theirs alone
    mine = (await family.client.get(f"/v1/members/{family.appa['id']}/profile", headers=h)).json()
    assert mine["is_me"] is True and mine["reach"]["quiet_from"] is not None
    assert (await family.client.put(f"/v1/members/{family.appa['id']}/work", headers=family.h("amma"), json={"label": None, "lat": None, "lon": None, "starts": None})).json()["work"]["place"] is None


async def test_a_profile_is_private_to_the_person_and_guardians_and_a_child_has_no_work_place(family):
    for path, verb, body in ((f"/v1/members/{family.amma['id']}/profile", "get", None),
                             (f"/v1/members/{family.amma['id']}/work", "put", {"label": "x", "lat": 1.0, "lon": 1.0})):
        r = await getattr(family.client, verb)(path, headers=family.h("paati"), **({"json": body} if body else {}))
        assert r.status_code == 403, (path, r.text)                                   # another adult (not a guardian) sees nothing of it
    child = await family.client.put(f"/v1/members/{family.older['id']}/work", headers=family.h("amma"), json={"label": "x", "lat": 1.0, "lon": 1.0})
    assert child.status_code in (400, 422)


async def test_a_place_is_its_words_and_a_point_together_and_a_time_must_be_a_time(family):
    me = _p(family, "appa")
    with pytest.raises(Invalid):
        await profile.set_work(me, me.member_id, label="Office", lat=1.0, lon=None, starts=None)
    with pytest.raises(Invalid):
        await profile.set_work(me, me.member_id, label=None, lat=1.0, lon=1.0, starts=None)
    with pytest.raises(Invalid, match="time"):
        await profile.set_work(me, me.member_id, label="Office", lat=1.0, lon=1.0, starts="late")


async def test_each_adults_commute_is_shown_to_them_and_to_a_guardian_and_to_no_other_adult(family, database, monkeypatch):
    async def usual(a, b, at=None, *, client=None):
        return 25 if b[0] == 13.058 else 40

    async def drive(a, b, *, client=None):
        return 25 if b[0] == 13.058 else 40

    async def live(a, b, *, client=None):
        return None
    monkeypatch.setattr(publiccontext, "usual_drive", usual)
    monkeypatch.setattr(publiccontext, "drive_minutes", drive)
    monkeypatch.setattr(publiccontext, "live_drive", live)
    hid = uuid.UUID(family.household["id"])
    await database.execute("UPDATE households SET travel_time = TRUE, home_place = 'Home', home_lat = 13.0, home_lon = 80.0 WHERE id = $1", hid)
    await profile.set_work(_p(family, "appa"), uuid.UUID(family.appa["id"]), label="Riverside Tower", lat=13.058, lon=80.25, starts="09:30")      # a guardian
    await profile.set_work(_p(family, "paati"), uuid.UUID(family.paati["id"]), label="Clinic", lat=13.2, lon=80.3, starts=None)                     # an adult
    household = dict(await database.fetchrow("SELECT id, travel_time, home_place, home_lat, home_lon, work_place, work_lat, work_lon, country, timezone FROM households WHERE id = $1", hid))
    now = dt.datetime(2026, 10, 12, 8, 0, tzinfo=IST)

    def offices(runs):
        return sorted(r["school"] for r in runs if r.get("office"))
    # an adult who is not a guardian sees only their own, and an adult with none set sees none
    assert offices(await publiccontext.school_runs(household, now=now, viewer=_p(family, "paati"))) == ["Clinic"]
    cousin = (await family.client.post("/v1/household/members", headers=family.h("amma"), json={"display_name": "Cousin", "role": "adult", "email": "cousin@example.com"})).json()
    cousin_p = Principal(member_id=uuid.UUID(cousin["member"]["id"]), household_id=hid, role="adult", display_name="Cousin")
    assert offices(await publiccontext.school_runs(household, now=now, viewer=cousin_p)) == []
    # a guardian sees everyone's, each named, and their own plain
    assert offices(await publiccontext.school_runs(household, now=now, viewer=_p(family, "amma"))) == ["Appa: Riverside Tower", "Paati: Clinic"]
    assert offices(await publiccontext.school_runs(household, now=now, viewer=_p(family, "appa"))) == ["Paati: Clinic", "Riverside Tower"]
    assert offices(await publiccontext.school_runs(household, now=now)) == []                                                      # the system's own look: no personal run
    appa = next(r for r in await publiccontext.school_runs(household, now=now, viewer=_p(family, "appa")) if r.get("office") and r["school"] == "Riverside Tower")
    assert appa["minutes"] == 25 and appa["starts_at"] == "09:30"


async def test_the_households_single_office_still_gives_a_run_until_an_adult_sets_theirs(family, database, monkeypatch):
    async def drive(a, b, *, client=None):
        return 31

    async def none(*a, **k):
        return None
    monkeypatch.setattr(publiccontext, "usual_drive", none)
    monkeypatch.setattr(publiccontext, "drive_minutes", drive)
    monkeypatch.setattr(publiccontext, "live_drive", none)
    hid = uuid.UUID(family.household["id"])
    await database.execute("UPDATE households SET travel_time = TRUE, home_lat = 13.0, home_lon = 80.0, work_place = 'Old office', work_lat = 13.05, work_lon = 80.2 WHERE id = $1", hid)
    household = dict(await database.fetchrow("SELECT id, travel_time, home_place, home_lat, home_lon, work_place, work_lat, work_lon, country, timezone FROM households WHERE id = $1", hid))
    now = dt.datetime(2026, 10, 12, 8, 0, tzinfo=IST)
    assert [r["school"] for r in await publiccontext.school_runs(household, now=now) if r.get("office")] == ["Old office"]
    await profile.set_work(_p(family, "appa"), uuid.UUID(family.appa["id"]), label="New office", lat=13.058, lon=80.25, starts=None)
    assert [r["school"] for r in await publiccontext.school_runs(household, now=now, viewer=_p(family, "paati")) if r.get("office")] == []   # the old one steps aside
