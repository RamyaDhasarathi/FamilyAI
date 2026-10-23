"""The lines of a receipt, read deterministically.

A grocery receipt asks the family for nothing, so the extractor rightly
proposes nothing from it. But its lines are the one place the household's
*rhythm* is written down: eggs every nine days, paneer twice a month, the
glue gun once. Reading those lines is not a judgement call, so no model is
involved: three patterns cover the receipts a family actually gets --

    1 x Fresh Eggs White eggs ₹106.00        (Instamart, Blinkit, Zepto)
    Chicken Popcorn - Large x1 / ₹268.57     (Swiggy: item, then its price)
    * Jockey NB01 Boys ... Brief             (Amazon: a list, no prices)

-- and anything that does not match is simply not an item. Fees, taxes,
discounts and totals are named and skipped.
"""
from __future__ import annotations

import logging
import re
import uuid

from familyos import categories
from familyos.db import pool

logger = logging.getLogger(__name__)

CATEGORIES = frozenset({"food", "shopping"})
MAX_ITEMS = 60

_MONEY = r"(?:₹|Rs\.?\s?|INR\s?)(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)"
# "1 x Indian Tomato (Thakkali) ₹24.00"
_QTY_X_ITEM = re.compile(r"^\s*(?P<qty>\d{1,3})\s*[x×]\s*(?P<item>.+?)\s*" + _MONEY + r"\s*$", re.I)
# "Chicken Popcorn - Large x1"  (price on the next line)
_ITEM_X_QTY = re.compile(r"^\s*(?P<item>.+?)\s*[x×]\s*(?P<qty>\d{1,3})\s*$", re.I)
_PRICE_LINE = re.compile(r"^\s*-?\s*" + _MONEY + r"\s*$", re.I)
# "* Jockey NB01 Boys Super Combed Cotton ..."
_BULLET = re.compile(r"^\s*[*•]\s+(?P<item>.{4,120})$")

_NOT_AN_ITEM = re.compile(r"\b(total|subtotal|sub-total|fee|fees|tax|taxes|gst|igst|cgst|sgst|discount|coupon|saved|savings|"
                          r"delivery|packaging|platform|handling|tip|round ?off|paid|payment|bill|charges?|offer|"
                          r"membership|convenience|surcharge)\b", re.I)


def item_key(item: str) -> str:
    """The pattern key: the item's words, lower-cased, without quantities,
    weights and packaging, so "Amul Fresh Paneer 200 g" and "Amul Fresh
    Paneer (200g)" are the same thing bought twice."""
    s = item.casefold()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b\d+(\.\d+)?\s*(g|gm|gms|kg|ml|l|ltr|litre|liters?|pcs?|pieces?|pack|packs|nos?|units?|x)\b", " ", s)
    s = re.sub(r"[^a-z0-9ऀ-ൿ ]+", " ", s)
    return " ".join(s.split())[:80]


def parse_items(text: str) -> list[dict]:
    """Line items from a receipt's text. Each: item, quantity, amount (or
    None), currency. Never a fee, a total or a discount."""
    out: list[dict] = []
    lines = [ln.strip() for ln in (text or "").splitlines()]
    i = 0
    while i < len(lines) and len(out) < MAX_ITEMS:
        ln = lines[i]
        m = _QTY_X_ITEM.match(ln)
        if m and not _NOT_AN_ITEM.search(m.group("item")):
            out.append({"item": m.group("item").strip(" -:"), "quantity": float(m.group("qty")),
                        "amount": float(m.group("amount").replace(",", "")), "currency": "INR"})
            i += 1
            continue
        m = _ITEM_X_QTY.match(ln)
        if m and not _NOT_AN_ITEM.search(m.group("item")):
            # The price sits on the next non-empty line; an HTML table leaves blanks between.
            j = i + 1
            while j < len(lines) and j <= i + 4 and not lines[j]:
                j += 1
            p = _PRICE_LINE.match(lines[j]) if j < len(lines) else None
            if p:
                out.append({"item": m.group("item").strip(" -:"), "quantity": float(m.group("qty")),
                            "amount": float(p.group("amount").replace(",", "")), "currency": "INR"})
                i = j + 1
                continue
        m = _BULLET.match(ln)
        if m and not _NOT_AN_ITEM.search(m.group("item")) and "http" not in m.group("item"):
            out.append({"item": m.group("item").strip(), "quantity": 1.0, "amount": None, "currency": None})
        i += 1
    return out


async def record(household_id: uuid.UUID, artifact_id: uuid.UUID, text: str) -> int:
    """Keep the receipt's lines beside the artifact, replacing an earlier
    read's. Only for a message in a food or shopping category; the lines of
    a bank statement are not a shopping rhythm."""
    from familyos import ledger
    async with pool().acquire() as conn, conn.transaction():
        a = await conn.fetchrow(
            "SELECT a.id, a.parent_id, COALESCE(p.channel, a.channel) AS channel, COALESCE(p.source, a.source) AS source, "
            "COALESCE(p.received_at, a.received_at) AS received_at FROM input_artifacts a "
            "LEFT JOIN input_artifacts p ON p.id = a.parent_id WHERE a.id = $1 AND a.household_id = $2",
            artifact_id, household_id)
        if a is None:
            return 0
        category = categories.category_of(a["channel"], a["source"])
        await conn.execute("DELETE FROM receipt_items WHERE artifact_id = $1", artifact_id)
        if category not in CATEGORIES:
            return 0
        found = parse_items(text)
        if not found:
            return 0
        merchant = ledger.merchant_of(a["source"])
        bought_on = ledger._sent_date(a["source"]) or a["received_at"].date()
        await conn.executemany(
            "INSERT INTO receipt_items (id, household_id, artifact_id, merchant, item, item_key, quantity, amount, "
            "currency, bought_on) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            [(uuid.uuid4(), household_id, artifact_id, merchant, it["item"][:200], item_key(it["item"]),
              it["quantity"], it["amount"], it["currency"], bought_on) for it in found if item_key(it["item"])])
        return len(found)
