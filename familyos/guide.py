"""A plan's guide page, composed by the model from an allow-listed component
library (OpenUI), streamed line by line. A pilot, 11 Oct 2026.

The spec said the interface should be built for the question. Here the
model does not draw the screen: it picks and fills components from a
library the page declares (cards, lists, tables, buttons), and the server
forwards only lines that name those components. A button can do two
things: open the option's own page in a new tab, or hand a sentence to
Ask. Nothing on the page books, pays or changes the record; a booking
becomes an errand proposed through Ask and approved by a guardian, as
everywhere else.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from familyos import chat, plans
from familyos.identity import Principal

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent / "web_guide" / "openui-prompt.txt"
_SIGNATURE = re.compile(r"^([A-Z][A-Za-z]*)\(", re.M)
_CALL = re.compile(r"(?<![@\w])([A-Z][A-Za-z]*)\(")   # a component call; @Steps are checked apart
_STEP = re.compile(r"@([A-Za-z]+)\(")
_STATEMENT = re.compile(r"^\s*\$?[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S")
# Always allowed: the root container the language assumes, and Action, which wraps steps.
BASE = {"Stack", "Action"}
# The only steps a button may take here: open the option's own page, or hand words to Ask.
STEPS = {"OpenUrl", "ToAssistant"}


def library_prompt() -> str:
    return PROMPT_FILE.read_text() if PROMPT_FILE.is_file() else ""


def allowed_components() -> frozenset[str]:
    """The component names the library's own prompt declares."""
    return frozenset(_SIGNATURE.findall(library_prompt())) | BASE


def _depth(text: str) -> int:
    """Open brackets minus closed, outside strings: a statement is whole when it is zero."""
    depth, in_str, esc = 0, False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    return depth


class Statements:
    """Lines in, whole statements out. The language is one statement per
    line, but a model wraps a long array over several; those are joined
    into the one line the renderer expects before the gate sees them."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def feed(self, line: str) -> list[str]:
        stripped = line.strip()
        if not stripped:
            return []
        if not self.parts and not _STATEMENT.match(line):
            return [stripped]   # not a statement: the gate drops it
        self.parts.append(stripped)
        joined = " ".join(self.parts)
        if _depth(joined) > 0:
            return []
        self.parts = []
        return [joined]

    def flush(self) -> list[str]:
        out = [" ".join(self.parts)] if self.parts else []
        self.parts = []
        return out


def gate(line: str, allowed: frozenset[str]) -> bool:
    """A line passes when it is a statement and every call in it names an
    allowed component. Anything else -- prose, markdown fences, a component
    the library does not have -- is dropped before it reaches the page."""
    if not _STATEMENT.match(line):
        return False
    return all(name in allowed for name in _CALL.findall(line)) and all(step in STEPS for step in _STEP.findall(line))


RULES = """
## This page

You are composing a guide page for one family trip, for FamilyOS. Use only the facts below; invent no prices, places, times or
availability. Money is in {currency}. Lay the page out around what the family said matters in the brief and summary: if dates
or school clashes matter, put them first; if cost matters, put the estimates and the budget first; if it is a family trip with
children, put the stay and the day-by-day plan first. Use Card, CardHeader, TextContent, ListBlock/ListItem, Table, OptionCards,
Callout, Steps and Buttons. Keep it to one screen's worth of sections. Write in plain, specific sentences; use the family's
names where the facts use them; no emoji.

Buttons may do exactly two things: open an option's own page (Action([@OpenUrl(the option's url)])), or hand a sentence to Ask
(Action([@ToAssistant("...")])), for example "Propose booking the return train to Madurai". FamilyOS never books or pays from
this page; say "open" or "propose", never "book now" or "pay". If a fact is uncertain (an estimate, a date to confirm), say so
in the words next to it. The people are exactly those listed under Members; never name anyone else, and never invent a
person, a child or a companion.
"""


async def facts_for(p: Principal, plan_id: uuid.UUID) -> tuple[dict, str]:
    plan = await plans.get(p, plan_id)
    from familyos.db import pool
    members = await pool().fetch("SELECT display_name, role FROM members WHERE household_id = $1 ORDER BY created_at", p.household_id)
    lines = ["Members: " + ", ".join(f"{m['display_name']} ({m['role']})" for m in members),
             f"Title: {plan.get('title')}", f"Shape: {plan.get('shape')}; status: {plan.get('status')}",
             f"Dates: {plan.get('starts_on')} to {plan.get('ends_on')}",
             f"Budget: {plan.get('budget_amount')} {plan.get('budget_currency')}",
             f"Brief (the family's words): {plan.get('brief')}", f"Summary: {plan.get('summary')}", "Options:"]
    for o in plan.get("options") or []:
        lines.append(f"- [{o.get('kind')}] {o.get('label')} via {o.get('provider')}: estimate {o.get('estimate')} {o.get('currency')}; "
                     f"url {o.get('url')}; note: {o.get('note')}")
    lines.append("Itinerary:")
    for d in plan.get("itinerary") or []:
        lines.append(f"- Day {d.get('day')} ({d.get('date')}): {d.get('title')}. {d.get('notes')}")
    todos = [t for t in (plan.get("todos") or []) if not t.get("done_at")]
    if todos:
        lines.append("Open to-dos: " + "; ".join(str(t.get("title")) for t in todos[:12]))
    return plan, "\n".join(lines)


async def stream(p: Principal, plan_id: uuid.UUID):
    """Events: {type: line, text} for each line that passed the gate,
    {type: done, lines, dropped}, or {type: error, detail}."""
    try:
        plan, facts = await facts_for(p, plan_id)
        system = library_prompt() + RULES.format(currency=plan.get("budget_currency") or "INR") + "\n\n## FACTS\n" + facts
        model = await chat.model_for(p.household_id)
        if not hasattr(model, "stream_text"):
            yield {"type": "error", "detail": "no model is configured to compose a page on this deployment"}
            return
        allowed = allowed_components()
        buf, kept, dropped = "", 0, 0
        statements = Statements()

        def judged(whole: str):
            nonlocal kept, dropped
            if gate(whole, allowed):
                kept += 1
                return {"type": "line", "text": whole}
            dropped += 1
            logger.info("guide: dropped a line: %s", whole[:160])
            return None

        async for delta in model.stream_text(system, [{"role": "user", "content": "Compose the guide page now, in openui-lang only."}]):
            buf += delta
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                for whole in statements.feed(line):
                    if ev := judged(whole):
                        yield ev
        for whole in statements.feed(buf) + statements.flush():
            if ev := judged(whole):
                yield ev
        yield {"type": "done", "lines": kept, "dropped": dropped}
    except Exception as exc:  # noqa: BLE001 - the page already streams; the error is an event
        logger.warning("guide failed", exc_info=True)
        yield {"type": "error", "detail": chat.said_by_provider(exc)}
