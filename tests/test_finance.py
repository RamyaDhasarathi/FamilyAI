"""Finance intelligence: a timeline of what goes out, budgets, return and warranty dates, goals, splits, and a limit per member."""
import datetime as dt
import uuid

from familyos import clock, finance
from familyos.identity import Principal

TODAY = clock.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_a_purchase_with_a_return_window_and_a_warranty_lands_on_the_timeline(family):
    r = await family.client.post("/v1/finance/warranties", headers=family.h("amma"),
                                 json={"title": "Water purifier", "merchant": "Croma", "return_days": 10, "warranty_months": 12})
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["return_by"] == (TODAY + dt.timedelta(days=10)).isoformat() and got["warranty_until"].startswith(str(TODAY.year + 1))
    tl = (await family.client.get("/v1/finance/timeline?days=30", headers=family.h("amma"))).json()
    titles = [i["title"] for d in tl["days"] for i in d["items"]]
    assert "Return window ends: Water purifier" in titles and not any("Warranty ends" in t for t in titles)     # a year away
    assert (await family.client.delete(f"/v1/finance/warranties/{got['id']}", headers=family.h("amma"))).status_code == 204
    assert (await family.client.get("/v1/finance/warranties", headers=family.h("amma"))).json() == []


async def test_month_end_dates_do_not_overflow(family):
    from familyos.finance import _add_months
    assert _add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28) and _add_months(dt.date(2027, 12, 15), 2) == dt.date(2028, 2, 15)


async def test_a_standing_payment_is_on_the_timeline_with_its_amount(family):
    r = await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "Rent", "payee": "Landlord", "amount": 25000, "currency": "INR", "day_of_month": 5})
    assert r.status_code in (200, 201), r.text
    tl = (await family.client.get("/v1/finance/timeline?days=40", headers=family.h("amma"))).json()
    rent = [i for d in tl["days"] for i in d["items"] if i["title"] == "Rent"]
    assert rent and rent[0]["amount"] == 25000 and tl["totals"]["INR"] >= 25000


async def test_only_a_guardian_sets_a_budget_and_progress_is_shown(family):
    ok = await family.client.put("/v1/finance/budgets", headers=family.h("amma"), json={"category": "food", "monthly_limit": 12000})
    assert ok.status_code == 200, ok.text
    assert (await family.client.put("/v1/finance/budgets", headers=family.h("paati"), json={"category": "food", "monthly_limit": 5})).status_code == 403
    rows = (await family.client.get("/v1/finance/budgets", headers=family.h("amma"))).json()
    assert rows == [{"category": "food", "currency": "INR", "monthly_limit": 12000.0, "spent": 0.0, "left": 12000.0, "percent": 0.0, "over": False}]


async def test_a_goal_fills_up_with_contributions(family):
    g = (await family.client.post("/v1/finance/goals", headers=family.h("amma"), json={"title": "Kodaikanal trip", "target_amount": 20000})).json()
    assert g["saved"] == 0 and g["percent"] == 0
    after = (await family.client.post(f"/v1/finance/goals/{g['id']}/contribute", headers=family.h("appa"), json={"amount": 5000, "note": "bonus"})).json()
    assert after["saved"] == 5000 and after["left"] == 15000 and after["percent"] == 25.0 and after["done"] is False
    done = (await family.client.post(f"/v1/finance/goals/{g['id']}/contribute", headers=family.h("amma"), json={"amount": 15000})).json()
    assert done["done"] is True


async def test_a_bill_split_says_who_owes_whom_and_settling_clears_it(family):
    body = {"title": "Electricity", "amount": 3000, "paid_by": family.amma["id"],
            "shares": [{"member_id": family.amma["id"], "percent": 50}, {"member_id": family.appa["id"], "percent": 50}]}
    s = (await family.client.post("/v1/finance/splits", headers=family.h("amma"), json=body)).json()
    assert s["owed"] == [{"name": family.appa["display_name"], "to": family.amma["display_name"], "amount": 1500.0}]
    done = (await family.client.post(f"/v1/finance/splits/{s['id']}/settle/{family.appa['id']}", headers=family.h("amma"))).json()
    assert done["owed"] == []
    bad = dict(body, shares=[{"member_id": family.amma["id"], "percent": 50}])
    assert (await family.client.post("/v1/finance/splits", headers=family.h("amma"), json=bad)).status_code in (400, 422)


async def test_a_child_cannot_be_in_a_split(family):
    body = {"title": "Fees", "amount": 100, "paid_by": family.amma["id"], "shares": [{"member_id": family.younger["id"], "percent": 100}]}
    assert (await family.client.post("/v1/finance/splits", headers=family.h("amma"), json=body)).status_code in (400, 422)


async def test_a_personal_purchase_limit_sits_inside_the_households(family, database, monkeypatch):
    from familyos import payments
    monkeypatch.setattr(payments, "provider", lambda: object())
    hid = uuid.UUID(family.household["id"])
    await database.execute("UPDATE households SET payments_enabled = TRUE, payment_limit = 5000, payment_month_limit = 50000, currency = 'INR' WHERE id = $1", hid)
    assert (await family.client.put(f"/v1/members/{family.paati['id']}/payment-limit", headers=family.h("amma"), json={"payment_limit": 1000})).status_code == 200
    assert (await family.client.put(f"/v1/members/{family.paati['id']}/payment-limit", headers=family.h("paati"), json={"payment_limit": 99999})).status_code == 403
    import decimal
    try:
        await payments.request(_p(family, "paati"), title="Gift", merchant_name="Shop", merchant_url=None, amount=decimal.Decimal("2000"), currency="INR")
        raised = None
    except Exception as exc:  # noqa: BLE001
        raised = str(exc)
    assert raised and "most you may ask to buy" in raised
    _ = finance


async def test_a_warranty_can_only_name_a_notice_the_caller_may_see_in_their_own_household(client, family):
    from tests.conftest import Family, pdf
    other = await Family(client).setup(name="Neighbours", guardian_email="n@example.com")
    foreign = (await other.upload("amma", pdf("foreign"), filename="f.pdf", visibility="shared")).json()["artifact"]["id"]
    hidden = (await family.upload("appa", pdf("hidden"), filename="h.pdf", visibility="private")).json()["artifact"]["id"]
    shown = (await family.upload("appa", pdf("shown"), filename="s.pdf", visibility="shared")).json()["artifact"]["id"]
    post = lambda aid: client.post("/v1/finance/warranties", headers=family.h("amma"), json={"title": "Kettle", "artifact_id": aid})  # noqa: E731
    assert (await post(foreign)).status_code == 404
    assert (await post(hidden)).status_code == 404              # another member's private notice
    ok = await post(shown)
    assert ok.status_code == 201 and ok.json()["artifact_id"] == shown
