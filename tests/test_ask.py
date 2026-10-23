"""Asking the record: scoped by the visibility rule, and made to cite."""
import datetime as dt
import uuid

import pytest

from familyos import ask
from familyos.identity import Invalid, Principal
from familyos.settings import settings
from tests.conftest import pdf

TOMORROW = dt.date.today() + dt.timedelta(days=1)


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


class Echo:
    """An answerer that cites whatever it is told to."""

    def __init__(self, cite="o1", prose="The term fee is due on the 10th"):
        self.cite, self.prose = cite, prose
        self.saw: list[str] = []

    async def answer(self, question, facts):
        self.saw = [f.as_line() for f in facts]
        return f"{self.prose} [{self.cite}]." if self.cite else self.prose


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)


async def _obligation(database, family, *, who="amma", visibility="shared", title="Term 3 fee",
                      quote="Term 3 fee of Rs 24,500 is payable by 10 November"):
    household_id = uuid.UUID(family.household["id"])
    artifact_id = uuid.UUID((await family.upload(who, pdf(title), visibility=visibility)).json()["artifact"]["id"])
    e, c, o = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", e, household_id, artifact_id)
    await database.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, "
        "confidence) VALUES ($1, $2, $3, $4, 0, 'payment', $5, $6, 0.9)",
        c, e, household_id, artifact_id, title, quote)
    await database.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, status) "
        "VALUES ($1, $2, $3, $4, 'task', 'pay', $5, $6, 'accepted')",
        o, household_id, artifact_id, c, title, TOMORROW)
    return o


# ----------------------------------------------------------------------------
# the visibility rule, which is the whole point
# ----------------------------------------------------------------------------

async def test_the_same_question_has_different_answers_for_different_members(family, database):
    """A product where the household shares one agent account cannot do this."""
    await _obligation(database, family, who="appa", visibility="private", title="His own thing")
    echo = Echo()
    ask.use_answerer(echo)

    await ask.ask(_principal(family, "appa"), "what is coming up?")
    assert any("His own thing" in line for line in echo.saw)

    # Asserted on the context itself, not on what the answerer last saw: a
    # member with nothing visible returns before the answerer is called, so
    # echo.saw would still hold the previous member's facts.
    for_paati = await ask.context(_principal(family, "paati"))
    assert not any("His own thing" in f.text for f in for_paati)
    assert (await ask.ask(_principal(family, "paati"), "what is coming up?"))["grounded"] is False


async def test_a_member_with_nothing_visible_is_told_so(family, database):
    await _obligation(database, family, who="appa", visibility="private")
    ask.use_answerer(Echo())
    out = await ask.ask(_principal(family, "paati"), "what is coming up?")
    assert out["grounded"] is False and out["answer"] == ask.NOTHING
    assert "nothing in this household's record" in out["note"].lower()


# ----------------------------------------------------------------------------
# citations
# ----------------------------------------------------------------------------

async def test_an_answer_that_cites_nothing_is_replaced(family, database):
    """Fluent and unsourced is worse than silent, especially about money."""
    await _obligation(database, family)
    ask.use_answerer(Echo(cite=None, prose="You already paid it, nothing to worry about"))
    out = await ask.ask(_principal(family), "did we pay the fee?")
    assert out["answer"] == ask.NOTHING
    assert out["grounded"] is False
    assert "cannot point at a notice" in out["note"]


async def test_a_cited_answer_comes_back_with_the_words_behind_it(family, database):
    await _obligation(database, family)
    ask.use_answerer(Echo())
    out = await ask.ask(_principal(family), "when is the fee due?")
    assert out["grounded"] is True
    [cite] = out["citations"]
    assert cite["kind"] == "obligation"
    assert cite["quote"] == "Term 3 fee of Rs 24,500 is payable by 10 November"
    assert cite["artifact_id"] is not None


async def test_a_citation_the_member_was_never_given_is_dropped(family, database):
    """The references are ours, not the model's: one it invented points nowhere."""
    await _obligation(database, family)
    ask.use_answerer(Echo(cite="o99"))
    out = await ask.ask(_principal(family), "anything?")
    assert out["answer"] == ask.NOTHING and out["citations"] == []


# ----------------------------------------------------------------------------
# what the model is and is not given
# ----------------------------------------------------------------------------

async def test_the_model_sees_claims_and_never_a_raw_notice(family, database):
    """A notice written to be read by a machine is quoted and attributed
    rather than handed over whole."""
    await _obligation(database, family, quote="Pay Rs 24,500 by 10 November")
    echo = Echo()
    ask.use_answerer(echo)
    await ask.ask(_principal(family), "what is due?")
    joined = " ".join(echo.saw)
    assert "Term 3 fee" in joined
    # The artifact's bytes are nowhere near it.
    assert "%PDF" not in joined


async def test_asking_is_off_until_somebody_turns_it_on(family, database, monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", False)
    with pytest.raises(ask.NoAnswerer):
        await ask.ask(_principal(family), "anything?")
    assert "off" in ask.describe()


async def test_without_a_model_a_question_is_refused_not_guessed(family, database):
    await _obligation(database, family)
    ask.use_answerer(ask.RefusingAnswerer())
    with pytest.raises(ask.NoAnswerer):
        await ask.ask(_principal(family), "anything?")


async def test_a_question_has_to_be_one(family, database):
    ask.use_answerer(Echo())
    for bad in ("", "   ", "x" * 501):
        with pytest.raises(Invalid):
            await ask.ask(_principal(family), bad)


async def test_asking_cannot_do_anything(family, database):
    """It is a query surface. Acting goes through the rail, where the
    deny-list and the approval binding live."""
    assert not hasattr(ask, "send")
    assert not hasattr(ask, "approve")
    source = open("familyos/ask.py").read()
    assert "actions." not in source and "mail." not in source
