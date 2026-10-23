"""A past optional date, or a past note, dismisses itself with a reason; a
real deadline that passed stays missed until a person looks at it."""
import datetime as dt
import uuid

from familyos.db import pool
from familyos.extraction import service as extraction
from tests.conftest import pdf


async def _dated(family, title, due, *, action="pay", optional=False, end=None):
    artifact_id = uuid.UUID((await family.upload("amma", pdf(title), visibility="shared")).json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    xid, cid, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'deadline', $5, $5, 0.9)", cid, xid, household_id, artifact_id, title)
    await pool().execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, end_date, optional, status) "
        "VALUES ($1, $2, $3, $4, 'task', $5, $6, $7, $8, $9, 'proposed')",
        oid, household_id, artifact_id, cid, action, title, due, end, optional)
    return oid


async def test_past_optional_and_past_notes_file_themselves_and_a_real_deadline_stays(family, database):
    # Real dates around the real today: the brief judges "past" by the clock.
    today = dt.date.today()
    day = dt.timedelta(days=1)
    speak = await _dated(family, "Register as a speaker for the EGM", today - 8 * day, action="submit", optional=True)
    egm = await _dated(family, "Extra Ordinary General Meeting", today - 2 * day, action="note")
    fee = await _dated(family, "Pay the term fee", today - 7 * day, action="pay")
    later = await _dated(family, "Enter the contest", today + 13 * day, action="submit", optional=True)
    running = await _dated(family, "E-voting window", today - 3 * day, action="note", end=today + 2 * day)
    async with pool().acquire() as conn, conn.transaction():
        assert await extraction.file_the_past(conn, today) == 2
    status = {r["id"]: r["status"] for r in await database.fetch("SELECT id, status FROM obligations")}
    assert status[speak] == "dismissed" and status[egm] == "dismissed"
    assert status[fee] == "proposed" and status[later] == "proposed" and status[running] == "proposed"
    reasons = {r["target_id"]: r["detail"]["reason"] for r in
               await database.fetch("SELECT target_id, detail FROM audit_events WHERE action = 'obligation.filed'")}
    assert reasons == {speak: "optional_passed", egm: "note_passed"}
    assert await database.fetchval("SELECT decided_by FROM obligations WHERE id = $1", speak) is None
    # Filed, it no longer leads the brief as missed; the real deadline still does.
    brief = (await family.client.get("/v1/brief", headers=family.h("amma"))).json()
    missed = [i["title"] for i in brief["items"] if i["reason"] == "missed"]
    assert "Pay the term fee" in missed and "Register as a speaker for the EGM" not in missed
    # Running it again files nothing more.
    async with pool().acquire() as conn, conn.transaction():
        assert await extraction.file_the_past(conn, today) == 0
