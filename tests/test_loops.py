"""Loops closed from evidence, and rhythms that did not come.

A receipt that names the biller and the amount settles the bill: the
bill's notice is handled with the receipt as the reason, its reminders
stop, whoever held it is told. A receipt for a different amount, or from
a different biller, settles nothing. And a merchant that charged every
month and then did not is a thing the brief says."""
import datetime as dt
import uuid

import pytest

from familyos import brief, notify
from familyos.db import pool
from familyos.extraction import service
from familyos.extraction.claims import Amount, Claim, Extraction, ExtractorInfo
from familyos.identity import Principal
from tests.conftest import pdf
from tests.test_money import _receipt

GROUNDED = {"page": 1, "start": 0, "end": 16, "boxes": [[60.0, 78.0, 300.0, 93.0]], "match": "exact"}
TODAY = dt.date.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


def _read(claims, *, reference=None):
    return Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                      reference_date=reference or TODAY, actionable=True, page_count=1, claims=claims)


async def _mail(family, sender, subject, *, sent=None, who="amma"):
    r = await family.upload(who, pdf(subject), filename="m.pdf", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    sent = sent or TODAY
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", artifact_id,
                         {"from": sender, "subject": subject, "date": sent.strftime("%a, %d %b %Y 09:00:00 +0530")})
    return artifact_id


async def _bill(family, *, amount=1940.98, due=None, sender="Airtel <ebill@airtel.com>", title="Pay Airtel Black monthly statement"):
    due = due or TODAY + dt.timedelta(days=8)
    artifact_id = await _mail(family, sender, "Bill for your Airtel Black account - Oct'26", sent=TODAY - dt.timedelta(days=6))
    await service.save(uuid.UUID(family.household["id"]), artifact_id, _read([
        Claim(kind="deadline", title=title, date=due, requires=["payment"],
              amount=Amount(value=amount, currency="INR", text=f"₹{amount:,.2f}"), quote="Pay by the due date",
              location=GROUNDED, confidence=0.95)], reference=TODAY - dt.timedelta(days=6)))
    return artifact_id


async def _receipt_for(family, *, amount=1940.98, sender="Airtel <ebill@airtel.com>", subject="Payment received for your Airtel Black account",
                       title="Payment received", on=None):
    artifact_id = await _mail(family, sender, subject, sent=on or TODAY)
    return artifact_id, await service.save(uuid.UUID(family.household["id"]), artifact_id, _read([
        Claim(kind="payment", title=title, date=on or TODAY,
              amount=Amount(value=amount, currency="INR", text=f"₹{amount:,.2f}"),
              quote="Payment received", location=GROUNDED, confidence=0.9)], reference=on or TODAY))


@pytest.fixture
def told(monkeypatch):
    out = []

    async def member(member_id, subject, body):
        out.append((member_id, subject, body))
        return "test"

    monkeypatch.setattr(notify, "member", member)
    return out


async def test_a_receipt_for_the_bill_marks_it_handled_and_tells_whoever_held_it(family, database, told):
    bill = await _bill(family)
    obligation = await database.fetchrow("SELECT id FROM obligations WHERE artifact_id = $1", bill)
    await family.client.post(f"/v1/obligations/{obligation['id']}/decision", headers=family.h("amma"), json={"status": "accepted"})
    r = await family.client.post(f"/v1/artifacts/{bill}/assign", headers=family.h("amma"),
                                 json={"member_id": family.appa["id"], "note": "can you pay this?"})
    assert r.status_code == 200, r.text
    await database.execute("INSERT INTO reminders (id, household_id, obligation_id, member_id, reason, lead_days, send_after, channel, status) "
                           "VALUES ($1, $2, $3, $4, 'due', 1, NOW() + interval '1 day', 'email', 'pending')",
                           uuid.uuid4(), uuid.UUID(family.household["id"]), obligation["id"], uuid.UUID(family.appa["id"]))
    told.clear()

    receipt, counts = await _receipt_for(family)
    assert counts["loops_closed"] == [str(bill)]
    row = await database.fetchrow("SELECT handled_at, handled_by, handled_note FROM input_artifacts WHERE id = $1", bill)
    assert row["handled_at"] is not None and row["handled_by"] is None
    assert row["handled_note"].startswith("paid — ₹1,940.98 receipt from Airtel on")
    assert await database.fetchval("SELECT status FROM reminders WHERE obligation_id = $1", obligation["id"]) == "cancelled"
    audit = await database.fetchrow("SELECT detail FROM audit_events WHERE action = 'artifact.handled' AND target_id = $1", bill)
    assert audit["detail"]["by"] == "receipt" and audit["detail"]["receipt_artifact_id"] == str(receipt)
    # Appa, who was handed the bill, hears it is paid; Amma handed it, and hears too.
    assert {t[0] for t in told} == {uuid.UUID(family.appa["id"]), uuid.UUID(family.amma["id"])} - {None}
    assert all(t[1].startswith("Paid:") for t in told)
    # The bill is off the brief's list of things needing someone.
    out = await brief.today(_p(family), limit=50)
    assert not any(i.get("artifact_id") == bill and i["reason"] in ("today", "soon", "undecided", "assigned") for i in out["items"])
    handled = next(i for i in out["items"] if i["reason"] == "handled" and i.get("artifact_id") == bill)
    assert "receipt" in handled["why"]
    # And out of Appa's hands: the brief no longer says it was handed to him.
    appa = await brief.today(_p(family, "appa"), limit=50)
    assert not any(i["reason"] == "assigned" and i.get("artifact_id") == bill for i in appa["items"])
    # The receipt itself asks nothing: "paid" is a record for the ledger, not a task.
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = $1", receipt) == 0


async def test_a_receipt_that_does_not_fit_settles_nothing(family, database, told):
    bill = await _bill(family)
    await _receipt_for(family, amount=1240.98)                                   # the wrong amount
    await _receipt_for(family, sender="Swiggy <noreply@swiggy.in>", subject="Payment received for your order",
                       title="Order paid via bank")                               # the right amount, another biller
    await _receipt_for(family, on=TODAY - dt.timedelta(days=90), subject="Payment received, Airtel")   # too long ago
    assert await database.fetchval("SELECT handled_at FROM input_artifacts WHERE id = $1", bill) is None
    assert told == []
    # The same amount from the same biller, within the window: that one does.
    _, counts = await _receipt_for(family, subject="Thank you for your payment, Airtel")
    assert counts["loops_closed"] == [str(bill)]


async def test_a_merchant_that_charged_monthly_and_then_did_not_is_on_the_brief(family, database):
    for days_ago in (100, 70, 40):
        await _receipt(family, "amma", "Netflix <info@mailer.netflix.com>", f"Your Netflix receipt, {days_ago} days ago",
                       [("payment", "Netflix monthly subscription charge", 649.0, "INR", None)], sent=TODAY - dt.timedelta(days=days_ago))
    out = await brief.today(_p(family), limit=50)
    item = next(i for i in out["items"] if i["reason"] == "unbilled")
    assert item["title"].startswith("No Netflix charge since") and "monthly" in item["why"] and item["when"] == "not arrived"
    # Once it comes, nothing is said.
    await _receipt(family, "amma", "Netflix <info@mailer.netflix.com>", "Your Netflix receipt, this month",
                   [("payment", "Netflix monthly subscription charge", 649.0, "INR", None)], sent=TODAY - dt.timedelta(days=9))
    out = await brief.today(_p(family), limit=50)
    assert not any(i["reason"] == "unbilled" for i in out["items"])
