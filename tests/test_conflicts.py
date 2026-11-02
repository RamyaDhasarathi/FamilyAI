"""A clash that says who could cover: free, busy or unknown per adult, never what the event is."""
import datetime as dt
import uuid

from familyos import clock, conflicts
from familyos.identity import Principal

DAY = clock.today() + dt.timedelta(days=3)


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def _calendar(database, family, who, summary, start, minutes=60, synced=True):
    member = uuid.UUID(getattr(family, who)["id"])
    hid = uuid.UUID(family.household["id"])
    account = await database.fetchval("SELECT id FROM google_accounts WHERE member_id = $1", member)
    if account is None:
        account = uuid.uuid4()
        await database.execute(
            "INSERT INTO google_accounts (id, household_id, member_id, email, subject, sealed_refresh_token, calendar_synced_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)", account, hid, member, f"{who}@example.com", str(uuid.uuid4()), b"x", dt.datetime.now(dt.UTC) if synced else None)
    if summary:
        await database.execute(
            "INSERT INTO calendar_events (id, household_id, member_id, account_id, external_id, summary, starts_at, ends_at, visibility) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'private')", uuid.uuid4(), hid, member, account, str(uuid.uuid4()), summary, start, start + dt.timedelta(minutes=minutes))


def test_a_timed_date_has_a_span_and_an_untimed_one_does_not():
    tz = conflicts.ZoneInfo("Asia/Kolkata")
    s, e = conflicts.window_of(DAY, "17:00", tz)
    assert (e - s) == dt.timedelta(hours=1) and s.astimezone(tz).strftime("%H:%M") == "17:00"
    assert conflicts.window_of(DAY, "5:30 PM", tz)[0].astimezone(tz).strftime("%H:%M") == "17:30"
    assert conflicts.window_of(DAY, None, tz) is None and conflicts.window_of(DAY, "EOD", tz) is None


async def test_free_busy_never_says_what_the_event_is(family, database):
    await database.execute("UPDATE households SET timezone = 'UTC' WHERE id = $1", uuid.UUID(family.household["id"]))
    at = dt.datetime.combine(DAY, dt.time(17, 0), tzinfo=dt.UTC)
    await _calendar(database, family, "appa", "Private dentist", at)
    await _calendar(database, family, "paati", None, at)                 # connected, nothing in the way
    cover = await conflicts.cover_for(_p(family), DAY, "17:00", [
        {"id": family.appa["id"], "name": "Appa"}, {"id": family.paati["id"], "name": "Paati"}])
    states = {x["name"]: x["state"] for x in cover["people"]}
    assert states == {"Appa": "busy", "Paati": "free"}
    assert [x["name"] for x in cover["people"]] == ["Paati", "Appa"]       # free first
    assert "Private dentist" not in str(cover)


async def test_no_calendar_connected_is_unknown_not_free(family, database):
    cover = await conflicts.cover_for(_p(family), DAY, "17:00", [{"id": family.appa["id"], "name": "Appa"}])
    assert cover["people"][0]["state"] == "unknown"


async def test_a_clashing_date_card_names_who_looks_free_and_hands_over_to_them(family, database, monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "calendar_enabled", True)
    from tests.conftest import pdf
    from tests.test_brief import _obligation
    hid = uuid.UUID(family.household["id"])
    await database.execute("UPDATE households SET timezone = 'UTC' WHERE id = $1", hid)
    a = (await family.upload("amma", pdf("cf1"), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=a, due=DAY, status="proposed", title="School pickup", action="attend")
    await database.execute("UPDATE obligations SET due_time = '17:00' WHERE id = $1", oid)
    at = dt.datetime.combine(DAY, dt.time(17, 0), tzinfo=dt.UTC)
    await _calendar(database, family, "amma", "Client meeting", at)
    await _calendar(database, family, "appa", None, at)
    cards = (await family.client.get("/v1/decisions", headers=family.h("amma"))).json()
    card = next(c for c in cards if c["title"] == "School pickup")
    assert card["conflict"]["with"] == "Client meeting" and family.appa["display_name"] in card["conflict"]["free"]
    assert card["recommendation"]["action"] == "delegate" and "looks free" in card["recommendation"]["text"]
    delegate = next(x for x in card["actions"] if x["key"] == "delegate")
    assert delegate["choices"][0]["label"].startswith(family.appa["display_name"]) and "(free then)" in delegate["choices"][0]["label"]
