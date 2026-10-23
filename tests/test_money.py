"""Money as far as mail can see it: the charge a person would point at,
what recurs, this month's spend, and when the plumber last came. All of it
derived from claims; nothing is stored, nothing is typed in."""
import datetime as dt
import uuid

from familyos import ledger
from familyos.db import pool
from tests.conftest import pdf

# ----------------------------------------------------------------------------
# pure
# ----------------------------------------------------------------------------

def _c(kind, title, amount, **kw):
    return {"kind": kind, "title": title, "amount": amount, "currency": "INR", "date": None, "end_date": None, **kw}


def test_the_charge_is_the_line_a_person_would_point_at():
    airtel = [_c("deadline", "Pay Airtel Black bill", 1940.98), _c("info", "Amount payable after the due date", 2176.98),
              _c("info", "ISD usage charge", 13.0), _c("info", "Xstream Play subscription charge", 83.9)]
    assert ledger.pick_charge(airtel)["amount"] == 1940.98
    apple = [_c("info", "IGST included in subscription charge", 29.75), _c("info", "Apple One monthly subscription charge", 195.0)]
    assert ledger.pick_charge(apple)["amount"] == 195.0
    x = [_c("info", "X Premium Plus price before discount", 2570.0), _c("info", "Premium Plus 50% discount", -1285.0),
         _c("deadline", "X Premium Plus invoice payment due", 1285.0)]
    assert ledger.pick_charge(x)["amount"] == 1285.0
    assert ledger.pick_charge([_c("info", "GST included", 3.81)]) is None


def test_cadence_from_gaps_or_from_what_the_receipt_says():
    d = dt.date(2026, 9, 9)
    assert ledger.cadence_of([d, d + dt.timedelta(days=30)], False) == "monthly"
    assert ledger.cadence_of([d, d + dt.timedelta(days=365)], False) == "yearly"
    assert ledger.cadence_of([d], True) == "stated"
    assert ledger.cadence_of([d], False) is None
    assert ledger.cadence_of([d, d + dt.timedelta(days=3), d + dt.timedelta(days=11)], False) is None


def test_merchants_are_named_as_a_family_would():
    assert ledger.merchant_of({"from": "no_reply@email.apple.com"}) == "Apple"
    assert ledger.merchant_of({"from": "receipts@stripe.com", "subject": "Your receipt from X #2446-6818"}) == "X"
    assert ledger.merchant_of({"from": "billing@somecorp.example"}) == "Somecorp"


def test_recurring_next_date_prefers_the_stated_period_end():
    today = dt.date(2026, 10, 6)
    charges = [
        {"merchant": "Anthropic", "currency": "SGD", "category": "subscriptions", "amount": 190.18,
         "date": dt.date(2026, 9, 18), "says_recurring": True, "period_end": dt.date(2026, 10, 18), "artifact_id": uuid.uuid4()},
        {"merchant": "Apple", "currency": "INR", "category": "subscriptions", "amount": 195.0,
         "date": dt.date(2026, 9, 9), "says_recurring": True, "period_end": None, "artifact_id": uuid.uuid4()},
        {"merchant": "KFC", "currency": "INR", "category": "food", "amount": 571.0,
         "date": dt.date(2026, 10, 3), "says_recurring": False, "period_end": None, "artifact_id": uuid.uuid4()},
    ]
    rows = {r["merchant"]: r for r in ledger.recurring(charges, today)}
    assert rows["Anthropic"]["next_date"] == dt.date(2026, 10, 18)
    assert rows["Apple"]["next_date"] == dt.date(2026, 10, 9) and rows["Apple"]["cadence"] == "stated"
    assert "KFC" not in rows


def test_a_bill_is_money_expected_not_money_gone_and_one_membership_does_not_make_dinner_recurring():
    today = dt.date(2026, 10, 6)
    a = uuid.uuid4()
    base = {"currency": "INR", "period_end": None, "artifact_id": a}
    charges = [
        {**base, "merchant": "Airtel", "category": "bills", "amount": 1925.64, "date": dt.date(2026, 9, 6), "says_recurring": True},
        {**base, "merchant": "Airtel", "category": "bills", "amount": 1940.98, "date": dt.date(2026, 10, 6), "says_recurring": True,
         "upcoming": True, "due": dt.date(2026, 10, 16)},
    ] + [{**base, "merchant": "Swiggy", "category": "food", "amount": 400.0, "date": dt.date(2026, 9, d), "says_recurring": False}
         for d in (6, 9, 12, 21, 27, 30)] + [
        {**base, "merchant": "Swiggy", "category": "food", "amount": 199.0, "date": dt.date(2026, 9, 6), "says_recurring": True,
         "period_end": dt.date(2026, 12, 6)},
    ]
    rows = {r["merchant"]: r for r in ledger.recurring(charges, today)}
    airtel = rows["Airtel"]
    assert airtel["last_date"] == dt.date(2026, 9, 6) and airtel["last_amount"] == 1925.64
    assert airtel["next_date"] == dt.date(2026, 10, 16) and airtel["next_amount"] == 1940.98
    assert "Swiggy" not in rows
    month = ledger.spend(charges, days=30, today=today)
    bills = next((x for x in month["by_category"] if x["category"] == "bills"), None)
    assert bills is not None and bills["total"] == 0.0 and bills["previous"] == 1925.64   # not spent yet; last month's is "previous"


def test_a_receipt_for_the_bill_settles_it_so_every_charge_lists_one_not_two():
    bill_id, receipt_id, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    base = {"currency": "INR", "period_end": None, "artifact_id": uuid.uuid4(), "says_recurring": True, "category": "bills", "merchant": "Airtel"}
    bill = {**base, "message_id": bill_id, "amount": 1940.98, "date": dt.date(2026, 10, 6), "upcoming": True, "due": dt.date(2026, 10, 16)}
    receipt = {**base, "message_id": receipt_id, "amount": 1940.98, "date": dt.date(2026, 10, 8), "upcoming": False, "due": None}
    last_month = {**base, "message_id": other, "amount": 1925.64, "date": dt.date(2026, 9, 6), "upcoming": False, "due": None}
    out = ledger.settle([receipt, bill, last_month])
    assert [c["message_id"] for c in out] == [receipt_id, other]
    assert out[0]["settles_message_id"] == bill_id and out[0]["settles_due"] == dt.date(2026, 10, 16)
    # Not settled: a different amount, a receipt before the bill came, or one long after its due date.
    for wrong in ({"amount": 1700.0}, {"date": dt.date(2026, 10, 5)}, {"date": dt.date(2026, 11, 5)}):
        out = ledger.settle([{**receipt, **wrong, "settles_message_id": None}, dict(bill)])
        assert len(out) == 2 and not out[0].get("settles_message_id")
    # A rupee's difference is the same bill; the receipt settles only one bill.
    out = ledger.settle([{**receipt, "amount": 1941.0, "settles_message_id": None}, dict(bill), {**bill, "message_id": uuid.uuid4()}])
    assert len(out) == 2
    # The settled bill no longer drives "next expected": the receipt's own cadence does.
    rows = {r["merchant"]: r for r in ledger.recurring(ledger.settle([{**receipt, "settles_message_id": None}, dict(bill), dict(last_month)]), dt.date(2026, 10, 9))}
    assert rows["Airtel"]["last_date"] == dt.date(2026, 10, 8) and rows["Airtel"]["next_date"] == dt.date(2026, 11, 8)


def test_spend_compares_with_the_window_before_and_names_what_moved_it():
    today = dt.date(2026, 10, 6)
    a = uuid.uuid4()
    def mk(merchant, cat, amount, day):
        return {"merchant": merchant, "category": cat, "currency": "INR", "amount": amount,
                                                 "date": day, "says_recurring": False, "period_end": None, "artifact_id": a}
    charges = [mk("KFC", "food", 700.0, dt.date(2026, 10, 3)), mk("KFC", "food", 650.0, dt.date(2026, 9, 27)),
               mk("Swiggy", "food", 400.0, dt.date(2026, 9, 30)),
               mk("Swiggy", "food", 450.0, dt.date(2026, 8, 20)), mk("Swiggy", "food", 380.0, dt.date(2026, 8, 28)),
               mk("Airtel", "bills", 1925.64, dt.date(2026, 9, 6))]
    month = ledger.spend(charges, days=30, today=today)
    food = next(x for x in month["by_category"] if x["category"] == "food")
    assert food["total"] == 1750.0 and food["previous"] == 830.0 and food["delta"] == 920.0 and food["driver"] == "KFC"


def test_services_group_by_what_was_done_and_remember_the_last_time():
    a = uuid.uuid4()
    charges = [
        {"merchant": "Urban Company", "currency": "INR", "category": "home", "amount": 319.0, "date": dt.date(2026, 9, 24),
         "title": "Plumber service invoice total", "headline": "Invoice for Customer Request", "artifact_id": a},
        {"merchant": "Urban Company", "currency": "INR", "category": "home", "amount": 319.0, "date": dt.date(2026, 10, 3),
         "title": "Plumber service invoice total", "headline": "Invoice", "artifact_id": a},
        {"merchant": "Urban Company", "currency": "INR", "category": "home", "amount": 4228.0, "date": dt.date(2026, 10, 4),
         "title": "AC Service and Repair", "headline": "Invoice", "artifact_id": a},
        {"merchant": "Swiggy", "currency": "INR", "category": "food", "amount": 300.0, "date": dt.date(2026, 10, 4),
         "title": "Invoice total", "headline": "Delivered", "artifact_id": a},
    ]
    out = ledger.services(charges)
    assert [e["kind"] for e in out["last_done"]] == ["air conditioning", "plumbing"]
    assert next(e for e in out["last_done"] if e["kind"] == "plumbing")["date"] == dt.date(2026, 10, 3)
    assert len(out["timeline"]) == 3


# ----------------------------------------------------------------------------
# through the database and the API
# ----------------------------------------------------------------------------

async def _receipt(family, who, sender, subject, claims, *, visibility="shared", sent=None):
    """A mail with claims already read out of it, the way the extractor leaves them."""
    r = await family.upload(who, pdf(subject), filename="r.pdf", visibility=visibility)
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    sent = sent or dt.date.today()
    await pool().execute(
        # The pool's jsonb codec takes the dict; a pre-dumped string would be stored as a JSON string.
        "UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", artifact_id,
        {"from": sender, "subject": subject, "date": sent.strftime("%a, %d %b %Y 09:00:00 +0530")})
    xid = uuid.uuid4()
    await pool().execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, model, prompt_version, parser_version, "
        "actionable, page_count) VALUES ($1, $2, $3, 'rules', NULL, 'p', 'p', FALSE, 1)",
        xid, uuid.UUID(family.household["id"]), artifact_id)
    for i, (kind, title, amount, currency, date) in enumerate(claims):
        await pool().execute(
            "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, amount, currency, date, "
            "quote, confidence) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $7, 0.9)",
            uuid.uuid4(), xid, uuid.UUID(family.household["id"]), artifact_id, i, kind, title, amount, currency, date)
    return artifact_id


async def test_the_overview_reads_charges_recurring_and_spend_from_claims(family, database):
    today = dt.date.today()
    await _receipt(family, "amma", "no_reply@email.apple.com", "Your receipt from Apple.",
                   [("info", "IGST included in subscription charge", 29.75, "INR", None),
                    ("info", "Apple One monthly subscription charge", 195.0, "INR", None)], sent=today - dt.timedelta(days=27))
    await _receipt(family, "amma", "ebill@airtel.com", "Bill for your Airtel Black account",
                   [("deadline", "Pay Airtel Black bill", 1940.98, "INR", today + dt.timedelta(days=10)),
                    ("info", "Amount payable after the due date", 2176.98, "INR", None)], sent=today)
    await _receipt(family, "amma", "noreply@swiggy.in", "Your Swiggy order was delivered",
                   [("info", "Order paid via bank", 459.0, "INR", None)], sent=today - dt.timedelta(days=2))
    # A private receipt of somebody else's is not in this member's picture.
    await _receipt(family, "appa", "receipts@stripe.com", "Your receipt from X #1",
                   [("deadline", "X Premium Plus invoice payment due", 1285.0, "INR", None)], visibility="private")
    r = await family.client.get("/v1/money?days=60", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    body = r.json()
    merchants = {c["merchant"]: c for c in body["charges"]}
    assert set(merchants) == {"Apple", "Airtel", "Swiggy"}
    assert merchants["Airtel"]["amount"] == 1940.98 and merchants["Airtel"]["upcoming"] is True
    assert merchants["Apple"]["amount"] == 195.0 and merchants["Apple"]["upcoming"] is False
    recurring = {x["merchant"]: x for x in body["recurring"]}
    assert recurring["Apple"]["cadence"] == "stated"
    assert recurring["Airtel"]["next_date"] == str(today + dt.timedelta(days=10)) and recurring["Airtel"]["last_date"] is None
    assert "Swiggy" not in recurring
    by_cat = {x["category"]: x["total"] for x in body["month"]["by_category"]}
    assert by_cat["food"] == 459.0 and by_cat["subscriptions"] == 195.0 and "bills" not in by_cat
    # Appa sees their own X receipt too.
    theirs = (await family.client.get("/v1/money", headers=family.h("appa"))).json()
    assert "X" in {c["merchant"] for c in theirs["charges"]}


def test_a_banks_alert_names_whoever_was_paid():
    from familyos.ledger import payee_of
    assert payee_of("UPI payment of Rs 1,940.98 to BHARTI AIRTEL LTD via UPI") == "Bharti Airtel Ltd"
    assert payee_of("Rs.449.00 debited from a/c XX1234 towards Swiggy on 08-10-26") == "Swiggy"
    assert payee_of("Amount debited: Rs 500") is None
    assert payee_of("paid to q12345@ybl via UPI") is None
    from familyos.ledger import merchant_of
    assert merchant_of({"from": "alerts@hdfcbank.bank.in"}) == "HDFC Bank"
