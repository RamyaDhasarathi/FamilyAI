"""Public context, read without any credential: the weather, travel time,
public holidays, a board's exam date sheet.

Each is a switch on the household, off until a guardian turns it on, and
each is class 1: a public page or a public API read with nothing of the
family's in the request beyond a city and a place name. What comes back is
context on the brief, said in a line beside the thing it is about, never a
fact of the record. Sources: Open-Meteo for geocoding and the forecast,
Google's public holiday calendars (iCalendar), OpenStreetMap's Nominatim
for a place and the OSRM demo server for a drive, a board's own page for
the date sheet. Everything is cached for a while so a brief costs nothing.

One source takes a key: TomTom's Routing API, for the school run with live
traffic. It is the one request that carries two points of the family's,
home and the school, so it is made only in the two hours before school and
the hour before pick-up, on a school day, with the "leave by" switch on;
and the morning's check tells the guardians only when the drive is
ALERT_DELAY minutes worse than usual for the hour. Without a key the
school run is the typical drive from public maps and nothing is sent.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import time
import uuid
from zoneinfo import ZoneInfo

import httpx

from familyos import notify
from familyos.db import pool
from familyos.execution.agent import TOKEN
from familyos.settings import settings

logger = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 " + TOKEN}
TIMEOUT = 12.0
_cache: dict[str, tuple[float, object]] = {}


class _http:
    """A client to use: the one handed in, left open for the next call, or a
    fresh one closed on the way out."""

    def __init__(self, client: httpx.AsyncClient | None):
        self.given, self.own = client, None

    async def __aenter__(self) -> httpx.AsyncClient:
        if self.given is not None:
            return self.given
        self.own = httpx.AsyncClient(timeout=TIMEOUT, headers=UA)
        return self.own

    async def __aexit__(self, *exc) -> None:
        if self.own is not None:
            await self.own.aclose()

# Google's public holiday calendars, by country: a public .ics, no key.
HOLIDAY_CALENDARS = {"IN": "en.indian#holiday@group.v.calendar.google.com", "AE": "en.ae#holiday@group.v.calendar.google.com",
                     "US": "en.usa#holiday@group.v.calendar.google.com", "GB": "en.uk#holiday@group.v.calendar.google.com",
                     "SG": "en.singapore#holiday@group.v.calendar.google.com"}
# WMO weather codes, in words a family uses.
WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle",
       55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 80: "showers", 81: "showers", 82: "heavy showers",
       95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}


def _cached(key: str, ttl: float):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    return None


def _keep(key: str, value):
    _cache[key] = (time.monotonic(), value)
    return value


def forget_cache() -> None:
    _cache.clear()


# ----------------------------------------------------------------------------
# where home is
# ----------------------------------------------------------------------------

async def geocode(place: str, *, client: httpx.AsyncClient | None = None) -> dict | None:
    """A city or town to a point, from Open-Meteo's geocoder. None when it is not found."""
    place = " ".join((place or "").split())[:100]
    if not place:
        return None
    if (hit := _cached("geo:" + place.casefold(), 86400)) is not None:
        return hit
    async with _http(client) as http:
        r = await http.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": place, "count": 1, "language": "en", "format": "json"})
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
    if not results:
        return None
    g = results[0]
    label = ", ".join(x for x in (g.get("name"), g.get("admin1"), g.get("country")) if x)
    return _keep("geo:" + place.casefold(), {"lat": float(g["latitude"]), "lon": float(g["longitude"]), "label": label, "timezone": g.get("timezone")})


# ----------------------------------------------------------------------------
# the weather
# ----------------------------------------------------------------------------

async def forecast(lat: float, lon: float, timezone: str, *, days: int = 3, client: httpx.AsyncClient | None = None) -> list[dict]:
    key = f"wx:{lat:.3f}:{lon:.3f}:{days}"
    if (hit := _cached(key, 3600)) is not None:
        return hit
    async with _http(client) as http:
        r = await http.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "timezone": timezone, "forecast_days": days,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"})
        r.raise_for_status()
        d = (r.json() or {}).get("daily") or {}
    out = []
    for i, day in enumerate(d.get("time") or []):
        out.append({"date": dt.date.fromisoformat(day), "tmax": (d.get("temperature_2m_max") or [None])[i],
                    "tmin": (d.get("temperature_2m_min") or [None])[i], "rain": (d.get("precipitation_probability_max") or [None])[i],
                    "code": (d.get("weather_code") or [None])[i]})
    return _keep(key, out)


def say_weather(day: dict, label: str) -> str:
    """One line a parent reads: "Tomorrow: 33°, showers likely (70%)."."""
    words = WMO.get(day.get("code") if day.get("code") is not None else -1, "")
    rain = day.get("rain")
    parts = []
    if day.get("tmax") is not None:
        parts.append(f"{round(day['tmax'])}°")
    if rain is not None and rain >= 40:
        parts.append(f"rain likely ({int(rain)}%)" if not words.startswith(("rain", "showers", "drizzle", "thunder")) else f"{words} likely ({int(rain)}%)")
    elif words:
        parts.append(words)
    return f"{label}: " + ", ".join(parts) + "." if parts else ""


# ----------------------------------------------------------------------------
# public holidays
# ----------------------------------------------------------------------------

def parse_ics(text: str) -> list[dict]:
    """The all-day events of an iCalendar feed: (date, name)."""
    out = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        m = re.search(r"DTSTART;VALUE=DATE:(\d{8})", block)
        s = re.search(r"SUMMARY:(.*)", block)
        if m and s:
            out.append({"date": dt.date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:])), "name": s.group(1).strip()})
    return sorted(out, key=lambda h: h["date"])


async def holidays(country: str, *, client: httpx.AsyncClient | None = None) -> list[dict]:
    cal = HOLIDAY_CALENDARS.get((country or "").upper())
    if not cal:
        return []
    if (hit := _cached("hol:" + country, 86400)) is not None:
        return hit
    url = "https://calendar.google.com/calendar/ical/" + cal.replace("#", "%23").replace("@", "%40") + "/public/basic.ics"
    async with _http(client) as http:
        r = await http.get(url)
        r.raise_for_status()
        text = r.text
    return _keep("hol:" + country, parse_ics(text))


def holidays_between(all_days: list[dict], start: dt.date, end: dt.date) -> list[dict]:
    return [h for h in all_days if start <= h["date"] <= end]


# ----------------------------------------------------------------------------
# travel time from home
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# a place the family picks: a map search, a pasted Google Maps link, a pair
# of coordinates
# ----------------------------------------------------------------------------

SHORT_MAP_HOSTS = {"maps.app.goo.gl", "goo.gl", "share.google", "g.co"}
MAP_HOSTS = {"www.google.com", "google.com", "maps.google.com", "www.google.co.in", "google.co.in"}
_PAIR = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_PIN = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
_AT = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")


def _point_in_url(url: httpx.URL) -> dict | None:
    """The pin a Google Maps URL carries, with the place's name from its path."""
    text = str(url)
    m = _PIN.search(text) or _AT.search(text)
    if not m:
        return None
    name = None
    parts = url.path.split("/")
    if "place" in parts and parts.index("place") + 1 < len(parts):
        name = httpx.URL(text).path.split("/place/")[1].split("/")[0].replace("+", " ")
    return {"lat": float(m.group(1)), "lon": float(m.group(2)), "label": " ".join((name or "").split()) or f"{float(m.group(1)):.5f}, {float(m.group(2)):.5f}"}


async def _follow(url: str, *, client: httpx.AsyncClient | None = None) -> httpx.URL:
    """Where a short map link lands, following at most four redirects."""
    async with _http(client) as http:
        r = await http.get(url, follow_redirects=True, headers={"User-Agent": UA["User-Agent"] + " Safari/605.1.15"})
        return r.url


def _parts(label: str) -> str:
    return ", ".join(p.strip() for p in label.split(",")[:3])


Near = tuple[float, float] | str | None   # a point to prefer places around, a town to add to the words, or nothing


def _near_params(words: str, near: Near) -> tuple[str, dict]:
    """The query and the bias: a point becomes a preferred box of about
    fifty kilometres around it; a town is appended to the words unless it
    is already there."""
    if isinstance(near, tuple):
        lat, lon = near
        return words, {"viewbox": f"{lon - 0.25},{lat + 0.25},{lon + 0.25},{lat - 0.25}", "bounded": "0"}
    if near and near.casefold() not in words.casefold():
        return f"{words}, {near}", {}
    return words, {}


async def _tomtom_search(words: str, near: Near, *, client: httpx.AsyncClient | None = None) -> list[dict]:
    """TomTom's search for the words, biased to home's point: it knows an
    apartment building by name where the public map knows the street."""
    params: dict = {"key": settings.tomtom_api_key, "limit": 5, "countrySet": settings.tomtom_country or "IN"}
    if isinstance(near, tuple):
        params.update(lat=near[0], lon=near[1])
    async with _http(client) as http:
        r = await http.get(f"https://api.tomtom.com/search/2/search/{httpx.URL(path=words).path.lstrip('/')}.json", params=params)
        r.raise_for_status()
        rows = (r.json() or {}).get("results") or []
    out = []
    for x in rows:
        name = ((x.get("poi") or {}).get("name") or "").strip()
        address = (x.get("address") or {}).get("freeformAddress") or ""
        label = _parts(f"{name}, {address}" if name and name.casefold() not in address.casefold() else address or name)
        if label and x.get("position"):
            out.append({"label": label, "lat": float(x["position"]["lat"]), "lon": float(x["position"]["lon"])})
    return out


async def suggestions(words: str, near: Near = None, *, client: httpx.AsyncClient | None = None) -> list[dict]:
    """Up to five places for typed words: TomTom's search first when the key
    is set, else the public geocoder, preferred around home when home has a
    point. Nothing found with the whole address: the first part (a building,
    a flat) is dropped and the street tried, since the public map knows
    streets better than buildings."""
    words = " ".join(words.split())
    if not words:
        return []
    if settings.tomtom_api_key:
        key = "tt-suggest:" + words.casefold() + ":" + (f"{near[0]:.2f},{near[1]:.2f}" if isinstance(near, tuple) else "")
        if (hit := _cached(key, 24 * 3600)) is not None:
            return hit
        try:
            found = await _tomtom_search(words, near, client=client)
        except Exception:  # noqa: BLE001
            logger.info("tomtom search unavailable", exc_info=True)
            found = []
        if found:
            return _keep(key, found)
    q, bias = _near_params(words, near)
    key = "suggest:" + q.casefold() + ":" + bias.get("viewbox", "")
    if (hit := _cached(key, 24 * 3600)) is not None:
        return hit
    async with _http(client) as http:
        r = await http.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "json", "limit": 5, **bias})
        r.raise_for_status()
        rows = r.json() or []
    out = [{"label": _parts(x.get("display_name") or q), "lat": float(x["lat"]), "lon": float(x["lon"])} for x in rows]
    if not out and "," in words:
        out = await suggestions(words.split(",", 1)[1], near, client=client)
    return _keep(key, out)


async def resolve(query: str, near: Near = None, *, client: httpx.AsyncClient | None = None) -> list[dict]:
    """What a guardian typed or pasted, as places to pick from: a pair of
    coordinates is one place; a Google Maps link is the pin it carries, or
    the words it searches for; anything else is a map search."""
    q = (query or "").strip()
    if not q:
        return []
    if m := _PAIR.match(q):
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return [{"lat": lat, "lon": lon, "label": f"{lat:.5f}, {lon:.5f}"}]
    if q.startswith(("http://", "https://")):
        try:
            url = httpx.URL(q)
            if url.host in SHORT_MAP_HOSTS:
                url = await _follow(q, client=client)
            if url.host in MAP_HOSTS or url.host in SHORT_MAP_HOSTS:
                if pt := _point_in_url(url):
                    return [pt]
                words = url.params.get("q") or url.params.get("query") or ""
                return await suggestions(words, near, client=client) if words else []
        except Exception:  # noqa: BLE001
            logger.info("map link unreadable", exc_info=True)
        return []
    return await suggestions(q, near, client=client)


async def place_point(place: str, near: str | None = None, *, client: httpx.AsyncClient | None = None) -> dict | None:
    """A named place to a point, from Nominatim. Nothing of the family's goes
    in the query but the place's own words and the home town."""
    q = " ".join(x for x in (place, near) if x).strip()
    if not q:
        return None
    if (hit := _cached("place:" + q.casefold(), 86400)) is not None:
        return hit or None
    async with _http(client) as http:
        r = await http.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "json", "limit": 1})
        r.raise_for_status()
        rows = r.json() or []
    if not rows:
        _keep("place:" + q.casefold(), {})
        return None
    return _keep("place:" + q.casefold(), {"lat": float(rows[0]["lat"]), "lon": float(rows[0]["lon"]), "label": rows[0].get("display_name", q).split(",")[0]})


async def drive_minutes(a: tuple[float, float], b: tuple[float, float], *, client: httpx.AsyncClient | None = None) -> int | None:
    key = f"route:{a[0]:.4f},{a[1]:.4f}>{b[0]:.4f},{b[1]:.4f}"
    if (hit := _cached(key, 6 * 3600)) is not None:
        return hit
    async with _http(client) as http:
        r = await http.get(f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}", params={"overview": "false"})
        r.raise_for_status()
        routes = (r.json() or {}).get("routes") or []
    if not routes:
        return None
    return _keep(key, int(round(routes[0]["duration"] / 60)))


async def live_drive(a: tuple[float, float], b: tuple[float, float], *, client: httpx.AsyncClient | None = None) -> dict | None:
    """Minutes from a to b now, with live traffic, and the usual minutes for
    this hour from historic traffic, from TomTom's Routing API under the
    deployment's key. None without a key. Cached ten minutes."""
    if not settings.tomtom_api_key:
        return None
    key = f"live:{a[0]:.4f},{a[1]:.4f}>{b[0]:.4f},{b[1]:.4f}"
    if (hit := _cached(key, 600)) is not None:
        return hit
    async with _http(client) as http:
        r = await http.get(f"https://api.tomtom.com/routing/1/calculateRoute/{a[0]},{a[1]}:{b[0]},{b[1]}/json",
                           params={"key": settings.tomtom_api_key, "traffic": "true", "travelMode": "car", "computeTravelTimeFor": "all"})
        r.raise_for_status()
        routes = (r.json() or {}).get("routes") or []
    summary = (routes[0].get("summary") or {}) if routes else {}
    now = summary.get("travelTimeInSeconds")
    if now is None:
        return None
    usual = summary.get("historicTrafficTravelTimeInSeconds") or summary.get("noTrafficTravelTimeInSeconds") or now
    return _keep(key, {"minutes": int(round(now / 60)), "usual": int(round(usual / 60))})


async def usual_drive(a: tuple[float, float], b: tuple[float, float], at: dt.datetime | None = None, *, client: httpx.AsyncClient | None = None) -> int | None:
    """Minutes from a to b in the usual traffic for the hour, from TomTom's
    historic traffic, for a departure at `at` (now when not given). None
    without a key. Cached a day: the usual does not move."""
    if not settings.tomtom_api_key:
        return None
    when = at.astimezone(dt.UTC) if at else None
    key = f"usual:{a[0]:.4f},{a[1]:.4f}>{b[0]:.4f},{b[1]:.4f}@{when.strftime('%H%M') if when else 'now'}"
    if (hit := _cached(key, 24 * 3600)) is not None:
        return hit
    params = {"key": settings.tomtom_api_key, "traffic": "true", "travelMode": "car", "computeTravelTimeFor": "all"}
    if when:
        params["departAt"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    async with _http(client) as http:
        r = await http.get(f"https://api.tomtom.com/routing/1/calculateRoute/{a[0]},{a[1]}:{b[0]},{b[1]}/json", params=params)
        r.raise_for_status()
        routes = (r.json() or {}).get("routes") or []
    summary = (routes[0].get("summary") or {}) if routes else {}
    usual = summary.get("historicTrafficTravelTimeInSeconds") or summary.get("travelTimeInSeconds")
    return _keep(key, int(round(usual / 60))) if usual else None


def leave_by(due_time: str | None, minutes: int) -> str | None:
    m = re.search(r"(\d{1,2}):(\d{2})", due_time or "")
    if not m:
        return None
    at = dt.datetime(2000, 1, 1, int(m.group(1)), int(m.group(2))) - dt.timedelta(minutes=minutes + 10)
    return at.strftime("%-I:%M %p").lower()


# ----------------------------------------------------------------------------
# the school run
# ----------------------------------------------------------------------------

LIVE_BEFORE_SCHOOL = 120   # minutes before school starts that the drive is read live
LIVE_BEFORE_PICKUP = 60    # and before it ends
ALERT_DELAY = 8            # minutes worse than usual before a guardian is told
ALERT_LEAD = 75            # minutes before school the morning's check runs


def _tz(household: dict) -> ZoneInfo:
    try:
        return ZoneInfo(household.get("timezone") or "Asia/Kolkata")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Kolkata")


def _next_departure(now_local: dt.datetime, at: dt.time | None) -> dt.datetime | None:
    """The next weekday morning at `at`, less a typical drive's lead, in the
    household's time: the hour the usual is asked for. None without a time."""
    if at is None:
        return None
    day = now_local.date()
    for _ in range(8):
        when = dt.datetime.combine(day, at.replace(tzinfo=None), now_local.tzinfo) - dt.timedelta(minutes=30)
        if when > now_local and when.weekday() < 5:
            return when
        day += dt.timedelta(days=1)
    return None


def _within(now_local: dt.datetime, at: dt.time | None, minutes: int) -> bool:
    if at is None:
        return False
    end = dt.datetime.combine(now_local.date(), at.replace(tzinfo=None))
    return end - dt.timedelta(minutes=minutes) <= now_local.replace(tzinfo=None) <= end


async def school_runs(household: dict, *, now: dt.datetime | None = None, client: httpx.AsyncClient | None = None) -> list[dict]:
    """The school run from home, per school: the typical drive from public
    maps always; and on a school day, in the window before school or before
    pick-up, the minutes now with live traffic and how much worse than usual
    that is, when a key is set. A school with a start time gets a leave-by."""
    tz = _tz(household)
    now_local = (now or dt.datetime.now(dt.UTC)).astimezone(tz)
    schoolday = now_local.weekday() < 5
    home = (household["home_lat"], household["home_lon"])
    runs = []
    for s in await pool().fetch("SELECT id, name, address, lat, lon, starts_at, ends_at FROM schools WHERE household_id = $1 ORDER BY name", household["id"]):
        try:
            # The point a guardian picked first; then the address typed; then the name with the home town.
            town = household.get("home_place") if household.get("home_place") and "," not in household["home_place"] else None
            pt = ({"lat": s["lat"], "lon": s["lon"]} if s["lat"] is not None
                  else await place_point(s["address"], None, client=client) if s["address"]
                  else await place_point(s["name"], town, client=client))
            if not pt:
                continue
            # The usual for the hour (a school morning when the start is known), or the drive without traffic.
            depart = _next_departure(now_local, s["starts_at"])
            minutes = await usual_drive(home, (pt["lat"], pt["lon"]), depart, client=client) or await drive_minutes(home, (pt["lat"], pt["lon"]), client=client)
            if not minutes:
                continue
            run: dict = {"school": s["name"], "minutes": minutes, "usual": bool(settings.tomtom_api_key),
                         "starts_at": s["starts_at"].strftime("%H:%M") if s["starts_at"] else None,
                         "ends_at": s["ends_at"].strftime("%H:%M") if s["ends_at"] else None}
            if schoolday and (_within(now_local, s["starts_at"], LIVE_BEFORE_SCHOOL) or _within(now_local, s["ends_at"], LIVE_BEFORE_PICKUP)):
                live = await live_drive(home, (pt["lat"], pt["lon"]), client=client)
                if live:
                    run.update(live_minutes=live["minutes"], usual_minutes=live["usual"], delay_minutes=max(0, live["minutes"] - live["usual"]))
            if s["starts_at"]:
                run["leave_by"] = leave_by(run["starts_at"], run.get("live_minutes") or minutes)
            runs.append(run)
        except Exception:  # noqa: BLE001
            logger.info("school run unavailable for %s", s["name"], exc_info=True)
    if household.get("work_lat") is not None:
        # The commute, when the office is set: typical always; live on a weekday
        # morning, the same hours the school run is read live.
        try:
            office = (household["work_lat"], household["work_lon"])
            minutes = await usual_drive(home, office, _next_departure(now_local, dt.time(9, 0)), client=client) or await drive_minutes(home, office, client=client)
            if minutes:
                run = {"school": household.get("work_place") or "Office", "office": True, "minutes": minutes, "usual": bool(settings.tomtom_api_key),
                       "starts_at": None, "ends_at": None}
                if schoolday and dt.time(7, 0) <= now_local.time() <= dt.time(10, 0):
                    live = await live_drive(home, office, client=client)
                    if live:
                        run.update(live_minutes=live["minutes"], usual_minutes=live["usual"], delay_minutes=max(0, live["minutes"] - live["usual"]))
                runs.append(run)
        except Exception:  # noqa: BLE001
            logger.info("commute unavailable", exc_info=True)
    return runs


async def next_school_morning(household: dict, after: dt.datetime, starts: list[dt.time], *, client: httpx.AsyncClient | None = None) -> dt.datetime | None:
    """When the morning's check next runs: ALERT_LEAD minutes before the
    earliest start, on the next weekday that is not a public holiday, in the
    household's own time. None when no school has a start time."""
    if not starts:
        return None
    tz = _tz(household)
    local = after.astimezone(tz)
    try:
        off = {h["date"] for h in await holidays(household.get("country") or "IN", client=client)}
    except Exception:  # noqa: BLE001
        off = set()
    for n in range(0, 21):
        day = local.date() + dt.timedelta(days=n)
        if day.weekday() >= 5 or day in off:
            continue
        at = dt.datetime.combine(day, min(starts), tz) - dt.timedelta(minutes=ALERT_LEAD)
        if at > local:
            return at.astimezone(dt.UTC)
    return None


async def run_alert(household_id: uuid.UUID, *, now: dt.datetime | None = None, client: httpx.AsyncClient | None = None) -> dict:
    """The morning's check: the drive to each school now against the usual for
    the hour. The guardians are told only when it is ALERT_DELAY minutes
    worse, with a leave-by for the school's start. A normal morning is quiet."""
    household = await pool().fetchrow(
        "SELECT id, travel_time, home_place, home_lat, home_lon, work_place, work_lat, work_lon, country, timezone FROM households WHERE id = $1", household_id)
    told, worse = 0, []
    if household and household["travel_time"] and household["home_lat"] is not None:
        for run in await school_runs(dict(household), now=now, client=client):
            if run.get("office") or run.get("delay_minutes", 0) < ALERT_DELAY:
                continue
            worse.append(run["school"])
            subject = f"School run to {run['school']}: {run['live_minutes']} min now, usually {run['usual_minutes']}"
            body = (f"Traffic is {run['delay_minutes']} minutes worse than usual for this hour. "
                    + (f"Leave by {run['leave_by']} for {run['starts_at']}. " if run.get("leave_by") else "")
                    + "Live traffic from TomTom, for the drive from home to the school.")
            for g in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role = 'guardian'", household_id):
                if await notify.member(g["id"], subject, body):
                    told += 1
    return {"told": told, "worse": worse}


RUN_KIND = "school_run_alert"


async def _next_run(household_id: uuid.UUID, after: dt.datetime, *, client: httpx.AsyncClient | None = None) -> dt.datetime | None:
    household = await pool().fetchrow("SELECT id, travel_time, home_lat, country, timezone FROM households WHERE id = $1", household_id)
    if not household or not household["travel_time"] or household["home_lat"] is None:
        return None
    starts = [r["starts_at"] for r in await pool().fetch("SELECT starts_at FROM schools WHERE household_id = $1 AND starts_at IS NOT NULL", household_id)]
    return await next_school_morning(dict(household), after, starts, client=client)


async def ensure_run_scheduled(household_id: uuid.UUID) -> dict | None:
    """One morning check per household, a job that reschedules itself to the
    next school morning. Called when the switch, a school's timings or its
    address change: a scheduled one moves to the new time, a missing one is
    made, and with nothing to check none is made."""
    from familyos import jobs
    try:
        at = await _next_run(household_id, dt.datetime.now(dt.UTC))
    except Exception:  # noqa: BLE001
        logger.info("could not place the school-run check", exc_info=True)
        return None
    existing = await pool().fetchrow("SELECT id, status FROM jobs WHERE kind = $1 AND household_id = $2 AND status IN ('queued', 'scheduled', 'running') LIMIT 1",
                                     RUN_KIND, household_id)
    if existing:
        if at and existing["status"] == "scheduled":
            await pool().execute("UPDATE jobs SET next_run_at = $2 WHERE id = $1 AND status = 'scheduled'", existing["id"], at)
        return None
    if at is None:
        return None
    return await jobs.create(RUN_KIND, {"household_id": str(household_id)}, household_id=household_id, next_run_at=at)


# ----------------------------------------------------------------------------
# the brief's context
# ----------------------------------------------------------------------------

async def for_brief(household: dict, items: list[dict], on: dt.date, *, now: dt.datetime | None = None,
                    client: httpx.AsyncClient | None = None) -> dict | None:
    """The lines the switches allow, for this brief: the weather for today and
    tomorrow, the holidays in the next two weeks, and "leave by" on the dated
    things with a place. Each failure is logged and skipped: a weather site
    down must not take the brief down."""
    out: dict = {}
    tz = household.get("timezone") or "Asia/Kolkata"
    if household.get("weather_lines") and household.get("home_lat") is not None:
        try:
            days = await forecast(household["home_lat"], household["home_lon"], tz, client=client)
            soon = [d for d in days if d["date"] in (on, on + dt.timedelta(days=1))]
            said = [say_weather(d, "Today" if d["date"] == on else "Tomorrow") for d in soon]
            out["weather"] = " ".join(s for s in said if s) or None
            out["weather_days"] = [{"date": d["date"], "label": "Today" if d["date"] == on else "Tomorrow", "tmax": d.get("tmax"), "tmin": d.get("tmin"),
                                    "rain": d.get("rain"), "words": WMO.get(d.get("code") if d.get("code") is not None else -1, "")} for d in soon]
        except Exception:  # noqa: BLE001
            logger.info("weather unavailable", exc_info=True)
    if household.get("travel_time") and household.get("home_lat") is not None and household.get("id"):
        runs = await school_runs(household, now=now, client=client)
        if runs:
            out["school_runs"] = runs
    if household.get("public_holidays"):
        try:
            soon = holidays_between(await holidays(household.get("country") or "IN", client=client), on, on + dt.timedelta(days=14))
            out["holidays"] = [{"date": h["date"], "name": h["name"]} for h in soon[:4]]
        except Exception:  # noqa: BLE001
            logger.info("holidays unavailable", exc_info=True)
    if household.get("travel_time") and household.get("home_lat") is not None:
        soon_items = [i for i in items if i.get("due_date") in (on, on + dt.timedelta(days=1)) and i.get("due_time") and i.get("obligation_id")][:3]
        if soon_items:
            places = {r["id"]: r["place"] for r in await pool().fetch(
                "SELECT o.id, c.place FROM obligations o JOIN claims c ON c.id = o.claim_id WHERE o.id = ANY($1::uuid[]) AND c.place IS NOT NULL",
                [uuid.UUID(str(i["obligation_id"])) for i in soon_items])}
            for i in soon_items:
                place = places.get(uuid.UUID(str(i["obligation_id"])))
                if not place:
                    continue
                try:
                    pt = await place_point(place, household.get("home_place"), client=client)
                    if not pt:
                        continue
                    minutes = await drive_minutes((household["home_lat"], household["home_lon"]), (pt["lat"], pt["lon"]), client=client)
                    if minutes:
                        i["travel_minutes"] = minutes
                        i["leave_by"] = leave_by(i.get("due_time"), minutes)
                except Exception:  # noqa: BLE001
                    logger.info("travel time unavailable for %s", place, exc_info=True)
    return out or None


# ----------------------------------------------------------------------------
# a board's exam date sheet, read once as a notice when it changes
# ----------------------------------------------------------------------------

KIND = "exam_sheets"
HANDLER_VERSION = "1"


async def read_exam_sheets(*, client: httpx.AsyncClient | None = None) -> dict[str, int]:
    """For every school with a date-sheet URL whose household has the switch
    on: read the page without any credential, and if its text changed since
    the last read, hand it in as a shared notice of the school's so the
    reader proposes its dates."""
    from familyos.execution import disposable
    from familyos.identity import Principal
    from familyos.intake import gateway
    counts = {"read": 0, "changed": 0, "skipped": 0}
    rows = await pool().fetch(
        "SELECT s.id, s.name, s.household_id, s.exam_sheet_url, s.exam_sheet_sha256, m.id AS guardian, m.display_name, m.role "
        "FROM schools s JOIN households h ON h.id = s.household_id "
        "JOIN LATERAL (SELECT id, display_name, role FROM members WHERE household_id = h.id AND role = 'guardian' ORDER BY created_at LIMIT 1) m ON TRUE "
        "WHERE h.exam_dates AND s.exam_sheet_url IS NOT NULL")
    for s in rows:
        try:
            host = httpx.URL(s["exam_sheet_url"]).host
            page = await disposable.read(s["exam_sheet_url"], frozenset({host}), client=client)
        except Exception:  # noqa: BLE001
            logger.info("exam sheet unreadable for %s", s["name"], exc_info=True)
            counts["skipped"] += 1
            continue
        counts["read"] += 1
        digest = hashlib.sha256(page.text.encode()).hexdigest()
        if digest == s["exam_sheet_sha256"]:
            continue
        p = Principal(member_id=s["guardian"], household_id=s["household_id"], role=s["role"], display_name=s["display_name"])
        await gateway.receive_share(p, text=page.text[:20000], visibility="shared", tag=s["name"],
                                    note=f"the exam date sheet, read from {s['exam_sheet_url']}")
        await pool().execute("UPDATE schools SET exam_sheet_sha256 = $2, exam_sheet_read_at = NOW() WHERE id = $1", s["id"], digest)
        counts["changed"] += 1
    return counts


def register() -> None:
    from familyos import jobs

    async def handle(row: dict, ctx) -> dict:
        now = dt.datetime.now(dt.UTC)
        await ctx.plan(["Read the boards' exam date sheets"])
        await ctx.step("0")
        counts = await read_exam_sheets()
        await ctx.finish_step("0")
        return {**counts, "next_run_at": (now + dt.timedelta(hours=24)).isoformat()}
    jobs.register(KIND, handle, version=HANDLER_VERSION)

    async def morning(row: dict, ctx) -> dict:
        household_id = uuid.UUID(str((row.get("spec") or {}).get("household_id") or row["household_id"]))
        await ctx.plan(["Check the drive to school against the usual"])
        await ctx.step("0")
        out = await run_alert(household_id)
        await ctx.finish_step("0", f"{len(out['worse'])} worse than usual" if out["worse"] else "a normal morning")
        nxt = await _next_run(household_id, dt.datetime.now(dt.UTC) + dt.timedelta(minutes=1))
        return {**out, "next_run_at": nxt.isoformat() if nxt else None}
    jobs.register(RUN_KIND, morning, version=HANDLER_VERSION)


async def ensure_scheduled() -> dict | None:
    """One daily read for the whole deployment, like the mailbox sweep: a job
    that reschedules itself. Nothing is read for a household whose switch is off."""
    from familyos import jobs
    for h in await pool().fetch("SELECT DISTINCT h.id FROM households h JOIN schools s ON s.household_id = h.id "
                                "WHERE h.travel_time AND h.home_lat IS NOT NULL AND s.starts_at IS NOT NULL"):
        await ensure_run_scheduled(h["id"])
    if await pool().fetchval("SELECT 1 FROM jobs WHERE kind = $1 AND status IN ('queued', 'scheduled', 'running') LIMIT 1", KIND):
        return None
    return await jobs.create(KIND, {}, next_run_at=dt.datetime.now(dt.UTC))
