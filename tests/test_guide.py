"""A plan's guide page composed by the model from an allow-listed library,
streamed line by line, with the server's gate in front of the page."""
import re
import uuid
from pathlib import Path

import pytest

from familyos import chat, guide
from familyos.settings import settings
from tests.test_chat import Scripted


class PageModel(Scripted):
    """A model that writes a page in openui-lang, in pieces, with one line the
    library does not know and one line of prose the gate must drop."""
    name = "scripted-page"

    def __init__(self, text, pieces=3):
        super().__init__(None)
        self.text, self.pieces = text, pieces

    async def stream_text(self, system, messages):
        self.system, self.messages = system, messages
        n = max(1, len(self.text) // self.pieces)
        for i in range(0, len(self.text), n):
            yield self.text[i:i + n]


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)
    yield
    chat.use_model(chat.RefusingModel())


def test_the_gate_keeps_library_components_and_drops_everything_else():
    allowed = guide.allowed_components()
    urls = frozenset({"https://www.irctc.co.in/"})
    assert {"Card", "CardHeader", "TextContent", "Buttons", "Button", "Table", "Col", "Action"} <= allowed
    assert guide.gate('header = CardHeader("Five Days in Madurai", "18 to 22 Oct")', allowed, urls)
    assert guide.gate('go = Button("Open the train search", Action([@OpenUrl("https://www.irctc.co.in/")]))', allowed, urls)
    assert not guide.gate('Here is your guide:', allowed, urls)
    assert not guide.gate('```openui', allowed, urls)
    assert not guide.gate('pay = PayButton("Pay now", 12000)', allowed, urls)
    assert not guide.gate('x = Stack([Card([Script("alert(1)")])])', allowed, urls)


def test_a_button_may_open_only_a_page_the_plan_itself_names():
    allowed, urls = guide.allowed_components(), frozenset({"https://www.irctc.co.in/"})
    def go(url): return f'go = Button("Open", Action([@OpenUrl({url})]))'                     # noqa: E704 - one-line builder
    assert guide.gate(go('"https://www.irctc.co.in/"'), allowed, urls)
    assert not guide.gate(go('"https://evil.example/login"'), allowed, urls)                  # a page the plan never named
    assert not guide.gate(go('"javascript:alert(1)"'), allowed, urls)
    assert not guide.gate(go('"https://www.irctc.co.in/@evil.example"'), allowed, urls)       # near, not equal
    assert not guide.gate(go('someVariable'), allowed, urls)                                  # not a plain string: cannot be checked, so not shown
    assert not guide.gate('go = Button("Open", Action([@OpenUrl("https://www.irctc.co.in/"), @OpenUrl("https://evil.example/")]))', allowed, urls)
    assert guide.gate('ask = Button("Ask", Action([@ToAssistant("Propose the train")]))', allowed, urls)     # asking is not opening


def test_a_statement_wrapped_over_several_lines_is_joined_before_the_gate():
    st = guide.Statements()
    out = []
    for line in ['items = ListBlock([', '    ListItem("Train", "₹12,000 (an estimate)"),', '    ListItem("Bus", "₹14,000, \\"refundable\\" (seats)")', '], "number")', 'root = Stack([items])']:
        out += st.feed(line)
    assert out == ['items = ListBlock([ ListItem("Train", "₹12,000 (an estimate)"), ListItem("Bus", "₹14,000, \\"refundable\\" (seats)") ], "number")', 'root = Stack([items])']
    assert all(guide.gate(x, guide.allowed_components(), frozenset()) for x in out)
    assert st.feed("Here is the page:") == ["Here is the page:"] and st.flush() == []


async def test_a_plan_guide_streams_the_lines_that_pass_the_gate(family, database):
    household_id = uuid.UUID(family.household["id"])
    plan_id = uuid.uuid4()
    await database.execute(
        "INSERT INTO plans (id, household_id, created_by, title, brief, status, shape, starts_on, ends_on, budget_amount, budget_currency, options, itinerary) "
        "VALUES ($1, $2, $3, 'Five Days in Madurai', 'after the exams, five days', 'draft', 'trip', '2026-10-18', '2026-10-22', 55000, 'INR', $4, $5)",
        plan_id, household_id, uuid.UUID(family.amma["id"]),
        [{"id": "a1", "kind": "transport", "label": "Return train", "provider": "IRCTC", "url": "https://www.irctc.co.in/", "estimate": 12000, "currency": "INR", "note": "estimate"}],
        [{"day": 1, "date": "2026-10-18", "title": "Travel", "notes": "Check in and rest."}])
    page = ('Here is the page:\n'
            'header = CardHeader(\n    "Five Days in Madurai",\n    "18 to 22 Oct, under ₹55,000"\n)\n'
            'train = TextContent("Return train via IRCTC, about ₹12,000 (an estimate).")\n'
            'go = Button("Open the train search", Action([@OpenUrl("https://www.irctc.co.in/")]))\n'
            'pay = PayNow("Book and pay", 12000)\n'
            'root = Stack([Card([header, train, Buttons([go])])])\n')
    model = PageModel(page)
    chat.use_model(model)
    events = []
    async with family.client.stream("POST", f"/v1/plans/{plan_id}/guide", headers=family.h("amma")) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.strip():
                events.append(chat.json.loads(line))
    lines = [e["text"] for e in events if e["type"] == "line"]
    assert lines[0].startswith("header = CardHeader") and lines[-1].startswith("root = Stack")
    assert not any("PayNow" in x for x in lines) and not any(x.startswith("Here is") for x in lines)
    assert events[-1] == {"type": "done", "lines": 4, "dropped": 2}
    # The model was told the library, the rules and the plan's own facts, and nothing it may book.
    assert "openui-lang" in model.system and "Return train" in model.system and "never books or pays" in model.system
    assert "Members: " in model.system and family.amma["display_name"] in model.system


def test_every_third_party_file_the_guide_page_loads_is_pinned_and_integrity_checked():
    """The page runs on the console's origin, so a changed file on the CDN would run beside the household's signed-in calls."""
    html = (Path(guide.__file__).parent / "web_guide" / "index.html").read_text()
    tags = re.findall(r'<(?:script|link)\b[^>]*(?:src|href)="https://[^"]+"[^>]*>', html)
    assert tags, "the page loads its bundle from somewhere"
    for tag in tags:
        assert re.search(r"@\d+\.\d+\.\d+/", tag), tag                                  # an exact version, not "latest"
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/=]{64}"', tag) and 'crossorigin="anonymous"' in tag, tag
