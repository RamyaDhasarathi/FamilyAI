"""An invoice that states a warranty or a return period becomes a card to track it, and one that states neither does not."""
import datetime as dt
import uuid

from familyos import warranty_hints as wh

CROMA = [
    {"kind": "payment", "title": "Paid ₹41,407.00 to Infiniti Retail Limited (Croma) via HDFC UPI", "date": dt.date(2026, 9, 26), "quote": "HDFC UPI INR 41407.00"},
    {"kind": "info", "title": "Invoice details for purchase of Bosch WM FL 10KG WGA254ZPIN washing machine", "date": dt.date(2026, 9, 26), "quote": "ZPLU - BOSCH"},
    {"kind": "info", "title": "1-year Zip EW warranty for washing machine (₹3409.00)", "date": dt.date(2026, 9, 26), "quote": "ZEXW - 1YR ZIP EW"},
    {"kind": "info", "title": "Exchange policy for home delivery products: only for inherent defects found at demo", "date": None, "quote": "Products that require Home Delivery"},
]


def test_the_croma_invoice_reads_as_a_purchase_with_a_year_of_warranty_and_no_return_window():
    got = wh.read_invoice(CROMA)
    assert got["product"] == "Bosch WM FL 10KG WGA254ZPIN washing machine" and got["merchant"] == "Croma"
    assert got["purchased_on"] == dt.date(2026, 9, 26) and got["warranty_months"] == 12 and got["return_days"] is None


def test_periods_are_read_in_months_and_in_days_and_never_guessed():
    shoes = [{"kind": "info", "title": "Invoice details for purchase of Running shoes", "date": dt.date(2026, 10, 1), "quote": ""},
             {"kind": "info", "title": "Returns accepted within 30 days of delivery", "date": None, "quote": ""},
             {"kind": "info", "title": "Warranty of 6 months against manufacturing defects", "date": None, "quote": ""}]
    got = wh.read_invoice(shoes)
    assert got["return_days"] == 30 and got["warranty_months"] == 6
    assert wh.read_invoice([shoes[0], {"kind": "info", "title": "Warranty applies as per brand policy", "date": None, "quote": ""}]) is None     # a warranty with no length
    assert wh.read_invoice([{"kind": "info", "title": "Annual day on Friday", "date": dt.date(2026, 10, 17), "quote": ""}]) is None


async def _artifact_with(family, database, claims):
    from tests.conftest import pdf
    r = await family.upload("amma", pdf("croma"), filename="invoice.pdf", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    hid = uuid.UUID(family.household["id"])
    eid = await database.fetchval("SELECT id FROM extractions WHERE artifact_id = $1", aid)
    if eid is None:
        eid = uuid.uuid4()
        await database.execute("INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) VALUES ($1, $2, $3, 'rules', 'v1', 'v1', false, 1)", eid, hid, aid)
    await database.execute("DELETE FROM claims WHERE artifact_id = $1", aid)
    for i, c in enumerate(claims):
        await database.execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, date, quote, confidence) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0.9)",
                               uuid.uuid4(), eid, hid, aid, i, c["kind"] if c["kind"] in ("payment", "deadline") else "deadline", c["title"], c["date"] or dt.date(2026, 9, 26), c["quote"] or "q")
    return aid


async def test_the_card_tracks_it_when_confirmed_and_goes_when_dismissed(family, database):
    aid = await _artifact_with(family, database, CROMA)
    h = family.h("amma")
    cards = [c for c in (await family.client.get("/v1/decisions", headers=h)).json() if c["kind"] == "warranty"]
    assert len(cards) == 1 and cards[0]["id"] == f"warranty:{aid}" and "12 months of warranty" in cards[0]["happened"]
    track = next(a for a in cards[0]["actions"] if a["key"] == "track")
    made = await family.client.post(track["path"], headers=h, json=track["body"])
    assert made.status_code == 201, made.text
    w = (await family.client.get("/v1/finance/warranties", headers=h)).json()[0]
    assert w["title"].startswith("Bosch") and w["merchant"] == "Croma" and w["warranty_until"] == "2027-09-26"
    assert [c for c in (await family.client.get("/v1/decisions", headers=h)).json() if c["kind"] == "warranty"] == []


async def test_not_this_is_remembered(family, database):
    aid = await _artifact_with(family, database, CROMA)
    h = family.h("amma")
    (card,) = [c for c in (await family.client.get("/v1/decisions", headers=h)).json() if c["kind"] == "warranty"]
    no = next(a for a in card["actions"] if a["key"] == "dismiss")
    assert (await family.client.post(no["path"], headers=h)).status_code == 204
    assert [c for c in (await family.client.get("/v1/decisions", headers=h)).json() if c["kind"] == "warranty"] == []
    assert aid
