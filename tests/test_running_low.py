"""The household's rhythm from receipts: the same item bought at a steady
gap is expected again, and said before it runs out -- as a link, never an
order."""
import datetime as dt
import uuid

from familyos import ledger
from familyos.db import pool
from familyos.extraction import items
from tests.conftest import pdf

INSTAMART = """Order Items
 1 x Indian Tomato (Thakkali) ₹24.00
 1 x Fresh Eggs White eggs ₹106.00
 2 x Amul Fresh Paneer ₹210.00
 Order Summary
 Item Bill ₹595.00
 Handling Fee ₹12.00
 Grand Total ₹607.00"""

SWIGGY = """BILL DETAILS
Chicken Zinger Burger - Classic x1
₹228.57
French Fries - Large x1
₹139.05
Restaurant Packaging
₹42.86
Platform fee with GST
₹17.98
Paid Via Bank
₹571"""

AMAZON = """Your package is out for delivery!
* Jockey NB01 Boys Super Combed Cotton Brief
* Kleenest Magic Eraser Sponge
https://www.amazon.in/progress-tracker"""


def test_the_three_receipt_shapes_are_read_and_fees_are_not_items():
    got = items.parse_items(INSTAMART)
    assert [(g["item"], g["quantity"], g["amount"]) for g in got] == [
        ("Indian Tomato (Thakkali)", 1.0, 24.0), ("Fresh Eggs White eggs", 1.0, 106.0), ("Amul Fresh Paneer", 2.0, 210.0)]
    got = items.parse_items(SWIGGY)
    assert [(g["item"], g["amount"]) for g in got] == [("Chicken Zinger Burger - Classic", 228.57), ("French Fries - Large", 139.05)]
    got = items.parse_items(AMAZON)
    assert [g["item"] for g in got] == ["Jockey NB01 Boys Super Combed Cotton Brief", "Kleenest Magic Eraser Sponge"]
    assert all(g["amount"] is None for g in got)


def test_the_item_key_makes_the_same_thing_the_same():
    assert items.item_key("Amul Fresh Paneer 200 g") == items.item_key("Amul Fresh Paneer (200g)") == "amul fresh paneer"
    assert items.item_key("Fresh Eggs White eggs 6 pcs") == "fresh eggs white eggs"


def test_a_steady_rhythm_is_expected_again_and_a_one_off_is_not():
    today = dt.date(2026, 10, 7)
    a = uuid.uuid4()
    def mk(key, day, item="Fresh Eggs White eggs"):
        return {"item_key": key, "item": item, "merchant": "Instamart",
                                                            "bought_on": day, "quantity": 1, "amount": 106.0, "currency": "INR", "artifact_id": a}
    rows = [mk("eggs", dt.date(2026, 9, 10)), mk("eggs", dt.date(2026, 9, 19)), mk("eggs", dt.date(2026, 9, 28)),
            mk("glue gun", dt.date(2026, 9, 20), "Fadman glue gun"),
            mk("paneer", dt.date(2026, 9, 1), "Amul Fresh Paneer"), mk("paneer", dt.date(2026, 10, 2), "Amul Fresh Paneer")]
    out = {r["item_key"]: r for r in ledger.standing(rows, today)}
    eggs = out["eggs"]
    assert eggs["every_days"] == 9 and eggs["expected_on"] == dt.date(2026, 10, 7) and eggs["status"] == "soon"
    assert eggs["reorder_url"].startswith("https://www.swiggy.com/instamart/search?") and "Fresh+Eggs" in eggs["reorder_url"]
    assert "glue gun" not in out                      # once is not a rhythm
    meals = [dict(mk("zinger", dt.date(2026, 9, 20) + dt.timedelta(days=7 * i), "Chicken Zinger Burger"), merchant="Swiggy") for i in range(3)]
    assert "zinger" not in {r["item_key"] for r in ledger.standing(meals, today)}   # a habit, not stock
    assert out["paneer"]["status"] == "fine"          # 31 days; next in November


async def test_a_receipt_read_records_its_lines_and_money_says_running_low(family, database):
    household_id = uuid.UUID(family.household["id"])

    async def receipt(day: dt.date, text: str):
        r = await family.upload("amma", pdf(text + str(day)), filename="r.txt", content_type="text/plain", visibility="shared")
        artifact_id = uuid.UUID(r.json()["artifact"]["id"])
        await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", artifact_id,
                             {"from": "noreply@instamart.in", "subject": "Your Instamart order was successfully delivered",
                              "date": day.strftime("%a, %d %b %Y 09:00:00 +0530")})
        assert await items.record(household_id, artifact_id, text) == 3
        return artifact_id

    today = dt.date.today()
    for back in (27, 18, 9):
        await receipt(today - dt.timedelta(days=back), INSTAMART)
    low = await ledger.running_low(_p(family))
    keys = {r["item_key"]: r for r in low}
    assert "fresh eggs white eggs" in keys and keys["fresh eggs white eggs"]["status"] in ("soon", "overdue")
    body = (await family.client.get("/v1/money?days=120", headers=family.h("amma"))).json()
    assert [x["item"] for x in body["running_low"]][:1] and body["running_low"][0]["every_days"] == 9
    # A bank statement's lines are not a rhythm: the function says no by category.
    r = await family.upload("amma", pdf("stmt"), filename="s.txt", content_type="text/plain", visibility="shared")
    sid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", sid,
                         {"from": "x@hdfcbank.bank.in", "subject": "Statement", "date": today.strftime("%a, %d %b %Y 09:00:00 +0530")})
    assert await items.record(household_id, sid, INSTAMART) == 0


def _p(family, who="amma"):
    from familyos.identity import Principal
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


def test_the_usual_is_anything_ordered_twice_dishes_included_most_often_first():
    d = dt.date(2026, 10, 1)
    rows = [
        {"item": "Chicken 65 Biryani", "item_key": "chicken 65 biryani", "merchant": "Swiggy", "bought_on": d - dt.timedelta(days=x), "amount": 380, "currency": "INR"}
        for x in (1, 8, 15, 22)
    ] + [
        {"item": "Fresh Eggs", "item_key": "fresh eggs", "merchant": "Instamart", "bought_on": d - dt.timedelta(days=x), "amount": 95, "currency": "INR"}
        for x in (2, 11)
    ] + [{"item": "Once", "item_key": "once", "merchant": "Instamart", "bought_on": d, "amount": 10, "currency": "INR"}]
    out = ledger.usual(rows)
    assert [u["item"] for u in out] == ["Chicken 65 Biryani", "Fresh Eggs"]
    assert out[0]["kind"] == "meal" and out[0]["times"] == 4 and out[0]["reorder_url"].startswith("https://www.swiggy.com/search?query=Chicken")
    assert out[1]["kind"] == "grocery" and out[1]["reorder_url"].startswith("https://www.swiggy.com/instamart/search?")
    # A dish is the usual, never "running low": the rhythm list still refuses restaurants.
    assert all(r["merchant"] != "Swiggy" for r in ledger.standing(rows, d))
