"""A bill that mentions a warranty becomes a suggestion to track it.

A shop invoice says what was bought, when, from whom, and often how long it is under warranty or how many days it can be returned.
The reader files those lines as plain information, so nothing ever warned the family when the window closed. This reads the
claims already made from an invoice (no model, no second reading) and, when it finds a product and a warranty or return period, offers a card
with the entry filled in: "Track the warranty on the Bosch washing machine", which the person confirms. Nothing is added by itself, and a
period the invoice does not state is never guessed; an invoice that names a warranty but no length gets no card.
"""
from __future__ import annotations

import datetime as dt
import re

from familyos.artifacts import VISIBLE_TO_MEMBER
from familyos.db import pool
from familyos.identity import Principal

DAYS = 60
_WARRANTY = re.compile(r"warrant", re.I)
_YEARS = re.compile(r"\b(\d{1,2})[\s-]*(?:year|yr)s?\b", re.I)
_MONTHS = re.compile(r"\b(\d{1,3})[\s-]*months?\b", re.I)
_RETURN_DAYS = re.compile(r"\b(\d{1,3})[\s-]*days?\b.{0,40}\b(?:return|exchange|replacement)|\b(?:return|exchange|replacement)\w*.{0,40}?\b(\d{1,3})[\s-]*days?\b", re.I)
_PRODUCT = re.compile(r"(?:purchase|bought|order) of (.{3,120})$", re.I)
_PAID_TO = re.compile(r"\bto (.+?)(?: \(([^)]+)\))?(?: via\b.*)?$", re.I)


def read_invoice(claims: list[dict]) -> dict | None:
    """What the claims from one document say about a purchase, or None when it is not one with a stated warranty or return period."""
    text = [" ".join(filter(None, [c.get("title"), c.get("quote")])) for c in claims]
    warranty_lines = [t for t in text if _WARRANTY.search(t)]
    months = return_days = None
    for c in claims:
        title = c.get("title") or ""
        if _WARRANTY.search(title) and months is None:
            if (m := _YEARS.search(title)):
                months = int(m.group(1)) * 12
            elif (m := _MONTHS.search(title)):
                months = int(m.group(1))
        if return_days is None and (m := _RETURN_DAYS.search(title)):
            return_days = int(m.group(1) or m.group(2))
    if not months and not return_days:
        return None
    product = next((m.group(1).strip() for c in claims if (m := _PRODUCT.search((c.get("title") or "").strip())) ), None)
    merchant = None
    for c in claims:
        if c.get("kind") == "payment" and (m := _PAID_TO.search(c.get("title") or "")):
            merchant = (m.group(2) or m.group(1)).strip()
            break
    if not product:
        return None
    dates = [c["date"] for c in claims if c.get("date") and "invoice" in (c.get("title") or "").lower()] or [c["date"] for c in claims if c.get("date")]
    purchased = min(dates) if dates else None
    return {"product": product[:120], "merchant": merchant[:120] if merchant else None, "purchased_on": purchased,
            "warranty_months": months if months and months <= 120 else None, "return_days": return_days if return_days and return_days <= 365 else None,
            "said": warranty_lines[0][:160] if warranty_lines else None}


_WARRANTY_TITLE = re.compile(r"(warrant|return|exchange|replacement)", re.I)


async def waiting(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        f"SELECT a.id, a.received_at FROM input_artifacts a WHERE {VISIBLE_TO_MEMBER} AND a.received_at > NOW() - make_interval(days => $3) AND a.handled_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM warranties w WHERE w.artifact_id = a.id) "
        "AND NOT EXISTS (SELECT 1 FROM suggestion_dismissals d WHERE d.household_id = a.household_id AND d.source_key = 'warranty:' || a.id::text) "
        "AND EXISTS (SELECT 1 FROM claims c WHERE c.artifact_id = a.id) ORDER BY a.received_at DESC", p.household_id, p.member_id, DAYS)
    out = []
    candidates = 0
    for r in rows:
        claims = [dict(c) for c in await pool().fetch("SELECT kind, title, date, quote FROM claims WHERE artifact_id = $1 ORDER BY ordinal", r["id"])]
        # Titles are sealed, so "a claim whose title says warranty, return, exchange or replacement" is checked here, after they are opened
        # (it was a regex in the query); the first 20 such notices are kept, as before.
        if not any(_WARRANTY_TITLE.search(c["title"] or "") for c in claims):
            continue
        candidates += 1
        found = read_invoice(claims)
        if found:
            out.append({"artifact_id": r["id"], **found})
        if candidates >= 20:
            break
    return out


_ = dt
