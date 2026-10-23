"""The Sunday digest: the week ahead as one message, once per member per
week, only what they may see."""
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest

from familyos import digest, notify, todos
from familyos.db import pool
from familyos.identity import Principal
from familyos.settings import settings
from tests.conftest import pdf


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    out = []

    async def member(member_id, subject, body):
        out.append((member_id, subject, body))
        return "telegram"

    monkeypatch.setattr(notify, "member", member)
    return out


async def _dated(family, who, title, due, status="proposed", visibility="shared"):
    artifact_id = uuid.UUID((await family.upload(who, pdf(title), visibility=visibility)).json()["artifact"]["id"])
    household_id = uuid.UUID(family.household["id"])
    xid, cid = uuid.uuid4(), uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    await pool().execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
        "VALUES ($1, $2, $3, $4, 0, 'deadline', $5, $5, 0.9)", cid, xid, household_id, artifact_id, title)
    await pool().execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, status) "
        "VALUES ($1, $2, $3, $4, 'task', 'pay', $5, $6, $7)", uuid.uuid4(), household_id, artifact_id, cid, title, due, status)
    return artifact_id


async def test_the_digest_says_what_is_due_waiting_and_coming_out_of_the_account(family, database):
    today = dt.date.today()
    await _dated(family, "amma", "Pay the Airtel bill", today + dt.timedelta(days=3))
    await _dated(family, "amma", "Pay the term fee", today + dt.timedelta(days=20))      # not this week
    handed = await _dated(family, "amma", "Return the consent form", today + dt.timedelta(days=5))
    await family.client.post(f"/v1/artifacts/{handed}/assign", headers=family.h("amma"),
                             json={"member_id": family.appa["id"], "note": "yours this week"})
    await todos.add(_p(family, "amma"), "Book the car service", due_date=today + dt.timedelta(days=4),
                    assigned_to=uuid.UUID(family.appa["id"]))
    subject, body = await digest.compose(_p(family, "appa"), today)
    assert subject.startswith("Your week")
    assert "This week" in body and "Pay the Airtel bill" in body and "Pay the term fee" not in body
    assert "Waiting on you" in body and "Return the consent form" in body and "Amma asked" in body
    assert "To-dos" in body and "Book the car service" in body


async def test_a_private_notice_of_somebody_else_is_not_in_my_digest(family, database):
    today = dt.date.today()
    await _dated(family, "amma", "Amma's private thing", today + dt.timedelta(days=2), visibility="private")
    _, body = await digest.compose(_p(family, "appa"), today)
    assert "private thing" not in body


async def test_an_empty_week_is_said_plainly(family, database):
    _, body = await digest.compose(_p(family, "paati"), dt.date.today())
    assert "Nothing is due this week" in body


async def test_the_sweep_sends_once_per_adult_on_the_day_and_not_before(family, database, sent, monkeypatch):
    monkeypatch.setattr(settings, "digest_weekday", 6)
    monkeypatch.setattr(settings, "digest_hour", 8)
    monkeypatch.setattr(settings, "timezone", "Asia/Kolkata")
    tz = ZoneInfo("Asia/Kolkata")
    sunday_7am = dt.datetime(2026, 10, 11, 7, 0, tzinfo=tz)         # a Sunday, too early
    assert (await digest.sweep(sunday_7am))["sent"] == 0 and sent == []
    sunday_9am = dt.datetime(2026, 10, 11, 9, 0, tzinfo=tz)
    out = await digest.sweep(sunday_9am)
    # Three adults, no child.
    assert out["sent"] == 3 and {str(m) for m, _, _ in sent} == {family.amma["id"], family.appa["id"], family.paati["id"]}
    # Later the same day: nothing goes twice.
    assert (await digest.sweep(sunday_9am + dt.timedelta(hours=6)))["sent"] == 0 and len(sent) == 3
    # Next Sunday it goes again.
    assert (await digest.sweep(sunday_9am + dt.timedelta(days=7)))["sent"] == 3


async def test_send_me_now_sends_and_the_preview_is_the_same_words(family, database, sent):
    r = await family.client.get("/v1/digest", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["subject"].startswith("Your week")
    r2 = await family.client.post("/v1/digest/send", headers=family.h("amma"))
    assert r2.status_code == 200 and r2.json()["sent"] is True and r2.json()["channel"] == "telegram"
    assert sent[-1][1] == r.json()["subject"]


async def test_the_digest_says_money_against_last_month_and_once_a_month_the_subscriptions(family, database, monkeypatch):
    from familyos import ledger
    today = dt.date(2026, 10, 4)
    a = uuid.uuid4()
    charges = [
        {"merchant": "KFC", "category": "food", "currency": "INR", "amount": 2100.0, "date": dt.date(2026, 9, 27),
         "says_recurring": False, "period_end": None, "artifact_id": a, "title": "x", "headline": "x"},
    ] + [
        {"merchant": "Swiggy", "category": "food", "currency": "INR", "amount": 120.0, "date": dt.date(2026, 8, 20 + i),
         "says_recurring": False, "period_end": None, "artifact_id": a, "title": "x", "headline": "x"} for i in range(5)
    ] + [
        {"merchant": "Apple", "category": "subscriptions", "currency": "INR", "amount": 195.0, "date": dt.date(2026, 9, 9),
         "says_recurring": True, "period_end": None, "artifact_id": a, "title": "x", "headline": "x"},
    ]

    async def overview(p, *, days=90):
        return {"days": days, "charges": charges, "recurring": ledger.recurring(charges, today),
                "month": ledger.spend(charges, days=30, today=today), "services": {"timeline": [], "last_done": []}}

    monkeypatch.setattr(ledger, "overview", overview)
    _, body = await digest.compose(_p(family), today)
    assert "Money, last 30 days" in body and "₹2,295 on receipts" in body and "more than the 30 days before" in body
    assert "Food ₹2,100, ₹1,500 more — mostly KFC" in body
    # One lonely earlier receipt is not a "last month": no comparison is claimed.
    thin = [c for c in charges if c["date"] > dt.date(2026, 9, 1)] + [charges[1]]

    async def thin_overview(p, *, days=90):
        return {"days": days, "charges": thin, "recurring": ledger.recurring(thin, today),
                "month": ledger.spend(thin, days=30, today=today), "services": {"timeline": [], "last_done": []}}

    monkeypatch.setattr(ledger, "overview", thin_overview)
    _, body2 = await digest.compose(_p(family), today)
    assert "not enough earlier receipts to compare" in body2 and "more than the 30 days before" not in body2
    assert "Still want these?" in body and "Apple ₹195 — manage: https://account.apple.com/account/manage" in body
    # Not the first week of the month: no subscriptions prompt.
    _, later = await digest.compose(_p(family), dt.date(2026, 10, 20))
    assert "Still want these?" not in later


async def test_a_span_as_a_due_time_does_not_break_the_digest(family, database):
    """"08:30 to 12:30" is a due_time the reader writes for a half day; the
    clash check reads the first time in it rather than choking."""
    import uuid as _uuid

    from familyos.db import pool
    from tests.conftest import pdf
    r = await family.upload("amma", pdf("Half days"), filename="h.pdf", visibility="shared")
    artifact_id = _uuid.UUID(r.json()["artifact"]["id"])
    household_id = _uuid.UUID(family.household["id"])
    xid, cid = _uuid.uuid4(), _uuid.uuid4()
    await pool().execute("INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, actionable, page_count) "
                         "VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', TRUE, 1)", xid, household_id, artifact_id)
    await pool().execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
                         "VALUES ($1, $2, $3, $4, 0, 'event', 'Half days', 'Half days', 0.9)", cid, xid, household_id, artifact_id)
    await pool().execute("INSERT INTO obligations (id, household_id, artifact_id, claim_id, kind, action, title, due_date, end_date, due_time, status) "
                         "VALUES ($1, $2, $3, $4, 'calendar', 'note', 'Half days', $5, $6, '08:30 to 12:30', 'accepted')",
                         _uuid.uuid4(), household_id, artifact_id, cid, dt.date.today() + dt.timedelta(days=1), dt.date.today() + dt.timedelta(days=8))
    r = await family.client.get("/v1/digest", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    r = await family.client.get("/v1/brief?limit=20", headers=family.h("amma"))
    assert r.status_code == 200
