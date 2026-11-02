"""One idea of today: the household's. Stored in UTC, shown in the household's zone."""
import datetime as dt
import uuid

from familyos import clock
from familyos.settings import settings


def test_today_is_the_households_day_not_the_servers(monkeypatch):
    real = dt.datetime
    class At(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 10, 20, 21, 30, tzinfo=dt.UTC).astimezone(tz) if tz else real(2026, 10, 20, 21, 30)
    monkeypatch.setattr(clock.dt, "datetime", At)
    assert clock.today("UTC") == dt.date(2026, 10, 20)
    assert clock.today("Asia/Dubai") == dt.date(2026, 10, 21)          # 01:30 the next morning in Dubai
    assert clock.today("America/Los_Angeles") == dt.date(2026, 10, 20)
    assert clock.now("Asia/Kolkata").hour == 3 and clock.now("Asia/Kolkata").minute == 0
    monkeypatch.setattr(settings, "timezone", "Asia/Dubai")
    assert clock.today() == dt.date(2026, 10, 21)                       # no household bound: the deployment's zone, never the machine's
    with clock.use("America/Los_Angeles"):
        assert clock.today() == dt.date(2026, 10, 20)
    assert clock.today() == dt.date(2026, 10, 21)
    assert clock.today("Not/AZone") == dt.date(2026, 10, 21)            # an unknown zone falls back, never raises


def test_the_sql_date_is_a_literal_made_by_us():
    assert clock.sql_date("UTC").endswith("'::date") and clock.sql_date("UTC").count("'") == 2


async def test_a_request_is_bound_to_its_households_zone(family, database):
    from familyos.db import pool
    await pool().execute("UPDATE households SET timezone = 'Pacific/Auckland' WHERE id = $1", uuid.UUID(family.household["id"]))
    clock.forget(uuid.UUID(family.household["id"]))
    r = await family.client.get("/v1/brief", headers=family.h("amma"))
    assert r.status_code == 200
    # the brief names the household's day
    assert r.json()["date"] == clock.today("Pacific/Auckland").isoformat()


async def test_a_person_can_have_their_own_zone_and_language_in_the_database(family, database):
    import uuid as _uuid
    r = await family.client.get("/v1/me/locale", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["timezone"] == r.json()["household_timezone"] and r.json()["language"] == "en"
    assert (await family.client.put("/v1/me/locale", headers=family.h("amma"), json={"timezone": "Asia/Nowhere"})).status_code == 422
    assert (await family.client.put("/v1/me/locale", headers=family.h("amma"), json={"language": "not a tag"})).status_code == 422
    r = await family.client.put("/v1/me/locale", headers=family.h("amma"), json={"timezone": "Asia/Dubai", "language": "TA"})
    assert r.status_code == 200 and r.json()["timezone"] == "Asia/Dubai" and r.json()["language"] == "ta"
    assert r.json()["household_timezone"] != "Asia/Dubai" or r.json()["own_timezone"] == "Asia/Dubai"
    assert await database.fetchval("SELECT timezone FROM members WHERE id = $1", _uuid.UUID(family.amma["id"])) == "Asia/Dubai"
    assert await database.fetchval("SELECT timezone FROM members WHERE id = $1", _uuid.UUID(family.appa["id"])) is None
    assert (await family.client.get("/v1/brief", headers=family.h("amma"))).json()["date"] == clock.today("Asia/Dubai").isoformat()
    r = await family.client.put("/v1/me/locale", headers=family.h("amma"), json={"clear": True})
    assert r.json()["own_timezone"] is None and r.json()["language"] == "en"
    # a guardian can set the household's language along with where it lives
    r = await family.client.put("/v1/household/locale", headers=family.h("amma"), json={"country": "IN", "timezone": "Asia/Kolkata", "currency": "INR", "language": "hi"})
    assert r.status_code == 200
    assert (await family.client.get("/v1/me/locale", headers=family.h("appa"))).json()["language"] == "hi"


async def test_a_reminder_goes_at_the_persons_own_morning_in_their_own_zone(family, database):
    import datetime as _dt
    import uuid as _uuid

    from familyos import reminders
    from familyos.db import pool
    from tests.test_brief import _obligation
    household = _uuid.UUID(family.household["id"])
    await pool().execute("UPDATE households SET timezone = 'America/Los_Angeles' WHERE id = $1", household)
    await pool().execute("UPDATE members SET timezone = 'Asia/Dubai' WHERE id = $1", _uuid.UUID(family.appa["id"]))
    aid = (await family.upload("amma", __import__("tests.conftest", fromlist=["pdf"]).pdf("tz"), filename="t.pdf", visibility="shared")).json()["artifact"]["id"]
    due = _dt.date(2026, 11, 10)
    await _obligation(database, family, artifact_id=aid, due=due, title="Fees")
    async with pool().acquire() as conn, conn.transaction():
        await reminders.schedule(conn, _dt.date(2026, 11, 1))
    rows = {r["display_name"]: r["send_after"] for r in await database.fetch(
        "SELECT m.display_name, r.send_after FROM reminders r JOIN members m ON m.id = r.member_id WHERE r.lead_days = 0 AND r.reason = 'due'")}
    assert rows["Amma"] == _dt.datetime(2026, 11, 10, 16, 0, tzinfo=_dt.UTC)       # 08:00 in Los Angeles (UTC-8 in November)
    assert rows["Appa"] == _dt.datetime(2026, 11, 10, 4, 0, tzinfo=_dt.UTC)        # 08:00 in Dubai, the person's own zone


async def test_a_loop_over_households_does_not_carry_one_zone_into_the_next(family, database):
    hid = uuid.UUID(family.household["id"])
    from familyos.db import pool
    await pool().execute("UPDATE households SET timezone = 'Pacific/Auckland' WHERE id = $1", hid)
    clock.forget(hid)
    before = clock.today()
    async with clock.household(hid):
        assert clock.today() == clock.today("Pacific/Auckland")
    assert clock.today() == before                                      # the turn ended with its zone
    async with clock.household(None):
        assert clock.today() == before                                  # a job with no household: the deployment's


async def test_a_job_runs_on_its_households_day(family, database):
    from familyos import jobs
    hid = uuid.UUID(family.household["id"])
    from familyos.db import pool
    await pool().execute("UPDATE households SET timezone = 'Pacific/Kiritimati' WHERE id = $1", hid)      # UTC+14
    clock.forget(hid)
    seen = {}

    async def handler(job, ctx):
        seen["today"] = clock.today()
        return {}
    jobs.register("tz_probe", handler, version="1", settings_keys=())
    job = await jobs.create("tz_probe", {}, household_id=hid)
    await jobs.run(job)
    assert seen["today"] == clock.today("Pacific/Kiritimati")


async def test_a_reminder_is_scheduled_by_the_households_own_day(family, database):
    """On a server in UTC at 02:00 on the 21st, a Los Angeles household is still on the 20th: something due on the 20th is today, not past."""
    import datetime as _dt

    from familyos import reminders
    from familyos.db import pool
    from tests.test_brief import _obligation
    hid = uuid.UUID(family.household["id"])
    await pool().execute("UPDATE households SET timezone = 'America/Los_Angeles' WHERE id = $1", hid)
    aid = (await family.upload("amma", __import__("tests.conftest", fromlist=["pdf"]).pdf("la"), filename="la.pdf", visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=aid, due=_dt.date(2026, 10, 20), title="LA fees")
    with clock.freeze(_dt.datetime(2026, 10, 21, 2, 0, tzinfo=_dt.UTC)):
        async with pool().acquire() as conn, conn.transaction():
            made = await reminders.schedule(conn)
    assert made["due"] >= 1
    await database.execute("DELETE FROM reminders")
    await pool().execute("UPDATE households SET timezone = 'Asia/Kolkata' WHERE id = $1", hid)      # 07:30 on the 21st there: the 20th has passed
    with clock.freeze(_dt.datetime(2026, 10, 21, 2, 0, tzinfo=_dt.UTC)):
        async with pool().acquire() as conn, conn.transaction():
            made = await reminders.schedule(conn)
    assert made["due"] == 0
