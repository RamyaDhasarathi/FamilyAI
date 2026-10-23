"""Where a household lives. India unless said; a guardian can say otherwise;
the school year, the digest's money line and Ask's "today" follow the
household, not the server."""
import datetime as dt
import uuid

from familyos import brief, country
from familyos.identity import Principal


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_a_household_is_in_india_unless_said(family):
    r = await family.client.get("/v1/household", headers=family.h("amma"))
    assert r.status_code == 200
    assert (r.json()["country"], r.json()["timezone"], r.json()["currency"]) == ("IN", "Asia/Kolkata", "INR")


async def test_a_guardian_moves_the_household_and_an_adult_cannot(family, database):
    r = await family.client.put("/v1/household/locale", headers=family.h("amma"), json={"country": "ae", "timezone": "Asia/Dubai", "currency": "aed"})
    assert r.status_code == 200, r.text
    assert (r.json()["country"], r.json()["timezone"], r.json()["currency"]) == ("AE", "Asia/Dubai", "AED")
    r = await family.client.put("/v1/household/locale", headers=family.h("amma"), json={"country": "AE", "timezone": "Mars/Olympus", "currency": "AED"})
    assert r.status_code == 422 and "zone" in r.json()["detail"]
    # Appa is an adult, not a guardian.
    adult = next((m for m in [family.appa] if m["role"] != "guardian"), None)
    if adult:
        r = await family.client.put("/v1/household/locale", headers=family.h("appa"), json={"country": "IN", "timezone": "Asia/Kolkata", "currency": "INR"})
        assert r.status_code == 403
    audit = await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'household.locale_set' AND household_id = $1", uuid.UUID(family.household["id"]))
    assert audit == 1


async def test_the_school_year_nudge_follows_the_country(family, database):
    child = family.older
    h = family.h("amma")
    await family.client.patch(f"/v1/members/{child['id']}/school", headers=h, json={"school": "GEMS", "class_label": "4", "since": "2025-09-01"})
    await family.client.put("/v1/household/locale", headers=h, json={"country": "AE", "timezone": "Asia/Dubai", "currency": "AED"})
    # June is not the start of a Dubai school year; September is.
    assert not [i for i in (await brief.today(_p(family), on=dt.date(2026, 6, 15), limit=50))["items"] if i["reason"] == "school_year"]
    assert [i for i in (await brief.today(_p(family), on=dt.date(2026, 9, 15), limit=50))["items"] if i["reason"] == "school_year"]


def test_money_is_said_in_the_currency_it_is_in():
    assert country.money(1940.98, "INR") == "₹1,940.98"
    assert country.money(350, "AED") == "AED 350"
    assert country.money(43, "USD") == "$43"
    assert country.money(12.5, "CHF") == "CHF 12.5"
    assert country.profile("AE")["school_year_months"] == (4, 8, 9, 10)
    assert country.profile("ZZ") == country.profile("IN")


def test_the_reader_is_told_how_the_country_writes_dates():
    from familyos.extraction.llm import build_request
    from familyos.extraction.parse import Page, ParsedDocument
    doc = ParsedDocument("text/plain", [Page(1, "Fee due 4/10/2026", [], 100, 100, "text")], [])
    india = build_request(doc, dt.date(2026, 10, 1), model="m", effort="low", country="IN")["system"]
    assert "day first" in india and "India" in india
    us = build_request(doc, dt.date(2026, 10, 1), model="m", effort="low", country="US")["system"]
    assert "month first" in us
    unknown = build_request(doc, dt.date(2026, 10, 1), model="m", effort="low")["system"]
    assert "the way the notice's country writes them" in unknown
