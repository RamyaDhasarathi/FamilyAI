"""Reading the family's own calendar, so a notice can be told it clashes."""
import datetime as dt
import uuid

import pytest

from familyos import brief, calendar
from familyos.intake import google
from familyos.settings import settings
from tests.test_gmail import FakeGoogle, _connect, _principal

TOMORROW = dt.date.today() + dt.timedelta(days=1)
NOON = dt.datetime.combine(TOMORROW, dt.time(12, 0), tzinfo=dt.UTC)


def _event(event_id, summary, start, minutes=60, all_day=False, status="confirmed"):
    if all_day:
        return {"id": event_id, "summary": summary, "status": status,
                "start": {"date": start.date().isoformat()},
                "end": {"date": (start.date() + dt.timedelta(days=1)).isoformat()},
                "updated": "2026-10-01T00:00:00Z"}
    return {"id": event_id, "summary": summary, "status": status,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": (start + dt.timedelta(minutes=minutes)).isoformat()},
            "updated": "2026-10-01T00:00:00Z"}


@pytest.fixture(autouse=True)
def calendar_on(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/v1/google/callback")
    monkeypatch.setattr(settings, "calendar_enabled", True)
    monkeypatch.setattr(settings, "gmail_enabled", True)


async def _obligation(database, family, *, due=TOMORROW, due_time="12:30", title="School trip", action="attend"):
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload("amma", b"%PDF-1.4 " + title.encode(),
                                                 visibility="shared")).json()["artifact"]["id"])
    extraction_id, claim_id, obligation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)",
        extraction_id, household_id, artifact_id)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, "
        "confidence) VALUES ($1, $2, $3, $4, 0, 'event', $5, 'the words', 0.9)",
        claim_id, extraction_id, household_id, artifact_id, title)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, "
        "due_time, status) VALUES ($1, $2, $3, $4, 'task', $8, $5, $6, $7, 'accepted')",
        obligation_id, household_id, artifact_id, claim_id, title, due, due_time, action)
    return obligation_id


# ----------------------------------------------------------------------------
# the scopes, which is the whole reason this ships before Gmail
# ----------------------------------------------------------------------------

def test_calendar_is_asked_for_separately_from_gmail():
    assert google.CALENDAR_SCOPE not in google.scopes(gmail=True, calendar=False)
    assert google.CALENDAR_SCOPE in google.scopes(gmail=False, calendar=True)
    # A calendar-only deployment never asks for the restricted scope at all.
    assert google.GMAIL_SCOPE not in google.scopes(gmail=False, calendar=True)
    assert "openid" in google.scopes(gmail=False, calendar=True)


async def test_the_consent_screen_asks_for_what_the_deployment_reads(family, monkeypatch):
    from familyos.intake import mailbox
    monkeypatch.setattr(settings, "calendar_enabled", True)
    begun = await mailbox.begin(_principal(family))
    assert "calendar.readonly" in begun["url"]
    monkeypatch.setattr(settings, "calendar_enabled", False)
    begun = await mailbox.begin(_principal(family))
    assert "calendar.readonly" not in begun["url"]


# ----------------------------------------------------------------------------
# syncing
# ----------------------------------------------------------------------------

async def test_events_are_read_into_the_window_and_stale_ones_dropped(family, database):
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Swimming", NOON), _event("e2", "Dentist", NOON + dt.timedelta(days=2))])
    account = await _connect(family, fake)

    assert (await calendar.sync(account["id"], transport=fake))["kept"] == 2
    rows = await database.fetch("SELECT summary FROM calendar_events ORDER BY starts_at")
    assert [r["summary"] for r in rows] == ["Swimming", "Dentist"]

    # The dentist appointment is cancelled at Google; it must stop causing clashes.
    fake.events = [_event("e1", "Swimming", NOON)]
    result = await calendar.sync(account["id"], transport=fake)
    assert result == {"kept": 1, "dropped": 1}
    assert [r["summary"] for r in await database.fetch("SELECT summary FROM calendar_events")] == ["Swimming"]


async def test_a_cancelled_event_is_not_stored(family, database):
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Called off", NOON, status="cancelled")])
    account = await _connect(family, fake)
    assert (await calendar.sync(account["id"], transport=fake))["kept"] == 0


async def test_an_account_without_the_scope_is_left_alone(family, database):
    fake = FakeGoogle(scopes=[google.GMAIL_SCOPE, "openid"], events=[_event("e1", "Swimming", NOON)])
    account = await _connect(family, fake)
    assert (await calendar.sync(account["id"], transport=fake)) == {"skipped": "no_calendar_scope"}


# ----------------------------------------------------------------------------
# clashes -- the point of the feature
# ----------------------------------------------------------------------------

async def test_a_notice_that_collides_says_so_in_the_brief(family, database):
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Swimming lesson", NOON, minutes=90)])
    account = await _connect(family, fake)
    await calendar.sync(account["id"], transport=fake)
    await _obligation(database, family, due_time="12:30")

    out = await brief.today(_principal(family), limit=50)
    item = next(i for i in out["items"] if i["title"] == "School trip")
    assert item["clashes"] == ["Swimming lesson"]
    # Said the way a person would, first.
    assert "is tight: clashes with Swimming lesson" in item["why"] and "move one?" in item["why"]


async def test_something_at_another_hour_does_not_clash(family, database):
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Swimming lesson", NOON.replace(hour=7), minutes=60)])
    account = await _connect(family, fake)
    await calendar.sync(account["id"], transport=fake)
    await _obligation(database, family, due_time="12:30")

    out = await brief.today(_principal(family), limit=50)
    item = next(i for i in out["items"] if i["title"] == "School trip")
    assert item["clashes"] is None


async def test_a_notice_with_no_time_is_compared_against_the_whole_day(family, database):
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Grandparents visiting", NOON, all_day=True)])
    account = await _connect(family, fake)
    await calendar.sync(account["id"], transport=fake)
    await _obligation(database, family, due_time=None)

    out = await brief.today(_principal(family), limit=50)
    item = next(i for i in out["items"] if i["title"] == "School trip")
    assert item["clashes"] == ["Grandparents visiting"]


async def test_a_deadline_by_end_of_day_does_not_clash_with_an_all_day_entry(family, database):
    """Seen 10 Oct 2026: "Sign and return the offer letter, EOD" read as 00:00
    and clashed with an all-day calendar entry. A deadline is not a slot."""
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Confirm identification rules", NOON, all_day=True)])
    account = await _connect(family, fake)
    await calendar.sync(account["id"], transport=fake)
    await _obligation(database, family, due_time="EOD", action="sign", title="Sign and return the offer letter")
    out = await brief.today(_principal(family), limit=50)
    item = next(i for i in out["items"] if i["title"] == "Sign and return the offer letter")
    assert not item.get("clashes")
    # But a deadline at a clock time still collides with what is at that hour.
    await _obligation(database, family, due_time="12:30", action="pay", title="Pay the fee at the office")
    fake.events.append(_event("e2", "Dentist", NOON, minutes=90))
    await calendar.sync(account["id"], transport=fake)
    out = await brief.today(_principal(family), limit=50)
    item = next(i for i in out["items"] if i["title"] == "Pay the fee at the office")
    assert "Dentist" in item["clashes"]


async def test_one_members_calendar_is_not_anothers(family, database):
    """An event is private to whoever's calendar it came from, exactly like a
    forwarded notice."""
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Therapy", NOON, minutes=90)])
    account = await _connect(family, fake, who="amma")
    await calendar.sync(account["id"], transport=fake)
    await _obligation(database, family, due_time="12:30")

    mine = await brief.today(_principal(family, "amma"), limit=50)
    assert next(i for i in mine["items"] if i["title"] == "School trip")["clashes"] == ["Therapy"]

    theirs = await brief.today(_principal(family, "appa"), limit=50)
    assert next(i for i in theirs["items"] if i["title"] == "School trip")["clashes"] is None
    assert await calendar.upcoming(_principal(family, "appa")) == []


async def test_nothing_is_read_while_the_calendar_is_off(family, database, monkeypatch):
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Swimming", NOON)])
    account = await _connect(family, fake)
    await calendar.sync(account["id"], transport=fake)
    monkeypatch.setattr(settings, "calendar_enabled", False)

    assert await calendar.sweep() == {"synced": 0, "skipped": 0}
    assert await calendar.clashes_for(_principal(family), [uuid.uuid4()]) == {}
    assert "off" in calendar.describe()


async def test_the_brief_carries_the_clashing_titles_for_the_console(family, database):
    """The console shows the names, not just a flag -- "clashes with what?" is
    the first thing anyone asks."""
    fake = FakeGoogle(scopes=list(google.scopes(gmail=True, calendar=True)),
                      events=[_event("e1", "Swimming lesson", NOON, minutes=90),
                              _event("e2", "Dentist", NOON + dt.timedelta(minutes=15), minutes=30),
                              # Ends exactly as the window opens, so it does not overlap.
                              _event("e3", "School run", NOON, minutes=30)])
    account = await _connect(family, fake)
    await calendar.sync(account["id"], transport=fake)
    await _obligation(database, family, due_time="12:30")

    r = await family.client.get("/v1/brief", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["title"] == "School trip")
    assert sorted(item["clashes"]) == ["Dentist", "Swimming lesson"]


async def test_an_account_connected_for_writing_is_read_too(family, database):
    """calendar.events.owned reads the calendars the member owns, so the
    events FamilyOS wrote come back into the window without a second consent."""
    fake = FakeGoogle(scopes=[google.GMAIL_SCOPE, google.CALENDAR_WRITE_SCOPE, "openid"], events=[_event("e1", "Swimming", NOON)])
    account = await _connect(family, fake)
    out = await calendar.sync(account["id"], transport=fake)
    assert out.get("kept") == 1, out
    assert google.has_calendar([google.CALENDAR_WRITE_SCOPE]) and not google.has_calendar([google.GMAIL_SCOPE])
