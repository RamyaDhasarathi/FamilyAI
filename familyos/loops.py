"""Closing a loop from evidence: a receipt is the proof that a bill was paid.

Until now nothing marked a notice handled except a person. The household's
mail carries the proof already -- "payment received", "thank you for your
payment", a transaction id -- and when that receipt names the same biller
for the same amount around the bill's due date, the bill is done. It is
marked handled with the receipt as the reason, its reminders stop, whoever
was handed it is told, and the count of things needing someone falls
without anybody opening the app.

The match is deliberately narrow, because a wrong "handled" hides a real
bill: the same currency and amount (to a rupee, or one per cent), the same
biller by sending domain or by a shared significant word, and a receipt
dated in the window a payment for that bill could fall in. One receipt may
close several obligations of one notice (the PDF and the mail that carried
it); it never closes a bill from a different biller because the amount
happened to agree.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid

from familyos import audit, categories
from familyos.inbox import HEADLINE

logger = logging.getLogger(__name__)

RECEIPT_WORDS = re.compile(
    r"\b(paid|payment (?:received|successful|successfully|confirm\w*|complete\w*|done)|receipt|"
    r"thank you for (?:your |the )?payment|transaction (?:successful|id|reference)|amount received|"
    r"successfully (?:paid|made)|has been (?:paid|received)|payment of)\b", re.I)
STOP = frozenset({"payment", "pay", "bill", "fee", "fees", "monthly", "statement", "subscription", "renewal", "charge",
                  "charges", "receipt", "invoice", "account", "your", "the", "for", "of", "and", "to", "due", "amount",
                  "total", "plan", "order", "with", "this", "from", "paid", "received", "thank", "you", "successful",
                  "reminder", "notice", "mail", "email", "noreply", "info", "care", "team", "ebill", "bills"})
BEFORE_DUE = dt.timedelta(days=45)      # a bill may be paid this long before it is due
AFTER_DUE = dt.timedelta(days=21)       # or this long after
UNDATED = dt.timedelta(days=60)         # a bill with no date: a receipt within this long of its arrival

_OPEN_BILLS = f"""
SELECT o.id, o.title, o.due_date, o.artifact_id, cl.amount, cl.currency,
       a.id AS top_id, a.source AS top_source, a.received_at, a.assigned_to, a.assigned_by,
       {HEADLINE} AS headline
FROM obligations o
JOIN claims cl ON cl.id = o.claim_id
JOIN input_artifacts own ON own.id = o.artifact_id
JOIN input_artifacts a ON a.id = COALESCE(own.parent_id, own.id)
WHERE o.household_id = $1 AND o.action = 'pay' AND o.superseded_at IS NULL AND o.status <> 'dismissed'
  AND a.handled_at IS NULL AND cl.amount IS NOT NULL AND a.id <> $2
"""


def words_of(*texts: str | None) -> set[str]:
    out: set[str] = set()
    for t in texts:
        for w in re.findall(r"[a-z0-9]+", (t or "").lower()):
            if len(w) >= 4 and w not in STOP and not w.isdigit():
                out.add(w)
    return out


def receipt_amounts(claims, *, subject: str | None, transactional: bool) -> list[tuple[float, str | None, dt.date | None]]:
    """The amounts a notice says were paid: claims whose own words say so,
    or, from a shop or a biller, the largest amount the notice carries."""
    said = []
    for c in claims:
        amount = getattr(c, "amount", None)
        if amount is None or not amount.value:
            continue
        if RECEIPT_WORDS.search(f"{c.title} {c.quote}"):
            said.append((float(amount.value), amount.currency, c.date))
    if not said and transactional and RECEIPT_WORDS.search(subject or ""):
        best = max((c for c in claims if getattr(c, "amount", None) and c.amount.value), key=lambda c: c.amount.value, default=None)
        if best is not None:
            said.append((float(best.amount.value), best.amount.currency, best.date))
    seen, out = set(), []
    for a in said:
        key = (round(a[0], 2), (a[1] or "").upper())
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def _close(amount: float, other: float) -> bool:
    return abs(amount - other) <= max(1.0, 0.01 * max(amount, other))


def _biller_matches(receipt_domain: str | None, receipt_words: set[str], bill: dict) -> bool:
    bill_domain = categories.sender_domain(bill["top_source"])
    if receipt_domain and bill_domain and (receipt_domain == bill_domain or receipt_domain.endswith("." + bill_domain)
                                           or bill_domain.endswith("." + receipt_domain)):
        return True
    src = bill["top_source"] or {}
    return bool(receipt_words & words_of(bill["title"], bill["headline"], src.get("from"), src.get("subject")))


def _in_window(receipt_on: dt.date | None, bill: dict) -> bool:
    if receipt_on is None:
        return True
    due = bill["due_date"]
    if due is None:
        arrived = bill["received_at"].date() if bill["received_at"] else None
        return arrived is None or 0 <= (receipt_on - arrived).days <= UNDATED.days
    return due - BEFORE_DUE <= receipt_on <= due + AFTER_DUE


def _money(amount: float, currency: str | None) -> str:
    sym = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}.get((currency or "").upper())
    text = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"{sym}{text}" if sym else f"{currency or ''} {text}".strip()


async def close_from_receipt(conn, household_id: uuid.UUID, artifact: dict, claims, *, sent_on: dt.date | None,
                             source: dict | None, category: str) -> list[dict]:
    """Bills this notice proves paid. Marks their notices handled inside the
    caller's transaction and returns what to tell people, which the caller
    sends after the commit."""
    source = source or {}
    amounts = receipt_amounts(claims, subject=source.get("subject"), transactional=category in categories.RECORDS_THE_PAST)
    if not amounts:
        return []
    top_id = artifact.get("parent_id") or artifact["id"]
    receipt_domain = categories.sender_domain(source)
    receipt_words = words_of(source.get("from"), source.get("subject"), *[getattr(c, "title", "") for c in claims])
    bills = [dict(r) for r in await conn.fetch(_OPEN_BILLS, household_id, top_id)]
    closed: list[dict] = []
    done: set[uuid.UUID] = set()
    for amount, currency, on in amounts:
        on = on or sent_on
        for bill in bills:
            if bill["top_id"] in done:
                continue
            if (bill["currency"] or "").upper() != (currency or "").upper() or not _close(amount, float(bill["amount"])):
                continue
            if not _biller_matches(receipt_domain, receipt_words, bill) or not _in_window(on, bill):
                continue
            from familyos.ledger import merchant_of
            who = (source.get("from") or "").split("<")[0].strip().strip('"')
            if not who or "@" in who:
                who = merchant_of(source) if receipt_domain else "the biller"
            note = f"paid — {_money(amount, currency)} receipt from {who}" + (f" on {on.isoformat()}" if on else "")
            await conn.execute("UPDATE input_artifacts SET handled_at = NOW(), handled_by = NULL, handled_note = $2 "
                               "WHERE id = $1 AND handled_at IS NULL", bill["top_id"], note[:500])
            cancelled = await conn.fetch(
                "UPDATE reminders r SET status = 'cancelled' FROM obligations o, input_artifacts a "
                "WHERE o.id = r.obligation_id AND a.id = o.artifact_id AND COALESCE(a.parent_id, a.id) = $1 "
                "AND r.status = 'pending' RETURNING r.id", bill["top_id"])
            from familyos.inbox import _calendar_follows
            await _calendar_follows(conn, household_id, bill["top_id"])
            await audit.record(household_id, "artifact.handled", actor_kind="system", target_type="artifact",
                               target_id=bill["top_id"],
                               detail={"by": "receipt", "receipt_artifact_id": str(top_id), "obligation_id": str(bill["id"]),
                                       "amount": amount, "currency": currency, "reminders_cancelled": len(cancelled)}, conn=conn)
            done.add(bill["top_id"])
            closed.append({"artifact_id": bill["top_id"], "headline": bill["headline"], "note": note,
                           "tell": [m for m in {bill["assigned_to"], bill["assigned_by"]} if m]})
            logger.info("loop closed: %s paid by receipt %s", bill["top_id"], top_id)
    return closed


async def tell(closed: list[dict]) -> None:
    """After the commit: whoever held the bill hears it is paid."""
    from familyos import notify
    for c in closed:
        for member_id in c["tell"]:
            try:
                await notify.member(member_id, f"Paid: {c['headline']}",
                                    f"A receipt arrived that settles a notice you were handling: {c['headline']}\n\n"
                                    f"“{c['note']}”\n\nNothing more to do on it.")
            except Exception:  # noqa: BLE001 - the loop is closed; the telling is best effort
                logger.warning("could not tell %s about a paid bill", member_id, exc_info=True)
