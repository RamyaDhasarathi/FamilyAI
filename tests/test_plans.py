"""Plans: written with the household in view, booked by the household.
Candidate pages are watched without signing in; the legwork becomes
to-dos; nothing is paid."""
import uuid

import pytest

from familyos import calendar, chat, notify, plans
from familyos.db import pool
from familyos.identity import Principal
from familyos.intake import google
from familyos.settings import settings
from tests.test_calendar_write import FakeCalendar
from tests.test_gmail import _connect


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


class Scripted:
    name = "scripted"

    def __init__(self, answer):
        self.answer, self.system, self.schema = answer, None, None

    async def reply(self, system, messages, schema=None):
        self.system, self.schema = system, schema
        return self.answer


PLAN = {
    "title": "A week in Switzerland", "starts_on": "2031-10-20", "ends_on": "2031-10-27",
    "budget_amount": 400000, "budget_currency": "INR",
    "summary": "Seven nights, Zurich and Interlaken, within the Diwali break and under four lakh.",
    "itinerary": [{"day": 1, "date": "2031-10-20", "title": "Fly to Zurich", "notes": "Overnight."},
                  {"day": 2, "date": "2031-10-21", "title": "Zurich old town", "notes": None}],
    "options": [
        {"kind": "flight", "label": "BLR-ZRH return", "provider": "Google Flights",
         "url": "https://www.google.com/travel/flights?q=BLR+to+ZRH", "estimate": 180000, "currency": "INR",
         "note": "Look at the Swiss direct.", "look_for": "Zurich"},
        {"kind": "stay", "label": "Interlaken apartment", "provider": "Booking.com",
         "url": "https://www.booking.com/searchresults.html?ss=Interlaken", "estimate": 90000, "currency": "INR",
         "note": None, "look_for": "Interlaken"},
        {"kind": "visa", "label": "Schengen appointment", "provider": "VFS",
         "url": "http://insecure.example/appointments", "estimate": None, "currency": None, "note": None, "look_for": None},
    ],
    "todos": [{"title": "Check passport expiry dates", "due_date": "2031-09-01", "member": "Appa", "note": "all four"},
              {"title": "School leave letter", "due_date": "2031-10-01", "member": "Older one", "note": None},
              {"title": "Travel insurance", "due_date": None, "member": None, "note": None}],
}


async def _written(family, who="amma", **body):
    """Ask, then run the write the job would run, then read the plan back."""
    r = await family.client.post("/v1/plans", headers=family.h(who), json=body)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "writing" and r.json()["brief"] == " ".join(body["brief"].split())
    await plans.write(uuid.UUID(r.json()["id"]))
    r = await family.client.get("/v1/plans/" + r.json()["id"], headers=family.h(who))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)

    async def member(member_id, subject, body):
        return "test"

    monkeypatch.setattr(notify, "member", member)
    yield
    chat.use_model(chat.RefusingModel())


async def test_a_plan_is_written_with_the_household_in_view_and_kept(family, database):
    model = Scripted(PLAN)
    chat.use_model(model)
    plan = await _written(family, brief="a week in Switzerland in the Diwali break under 4 lakh")
    # The model was asked with the plan's own schema and saw the members.
    assert model.schema is plans.PLAN_SCHEMA and "[MEMBERS] Amma (guardian)" in model.system
    assert plan["title"] == "A week in Switzerland" and plan["starts_on"] == "2031-10-20" and plan["budget_amount"] == 400000.0
    assert [d["title"] for d in plan["itinerary"]] == ["Fly to Zurich", "Zurich old town"]
    # An option on a plain-http page is dropped; the two https ones are kept and watched.
    assert [o["kind"] for o in plan["options"]] == ["flight", "stay"]
    assert all(o["watch_id"] for o in plan["options"])
    watched = await database.fetch("SELECT label, look_for, url FROM watches WHERE household_id = $1", uuid.UUID(family.household["id"]))
    assert {w["look_for"] for w in watched} == {"Zurich", "Interlaken"}
    # The legwork became to-dos: Appa's, dated; a child cannot be given one, so that one is unassigned.
    todos = {t["title"]: t for t in plan["todos"]}
    assert todos["Check passport expiry dates"]["assigned_to"] == family.appa["id"]
    assert todos["School leave letter"]["assigned_to"] is None
    assert len(todos) == 3
    # Listed and readable by another adult; the household's, not the author's.
    listed = (await family.client.get("/v1/plans", headers=family.h("appa"))).json()
    assert [x["id"] for x in listed] == [plan["id"]]


async def test_booking_an_option_stops_its_watch_and_nothing_is_paid(family, database):
    chat.use_model(Scripted(PLAN))
    plan = await _written(family, brief="x")
    flight = next(o for o in plan["options"] if o["kind"] == "flight")
    r = await family.client.post(f"/v1/plans/{plan['id']}/choose", headers=family.h("appa"),
                                 json={"option_id": flight["id"], "booked": True})
    assert r.status_code == 200, r.text
    out = r.json()
    chosen = next(o for o in out["options"] if o["id"] == flight["id"])
    assert chosen["chosen"] and chosen["booked_at"] and out["status"] == "active"
    # The watch on that page is paused, by the member who booked it -- a watch is the author's errand,
    # so it is paused only if the booker owns it; here Amma made the watches and Appa booked.
    paused = await database.fetchval("SELECT paused_at FROM watches WHERE id = $1", uuid.UUID(flight["watch_id"]))
    assert paused is None
    r = await family.client.post(f"/v1/plans/{plan['id']}/choose", headers=family.h("amma"),
                                 json={"option_id": flight["id"], "booked": True})
    paused = await database.fetchval("SELECT paused_at FROM watches WHERE id = $1", uuid.UUID(flight["watch_id"]))
    assert paused is not None
    # No action of any kind was created: the deny-list is untouched.
    assert await database.fetchval("SELECT count(*) FROM actions") == 0


async def test_the_chat_proposes_a_plan_and_confirming_is_the_plans_endpoint(family, database):
    chat.use_model(Scripted({"say": "I can plan that.", "proposals": [
        {"kind": "plan", "title": "A week in Switzerland", "brief": "a week in Switzerland in the Diwali break under 4 lakh"}]}))
    out = await chat.turn(_p(family), "plan a week in switzerland for us in the diwali break, under 4 lakh")
    [p] = out["proposals"]
    assert p["kind"] == "plan" and p["ok"] and p["brief"].startswith("a week in Switzerland")


async def test_without_a_model_a_plan_is_refused_plainly(family, database):
    chat.use_model(chat.RefusingModel())
    r = await family.client.post("/v1/plans", headers=family.h("amma"), json={"brief": "x"})
    assert r.status_code in (422, 503) and "no model" in r.text


MEALS = {
    "title": "Meals, 13–19 Oct", "starts_on": "2031-10-13", "ends_on": "2031-10-19", "budget_amount": 3500, "budget_currency": "INR",
    "summary": "Mostly cooked; one Swiggy night.",
    "itinerary": [{"day": i + 1, "date": f"2031-10-{13 + i}", "title": t, "notes": None} for i, t in enumerate(
        ["Mon: idli, sambar rice, dal-roti", "Tue: upma, curd rice (late PTM)", "Wed: dosa, rasam", "Thu: poha, chicken curry",
         "Fri: paratha, pulao", "Sat: Swiggy night", "Sun: pongal, biryani"])],
    "options": [
        {"kind": "grocery", "label": "Fresh Eggs x12", "provider": "Instamart", "url": None, "estimate": 106, "currency": "INR", "note": None, "look_for": None},
        {"kind": "grocery", "label": "Amul Fresh Paneer 200 g", "provider": "Instamart", "url": None, "estimate": 105, "currency": "INR", "note": None, "look_for": None},
    ],
    "todos": [{"title": "Order groceries", "due_date": "2031-10-12", "member": "Amma", "note": None}],
}


async def test_a_week_of_meals_is_fed_the_receipt_lines_and_its_groceries_link_to_the_shop(family, database):
    from familyos.extraction import items
    household_id = uuid.UUID(family.household["id"])
    from tests.conftest import pdf
    r = await family.upload("amma", pdf("instamart"), filename="r.txt", content_type="text/plain", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", aid,
                         {"from": "noreply@instamart.in", "subject": "Your Instamart order", "date": "Mon, 06 Oct 2026 09:00:00 +0530"})
    await items.record(household_id, aid, "Order Items\n 1 x Fresh Eggs White eggs ₹106.00\n 2 x Amul Fresh Paneer ₹210.00\n Grand Total ₹316.00")
    model = Scripted(MEALS)
    chat.use_model(model)
    plan = await _written(family, brief="meals for next week", shape="meals")
    assert plan["shape"] == "meals" and "RECENT GROCERIES: Fresh Eggs White eggs (Instamart" in model.system
    assert "You write the plan; the family cooks and shops" in model.system
    assert len(plan["itinerary"]) == 7
    groceries = [o for o in plan["options"] if o["kind"] == "grocery"]
    assert len(groceries) == 2 and all(o["url"].startswith("https://www.swiggy.com/instamart/search?") for o in groceries)
    assert all(o["watch_id"] is None for o in groceries)       # a grocery line is not watched
    assert [t["title"] for t in plan["todos"]] == ["Order groceries"]


async def test_the_ask_answers_at_once_and_the_job_writes_it_or_says_why_not(family, database):
    chat.use_model(Scripted(PLAN))
    r = await family.client.post("/v1/plans", headers=family.h("amma"), json={"brief": "a week in Switzerland"})
    assert r.status_code == 202, r.text
    pid = uuid.UUID(r.json()["id"])
    assert r.json()["status"] == "writing" and r.json()["options"] == [] and r.json()["todos"] == []
    # Listed at once, as writing, so the page can open on it.
    assert [x["status"] for x in (await family.client.get("/v1/plans", headers=family.h("appa"))).json()] == ["writing"]
    job = await database.fetchrow("SELECT spec, status FROM jobs WHERE kind = $1", plans.KIND)
    assert job["spec"]["plan_id"] == str(pid)
    assert (await plans._handle(dict(job), None))["written"] == str(pid)
    got = (await family.client.get(f"/v1/plans/{pid}", headers=family.h("amma"))).json()
    assert got["status"] == "draft" and got["title"] == "A week in Switzerland" and len(got["options"]) == 2
    # Running the job again does nothing: the plan is written.
    assert (await plans.write(pid))["skipped"] == "draft"

    class Broken:
        name = "broken"

        async def reply(self, system, messages, schema=None):
            raise RuntimeError("the model timed out")
    chat.use_model(Broken())
    r = await family.client.post("/v1/plans", headers=family.h("amma"), json={"brief": "another"})
    pid2 = uuid.UUID(r.json()["id"])
    with pytest.raises(RuntimeError):
        await plans.write(pid2)
    got = (await family.client.get(f"/v1/plans/{pid2}", headers=family.h("amma"))).json()
    assert got["status"] == "failed" and "timed out" in got["error"]
    assert await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'plan.failed'") == 1


async def test_dropping_a_plan_takes_its_open_todos_with_it(family, database, monkeypatch):
    monkeypatch.setattr(settings, "calendar_write_enabled", True)
    chat.use_model(Scripted(PLAN))
    plan = await _written(family, brief="a week in Switzerland")
    assert len(plan["todos"]) == 3
    # One done already stays as a record; the open two go with the plan.
    done_id = plan["todos"][0]["id"]
    await family.client.patch(f"/v1/todos/{done_id}", headers=family.h("amma"), json={"done": True})
    # One of the open two sits on a calendar: it comes off it when the plan goes.
    account = await _connect(family, FakeCalendar(scopes=list(google.scopes(gmail=True, calendar_write=True))), "amma")
    await database.execute("UPDATE todos SET calendar_event_id = 'evt-plan', calendar_account_id = $2 WHERE id = $1",
                           uuid.UUID(plan["todos"][1]["id"]), account["id"])
    r = await family.client.patch(f"/v1/plans/{plan['id']}", headers=family.h("amma"), json={"status": "dropped"})
    assert r.status_code == 200, r.text
    left = await database.fetch("SELECT id, done_at FROM todos WHERE plan_id = $1", uuid.UUID(plan["id"]))
    assert [str(x["id"]) for x in left] == [done_id] and left[0]["done_at"] is not None
    assert [t["title"] for t in (await family.client.get("/v1/todos", headers=family.h("amma"))).json()] == []
    job = await database.fetchrow("SELECT spec FROM jobs WHERE kind = $1 AND spec ? 'remove_event_id'", calendar.WRITE_KIND)
    assert job and job["spec"]["remove_event_id"] == "evt-plan"
