"""Asking the household record a question.

Not an agent. A query surface over a record that is already governed, with
two rules that make it safe and make it ours:

  * **Reads go through the visibility rule.** The model is handed facts that
    were fetched for this member, scoped by `VISIBLE_TO_MEMBER` and by any
    grant. It never queries anything itself. So the same question has
    different answers for different members, enforced in SQL rather than
    promised in a prompt -- which is the thing a product where the whole
    family shares one agent account cannot do.

  * **Every answer cites.** An answer that points at nothing is replaced with
    a sentence saying so. Uncited is a guess, and a guess about whether a fee
    was paid is worse than silence.

What the model is given is **claims**, never the raw notice. A claim has
already been grounded: it carries the words it came from and a notice to point
at. A school circular that says something strange is therefore quoted and
attributed rather than paraphrased as fact -- which is the only honest defence
against a notice written to be read by a machine.

Nothing here can act. Doing something about an answer goes through the action
rail, where the deny-list and the approval binding already live.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Protocol

from familyos import billers, calendar, grants
from familyos.db import pool
from familyos.identity import Invalid, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

MAX_QUESTION = 500
MAX_FACTS = 60


class NoAnswerer(Invalid):
    """Nothing is configured to answer, so the question is refused rather than
    guessed at."""


@dataclass(frozen=True)
class Fact:
    """One thing the member may see, with somewhere to point."""
    ref: str
    kind: str
    text: str
    artifact_id: uuid.UUID | None = None
    obligation_id: uuid.UUID | None = None
    quote: str | None = None

    def as_line(self) -> str:
        return f"[{self.ref}] {self.text}"


# What the asking member can see. Every row here came out of a function that
# already applies the visibility rule; nothing is read raw.
_OBLIGATIONS = f"""
SELECT o.id, o.title, o.action, o.due_date, o.status, o.subject_member_id,
       c.quote, c.subject_name, o.artifact_id
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
LEFT JOIN claims c ON c.id = o.claim_id
WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL
ORDER BY o.due_date NULLS LAST LIMIT 40
"""


async def context(p: Principal) -> list[Fact]:
    """The facts this member may see, each with a reference to cite."""
    facts: list[Fact] = []
    rows = await pool().fetch(_OBLIGATIONS, p.household_id, p.member_id)
    for n, row in enumerate(rows, start=1):
        when = f"due {row['due_date'].isoformat()}" if row["due_date"] else "no date"
        who = f" for {row['subject_name']}" if row["subject_name"] else ""
        facts.append(Fact(
            ref=f"o{n}", kind="obligation",
            text=f"{row['title']} — {row['action']}, {when}, {row['status']}{who}",
            artifact_id=row["artifact_id"], obligation_id=row["id"], quote=row["quote"]))

    for n, event in enumerate(await calendar.upcoming(p, days=30), start=1):
        facts.append(Fact(
            ref=f"c{n}", kind="calendar",
            text=f"{event['summary']} — {event['starts_at'].isoformat()}"))

    for n, row in enumerate(await billers.missing(p), start=1):
        facts.append(Fact(
            ref=f"b{n}", kind="bill",
            text=f"No {row['label']} bill from {row['provider']}; usually every "
                 f"{row['every_days']} days and {row['days_late']} days late"))

    return facts[:MAX_FACTS]


class Answerer(Protocol):
    """The seam a model plugs into. Given a question and the facts a member may
    see, return prose that cites them by reference."""

    async def answer(self, question: str, facts: list[Fact]) -> str:
        ...


class RefusingAnswerer:
    """The default. A deployment with no model says so rather than guessing."""

    async def answer(self, question: str, facts: list[Fact]) -> str:
        raise NoAnswerer("no model is configured to answer questions on this deployment")


_answerer: Answerer = RefusingAnswerer()


def use_answerer(answerer: Answerer) -> None:
    global _answerer
    _answerer = answerer


def current_answerer() -> Answerer:
    return _answerer


_REF = re.compile(r"\[([obc]\d{1,2})\]")
NOTHING = "Nothing I can see answers that."


async def ask(p: Principal, question: str) -> dict:
    """Answer from the record, or say that the record does not answer it."""
    text = (question or "").strip()
    if not text:
        raise Invalid("ask something")
    if len(text) > MAX_QUESTION:
        raise Invalid(f"keep a question under {MAX_QUESTION} characters")
    if not settings.ask_enabled:
        raise NoAnswerer("asking is off on this deployment (FAMILYOS_ASK_ENABLED=false)")

    facts = await context(p)
    if not facts:
        return {"answer": NOTHING, "citations": [], "grounded": False,
                "note": "There is nothing in this household's record that you can see."}

    said = await current_answerer().answer(text, facts)
    by_ref = {f.ref: f for f in facts}
    cited = [by_ref[ref] for ref in dict.fromkeys(_REF.findall(said or "")) if ref in by_ref]

    if not cited:
        # An answer that points at nothing is a guess. Say so rather than
        # passing it on, however fluent it was.
        logger.info("an uncited answer was discarded")
        return {"answer": NOTHING, "citations": [], "grounded": False,
                "note": "An answer that cannot point at a notice is not one."}

    return {
        "answer": said,
        "grounded": True,
        "citations": [{"ref": f.ref, "kind": f.kind, "text": f.text,
                       "quote": f.quote, "artifact_id": f.artifact_id,
                       "obligation_id": f.obligation_id} for f in cited],
        "note": None,
    }


def describe() -> str:
    if not settings.ask_enabled:
        return "Asking is off (FAMILYOS_ASK_ENABLED=false)."
    if isinstance(current_answerer(), RefusingAnswerer):
        return "Asking is on but no model is configured, so questions are refused."
    return ("Asking is on: the model sees claims this member may see, never a raw notice, "
            "and an answer that cites nothing is replaced.")
