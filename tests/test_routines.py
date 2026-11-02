"""Routines (an instruction and a time, said in chat) and the interruption budget that bounds what FamilyOS says unprompted."""
import datetime as dt
import uuid

import pytest

from familyos import chat, interruptions, notify, routines
from familyos.db import pool
from familyos.identity import Principal
from tests.test_chat import Scripted

SUNDAY = dt.date(2026, 10, 11)                       # a Sunday
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _at(hour, minute=0, day=SUNDAY):
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=IST).astimezone(dt.UTC)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def member(member_id, subject, body, buttons=None):
        out.append((member_id, subject, body))
        return "telegram"

    monkeypatch.setattr(notify, "member", member)
    return out


async def test_a_member_sets_lists_and_stops_their_own_routine(family):
    r = await family.client.post("/v1/routines", headers=family.h("amma"), json={"instruction": "List next week's school dates", "weekday": 6, "hour": 18})
    assert r.status_code == 201, r.text
    assert r.json()["when"] == "every Sunday at 6pm"
    assert len((await family.client.get("/v1/routines", headers=family.h("amma"))).json()) == 1
    assert (await family.client.get("/v1/routines", headers=family.h("appa"))).json() == []          # no one sees another's
    assert (await family.client.delete(f"/v1/routines/{r.json()['id']}", headers=family.h("appa"))).status_code == 404
    assert (await family.client.delete(f"/v1/routines/{r.json()['id']}", headers=family.h("amma"))).status_code == 204
    assert (await family.client.get("/v1/routines", headers=family.h("amma"))).json() == []


async def test_a_routine_runs_once_on_its_day_after_its_hour_and_says_what_it_found(family, sent):
    chat.use_model(Scripted({"say": "Two things next week: PTM on Friday [n1].", "proposals": []}))
    await routines.create(_p(family), "List next week's school dates", 6, 18)
    assert (await routines.sweep(_at(17, 30)))["sent"] == 0                       # before its hour
    assert (await routines.sweep(_at(19, 0)))["sent"] == 1
    assert "PTM on Friday" in sent[0][2] and sent[0][1].startswith("Routine:")
    assert (await routines.sweep(_at(20, 0)))["sent"] == 0                       # once for the day
    assert (await routines.sweep(_at(19, 0, day=SUNDAY + dt.timedelta(days=1))))["sent"] == 0     # not on a Monday


async def test_a_routine_with_nothing_to_say_is_silent_but_counts_as_run(family, sent):
    chat.use_model(Scripted({"say": "NOTHING", "proposals": []}))
    await routines.create(_p(family), "Anything late?", None, 9)
    assert (await routines.sweep(_at(10, 0)))["silent"] == 1 and sent == []
    assert (await routines.sweep(_at(11, 0)))["silent"] == 0


async def test_quiet_hours_hold_a_routine_until_they_end(family, sent):
    chat.use_model(Scripted({"say": "Something to report.", "proposals": []}))
    await routines.create(_p(family), "Anything late?", None, 21)
    assert (await routines.sweep(_at(22, 30)))["waited"] == 1 and sent == []         # the default quiet window is 22 to 7
    await interruptions.set_prefs(uuid.UUID(family.amma["id"]), quiet_from=23, quiet_to=7, daily_cap=None)
    assert (await routines.sweep(_at(22, 40)))["sent"] == 1


async def test_the_daily_cap_holds_the_rest(family, sent):
    chat.use_model(Scripted({"say": "Something to report.", "proposals": []}))
    await interruptions.set_prefs(uuid.UUID(family.amma["id"]), quiet_from=None, quiet_to=None, daily_cap=1)
    await routines.create(_p(family), "First", None, 8)
    await routines.create(_p(family), "Second", None, 8)
    out = await routines.sweep(_at(12, 0))
    assert out["sent"] == 1 and out["waited"] == 1


async def test_a_child_cannot_set_a_routine_and_a_bad_time_is_refused(family):
    kid = Principal(member_id=uuid.UUID(family.older["id"]), household_id=uuid.UUID(family.household["id"]), role="child", display_name="x")
    with pytest.raises(Exception):  # noqa: B017 - NotAllowed
        await routines.create(kid, "Anything", None, 9)
    assert (await family.client.post("/v1/routines", headers=family.h("amma"), json={"instruction": "Anything late", "hour": 25})).status_code == 422


def test_ask_proposals_for_a_routine_are_checked():
    good = chat.resolve([{"kind": "routine", "instruction": "Tell me next week's school dates", "weekday": 6, "hour": 18}], chat.Facts())[0]
    assert good["ok"] and good["weekday"] == 6 and good["hour"] == 18
    bad = chat.resolve([{"kind": "routine", "instruction": "x", "weekday": 9, "hour": 30}], chat.Facts())[0]
    assert bad["ok"] is False and bad["why"]


def test_the_quiet_window_may_cross_midnight():
    assert interruptions.in_quiet(23, 22, 7) and interruptions.in_quiet(3, 22, 7) and not interruptions.in_quiet(12, 22, 7)
    assert not interruptions.in_quiet(5, 6, 6)


async def test_the_interruption_prefs_round_trip(family):
    put = await family.client.put("/v1/me/interruptions", headers=family.h("amma"), json={"quiet_from": 23, "daily_cap": 5})
    assert put.status_code == 200 and put.json() == {"quiet_from": 23, "quiet_to": 7, "daily_cap": 5, "morning_hour": 8}
    assert (await pool().fetchval("SELECT proactive_daily_cap FROM members WHERE id = $1", uuid.UUID(family.amma["id"]))) == 5
