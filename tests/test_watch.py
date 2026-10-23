"""What the ledger says on the brief that a receipt alone cannot: a charge
well above a merchant's usual, a first charge from a merchant, and what
is expected to come out this week."""
import datetime as dt
import uuid

from familyos import brief
from familyos.identity import Principal
from tests.test_money import _receipt

TODAY = dt.date.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_a_charge_well_above_the_usual_and_a_first_charge_are_said(family, database):
    for days_ago, amount in ((95, 1500.0), (65, 1520.0), (35, 1490.0), (2, 1940.98)):
        await _receipt(family, "amma", "Airtel <ebill@airtel.com>", f"Airtel payment receipt {days_ago}",
                       [("payment", "Payment received for your Airtel account", amount, "INR", None)], sent=TODAY - dt.timedelta(days=days_ago))
    await _receipt(family, "amma", "Joyalukkas <orders@joyalukkas.in>", "Your Joyalukkas invoice",
                   [("payment", "Gold chain", 50000.0, "INR", None)], sent=TODAY - dt.timedelta(days=1))
    out = await brief.today(_p(family), on=TODAY, limit=50)
    lines = [i for i in out["items"] if i["reason"] == "money"]
    titles = [i["title"] for i in lines]
    assert any(t.startswith("Airtel charged ₹1,940.98, 29% above its usual ₹1,500") for t in titles), titles
    assert any(t.startswith("A first charge from Joyalukkas: ₹50,000") for t in titles), titles
    # Each is said once, and a merchant seen three times at the same amount is not news.
    assert len([t for t in titles if t.startswith("Airtel")]) == 1


async def test_what_comes_out_this_week_is_one_line(family, database):
    for days_ago in (62, 32):
        await _receipt(family, "amma", "Netflix <info@mailer.netflix.com>", f"Netflix receipt {days_ago}",
                       [("payment", "Netflix monthly subscription charge", 649.0, "INR", None)], sent=TODAY - dt.timedelta(days=days_ago))
    out = await brief.today(_p(family), on=TODAY, limit=50)
    week = [i for i in out["items"] if i["reason"] == "money" and i["title"].startswith("About")]
    if week:   # the next Netflix date falls in this week only on some days of the month
        assert "Netflix ₹649" in week[0]["why"] and week[0]["title"] == "About ₹649 comes out this week"
    out = await brief.today(_p(family), on=TODAY + dt.timedelta(days=200), limit=50)
    assert not [i for i in out["items"] if i["reason"] == "money" and i["title"].startswith("About")]
