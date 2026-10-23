"""The inbox: a headline a person would use, who is handling a notice, and
the one refusal that keeps assignment from leaking a private notice."""
import uuid

import pytest

from familyos import brief, notify
from familyos.db import pool
from familyos.identity import Principal
from tests.conftest import pdf


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


@pytest.fixture(autouse=True)
def quiet_notify(monkeypatch):
    """Assignment tells the assignee. The message itself is collected here,
    never sent, so the tests can say what it carried."""
    sent = []

    async def member(member_id, subject, body):
        sent.append((member_id, subject, body))
        return "test"

    monkeypatch.setattr(notify, "member", member)
    return sent


# ----------------------------------------------------------------------------
# the feed
# ----------------------------------------------------------------------------

async def test_a_pasted_notice_gets_a_headline_from_what_was_read_not_its_filename(family, database):
    r = await family.upload("amma", b"Dear Parents, PTM on Friday 9 October.", filename="pasted.txt",
                            content_type="text/plain", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    # Before extraction, the filename is all there is.
    rows = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()
    assert rows[0]["headline"] == "pasted.txt" and rows[0]["state"] == "info"
    # A claim arrives; the headline follows it, and the row becomes to do.
    xid = uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)",
        xid, uuid.UUID(family.household["id"]), artifact_id)
    cid = uuid.uuid4()
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'event', '1st Parent-Teacher Meeting', 'PTM on Friday', 0.9)",
        cid, xid, uuid.UUID(family.household["id"]), artifact_id)
    await pool().execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date) "
        "VALUES ($1, $2, $3, $4, 'task', 'attend', '1st Parent-Teacher Meeting', CURRENT_DATE + 3)",
        uuid.uuid4(), uuid.UUID(family.household["id"]), artifact_id, cid)
    rows = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()
    assert rows[0]["headline"] == "1st Parent-Teacher Meeting"
    assert rows[0]["state"] == "todo" and rows[0]["open"] == 1 and rows[0]["dates"] == 1
    assert rows[0]["preview"] == ["1st Parent-Teacher Meeting"]
    assert rows[0]["from_label"] == "you"


async def test_an_email_is_headed_by_its_subject_and_its_sender(family, database):
    from tests.test_email import message, post
    r = await post(family.client, message("amma@example.com", family.inbound, attachments=(("c.pdf", pdf("x")),)))
    assert r.status_code == 202
    rows = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()
    # The gateway keeps the bare address, so the sending domain is the label;
    # the subject the helper set is the headline.
    assert rows[0]["from_label"] == "example.com"
    assert rows[0]["headline"] and rows[0]["headline"] != "email"
    assert rows[0]["attachments"] == 1


async def test_the_feed_shows_only_what_the_member_can_see(family, database):
    await family.upload("amma", pdf("mine"), visibility="private")
    await family.upload("appa", pdf("theirs"), visibility="private")
    await family.upload("amma", pdf("ours"), visibility="shared")
    mine = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()
    theirs = (await family.client.get("/v1/inbox", headers=family.h("appa"))).json()
    assert len(mine) == 2 and len(theirs) == 2


# ----------------------------------------------------------------------------
# handing a notice over
# ----------------------------------------------------------------------------

async def test_a_shared_notice_can_be_handed_to_another_adult_with_a_note(family, database, quiet_notify):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                                 json={"member_id": family.appa["id"], "note": "  Can you  let them know who is on pickup? "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_to"] == family.appa["id"] and body["assigned_by"] == family.amma["id"]
    assert body["assigned_note"] == "Can you let them know who is on pickup?"
    # The assignee was told, with the note, and never the token.
    assert len(quiet_notify) == 1
    to, subject, text = quiet_notify[0]
    assert str(to) == family.appa["id"] and "pickup" in text and "Amma" in text
    # It shows on the artifact and in the feed.
    a = (await family.client.get(f"/v1/artifacts/{artifact_id}", headers=family.h("appa"))).json()
    assert a["assigned_to"] == family.appa["id"] and a["assigned_note"].endswith("pickup?")
    row = (await family.client.get("/v1/inbox", headers=family.h("appa"))).json()[0]
    assert row["assigned_to"] == family.appa["id"]


async def test_handing_it_to_yourself_tells_nobody(family, database, quiet_notify):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                                 json={"member_id": family.amma["id"]})
    assert r.status_code == 200 and quiet_notify == []


async def test_a_private_notice_cannot_be_handed_to_someone_who_cannot_see_it(family, database, quiet_notify):
    """The refusal that matters. Assigning must never be a side door that
    widens a private notice; the owner shares it first, on purpose."""
    artifact_id = (await family.upload("amma", pdf("x"), visibility="private")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                                 json={"member_id": family.appa["id"], "note": "yours"})
    assert r.status_code == 409
    assert "Share it" in r.json()["detail"]
    assert quiet_notify == []
    # Shared, the same request works.
    await family.client.patch(f"/v1/artifacts/{artifact_id}", headers=family.h("amma"), json={"visibility": "shared"})
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                                 json={"member_id": family.appa["id"], "note": "yours"})
    assert r.status_code == 200


async def test_a_child_cannot_be_handed_a_notice(family, database):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                                 json={"member_id": family.older["id"]})
    assert r.status_code == 422


async def test_taking_it_back_clears_the_note_too(family, database, quiet_notify):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                             json={"member_id": family.appa["id"], "note": "please"})
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("appa"), json={"member_id": None})
    assert r.status_code == 200
    assert r.json()["assigned_to"] is None and r.json()["assigned_note"] is None
    assert len(quiet_notify) == 1  # only the first hand-over told anyone


async def test_somebody_who_cannot_see_it_cannot_assign_it(family, database):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="private")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("appa"),
                                 json={"member_id": family.appa["id"]})
    assert r.status_code == 404


async def test_the_audit_records_who_and_never_the_note(family, database):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                             json={"member_id": family.appa["id"], "note": "the secret note"})
    row = await pool().fetchrow("SELECT detail::text AS d FROM audit_events WHERE action = 'artifact.assigned'")
    assert family.appa["id"] in row["d"] and "secret" not in row["d"] and '"with_note": true' in row["d"]


# ----------------------------------------------------------------------------
# it reaches the brief
# ----------------------------------------------------------------------------

async def test_a_notice_handed_to_you_leads_your_brief_with_the_note(family, database, quiet_notify):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                             json={"member_id": family.appa["id"], "note": "yours this week"})
    b = await brief.today(_p(family, "appa"))
    assigned = [i for i in b["items"] if i["reason"] == "assigned"]
    assert len(assigned) == 1
    assert assigned[0]["note"] == "yours this week" and assigned[0]["assigned_by_name"] == "Amma"
    assert "Amma asked" in assigned[0]["why"]
    # Not in the brief of the person who handed it over.
    mine = await brief.today(_p(family, "amma"))
    assert not [i for i in mine["items"] if i["reason"] == "assigned"]


# ----------------------------------------------------------------------------
# handled: the other half of a hand-over
# ----------------------------------------------------------------------------

async def test_the_assignee_marks_it_handled_and_the_one_who_asked_is_told(family, database, quiet_notify):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"]
    await family.client.post(f"/v1/artifacts/{artifact_id}/assign", headers=family.h("amma"),
                             json={"member_id": family.appa["id"], "note": "can you pay this?"})
    quiet_notify.clear()
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("appa"),
                                 json={"note": " paid,  ref 4471 "})
    assert r.status_code == 200, r.text
    assert r.json()["handled_by"] == family.appa["id"] and r.json()["handled_note"] == "paid, ref 4471"
    # Amma hears it, with the note; Appa does not tell himself.
    assert [str(to) for to, _, _ in quiet_notify] == [family.amma["id"]]
    assert "4471" in quiet_notify[0][2] and "Appa" in quiet_notify[0][2]
    # The row is done whatever its dates say, and the notice says who and what.
    row = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()[0]
    assert row["state"] == "done" and row["handled_by"] == family.appa["id"]
    a = (await family.client.get(f"/v1/artifacts/{artifact_id}", headers=family.h("amma"))).json()
    assert a["handled_note"] == "paid, ref 4471"
    # And it leads Amma's brief, once, as the loop closing.
    b = await brief.today(_p(family, "amma"))
    handled = [i for i in b["items"] if i["reason"] == "handled"]
    assert len(handled) == 1 and "Appa handled it" in handled[0]["why"] and "4471" in handled[0]["why"]
    assert not [i for i in (await brief.today(_p(family, "appa")))["items"] if i["reason"] == "handled"]


async def test_handled_cancels_the_pending_reminders_and_reopen_puts_the_dates_back(family, database, quiet_notify):
    artifact_id = uuid.UUID((await family.upload("amma", pdf("x"), visibility="shared")).json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    xid, cid, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'deadline', 'Pay the bill', 'pay by', 0.9)", cid, xid, household_id, artifact_id)
    await pool().execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, status) "
        "VALUES ($1, $2, $3, $4, 'task', 'pay', 'Pay the bill', CURRENT_DATE + 3, 'accepted')",
        oid, household_id, artifact_id, cid)
    await pool().execute(
        "INSERT INTO reminders (id, household_id, obligation_id, member_id, reason, lead_days, send_after, channel, status) "
        "VALUES ($1, $2, $3, $4, 'due', 1, NOW() + interval '1 day', 'log', 'pending')",
        uuid.uuid4(), household_id, oid, uuid.UUID(family.amma["id"]))
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("amma"), json={})
    assert r.status_code == 200
    assert await pool().fetchval("SELECT status FROM reminders WHERE obligation_id = $1", oid) == "cancelled"
    row = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()[0]
    assert row["state"] == "done" and row["dates"] == 1
    r = await family.client.delete(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["handled_at"] is None
    row = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()[0]
    assert row["state"] == "done" and row["handled_by"] is None   # the accepted date still makes it done


async def test_somebody_who_cannot_see_it_cannot_mark_it_handled(family, database):
    artifact_id = (await family.upload("amma", pdf("x"), visibility="private")).json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("appa"), json={"note": "x"})
    assert r.status_code == 404
