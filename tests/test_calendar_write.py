"""An accepted date on the member's own Google Calendar, and off it again
when it is dismissed or the notice is handled. One reconciler decides."""
import datetime as dt
import json
import uuid

import pytest

from familyos import calendar
from familyos.db import pool
from familyos.intake import google
from familyos.settings import settings
from tests.conftest import pdf
from tests.test_gmail import FakeGoogle, _connect

CAL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class FakeCalendar(FakeGoogle):
    """Google, plus a calendar that remembers what was written."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.events: dict[str, dict] = {}
        self.deleted: list[str] = []

    async def __call__(self, method, url, *, headers, params, data):
        if url == CAL and method == "POST":
            body = json.loads(data)
            event_id = f"evt{len(self.events) + 1}"
            self.events[event_id] = body
            return 200, json.dumps({"id": event_id}).encode()
        if url.startswith(CAL + "/") and method == "DELETE":
            event_id = url.rsplit("/", 1)[1]
            self.deleted.append(event_id)
            return (204, b"") if self.events.pop(event_id, None) is not None else (404, b"")
        return await super().__call__(method, url, headers=headers, params=params, data=data)


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/v1/google/callback")
    monkeypatch.setattr(settings, "gmail_enabled", True)
    monkeypatch.setattr(settings, "calendar_write_enabled", True)
    monkeypatch.setattr(settings, "timezone", "Asia/Kolkata")


async def _obligation(family, who="amma", title="Pay the term fee", due=None, time=None):
    due = due or dt.date.today() + dt.timedelta(days=5)
    artifact_id = uuid.UUID((await family.upload(who, pdf(title), visibility="shared")).json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    xid, cid, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'deadline', $5, $5, 0.9)", cid, xid, household_id, artifact_id, title)
    await pool().execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, due_time) "
        "VALUES ($1, $2, $3, $4, 'task', 'pay', $5, $6, $7)", oid, household_id, artifact_id, cid, title, due, time)
    return artifact_id, oid


def test_the_event_is_all_day_on_its_date_or_an_hour_from_its_time():
    row = {"id": uuid.uuid4(), "title": "PTM", "due_date": dt.date(2026, 10, 9), "end_date": None, "due_time": None,
           "headline": "Circular 12", "artifact_id": uuid.uuid4()}
    e = calendar.event_for(row)
    assert e["start"] == {"date": "2026-10-09"} and e["end"] == {"date": "2026-10-10"}
    assert e["summary"] == "PTM" and "Circular 12" in e["description"]
    assert e["extendedProperties"]["private"]["familyos_obligation"] == str(row["id"])
    row["due_time"] = "5:00 p.m."
    e = calendar.event_for(row)
    assert e["start"] == {"dateTime": "2026-10-09T17:00:00", "timeZone": "Asia/Kolkata"}
    assert e["end"]["dateTime"] == "2026-10-09T18:00:00"
    row["due_time"], row["end_date"] = None, dt.date(2026, 10, 11)
    assert calendar.event_for(row)["end"] == {"date": "2026-10-12"}


async def test_accepting_writes_the_event_and_dismissing_removes_it(family, database):
    fake = FakeCalendar(scopes=list(google.scopes(gmail=True, calendar_write=True)))
    await _connect(family, fake, "amma")
    artifact_id, oid = await _obligation(family)
    r = await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert r.status_code == 200
    # The decision queued the reconciler; run it.
    assert (await calendar.sync_obligation(oid, transport=fake))["written"] == "evt1"
    assert fake.events["evt1"]["summary"] == "Pay the term fee"
    assert await database.fetchval("SELECT calendar_event_id FROM obligations WHERE id = $1", oid) == "evt1"
    # Again: nothing to do, no second copy.
    assert (await calendar.sync_obligation(oid, transport=fake))["skipped"] == "already_there"
    # Dismissed: gone.
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "dismissed"})
    assert (await calendar.sync_obligation(oid, transport=fake))["removed"] == "evt1"
    assert fake.deleted == ["evt1"] and fake.events == {}
    assert await database.fetchval("SELECT calendar_event_id FROM obligations WHERE id = $1", oid) is None


async def test_handled_takes_the_date_off_the_calendar_and_reopen_puts_it_back(family, database):
    fake = FakeCalendar(scopes=list(google.scopes(gmail=True, calendar_write=True)))
    await _connect(family, fake, "amma")
    artifact_id, oid = await _obligation(family)
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    await calendar.sync_obligation(oid, transport=fake)
    await family.client.post(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("amma"), json={"note": "paid"})
    assert "removed" in await calendar.sync_obligation(oid, transport=fake)
    await family.client.delete(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("amma"))
    assert "written" in await calendar.sync_obligation(oid, transport=fake)
    assert len(fake.events) == 1


async def test_without_the_grant_nothing_is_written_and_nothing_breaks(family, database):
    fake = FakeCalendar()      # gmail only
    await _connect(family, fake, "amma")
    _, oid = await _obligation(family)
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert (await calendar.sync_obligation(oid, transport=fake))["skipped"] == "no_calendar_write"
    assert fake.events == {}


async def test_the_decision_queues_the_reconciler_only_when_writing_is_on(family, database, monkeypatch):
    _, oid = await _obligation(family)
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", calendar.WRITE_KIND) == 1
    monkeypatch.setattr(settings, "calendar_write_enabled", False)
    _, oid2 = await _obligation(family, title="Another")
    await family.client.post(f"/v1/obligations/{oid2}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", calendar.WRITE_KIND) == 1


def test_a_period_with_times_is_the_same_hours_every_school_day_until_it_ends(monkeypatch):
    """Half days during assessments: 8:30 to 12:30 from the 8th until the
    16th is one timed event repeating on weekdays, not one morning."""
    from familyos.settings import settings
    monkeypatch.setattr(settings, "timezone", "Asia/Kolkata")
    row = {"id": uuid.uuid4(), "title": "Half working days for SA 1 Assessments", "due_date": dt.date(2026, 10, 8),
           "end_date": dt.date(2026, 10, 16), "due_time": "8:30 a.m. to 12:30 p.m.", "headline": "Half working days", "artifact_id": uuid.uuid4()}
    e = calendar.event_for(row)
    assert e["start"] == {"dateTime": "2026-10-08T08:30:00", "timeZone": "Asia/Kolkata"}
    assert e["end"] == {"dateTime": "2026-10-08T12:30:00", "timeZone": "Asia/Kolkata"}
    assert e["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261016T182959Z"]
    # One day with a span: the span, no series. A span written "3 to 5 p.m." reads the morning right.
    one = calendar.event_for({**row, "end_date": None})
    assert "recurrence" not in one and one["end"]["dateTime"] == "2026-10-08T12:30:00"
    assert calendar._span("3 to 5 p.m.") == (dt.time(15, 0), dt.time(17, 0))
    assert calendar._span("0830-1230 Hrs") == (dt.time(8, 30), dt.time(12, 30))
    assert calendar._span("5:00 p.m.") == (dt.time(17, 0), None)


async def test_a_re_read_that_supersedes_an_accepted_date_takes_its_event_off(family, database):
    """Before 11 Oct 2026 the event stayed: a family saw "School reopens" three
    times on one day, each from a reading the next one had superseded."""
    from familyos.extraction import service
    fake = FakeCalendar(scopes=list(google.scopes(gmail=True, calendar_write=True)))
    await _connect(family, fake, "amma")
    artifact_id, oid = await _obligation(family, title="School reopens")
    await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert "written" in await calendar.sync_obligation(oid, transport=fake)
    household_id = uuid.UUID(family.household["id"])
    # The switch is turned off afterwards; the event must still come off.
    await database.execute("UPDATE households SET calendar_follows_decisions = FALSE WHERE id = $1", household_id)
    async with pool().acquire() as conn, conn.transaction():
        n = await service._supersede_unsupported(conn, household_id, artifact_id, proposed=[], claims=[])
    assert n == 1
    job = await database.fetchrow("SELECT spec FROM jobs WHERE kind = 'calendar_event' AND household_id = $1 ORDER BY created_at DESC LIMIT 1", household_id)
    assert job and job["spec"]["obligation_id"] == str(oid)
    assert "removed" in await calendar.sync_obligation(oid, transport=fake)
    assert fake.events == {}
