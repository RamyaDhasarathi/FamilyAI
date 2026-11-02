"""A to-do with a date goes to the member's Google Calendar under the same
rule as an accepted date: there while it is open, off again when it is
done or removed. The chat turns "Monday 11 AM" into that date and time."""
import datetime as dt
import uuid

from familyos import calendar, chat
from familyos.identity import Principal
from familyos.intake import google
from familyos.settings import settings
from tests.test_calendar_write import FakeCalendar, on  # noqa: F401 - the fixture turns writing on
from tests.test_gmail import _connect


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def test_a_dated_todo_is_written_as_an_hour_and_comes_off_when_done(family, database):
    fake = FakeCalendar(scopes=list(google.scopes(gmail=True, calendar_write=True)))
    await _connect(family, fake, "amma")
    r = await family.client.post("/v1/todos", headers=family.h("amma"),
                                 json={"title": "Meeting about the FAM project", "due_date": "2031-10-13", "due_time": "11:00"})
    assert r.status_code == 201, r.text
    tid = uuid.UUID(r.json()["id"])
    assert r.json()["due_time"] == "11:00:00"
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1 AND spec->>'todo_id' = $2", calendar.WRITE_KIND, str(tid)) == 1
    assert (await calendar.sync_todo(tid, transport=fake))["written"] == "evt1"
    ev = fake.events["evt1"]
    assert ev["summary"] == "Meeting about the FAM project"
    assert ev["start"]["dateTime"].startswith("2031-10-13T11:00") and ev["end"]["dateTime"].startswith("2031-10-13T12:00")
    assert ev["extendedProperties"]["private"]["familyos_todo"] == str(tid)
    assert (await calendar.sync_todo(tid, transport=fake))["skipped"] == "already_there"
    listed = (await family.client.get("/v1/todos", headers=family.h("appa"))).json()
    assert next(t for t in listed if t["id"] == str(tid))["calendar_event_id"] == "evt1"
    # Done: off the calendar.
    r = await family.client.patch(f"/v1/todos/{tid}", headers=family.h("amma"), json={"done": True})
    assert r.status_code == 200
    assert (await calendar.sync_todo(tid, transport=fake))["removed"] == "evt1" and fake.events == {}


async def test_an_undated_todo_is_not_written_and_a_removed_one_is_taken_off_by_its_ids(family, database):
    fake = FakeCalendar(scopes=list(google.scopes(gmail=True, calendar_write=True)))
    await _connect(family, fake, "amma")
    r = await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Someday"})
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", calendar.WRITE_KIND) == 0
    r = await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Dentist", "due_date": "2031-10-14"})
    tid = uuid.UUID(r.json()["id"])
    assert (await calendar.sync_todo(tid, transport=fake))["written"] == "evt1"
    assert "date" in fake.events["evt1"]["start"]          # all-day without a time
    r = await family.client.delete(f"/v1/todos/{tid}", headers=family.h("amma"))
    assert r.status_code == 204
    job = await database.fetchrow("SELECT spec FROM jobs WHERE kind = $1 AND spec ? 'remove_event_id'", calendar.WRITE_KIND)
    assert job["spec"]["remove_event_id"] == "evt1"
    out = await calendar.remove_event(uuid.UUID(job["spec"]["account_id"]), "evt1", household_id=uuid.UUID(family.household["id"]), transport=fake)
    assert out["removed"] == "evt1" and fake.deleted == ["evt1"]


async def test_the_households_switch_covers_todos_too(family, database):
    await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"calendar_follows_decisions": False})
    r = await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Dentist", "due_date": "2031-10-14"})
    assert r.status_code == 201
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", calendar.WRITE_KIND) == 0


async def test_the_chat_keeps_the_time_and_is_told_the_weekday(family, database, monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)

    class M:
        name = "scripted"
        system = None

        async def reply(self, system, messages, schema=None):
            M.system = system
            return {"say": "I can\u2019t book it; here is the to-do.", "proposals": [
                {"kind": "todo", "title": "Book the Monday 11 AM meeting", "due_date": "2031-10-13", "due_time": "11:00",
                 "member": "Amma", "note": None}]}
    chat.use_model(M())
    try:
        out = await chat.turn(_p(family), "book a meeting monday 11am about the FAM project")
    finally:
        chat.use_model(chat.RefusingModel())
    [p] = out["proposals"]
    assert p["ok"] and p["due_date"] == dt.date(2031, 10, 13) and p["due_time"] == dt.time(11, 0)
    # The model is told which day it is, so "Monday" can be worked out.
    assert any(day in M.system for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))


async def test_a_time_the_model_drops_is_read_from_the_persons_own_words(family, database, monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)

    class M:
        name = "scripted"

        async def reply(self, system, messages, schema=None):
            return {"say": "Here is the to-do.", "proposals": [
                {"kind": "todo", "title": "Meeting to discuss the FAM project", "due_date": "2031-10-13", "due_time": None,
                 "member": None, "note": None}]}
    chat.use_model(M())
    try:
        out = await chat.turn(_p(family), "book a meeting monday 11 AM about the FAM project")
    finally:
        chat.use_model(chat.RefusingModel())
    assert out["proposals"][0]["due_time"] == dt.time(11, 0)
    assert chat._time_in("Dentist at 5:30pm") == dt.time(17, 30) and chat._time_in("call at 14:15") == dt.time(14, 15)
    assert chat._time_in("Pay 2 bills", "nothing here") is None and chat._time_in("Room 12 pm") == dt.time(12, 0)
    assert chat._time_in("tomorrow 3.30PM") == dt.time(15, 30)
