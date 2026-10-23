"""A reply to the school: drafted from the notice and the family's decision,
sent only when a parent says so, to where the notice came from; the text
is not kept."""
import uuid

import pytest

from familyos import chat, mail
from familyos.db import pool
from familyos.intake import telegram
from tests.conftest import pdf


class Drafter:
    name = "drafter"

    def __init__(self):
        self.seen = None

    async def reply(self, system, messages, schema=None):
        self.seen = messages[0]["content"]
        return {"text": "Dear Ms Rao, Sashreek will attend the PTM on Friday at 9:30. Thank you.", "subject": "Re: PTM on Friday"}


@pytest.fixture
def drafter():
    d = Drafter()
    chat.use_model(d)
    yield d
    chat.use_model(chat.RefusingModel())


async def _mail_notice(family, sender, subject):
    r = await family.upload("amma", pdf(subject), filename="n.pdf", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", aid,
                         {"from": sender, "subject": subject, "date": "Thu, 08 Oct 2026 09:00:00 +0530"})
    return aid


async def test_a_reply_is_drafted_from_the_facts_and_sent_by_mail_on_approval(family, database, drafter, monkeypatch):
    aid = await _mail_notice(family, "Aachi Global <office@aachiglobal.edu>", "PTM on Friday")
    child = family.older
    await family.consent(child)
    r = await family.client.put(f"/v1/artifacts/{aid}/subjects", headers=family.h("amma"), json=[child["id"]])
    assert r.status_code == 200, r.text
    r = await family.client.post(f"/v1/artifacts/{aid}/reply/draft", headers=family.h("amma"), json={"stance": "yes", "note": "we will be a little late"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["channel"] == "email" and d["to"] == "Aachi Global <office@aachiglobal.edu>" and d["subject"] == "Re: PTM on Friday"
    assert "Sashreek will attend" in d["text"]
    assert "The parent's answer: yes" in drafter.seen and "we will be a little late" in drafter.seen and child["display_name"] in drafter.seen
    sent = []

    async def fake_send(to, subject, body, **kw):
        sent.append((to, subject, body))

    monkeypatch.setattr(mail, "send", fake_send)
    r = await family.client.post(f"/v1/artifacts/{aid}/reply", headers=family.h("amma"), json={"text": d["text"], "subject": d["subject"]})
    assert r.status_code == 200 and r.json()["sent"] is True and r.json()["channel"] == "email"
    [(to, subject, body)] = sent
    assert to == "office@aachiglobal.edu" and subject == "Re: PTM on Friday" and body.endswith(f"— {family.amma['display_name']}")
    audit = await database.fetchrow("SELECT detail FROM audit_events WHERE action = 'reply.sent' AND target_id = $1", aid)
    assert audit["detail"]["channel"] == "email" and "text" not in audit["detail"] and "attend" not in str(audit["detail"])


async def test_a_telegram_notice_is_answered_into_its_group(family, database, drafter, monkeypatch):
    r = await family.upload("amma", pdf("Holiday on Monday"), filename="n.pdf", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'telegram', source = $2 WHERE id = $1", aid,
                         {"chat_id": -100123, "chat_type": "supergroup", "chat_title": "Grade 4 parents"})
    monkeypatch.setattr(telegram, "send_message", _capture := _Capture())
    from familyos.settings import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    r = await family.client.post(f"/v1/artifacts/{aid}/reply/draft", headers=family.h("appa"), json={"stance": "no"})
    assert r.status_code == 200 and r.json()["channel"] == "telegram" and r.json()["to"] == "Grade 4 parents"
    r = await family.client.post(f"/v1/artifacts/{aid}/reply", headers=family.h("appa"), json={"text": "We will not be attending. Thank you."})
    assert r.status_code == 200
    assert _capture.calls == [(-100123, "We will not be attending. Thank you.")]


class _Capture:
    def __init__(self):
        self.calls = []

    async def __call__(self, chat_id, text, **kw):
        self.calls.append((chat_id, text))


async def test_a_notice_with_no_way_back_gets_no_draft(family, drafter):
    r = await family.upload("amma", pdf("A shared photo of a circular"), filename="c.pdf", visibility="shared")
    aid = r.json()["artifact"]["id"]
    r = await family.client.post(f"/v1/artifacts/{aid}/reply/draft", headers=family.h("amma"), json={"stance": "yes"})
    assert r.status_code == 422 and "no way back" in r.json()["detail"]
    r = await family.client.post(f"/v1/artifacts/{aid}/reply", headers=family.h("amma"), json={"text": "hello"})
    assert r.status_code == 422
