"""A plan's guide page composed by the model from an allow-listed library,
streamed line by line, with the server's gate in front of the page."""
import uuid

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
    assert {"Card", "CardHeader", "TextContent", "Buttons", "Button", "Table", "Col", "Action"} <= allowed
    assert guide.gate('header = CardHeader("Five Days in Madurai", "18 to 22 Oct")', allowed)
    assert guide.gate('go = Button("Open the train search", Action([@OpenUrl("https://www.irctc.co.in/")]))', allowed)
    assert not guide.gate('Here is your guide:', allowed)
    assert not guide.gate('```openui', allowed)
    assert not guide.gate('pay = PayButton("Pay now", 12000)', allowed)
    assert not guide.gate('x = Stack([Card([Script("alert(1)")])])', allowed)


def test_a_statement_wrapped_over_several_lines_is_joined_before_the_gate():
    st = guide.Statements()
    out = []
    for line in ['items = ListBlock([', '    ListItem("Train", "₹12,000 (an estimate)"),', '    ListItem("Bus", "₹14,000, \\"refundable\\" (seats)")', '], "number")', 'root = Stack([items])']:
        out += st.feed(line)
    assert out == ['items = ListBlock([ ListItem("Train", "₹12,000 (an estimate)"), ListItem("Bus", "₹14,000, \\"refundable\\" (seats)") ], "number")', 'root = Stack([items])']
    assert all(guide.gate(x, guide.allowed_components()) for x in out)
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
