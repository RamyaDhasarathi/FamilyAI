"""Household Autopilot: routines that fire on events as well as clocks, with a policy, a pause and a history."""
import datetime as dt
import uuid

from familyos import chat, clock, notify, routines
from familyos.identity import Principal
from tests.conftest import pdf
from tests.test_brief import _obligation

NOON = dt.datetime.combine(clock.today(), dt.time(6, 30), tzinfo=dt.UTC)       # midday in India: outside quiet hours


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _fakes(monkeypatch, say="Pay it by Friday."):
    sent, asked = [], []

    async def member(member_id, subject, body, buttons=None):
        sent.append((str(member_id), subject, body))
        return "test"

    async def turn(p, message, history=None):
        asked.append(message)
        return {"say": say, "proposals": []}
    monkeypatch.setattr(notify, "member", member)
    monkeypatch.setattr(chat, "turn", turn)
    return sent, asked


async def test_an_event_routine_is_set_with_its_trigger_and_policy(family):
    r = await family.client.post("/v1/routines", headers=family.h("amma"),
                                 json={"instruction": "Compare it with the usual", "trigger": "bill_arrived", "policy": "prepare"})
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["trigger"] == "bill_arrived" and got["policy"] == "prepare" and got["when"] == "when a bill arrives"
    bad = await family.client.post("/v1/routines", headers=family.h("amma"), json={"instruction": "Pack", "trigger": "trip_soon"})
    assert bad.status_code in (400, 422)
    ok = await family.client.post("/v1/routines", headers=family.h("amma"), json={"instruction": "Make a packing list", "trigger": "trip_soon", "trigger_days": 3})
    assert ok.json()["when"] == "3 days before travel"


async def test_a_bill_that_arrives_fires_the_routine_once_and_the_run_is_kept(family, database, monkeypatch):
    sent, asked = _fakes(monkeypatch)
    await routines.create(_p(family), "Compare it with the usual amount", None, 0, trigger="bill_arrived")
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=clock.today() + dt.timedelta(days=5), status="accepted", title="Electricity bill", action="pay")
    assert (await routines.sweep(NOON))["sent"] == 1
    assert "Trigger: a bill arrived: Electricity bill" in asked[0] and sent
    assert (await routines.sweep(NOON)) == {"sent": 0, "silent": 0, "waited": 0, "failed": 0, "already": 0}       # once per bill
    rid = (await family.client.get("/v1/me/day", headers=family.h("amma"))).json()["routines"][0]["id"]
    hist = (await family.client.get(f"/v1/routines/{rid}/history", headers=family.h("amma"))).json()
    assert [(h["trigger"], h["outcome"]) for h in hist] == [("bill_arrived", "sent")] and "Friday" in hist[0]["said"]


async def test_a_bill_that_was_already_there_does_not_fire_a_new_routine(family, database, monkeypatch):
    _, asked = _fakes(monkeypatch)
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=clock.today() + dt.timedelta(days=5), status="accepted", title="Old bill", action="pay")
    await routines.create(_p(family), "Compare it", None, 0, trigger="bill_arrived")
    await routines.sweep(NOON)
    assert asked == []


async def test_a_paused_routine_does_not_run_and_resuming_brings_it_back(family, database, monkeypatch):
    _, asked = _fakes(monkeypatch)
    r = await routines.create(_p(family), "Compare it", None, 0, trigger="bill_arrived")
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=clock.today() + dt.timedelta(days=5), status="accepted", title="Water bill", action="pay")
    assert (await family.client.put(f"/v1/routines/{r['id']}/pause", headers=family.h("amma"), json={"paused": True})).json()["paused"] is True
    await routines.sweep(NOON)
    assert asked == []
    await family.client.put(f"/v1/routines/{r['id']}/pause", headers=family.h("amma"), json={"paused": False})
    assert (await routines.sweep(NOON))["sent"] == 1


async def test_a_trip_n_days_away_fires_on_that_day_only(family, database, monkeypatch):
    _, asked = _fakes(monkeypatch)
    await routines.create(_p(family), "Make a packing list", None, 0, trigger="trip_soon", trigger_days=3)
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=a, due=clock.today() + dt.timedelta(days=3), status="accepted", title="Trip to Munnar", action="attend")
    b = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=b, due=clock.today() + dt.timedelta(days=9), status="accepted", title="Trip to Goa", action="attend")
    assert (await routines.sweep(NOON))["sent"] == 1 and "Munnar" in asked[0]


async def test_a_clock_routine_still_runs_and_is_logged(family, monkeypatch):
    sent, _ = _fakes(monkeypatch, say="Sports day on Friday.")
    r = await routines.create(_p(family), "List the week", None, 0)
    assert (await routines.sweep(NOON))["sent"] == 1
    hist = await routines.history(_p(family), r["id"])
    assert [(h["trigger"], h["outcome"]) for h in hist] == [("time", "sent")] and sent


async def test_nobody_reads_another_members_routine_history(family):
    r = await routines.create(_p(family), "List the week", None, 8)
    assert (await family.client.get(f"/v1/routines/{r['id']}/history", headers=family.h("appa"))).status_code == 404
