"""Health from the phone: the member's own, opt-in, daily summaries only, deleted when switched off, never shared."""
import datetime as dt

import pytest

from familyos import chat, clock, health
from familyos.identity import Principal
from familyos.settings import settings

TODAY = clock.today()


@pytest.fixture(autouse=True)
def _option_on(monkeypatch):
    monkeypatch.setattr(settings, "health_enabled", True)


def _days(n=3, **over):
    return [{"day": (TODAY - dt.timedelta(days=i)).isoformat(), "steps": 8000 + i, "sleep_minutes": 420, "resting_hr": 60, "workouts": 1, "workout_minutes": 30, **over}
            for i in range(n)]


async def _on(family, who="amma"):
    r = await family.client.put("/v1/health/sync", headers=family.h(who), json={"sync": True})
    assert r.status_code == 200, r.text


async def test_sync_is_off_by_default_and_an_upload_is_refused_until_it_is_on(family):
    assert (await family.client.get("/v1/health/sync", headers=family.h("amma"))).json() == {"available": True, "sync": False, "last_day": None}
    assert (await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days()})).status_code == 403


async def test_days_are_kept_and_an_upload_replaces_the_same_day(family):
    await _on(family)
    r = await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(3)})
    assert r.json() == {"stored": 3}
    await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(1, steps=12345)})
    rows = (await family.client.get("/v1/health/daily", headers=family.h("amma"))).json()
    assert len(rows) == 3 and rows[0]["steps"] == 12345


async def test_nobody_else_sees_it_not_even_a_guardian(family):
    await _on(family)
    await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(2)})
    assert (await family.client.get("/v1/health/daily", headers=family.h("appa"))).json() == []


async def test_switching_off_deletes_every_day(family):
    await _on(family)
    await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(2)})
    await family.client.put("/v1/health/sync", headers=family.h("amma"), json={"sync": False})
    assert (await family.client.get("/v1/health/daily", headers=family.h("amma"))).json() == []


async def test_a_value_that_cannot_be_a_body_is_refused(family):
    await _on(family)
    r = await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(1, resting_hr=900)})
    assert r.status_code == 422


def test_the_line_for_ask_states_numbers_and_gives_no_advice():
    rows = [{"day": TODAY, "steps": 8000, "sleep_minutes": 420, "resting_hr": 60, "workouts": 1, "workout_minutes": 30},
            {"day": TODAY, "steps": 6000, "sleep_minutes": 360, "resting_hr": 64, "workouts": 0, "workout_minutes": 0}]
    line = health.line(rows)
    assert "7,000 steps" in line and "6 h 30 min" in line and "62" in line and "1 workout." in line
    assert health.line([]) is None


async def test_ask_has_your_own_summary_and_only_yours(family):
    await _on(family)
    await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(3)})
    me = Principal(member_id=__import__("uuid").UUID(family.amma["id"]), household_id=__import__("uuid").UUID(family.household["id"]),
                   role=family.amma["role"], display_name=family.amma["display_name"])
    other = Principal(member_id=__import__("uuid").UUID(family.appa["id"]), household_id=me.household_id, role=family.appa["role"], display_name=family.appa["display_name"])
    assert any(line.startswith("[HEALTH]") for line in (await chat.context(me)).lines)
    assert not any(line.startswith("[HEALTH]") for line in (await chat.context(other)).lines)


async def test_when_the_option_is_off_nothing_is_offered_or_stored(family, monkeypatch):
    monkeypatch.setattr(settings, "health_enabled", False)
    assert (await family.client.get("/v1/health/sync", headers=family.h("amma"))).json() == {"available": False, "sync": False, "last_day": None}
    assert (await family.client.put("/v1/health/sync", headers=family.h("amma"), json={"sync": True})).status_code == 404
    assert (await family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days()})).status_code == 404
    assert (await family.client.get("/v1/health/daily", headers=family.h("amma"))).json() == []


async def test_an_upload_that_loses_the_race_with_switch_off_leaves_nothing_behind(family, database):
    """Off deletes every row. An upload that is still running when off lands must either be refused or be deleted by it."""
    import asyncio
    await _on(family)
    uploads = [family.client.post("/v1/health/daily", headers=family.h("amma"), json={"days": _days(5)}) for _ in range(6)]
    off = family.client.put("/v1/health/sync", headers=family.h("amma"), json={"sync": False})
    await asyncio.gather(*uploads, off)
    assert await database.fetchval("SELECT count(*) FROM health_daily WHERE member_id = $1", __import__("uuid").UUID(family.amma["id"])) == 0
