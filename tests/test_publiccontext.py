"""Public context read without any credential: the weather, travel time,
public holidays, a board's exam date sheet. Each behind a switch, each a
line beside the thing it is about, never a fact of the record."""
import datetime as dt
import uuid

import httpx
import pytest

from familyos import notify, publiccontext, rules
from familyos.identity import Principal
from familyos.settings import settings

TODAY = dt.date(2026, 10, 11)
ICS = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261020\nSUMMARY:Diwali\nEND:VEVENT\n"
       "BEGIN:VEVENT\nDTSTART;VALUE=DATE:20261225\nSUMMARY:Christmas\nEND:VEVENT\nEND:VCALENDAR\n")


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


def fake_client(calls):
    """Every public endpoint the module talks to, answered from here; nothing of the family's may be in a request."""
    async def handle(request: httpx.Request):
        calls.append(str(request.url))
        host, path = request.url.host, request.url.path
        if host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": [{"name": "Chennai", "latitude": 13.08, "longitude": 80.27, "admin1": "Tamil Nadu", "country": "India", "timezone": "Asia/Kolkata"}]}
                                  if "Chennai" in request.url.params.get("name", "") else {})
        if host == "api.open-meteo.com":
            return httpx.Response(200, json={"daily": {"time": ["2026-10-11", "2026-10-12", "2026-10-13"], "temperature_2m_max": [33.4, 31.2, 32.0],
                                                       "temperature_2m_min": [25, 24, 24], "precipitation_probability_max": [10, 70, 20], "weather_code": [2, 80, 3]}})
        if host == "calendar.google.com":
            return httpx.Response(200, text=ICS)
        if host == "nominatim.openstreetmap.org":
            q = request.url.params.get("q", "")
            if "Newry" in q:
                return httpx.Response(200, json=[])   # the public map does not know the building
            if "Halls Road" in q:
                return httpx.Response(200, json=[{"lat": "13.0729", "lon": "80.2558", "display_name": "Halls Road, Ward 61, Zone 5 Royapuram, Chennai, Tamil Nadu, India"}])
            return httpx.Response(200, json=[{"lat": "12.98", "lon": "80.22", "display_name": "Aachi Global School, Chennai"}])
        if host == "maps.app.goo.gl":
            return httpx.Response(302, headers={"location": "https://www.google.com/maps/place/Aachi+Global+School/@13.0853299,80.2141425,1002m/data=!3m2!1e3!4b1!4m6!3m5!8m2!3d13.0853299!4d80.2167174?entry=tts"})
        if host == "share.google":
            return httpx.Response(302, headers={"location": "https://www.google.com/search?q=Newry+Shivanee+Apartment,+Halls+Road&kgmid=x"})
        if host == "www.google.com":
            return httpx.Response(200, text="<html>a page</html>")
        if host == "router.project-osrm.org":
            return httpx.Response(200, json={"routes": [{"duration": 1860.0, "distance": 15000}]})
        if host == "api.tomtom.com" and path.startswith("/search/"):
            assert request.url.params.get("key") == "tt-test"
            if "Shivanee" in path:
                return httpx.Response(200, json={"results": [{"type": "POI", "poi": {"name": "Shivanee"}, "address": {"freeformAddress": "Halls Road, Shenoy Nagar, Chennai 600010, Tamil Nadu"},
                                                               "position": {"lat": 13.081485, "lon": 80.234752}}]})
            return httpx.Response(200, json={"results": []})
        if host == "api.tomtom.com":
            # Live traffic under a key: 41 minutes now against 30 usual for the hour.
            assert request.url.params.get("key") == "tt-test" and request.url.params.get("traffic") == "true"
            return httpx.Response(200, json={"routes": [{"summary": {"travelTimeInSeconds": 2460, "historicTrafficTravelTimeInSeconds": 1800,
                                                                      "noTrafficTravelTimeInSeconds": 1500, "trafficDelayInSeconds": 960}}]})
        return httpx.Response(404, json={})
    return httpx.AsyncClient(transport=httpx.MockTransport(handle), headers=publiccontext.UA)


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    publiccontext.forget_cache()
    # The deployment's own key (settings read .env) must not reach a test; each test sets the fake one it wants.
    monkeypatch.setattr(settings, "tomtom_api_key", "")
    async def member(member_id, subject, body):
        return "test"
    monkeypatch.setattr(notify, "member", member)


async def test_the_weather_line_is_said_in_a_parents_words():
    calls = []
    days = await publiccontext.forecast(13.08, 80.27, "Asia/Kolkata", client=fake_client(calls))
    assert publiccontext.say_weather(days[0], "Today") == "Today: 33°, partly cloudy."
    assert publiccontext.say_weather(days[1], "Tomorrow") == "Tomorrow: 31°, showers likely (70%)."
    assert all("family" not in c.lower() for c in calls)


def test_holidays_come_out_of_the_public_calendar_by_date():
    days = publiccontext.parse_ics(ICS)
    assert [h["name"] for h in days] == ["Diwali", "Christmas"]
    assert publiccontext.holidays_between(days, TODAY, TODAY + dt.timedelta(days=14)) == [{"date": dt.date(2026, 10, 20), "name": "Diwali"}]
    assert publiccontext.leave_by("15:30", 31) == "2:49 pm" and publiccontext.leave_by("EOD", 31) is None


async def test_home_is_typed_once_and_geocoded_and_the_lines_need_it(family, database, monkeypatch):
    calls = []
    monkeypatch.setattr(publiccontext, "geocode", lambda place, client=None: _geo(place, calls))
    async def nothing_on_the_map(q, near=None, *, client=None):
        return []
    monkeypatch.setattr(publiccontext, "resolve", nothing_on_the_map)
    r = await family.client.get("/v1/household/rules", headers=family.h("amma"))
    by = {x["key"]: x for x in r.json()["rules"]}
    assert by["weather_lines"]["fixed"] and by["weather_lines"]["why_fixed"] == "needs home" and by["home_place"]["text"] is None
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"home_place": "Chennai"})
    assert r.status_code == 200, r.text
    by = {x["key"]: x for x in r.json()["rules"]}
    assert by["home_place"]["text"] == "Chennai" and by["home_place"]["on"] and not by["weather_lines"]["fixed"]
    row = await database.fetchrow("SELECT home_place, home_lat, home_lon FROM households WHERE id = $1", uuid.UUID(family.household["id"]))
    assert row["home_place"] == "Chennai" and round(row["home_lat"], 2) == 13.08
    # A place the geocoder does not know keeps its name and no point.
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"home_place": "Nowhere Particular"})
    by = {x["key"]: x for x in r.json()["rules"]}
    assert by["home_place"]["text"] == "Nowhere Particular" and not by["home_place"]["on"] and by["weather_lines"]["fixed"]


async def _geo(place, calls):
    calls.append("geocode:" + place)
    return {"lat": 13.08, "lon": 80.27, "label": "Chennai, Tamil Nadu, India", "timezone": "Asia/Kolkata"} if "Chennai" in place else None


async def test_the_brief_carries_the_context_only_when_switched_on(family, database, monkeypatch):
    household_id = uuid.UUID(family.household["id"])
    calls = []
    monkeypatch.setattr(publiccontext, "for_brief", _for_brief_with(calls))
    from familyos import brief
    out = await brief.today(_p(family), on=TODAY)
    assert out["context"] is None and calls == []
    await database.execute("UPDATE households SET weather_lines = TRUE, public_holidays = TRUE, home_place = 'Chennai', home_lat = 13.08, home_lon = 80.27 WHERE id = $1", household_id)
    out = await brief.today(_p(family), on=TODAY)
    assert out["context"]["weather"] == "Today: 33°, partly cloudy. Tomorrow: 31°, showers likely (70%)."
    assert out["context"]["holidays"] == [{"date": dt.date(2026, 10, 20), "name": "Diwali"}]
    assert out["context"]["weather_days"][0]["label"] == "Today" and out["context"]["weather_days"][0]["words"] == "partly cloudy"
    # Leave by on: the typical school run from home, for each school.
    await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Aachi Global School')", uuid.uuid4(), household_id)
    await database.execute("UPDATE households SET travel_time = TRUE WHERE id = $1", household_id)
    out = await brief.today(_p(family), on=TODAY)
    [run] = out["context"]["school_runs"]
    assert run["school"] == "Aachi Global School" and run["minutes"] == 31 and "live_minutes" not in run
    r = await family.client.get("/v1/brief", headers=family.h("amma"))
    assert r.json()["context"]["weather"].startswith("Today: 33°")


def _for_brief_with(calls):
    real = publiccontext.for_brief
    async def wrapped(household, items, on, client=None):
        return await real(household, items, on, client=fake_client(calls))
    return wrapped


async def test_an_exam_date_sheet_is_read_once_and_handed_in_when_it_changes(family, database, monkeypatch):
    from familyos.execution import disposable
    household_id = uuid.UUID(family.household["id"])
    school_id = uuid.uuid4()
    await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Aachi Global School')", school_id, household_id)
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"exam_sheet_url": "https://cbse.example/datesheet"})
    assert r.status_code == 200 and r.json()["exam_sheet_url"] == "https://cbse.example/datesheet"
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"exam_sheet_url": "http://cbse.example/x"})
    assert r.status_code == 422
    pages = {"n": 0}
    async def read(url, allow_hosts, *, client=None):
        pages["n"] += 1
        text = "Class 4 Term 2 exams: Mathematics on 2 December 2026, English on 4 December 2026."
        return disposable.Page(url=url, title="Date sheet", text=text, sha256="x", bytes=len(text), truncated=False)
    monkeypatch.setattr(disposable, "read", read)
    # Off: nothing is read.
    assert await publiccontext.read_exam_sheets() == {"read": 0, "changed": 0, "skipped": 0} and pages["n"] == 0
    await database.execute("UPDATE households SET exam_dates = TRUE WHERE id = $1", household_id)
    assert await publiccontext.read_exam_sheets() == {"read": 1, "changed": 1, "skipped": 0}
    notice = await database.fetchrow("SELECT visibility, note FROM input_artifacts WHERE household_id = $1 ORDER BY received_at DESC LIMIT 1", household_id)
    assert notice["visibility"] == "shared" and "exam date sheet" in (notice["note"] or "")
    # The same page again changes nothing; a notice is not handed in twice.
    assert await publiccontext.read_exam_sheets() == {"read": 1, "changed": 0, "skipped": 0}
    assert await database.fetchval("SELECT count(*) FROM input_artifacts WHERE household_id = $1", household_id) == 1


def test_the_switches_are_in_the_catalogue_with_their_sentences():
    keys = [r["key"] for r in rules._catalogue({"childrens_notices_shared": True, "weekly_digest": True, "calendar_follows_decisions": True,
                                                   "local_models": False, "holidays_accepted": False, "receipts_close_bills": True,
                                                   "bills_handed_to": None, "investments_quiet": True, "pictures_by_model": False})]
    assert keys[-6:] == ["home_place", "work_place", "weather_lines", "travel_time", "public_holidays", "exam_dates"]


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


async def test_a_school_has_an_address_and_timings_and_only_the_fields_given_change(family, database):
    household_id = uuid.UUID(family.household["id"])
    school_id = uuid.uuid4()
    await database.execute("INSERT INTO schools (id, household_id, name, portal_url) VALUES ($1, $2, 'Aachi Global School', 'https://portal.example')", school_id, household_id)
    h = family.h("amma")
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=h, json={"address": "  Aachi Global School, Perungudi,  Chennai ", "starts_at": "08:00", "ends_at": "15:10"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["address"] == "Aachi Global School, Perungudi, Chennai" and body["starts_at"] == "08:00:00" and body["ends_at"] == "15:10:00"
    assert body["portal_url"] == "https://portal.example", "a field not given keeps its value"
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=h, json={"ends_at": "07:00"})
    assert r.status_code == 422
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=h, json={"ends_at": None})
    assert r.status_code == 200 and r.json()["ends_at"] is None and r.json()["starts_at"] == "08:00:00"
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("paati"), json={"address": "x"})
    assert r.status_code == 403


async def test_the_school_run_is_read_live_before_school_and_a_bad_morning_is_told(family, database, monkeypatch):
    household_id = uuid.UUID(family.household["id"])
    calls, told = [], []
    async def member(member_id, subject, body):
        told.append((str(member_id), subject, body))
        return "telegram"
    monkeypatch.setattr(notify, "member", member)
    monkeypatch.setattr(settings, "tomtom_api_key", "tt-test")
    await database.execute("UPDATE households SET travel_time = TRUE, home_place = 'Chennai', home_lat = 13.08, home_lon = 80.27 WHERE id = $1", household_id)
    await database.execute("INSERT INTO schools (id, household_id, name, address, starts_at) VALUES ($1, $2, 'Aachi Global School', 'Aachi Global School, Perungudi, Chennai', '08:00')",
                           uuid.uuid4(), household_id)
    household = dict(await database.fetchrow("SELECT id, travel_time, home_place, home_lat, home_lon, country, timezone FROM households WHERE id = $1", household_id))
    # Monday 12 Oct 2026, 06:45 at home: inside the two hours before school, so the drive is read live.
    morning = dt.datetime(2026, 10, 12, 6, 45, tzinfo=IST)
    [run] = await publiccontext.school_runs(household, now=morning, client=fake_client(calls))
    assert run["minutes"] == 30 and run["usual"] and run["live_minutes"] == 41 and run["usual_minutes"] == 30 and run["delay_minutes"] == 11
    assert run["starts_at"] == "08:00" and run["leave_by"] == "7:09 am", "leave by: the start, less the drive now, less ten minutes"
    tomtom = [c for c in calls if "api.tomtom.com" in c]
    assert len(tomtom) == 2 and all("13.08,80.27:12.98,80.22" in c and "Aachi" not in c for c in tomtom), "two points and the key leave; no name does"
    assert any("departAt=2026-10-12T02%3A00%3A00Z" in c for c in tomtom), "the usual is asked for the school morning, 07:30 at home"
    # The address is what finds the school, not the name with the home town.
    assert any("Perungudi" in c for c in calls if "nominatim" in c)
    # At night nothing live is read, and the leave-by is from the typical drive.
    publiccontext.forget_cache()
    calls.clear()
    [run] = await publiccontext.school_runs(household, now=dt.datetime(2026, 10, 12, 21, 0, tzinfo=IST), client=fake_client(calls))
    assert "live_minutes" not in run and run["leave_by"] == "7:20 am" and not [c for c in calls if "calculateRoute" in c and "departAt" not in c]
    # Nor on a Sunday morning.
    publiccontext.forget_cache()
    [run] = await publiccontext.school_runs(household, now=dt.datetime(2026, 10, 11, 6, 45, tzinfo=IST), client=fake_client(calls))
    assert "live_minutes" not in run
    # The morning's check tells both guardians, once each, with the leave-by.
    publiccontext.forget_cache()
    out = await publiccontext.run_alert(household_id, now=morning, client=fake_client(calls))
    assert out == {"told": 2, "worse": ["Aachi Global School"]}
    assert sorted(t[0] for t in told) == sorted([family.amma["id"], family.appa["id"]])
    assert told[0][1] == "School run to Aachi Global School: 41 min now, usually 30"
    assert "11 minutes worse than usual" in told[0][2] and "Leave by 7:09 am for 08:00" in told[0][2]
    # A normal morning is quiet.
    told.clear()
    publiccontext.forget_cache()
    async def quiet(request):
        if request.url.host == "api.tomtom.com":
            return httpx.Response(200, json={"routes": [{"summary": {"travelTimeInSeconds": 1860, "historicTrafficTravelTimeInSeconds": 1800}}]})
        return await fake_client(calls)._transport.handle_async_request(request)
    out = await publiccontext.run_alert(household_id, now=morning, client=httpx.AsyncClient(transport=httpx.MockTransport(quiet)))
    assert out == {"told": 0, "worse": []} and told == []
    # Without a key nothing is sent anywhere and the run is the typical drive.
    monkeypatch.setattr(settings, "tomtom_api_key", "")
    publiccontext.forget_cache()
    calls.clear()
    [run] = await publiccontext.school_runs(household, now=morning, client=fake_client(calls))
    assert "live_minutes" not in run and run["minutes"] == 31 and not run["usual"] and not [c for c in calls if "tomtom" in c]


async def test_the_morning_check_is_placed_before_the_earliest_start_on_the_next_school_day(family, database):
    household_id = uuid.UUID(family.household["id"])
    household = {"id": household_id, "country": "IN", "timezone": "Asia/Kolkata"}
    starts = [dt.time(8, 0), dt.time(8, 30)]
    calls = []
    # Monday 19 Oct, mid-morning: Tuesday 20 Oct is Diwali in the calendar, so Wednesday at 06:45.
    at = await publiccontext.next_school_morning(household, dt.datetime(2026, 10, 19, 9, 0, tzinfo=IST), starts, client=fake_client(calls))
    assert at == dt.datetime(2026, 10, 21, 6, 45, tzinfo=IST)
    # Friday evening: Monday.
    at = await publiccontext.next_school_morning(household, dt.datetime(2026, 10, 23, 19, 0, tzinfo=IST), starts, client=fake_client(calls))
    assert at == dt.datetime(2026, 10, 26, 6, 45, tzinfo=IST)
    # Early on a school day: that same morning.
    at = await publiccontext.next_school_morning(household, dt.datetime(2026, 10, 26, 5, 0, tzinfo=IST), starts, client=fake_client(calls))
    assert at == dt.datetime(2026, 10, 26, 6, 45, tzinfo=IST)
    assert await publiccontext.next_school_morning(household, dt.datetime(2026, 10, 26, 5, 0, tzinfo=IST), [], client=fake_client(calls)) is None
    # The job follows the switch and the timings: none without a start time, one once a school has one, moved when it changes.
    await database.execute("UPDATE households SET travel_time = TRUE, home_place = 'Chennai', home_lat = 13.08, home_lon = 80.27 WHERE id = $1", household_id)
    school_id = uuid.uuid4()
    await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Aachi Global School')", school_id, household_id)
    assert await publiccontext.ensure_run_scheduled(household_id) is None
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"starts_at": "08:00"})
    assert r.status_code == 200
    job = await database.fetchrow("SELECT status, next_run_at FROM jobs WHERE kind = 'school_run_alert' AND household_id = $1", household_id)
    assert job["status"] == "scheduled" and job["next_run_at"].astimezone(IST).time() == dt.time(6, 45)
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"starts_at": "09:00"})
    assert r.status_code == 200
    jobs = await database.fetch("SELECT status, next_run_at FROM jobs WHERE kind = 'school_run_alert' AND household_id = $1", household_id)
    assert len(jobs) == 1 and jobs[0]["next_run_at"].astimezone(IST).time() == dt.time(7, 45)


async def test_a_place_is_a_map_search_a_pasted_link_or_a_pair_of_coordinates(family, database, monkeypatch):
    calls = []
    client = fake_client(calls)
    # A Google Maps link: the pin it carries, named from its path.
    [pt] = await publiccontext.resolve("https://maps.app.goo.gl/mxwLcUnWnbs5FHEo9", client=client)
    assert pt == {"lat": 13.0853299, "lon": 80.2167174, "label": "Aachi Global School"}
    # A share link that lands on a search: its words, looked up; the building unknown, the street found.
    [pt] = await publiccontext.resolve("https://share.google/FXfaxYmQ1Y2yLBx0r", (13.08, 80.27), client=client)
    assert pt["label"] == "Halls Road, Ward 61, Zone 5 Royapuram" and pt["lat"] == 13.0729
    # Coordinates as typed.
    assert await publiccontext.resolve("13.05848, 80.25367", client=client) == [{"lat": 13.05848, "lon": 80.25367, "label": "13.05848, 80.25367"}]
    # Words, with the home town appended.
    publiccontext.forget_cache()
    found = await publiccontext.resolve("Aachi Global School", "Chennai", client=client)
    assert found[0]["lat"] == 12.98 and any("q=Aachi+Global+School%2C+Chennai" in c for c in calls)
    # With a point for home, the search prefers a box around it instead.
    publiccontext.forget_cache()
    found = await publiccontext.resolve("Aachi Global School", (13.08, 80.27), client=client)
    assert found[0]["lat"] == 12.98 and any("viewbox=80.02" in c and "q=Aachi+Global+School&" in c for c in calls)
    assert await publiccontext.resolve("", client=client) == [] and await publiccontext.resolve("https://evil.example/x", client=client) == []
    # With the key, TomTom's search goes first and knows the building; the public map still answers what it does not.
    monkeypatch.setattr(settings, "tomtom_api_key", "tt-test")
    publiccontext.forget_cache()
    [pt] = await publiccontext.resolve("Newry Shivanee Apartment, Halls Road", (13.08, 80.27), client=client)
    assert pt == {"label": "Shivanee, Halls Road, Shenoy Nagar", "lat": 13.081485, "lon": 80.234752}
    found = await publiccontext.resolve("Aachi Global School", (13.08, 80.27), client=client)
    assert found[0]["lat"] == 12.98
    monkeypatch.setattr(settings, "tomtom_api_key", "")
    # Through the API: adults search, a guardian picks home and the office; a child does neither.
    monkey = publiccontext.resolve
    async def resolve(q, near=None, *, client=None):
        return await monkey(q, near, client=fake_client(calls))
    publiccontext.resolve = resolve
    try:
        r = await family.client.get("/v1/places/search", params={"q": "Halls Road, Egmore"}, headers=family.h("paati"))
        assert r.status_code == 200 and r.json()[0]["label"].startswith("Halls Road")
        r = await family.client.put("/v1/household/places/home", headers=family.h("amma"), json={"label": "Newry Shivanee Apartment, Halls Road", "lat": 13.0729, "lon": 80.2558})
        assert r.status_code == 200, r.text
        home = next(x for x in r.json()["rules"] if x["key"] == "home_place")
        assert home["on"] and home["text"] == "Newry Shivanee Apartment, Halls Road" and home["kind"] == "place"
        r = await family.client.put("/v1/household/places/work", headers=family.h("amma"), json={"label": "Prestige Palladium Bayan", "lat": 13.05848, "lon": 80.25367})
        assert r.status_code == 200 and next(x for x in r.json()["rules"] if x["key"] == "work_place")["on"]
        r = await family.client.put("/v1/household/places/work", headers=family.h("paati"), json={"label": "x", "lat": 1, "lon": 1})
        assert r.status_code == 403
        r = await family.client.put("/v1/household/places/garden", headers=family.h("amma"), json={"label": "x", "lat": 1, "lon": 1})
        assert r.status_code == 404
        row = await database.fetchrow("SELECT home_place, home_lat, work_place, work_lat FROM households WHERE id = $1", uuid.UUID(family.household["id"]))
        assert row["home_lat"] == 13.0729 and row["work_lat"] == 13.05848
        # A school picked on the map keeps the point; words alone are placed by the map.
        school_id = uuid.uuid4()
        await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Aachi Global School')", school_id, uuid.UUID(family.household["id"]))
        r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"address": "Aachi Global School", "lat": 13.0853299, "lon": 80.2167174})
        assert r.status_code == 200 and r.json()["lat"] == 13.0853299
        r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"address": "Halls Road, Egmore"})
        assert r.status_code == 200 and r.json()["lat"] == 13.0729 and r.json()["address"] == "Halls Road, Egmore"
        r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"address": None, "lat": None, "lon": None})
        assert r.status_code == 200 and r.json()["lat"] is None
        # The office commute sits beside the school run; the alert never speaks of it.
        publiccontext.forget_cache()
        await database.execute("UPDATE households SET travel_time = TRUE WHERE id = $1", uuid.UUID(family.household["id"]))
        household = dict(await database.fetchrow("SELECT id, travel_time, home_place, home_lat, home_lon, work_place, work_lat, work_lon, country, timezone FROM households WHERE id = $1", uuid.UUID(family.household["id"])))
        runs = await publiccontext.school_runs(household, now=dt.datetime(2026, 10, 12, 8, 0, tzinfo=IST), client=fake_client(calls))
        office = next(r for r in runs if r.get("office"))
        assert office["school"] == "Prestige Palladium Bayan" and office["minutes"] == 31 and "live_minutes" not in office
    finally:
        publiccontext.resolve = monkey
