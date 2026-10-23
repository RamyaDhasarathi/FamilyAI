"""What kind of mail a notice is, and the one rule that follows from it: a
promotion is read and kept, and nothing in it becomes a task. The first real
mailbox put a life insurer's "lock in before the 21st" on the brief beside
the income-tax notice that had an actual deadline."""

import pytest

from familyos import categories
from familyos.settings import settings


def _src(sender, subject=""):
    return {"from": sender, "subject": subject}


# ----------------------------------------------------------------------------
# the pure rules
# ----------------------------------------------------------------------------

def test_the_sending_domain_decides_first():
    assert categories.category_of("gmail", _src("noreply@reportsmailer.zerodha.net", "Contract note")) == "trading"
    assert categories.category_of("gmail", _src("Airtel <bills@airtel.com>", "Bill for your account")) == "bills"
    assert categories.category_of("gmail", _src("cpc@cpc.incometax.gov.in", "Intimation u/s 143(1)")) == "government"


def test_the_longest_matching_domain_wins_so_a_marketing_arm_is_a_promo():
    # The insurer and its marketing sender share a parent domain.
    assert categories.category_of("gmail", _src("care@tataaia.com", "Your policy")) == "insurance"
    # Bought through the aggregator, written by the insurer: both send the policy.
    assert categories.category_of("gmail", _src("Policybazaar <care@policybazaar.com>", "Your car insurance policy")) == "insurance"
    assert categories.category_of("gmail", _src("noreply@acko.com", "Policy document")) == "insurance"
    assert categories.category_of("gmail", _src("offers@connect.tataaia.com", "Lock in your premium")) == "promo"
    assert categories.category_of("gmail", _src("x@emailers.idfcfirst.bank.in", "Support your child @ 0 fee")) == "promo"
    # A trial's upsell mails are the sender's marketing, whatever the product is.
    assert categories.category_of("gmail", _src("hello@dune.com", "Your premium access: 7 days remaining")) == "promo"
    assert categories.category_of("gmail", _src("x@idfcfirst.bank.in", "Your statement")) == "banking"


def test_the_subject_decides_only_for_a_domain_nobody_listed():
    assert categories.category_of("gmail", _src("admin@greenfield.example", "Circular 12: PTM on Friday")) == "school"
    assert categories.category_of("gmail", _src("x@somewhere.example", "Your appointment with Dr Rao")) == "medical"
    # A listed domain is not overruled by its subject line.
    assert categories.category_of("gmail", _src("x@swiggy.in", "Your invoice")) == "food"


def test_nothing_known_stays_unknown_rather_than_a_guess():
    assert categories.category_of("upload", None) == "unknown"
    assert categories.category_of("telegram", {"from": "", "from_name": "Priya"}) == "unknown"
    assert categories.category_of("gmail", _src("x@somewhere.example", "Hello")) == "unknown"


def test_only_promotions_newsletters_and_developer_mail_are_barred_from_proposing():
    assert not categories.may_obligate("promo")
    assert not categories.may_obligate("newsletter")
    assert not categories.may_obligate("developer")
    for c in categories.CATEGORIES:
        if c not in categories.NEVER_OBLIGATES:
            assert categories.may_obligate(c)


# ----------------------------------------------------------------------------
# through the inbox, by way of a connected mailbox
# ----------------------------------------------------------------------------

@pytest.fixture
def gmail_on(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/v1/google/callback")
    monkeypatch.setattr(settings, "gmail_enabled", True)
    monkeypatch.setattr(settings, "extractor", "rules")


async def _arrives(family, database, sender: str, subject: str, lines: list[str]) -> tuple[dict, dict]:
    """One message with one PDF attachment through a fake Gmail; returns the
    attachment's extraction result and the inbox row for the message."""
    from familyos.intake import mailbox
    from tests.test_extraction import _run_extraction, make_pdf
    from tests.test_gmail import FakeGoogle, _connect, _raw
    fake = FakeGoogle(messages={"m1": _raw(subject=subject, sender=sender, attach=make_pdf(lines))})
    account = await _connect(family, fake)
    await mailbox.poll(account["id"], transport=fake)
    attachment_id = await database.fetchval("SELECT id::text FROM input_artifacts WHERE channel = 'gmail_attachment'")
    done = await _run_extraction(database, attachment_id)
    assert done["status"] == "succeeded", done
    row = next(r for r in (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()
               if r["channel"] == "gmail")
    return done["result"], row


async def test_a_promotion_is_tagged_and_its_deadline_is_not_proposed_as_a_task(family, database, gmail_on):
    result, row = await _arrives(family, database, "Max Life <offers@maxlifeinsurance.info>", "Lock in Rs 2 Cr cover",
                                 ["Lock in your premium before 21 October 2031.",
                                  "Pay Rs 902 per month to keep this rate. Offer closes 21 October 2031."])
    assert result["category"] == "promo"
    assert result["obligations"] == 0 and result["obligations_withheld"] >= 1
    # Nothing to decide, anywhere.
    assert (await family.client.get("/v1/obligations?status=proposed", headers=family.h("amma"))).json() == []
    # The inbox says what it is, and the read says why nothing was asked.
    assert row["category"] == "promo" and row["state"] == "info"
    attachment_id = await database.fetchval("SELECT id::text FROM input_artifacts WHERE channel = 'gmail_attachment'")
    x = (await family.client.get(f"/v1/artifacts/{attachment_id}/extraction", headers=family.h("amma"))).json()
    assert x["extraction"]["actionable"] is False and "promotion" in x["extraction"]["non_actionable_reason"]


async def test_a_bill_from_a_listed_sender_still_proposes(family, database, gmail_on):
    result, row = await _arrives(family, database, "Airtel <ebill@airtel.com>", "Bill for your Airtel Black account",
                                 ["Total amount payable Rs 1,940.98.", "Due date 16 October 2031."])
    assert result["category"] == "bills" and result["obligations_withheld"] == 0
    assert result["obligations"] >= 1
    assert row["category"] == "bills" and row["state"] == "todo"


async def test_a_delivery_that_already_happened_is_a_record_not_a_missed_task(family, database, gmail_on):
    import datetime as dt
    today = dt.date.today()
    when = today.strftime("%A, %-d %B %Y")
    result, row = await _arrives(family, database, "Swiggy <noreply@swiggy.in>", "Your Swiggy order was delivered",
                                 [f"Your order from Ramaas was delivered on {when}.", "Paid via bank Rs 459."])
    assert result["category"] == "food"
    assert result["claims"] >= 1, "the fixture must read as something, or this test proves nothing"
    assert result["obligations"] == 0 and result["records_kept"] >= 1
    assert row["state"] == "info"


async def test_a_school_event_on_the_day_it_is_sent_still_proposes(family, database, gmail_on):
    import datetime as dt
    when = dt.date.today().strftime("%A, %-d %B %Y")
    result, row = await _arrives(family, database, "office@greenfield.example", "Circular: PTM today",
                                 [f"Parent-Teacher Meeting on {when}.", "Parents are requested to attend."])
    assert result["category"] == "school"
    assert result["obligations"] >= 1 and result["records_kept"] == 0


# ----------------------------------------------------------------------------
# receipts, statements and the same thing said twice
# ----------------------------------------------------------------------------

def _o(action, due=None, end=None, title="x"):
    from familyos.extraction.obligations import ProposedObligation
    return ProposedObligation(0, "task" if action != "note" else "calendar", action, title, due, end, None, False)


def test_a_receipt_line_item_is_not_a_bill():
    import datetime as dt

    from familyos.extraction.obligations import for_category
    sent = dt.date(2026, 10, 2)
    f = for_category([_o("pay", title="Indian Tomato, quantity 1"), _o("pay", title="Grand total")], "food", sent)
    assert f.kept == [] and f.recorded == 2


def test_statement_boilerplate_is_not_a_task_but_a_dated_deadline_is():
    import datetime as dt

    from familyos.extraction.obligations import for_category
    sent = dt.date(2026, 9, 26)
    f = for_category([_o("submit", title="Report any discrepancy within 7 days"),
                      _o("submit", dt.date(2026, 10, 16), title="Cast remote e-vote")], "trading", sent)
    assert [o.title for o in f.kept] == ["Cast remote e-vote"] and f.recorded == 1


def test_a_subscription_period_that_has_started_is_a_record_even_if_it_runs_on():
    import datetime as dt

    from familyos.extraction.obligations import for_category
    sent = dt.date(2026, 9, 7)
    f = for_category([_o("note", dt.date(2026, 9, 7), dt.date(2026, 10, 7), title="Claude Pro subscription period"),
                      _o("note", dt.date(2026, 10, 9), title="Apple One renews")], "subscriptions", sent)
    assert [o.title for o in f.kept] == ["Apple One renews"] and f.recorded == 1


def test_the_tax_office_keeps_its_undated_please_respond_but_not_the_date_it_wrote():
    import datetime as dt

    from familyos.extraction.obligations import for_category
    sent = dt.date(2026, 9, 23)
    f = for_category([_o("submit", title="Respond to the outstanding demand"),
                      _o("note", sent, title="Date of refund communication")], "government", sent)
    assert [o.title for o in f.kept] == ["Respond to the outstanding demand"] and f.recorded == 1


def test_a_school_or_clinic_keeps_an_event_on_the_day_it_is_sent():
    import datetime as dt

    from familyos.extraction.obligations import for_category
    sent = dt.date(2026, 10, 9)
    for category in ("school", "medical"):
        f = for_category([_o("note", sent, title="PTM today, 3 pm")], category, sent)
        assert len(f.kept) == 1 and f.recorded == 0


async def test_a_receipt_said_in_the_body_and_again_in_the_pdf_is_proposed_once(family, database, gmail_on):
    import datetime as dt
    from email.message import EmailMessage

    from familyos.intake import mailbox
    from tests.test_extraction import _run_extraction, make_pdf
    from tests.test_gmail import FakeGoogle, _connect
    soon = (dt.date.today() + dt.timedelta(days=20)).strftime("%A, %-d %B %Y")
    line = f"Your X Premium Plus subscription renews on {soon}."
    msg = EmailMessage()
    msg["From"] = "X <receipts@stripe.com>"
    msg["To"] = "amma@gmail.com"
    msg["Subject"] = "Your receipt from X"
    msg["Message-ID"] = "<dup@stripe.com>"
    msg["Authentication-Results"] = "mx.google.com; dkim=pass header.d=stripe.com; dmarc=pass"
    msg.set_content(line)
    msg.add_attachment(make_pdf([line]), maintype="application", subtype="pdf", filename="receipt.pdf")
    fake = FakeGoogle(messages={"m1": msg.as_bytes()})
    account = await _connect(family, fake)
    await mailbox.poll(account["id"], transport=fake)
    ids = [r["id"] for r in await database.fetch("SELECT id::text FROM input_artifacts ORDER BY parent_id NULLS FIRST")]
    results = [await _run_extraction(database, i) for i in ids]
    assert all(r["status"] == "succeeded" for r in results), results
    proposed = (await family.client.get("/v1/obligations?status=proposed", headers=family.h("amma"))).json()
    assert len(proposed) == 1, [o["title"] for o in proposed]
    assert sum(r["result"]["duplicates_in_message"] for r in results) == 1


async def test_the_same_ask_worded_differently_in_the_pdf_is_proposed_once(family, database, gmail_on):
    import datetime as dt
    from email.message import EmailMessage

    from familyos.intake import mailbox
    from tests.test_extraction import _run_extraction, make_pdf
    from tests.test_gmail import FakeGoogle, _connect
    due = (dt.date.today() + dt.timedelta(days=10)).strftime("%A, %-d %B %Y")
    msg = EmailMessage()
    msg["From"] = "Airtel <ebill@airtel.com>"
    msg["To"] = "amma@gmail.com"
    msg["Subject"] = "Bill for your Airtel Black account"
    msg["Message-ID"] = "<bill@airtel.com>"
    msg["Authentication-Results"] = "mx.google.com; dkim=pass header.d=airtel.com; dmarc=pass"
    msg.set_content(f"Total amount payable Rs 1,940.98. Pay your bill by {due}.")
    msg.add_attachment(make_pdf([f"Monthly statement. Amount payable Rs 1,940.98 by {due}."]),
                       maintype="application", subtype="pdf", filename="statement.pdf")
    fake = FakeGoogle(messages={"m1": msg.as_bytes()})
    account = await _connect(family, fake)
    await mailbox.poll(account["id"], transport=fake)
    ids = [r["id"] for r in await database.fetch("SELECT id::text FROM input_artifacts ORDER BY parent_id NULLS FIRST")]
    [await _run_extraction(database, i) for i in ids]
    proposed = (await family.client.get("/v1/obligations?status=proposed", headers=family.h("amma"))).json()
    assert len(proposed) == 1, [(o["action"], o["due_date"], o["title"]) for o in proposed]


def test_an_event_still_running_the_day_after_sending_is_a_calendar_entry_not_a_record():
    """Half days from the 8th to the 16th, sent on the 7th: started, not over."""
    import datetime as dt

    from familyos.extraction.obligations import ProposedObligation, category_for_filter, for_category
    sent = dt.date(2026, 10, 7)
    running = ProposedObligation(0, "calendar", "note", "Half working days", dt.date(2026, 10, 8), dt.date(2026, 10, 16), "8:30 a.m. to 12:30 p.m.", False)
    over = ProposedObligation(1, "calendar", "note", "Sports day", dt.date(2026, 10, 8), None, None, False)
    kept = for_category([running, over], "unknown", sent)
    assert [o.title for o in kept.kept] == ["Half working days"] and kept.recorded == 1
    # A notice a parent tagged with a child is a school notice, whatever its sender looked like.
    assert category_for_filter("unknown", tagged_with_child=True) == "school"
    assert category_for_filter("unknown", tagged_with_child=False) == "unknown"
    assert category_for_filter("promo", tagged_with_child=True) == "promo"
    assert category_for_filter("medical", tagged_with_child=True) == "medical"
    assert [o.title for o in for_category([over], "school", sent).kept] == ["Sports day"]


def test_money_already_gone_is_never_something_to_pay():
    import datetime as dt

    from familyos.extraction.claims import Amount, Claim
    from familyos.extraction.obligations import propose
    paid = Claim(kind="payment", title="Paid \u20b91,940.98 to Bharti Airtel via UPI", date=dt.date(2026, 10, 8),
                 amount=Amount(value=1940.98, currency="INR"), quote="Rs.1940.98 is debited from your account", location={"page": 1, "start": 0, "end": 5, "match": "exact"}, confidence=0.9)
    owed = Claim(kind="payment", title="Term 2 fee", amount=Amount(value=4000, currency="INR"), quote="The fee is Rs 4,000", location={"page": 1, "start": 0, "end": 5, "match": "exact"}, confidence=0.9)
    assert [o.title for o in propose([paid, owed])] == ["Term 2 fee"]
