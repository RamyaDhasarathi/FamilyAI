"""The public web through a research provider: public pages only, the
family's names scrubbed from every query, results shown as evidence."""
import json
import uuid

import httpx
import pytest

from familyos import chat, notify, plans, watches
from familyos.execution import research
from familyos.identity import Principal
from familyos.settings import settings


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


class FakeParallel:
    """Parallel, as far as these tests care: records requests, answers fixed pages."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def transport(self):
        async def handle(request: httpx.Request):
            body = json.loads(request.content or b"{}")
            self.calls.append((request.url.path, body))
            assert request.headers["x-api-key"] == "pk-test"
            if request.url.path.endswith("/search"):
                return httpx.Response(200, json={"search_id": "s1", "results": [
                    {"url": "https://www.sbb.ch/en/swiss-travel-pass", "title": "Swiss Travel Pass",
                     "publish_date": None, "excerpts": ["8 days from CHF 419 for adults; children under 16 travel free with the Family Card."]},
                    {"url": "http://insecure.example/x", "title": "nope", "excerpts": ["x"]}]})
            if request.url.path.endswith("/extract"):
                return httpx.Response(200, json={"results": [
                    {"url": body["urls"][0], "title": "Fares", "excerpts": ["Chennai to Zurich from ₹1,62,000 return"],
                     "full_content": "# Fares\n\nChennai to Zurich from ₹1,62,000 return. Zurich daily."}]})
            return httpx.Response(404, json={})
        return httpx.MockTransport(handle)


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)

    async def member(member_id, subject, body):
        return "test"

    monkeypatch.setattr(notify, "member", member)
    yield
    research.use(research.NoResearcher())
    chat.use_model(chat.RefusingModel())


def test_names_are_scrubbed_from_a_query():
    out = research.scrub("Flights for Amma, Appa and Older one to Zurich in October", ["Amma", "Appa", "Older one"])
    assert "Amma" not in out and "Older one" not in out and "Zurich" in out
    assert out == "Flights for the family, the family and the family to Zurich in October"


async def test_search_returns_only_https_hits_with_excerpts():
    fake = FakeParallel()
    r = research.ParallelResearcher("pk-test", transport=fake.transport())
    hits = await r.search("Swiss Travel Pass family 2031", ["Swiss Travel Pass"], limit=3)
    assert [h.url for h in hits] == ["https://www.sbb.ch/en/swiss-travel-pass"]
    assert "CHF 419" in hits[0].excerpt and hits[0].via == "parallel"
    assert set(fake.calls[0][1]) == {"objective", "search_queries"}      # the live API refuses anything else


async def test_a_plans_options_carry_evidence_and_no_name_leaves(family, database):
    fake = FakeParallel()
    research.use(research.ParallelResearcher("pk-test", transport=fake.transport()))
    chat.use_model(type("M", (), {"name": "scripted", "reply": staticmethod(lambda *a, **k: _plan())})())
    r = await family.client.post("/v1/plans", headers=family.h("amma"), json={"brief": "Switzerland for Amma and Older one"})
    assert r.status_code == 202, r.text
    await plans.write(uuid.UUID(r.json()["id"]))
    r = await family.client.get("/v1/plans/" + r.json()["id"], headers=family.h("amma"))
    [opt] = r.json()["options"]
    assert opt["evidence"]["url"] == "https://www.sbb.ch/en/swiss-travel-pass" and "CHF 419" in opt["evidence"]["excerpt"]
    assert opt["evidence"]["via"] == "parallel" and opt["evidence"]["read_at"]
    # The queries carried the option's words and nobody's name.
    searched = [b for path, b in fake.calls if path.endswith("/search")]
    assert searched and all("Amma" not in json.dumps(b) and "Older one" not in json.dumps(b) for b in searched)
    assert await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'plan.evidence_read'") == 1


async def _plan():
    return {"title": "Switzerland", "starts_on": "2031-10-20", "ends_on": "2031-10-27", "budget_amount": 400000,
            "budget_currency": "INR", "summary": "A week.", "itinerary": [], "todos": [],
            "options": [{"kind": "transport", "label": "Swiss Travel Pass for Amma and Older one", "provider": "SBB",
                         "url": "https://www.sbb.ch/en/tickets-offers", "estimate": 50000, "currency": "INR",
                         "note": None, "look_for": "Swiss Travel Pass"}]}


async def test_a_watch_reads_a_javascript_page_through_the_provider_and_is_still_vetted(family, database):
    fake = FakeParallel()
    research.use(research.ParallelResearcher("pk-test", transport=fake.transport()))
    w = await watches.create(_p(family), url="https://www.google.com/travel/flights?q=MAA+ZRH", look_for="Zurich",
                             label="Fares", every_hours=24, days=7)
    assert await watches.check_one(w) in ("notified", "same")
    row = await database.fetchrow("SELECT last_found, last_excerpt, last_error FROM watches WHERE id = $1", w["id"])
    assert row["last_found"] is True and "1,62,000" in row["last_excerpt"] and row["last_error"] is None
    assert fake.calls[-1][0].endswith("/extract")
    # A private address is refused before any provider is asked.
    with pytest.raises(Exception):  # noqa: B017 - refused before any provider; the type is the caller's
        await watches.create(_p(family), url="http://localhost:8088/app/", look_for="x", label="x")


def test_configure_is_named_never_inferred(monkeypatch):
    monkeypatch.setattr(settings, "web_research", "")
    monkeypatch.setattr(settings, "parallel_api_key", "pk-test")
    research.configure()
    assert not research.configured() and "off" in research.describe()
    monkeypatch.setattr(settings, "web_research", "parallel")
    research.configure()
    assert research.configured() and "parallel" in research.describe()
