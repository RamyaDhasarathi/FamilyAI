"""The one window: the model sees what the member sees, cites it, and may
propose; a person confirms; the ordinary endpoints act. And to-dos the
family wrote themselves."""
import datetime as dt
import uuid

import pytest

from familyos import chat, notify
from familyos.identity import Principal
from familyos.settings import settings
from tests.conftest import pdf


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


class Scripted:
    """A model that answers what it is told to, and records what it saw."""
    name = "scripted"

    def __init__(self, answer):
        self.answer, self.system, self.messages = answer, None, None

    async def reply(self, system, messages):
        self.system, self.messages = system, messages
        return self.answer


class StreamingScripted(Scripted):
    """A model that writes its JSON answer in pieces, cut wherever a provider
    might cut it: inside an escape, inside the key, mid-word."""
    name = "scripted-stream"

    def __init__(self, answer, pieces):
        super().__init__(answer)
        self.pieces = pieces

    async def stream(self, system, messages, schema=None):
        self.system, self.messages = system, messages
        for piece in self.pieces:
            yield piece


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)
    yield
    chat.use_model(chat.RefusingModel())


@pytest.fixture(autouse=True)
def quiet_notify(monkeypatch):
    sent = []

    async def member(member_id, subject, body):
        sent.append((member_id, subject, body))
        return "test"

    monkeypatch.setattr(notify, "member", member)
    return sent


async def _notice(family, who="amma", visibility="shared", subject="Bill for your Airtel Black account"):
    r = await family.upload(who, pdf(subject), filename="bill.pdf", visibility=visibility)
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    from familyos.db import pool
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", artifact_id,
                         {"from": "ebill@airtel.com", "subject": subject, "date": "Tue, 06 Oct 2026 07:36:47 +0530"})
    return artifact_id


# ----------------------------------------------------------------------------
# what the model sees
# ----------------------------------------------------------------------------

async def test_the_model_sees_the_members_and_the_notices_the_member_can_see(family, database):
    await _notice(family, "amma", "shared")
    await _notice(family, "appa", "private", subject="Appa's private thing")
    model = Scripted({"say": "Hello.", "proposals": []})
    chat.use_model(model)
    await chat.turn(_p(family, "amma"), "hi")
    assert "[MEMBERS] Amma (guardian); Appa (guardian); Paati (adult)" in model.system
    assert "Bill for your Airtel Black account" in model.system
    assert "Appa's private thing" not in model.system
    assert model.messages[-1] == {"role": "user", "content": "hi"}


async def test_history_is_passed_along_but_bounded(family, database):
    model = Scripted({"say": "Still here.", "proposals": []})
    chat.use_model(model)
    history = [{"role": "user", "content": f"q{i}"} for i in range(30)]
    await chat.turn(_p(family), "and?", history)
    assert len(model.messages) == chat.MAX_HISTORY + 1


# ----------------------------------------------------------------------------
# citing and proposing
# ----------------------------------------------------------------------------

async def test_an_answer_cites_a_notice_and_the_console_gets_the_link(family, database):
    artifact_id = await _notice(family)
    chat.use_model(Scripted({"say": "The Airtel bill is in [n1].", "proposals": []}))
    out = await chat.turn(_p(family), "any bills?")
    assert out["grounded"] and out["citations"][0]["artifact_id"] == artifact_id
    assert out["citations"][0]["text"] == "Bill for your Airtel Black account"


async def test_a_made_up_reference_cites_nothing(family, database):
    chat.use_model(Scripted({"say": "Your fee is due Friday [n9].", "proposals": []}))
    out = await chat.turn(_p(family), "fees?")
    assert out["grounded"] is False and out["citations"] == []


async def test_a_proposal_to_assign_is_resolved_to_ids_and_not_performed(family, database):
    artifact_id = await _notice(family)
    chat.use_model(Scripted({"say": "I can hand that to Appa.", "proposals": [
        {"kind": "assign", "notice": "n1", "member": "appa", "note": "can you pay this?"}]}))
    out = await chat.turn(_p(family), "give the airtel bill to appa")
    [p] = out["proposals"]
    assert p["ok"] and p["artifact_id"] == artifact_id and str(p["member_id"]) == family.appa["id"]
    assert p["note"] == "can you pay this?"
    # Nothing happened yet.
    row = await database.fetchrow("SELECT assigned_to FROM input_artifacts WHERE id = $1", artifact_id)
    assert row["assigned_to"] is None
    # Confirming is the ordinary endpoint.
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                                 json={"member_id": str(p["member_id"]), "note": p["note"]})
    assert r.status_code == 200


async def test_a_child_or_a_stranger_cannot_be_proposed_as_assignee(family, database):
    await _notice(family)
    chat.use_model(Scripted({"say": "", "proposals": [
        {"kind": "assign", "notice": "n1", "member": "Older one"},
        {"kind": "assign", "notice": "n1", "member": "Ravi"},
        {"kind": "assign", "notice": "n4", "member": "Appa"}]}))
    out = await chat.turn(_p(family), "hand it over")
    whys = [p["why"] for p in out["proposals"]]
    assert all(not p["ok"] for p in out["proposals"])
    assert "child" in whys[0] and "nobody here is called Ravi" in whys[1] and "not one you can see" in whys[2]


async def test_a_todo_proposal_carries_a_date_and_an_adult(family, database):
    chat.use_model(Scripted({"say": "Adding it.", "proposals": [
        {"kind": "todo", "title": "Book the dentist", "due_date": "2031-10-20", "member": "Paati", "note": None}]}))
    [p] = (await chat.turn(_p(family), "remind paati to book the dentist by the 20th"))["proposals"]
    assert p["ok"] and p["title"] == "Book the dentist" and p["due_date"] == dt.date(2031, 10, 20)
    assert str(p["member_id"]) == family.paati["id"]


async def test_chat_refuses_plainly_without_a_model(family, database):
    chat.use_model(chat.RefusingModel())
    r = await family.client.post("/v1/chat", headers=family.h("amma"), json={"message": "hi"})
    assert r.status_code in (422, 503), r.text
    assert "no model" in r.text


# ----------------------------------------------------------------------------
# to-dos
# ----------------------------------------------------------------------------

async def test_a_todo_is_shared_handed_over_and_the_assignee_is_told(family, database, quiet_notify):
    r = await family.client.post("/v1/todos", headers=family.h("amma"), json={
        "title": "  Book the   dentist ", "due_date": "2031-10-20", "assigned_to": family.appa["id"], "note": "for Older one"})
    assert r.status_code == 201, r.text
    todo = r.json()
    assert todo["title"] == "Book the dentist" and todo["assigned_to"] == family.appa["id"]
    assert len(quiet_notify) == 1 and "Book the dentist" in quiet_notify[0][1]
    # Appa sees it, marks it done; Amma sees it gone from the open list.
    mine = (await family.client.get("/v1/todos", headers=family.h("appa"))).json()
    assert [t["id"] for t in mine] == [todo["id"]]
    r = await family.client.patch(f"/v1/todos/{todo['id']}", headers=family.h("appa"), json={"done": True})
    assert r.status_code == 200 and r.json()["done_by"] == family.appa["id"]
    assert (await family.client.get("/v1/todos", headers=family.h("amma"))).json() == []
    assert len((await family.client.get("/v1/todos?include_done=true", headers=family.h("amma"))).json()) == 1


async def test_a_todo_is_never_handed_to_a_child(family, database):
    r = await family.client.post("/v1/todos", headers=family.h("amma"), json={
        "title": "Pack the bag", "assigned_to": family.older["id"]})
    assert r.status_code == 422


async def test_todos_are_the_households_not_the_worlds(family, database, client):
    await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Ours"})
    from tests.conftest import found
    other = (await found(client, "Other", "B", "b@example.com")).json()["credentials"]["token"]
    theirs = (await client.get("/v1/todos", headers={"Authorization": f"Bearer {other}"})).json()
    assert theirs == []


async def test_a_handled_proposal_resolves_to_the_notice_and_confirms_through_the_endpoint(family, database, quiet_notify):
    artifact_id = await _notice(family)
    chat.use_model(Scripted({"say": "Marking it handled.", "proposals": [
        {"kind": "handled", "notice": "n1", "note": "paid, ref 4471"}]}))
    [p] = (await chat.turn(_p(family), "the airtel bill is paid, ref 4471"))["proposals"]
    assert p["ok"] and p["artifact_id"] == artifact_id and p["note"] == "paid, ref 4471"
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("amma"), json={"note": p["note"]})
    assert r.status_code == 200 and r.json()["handled_note"] == "paid, ref 4471"


async def test_a_provider_that_will_not_answer_is_said_plainly_not_as_a_500(family, database, monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)

    class Broke:
        name = "broke"

        async def reply(self, system, messages, schema=None):
            raise RuntimeError("Error code: 429 - {'error': {'code': 'insufficient_quota', 'message': 'You have no credits remaining.'}}")
    chat.use_model(Broke())
    try:
        r = await family.client.post("/v1/chat", headers=family.h("amma"), json={"message": "what is due?"})
    finally:
        chat.use_model(chat.RefusingModel())
    assert r.status_code == 503, r.text
    assert "no credits remaining" in r.json()["detail"] and "FAMILYOS_CHAT_MODEL" in r.json()["detail"]


async def test_a_date_the_reader_found_is_a_fact_of_the_notice_even_when_it_has_passed(family, database):
    """A tournament last Sunday is no date to decide, so it is no obligation;
    but asked when it was, the model has the date, marked as passed."""
    artifact_id = await _notice(family, "amma", "shared", subject="Taekwondo tournament circular")
    from familyos.db import pool
    household_id = uuid.UUID(family.household["id"])
    xid = uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, actionable, page_count) "
        "VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    last_sunday = dt.date.today() - dt.timedelta(days=4)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, date, optional, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'event', 'Tamil Nadu State-Level TAEKWONDO Tournament', $5, TRUE, 'this Sunday', 0.9)",
        uuid.uuid4(), xid, household_id, artifact_id, last_sunday)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, amount, currency, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 1, 'payment', 'Taekwondo tournament entry fee', 4000, 'INR', 'The entry fee', 0.9)",
        uuid.uuid4(), xid, household_id, artifact_id)
    model = Scripted({"say": "It was last Sunday.", "proposals": []})
    chat.use_model(model)
    await chat.turn(_p(family, "amma"), "when is the taekwondo event?")
    line = next(s for s in model.system.splitlines() if "Taekwondo tournament circular" in s)
    assert f"dates in it: Tamil Nadu State-Level TAEKWONDO Tournament (event, {last_sunday.isoformat()}, already passed, optional)" in line
    assert "entry fee" not in line.split("dates in it")[1]           # undated claims are not dates
    assert "dates in it" in model.system and "already passed" in chat.SYSTEM


# ----------------------------------------------------------------------------
# the answer as it is written
# ----------------------------------------------------------------------------

def test_the_say_string_is_read_out_of_the_json_as_it_streams():
    """Deltas cut anywhere: inside the key, inside an escape, inside a \\u
    sequence. What comes out is the readable sentence, nothing else."""
    x = chat.SayExtractor()
    pieces = ['{"sa', 'y": "The fee is \\u20b9', '1,2', '00 \\"by Fri', 'day\\"\\n', 'then [a1].", "propo', 'sals": []}']
    out = "".join(x.feed(p) for p in pieces)
    assert out == 'The fee is ₹1,200 "by Friday"\nthen [a1].'
    assert chat.json.loads(x.raw)["proposals"] == []


async def test_a_turn_streams_the_answer_then_the_citations_and_proposals(family, database):
    """The person reads the sentence as it is written; the citations and the
    proposals arrive with the finished turn, since they need the whole answer."""
    await _notice(family)
    answer = '{"say": "The PTM is on 18 October [n1]. Shall I add a to-do?", "proposals": [{"kind": "todo", "title": "Prepare for the PTM", "due_date": "2026-10-17", "due_time": null, "note": null, "notice": null, "obligation": null, "member": null, "status": null, "brief": null, "shape": null, "service": null, "what": null, "details": null, "part": null, "max_amount": null, "currency": null, "look": null}]}'
    pieces = [answer[:12], answer[12:30], answer[30:41], answer[41:]]
    chat.use_model(StreamingScripted(None, pieces))
    events = []
    async with family.client.stream("POST", "/v1/chat/stream", headers=family.h("amma"), json={"message": "when is the PTM?"}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
        async for line in r.aiter_lines():
            if line.strip():
                events.append(chat.json.loads(line))
    says = [e["delta"] for e in events if e["type"] == "say"]
    assert len(says) >= 2 and "".join(says) == "The PTM is on 18 October [n1]. Shall I add a to-do?"
    turn = events[-1]
    assert turn["type"] == "turn" and turn["say"].startswith("The PTM is on 18 October")
    assert turn["citations"] and turn["citations"][0]["ref"] == "n1" and turn["proposals"][0]["kind"] == "todo"


async def test_a_model_that_cannot_stream_answers_whole_and_an_error_is_an_event(family, database):
    chat.use_model(Scripted({"say": "Nothing is due.", "proposals": []}))
    events = []
    async with family.client.stream("POST", "/v1/chat/stream", headers=family.h("amma"), json={"message": "anything due?"}) as r:
        async for line in r.aiter_lines():
            if line.strip():
                events.append(chat.json.loads(line))
    assert [e["type"] for e in events] == ["say", "turn"] and events[0]["delta"] == "Nothing is due."
    chat.use_model(chat.RefusingModel())
    events = []
    async with family.client.stream("POST", "/v1/chat/stream", headers=family.h("amma"), json={"message": "hi"}) as r:
        async for line in r.aiter_lines():
            if line.strip():
                events.append(chat.json.loads(line))
    assert events[-1]["type"] == "error" and "no model" in events[-1]["detail"]
