"""Money, as far as a mailbox can see it.

A receipt is not a bill, and the extractor has been taught not to propose one
as a task. But a month of receipts is still the only honest picture of what
the family pays for that email can give: Apple on the 9th, Airtel by the
16th, the gold scheme on the 25th, the plumber twice. This module reads that
picture out of the claims already extracted. Nothing is stored and nothing is
asked of the extractor; the view follows every re-read.

Three views, all derived:

- **Charges.** One per message. A receipt states its total five ways -- the
  subtotal, the tax, the amount after the due date, the price before the
  discount -- and the claim that is the charge is the one a person would
  point at: a payment or deadline first, then a line that says paid, total or
  received, never a line that says tax, discount or "after the due date".
- **Recurring.** The same merchant charging again. Monthly when the gaps say
  so, or when the receipt says so ("subscription", "renews", "plan",
  "scheme") and only one has arrived yet. The next date is the period's end
  when the receipt states one, else a month on. Expected amount is the last.
- **Services.** The home category as a timeline, and the last time each kind
  of thing was done -- the plumber, the AC, the washing machine -- which is
  what a family asks before calling anyone.

What email cannot see is said plainly elsewhere: UPI and card spend that
never produced a receipt lives in the bank statements, which are locked.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import re
import uuid
from collections import defaultdict

from familyos import categories
from familyos.artifacts import VISIBLE_TO_MEMBER
from familyos.db import pool
from familyos.identity import Principal

# Categories whose charges are the family's spend. Trading is not: a fund
# transfer to a broker is money moved, not money spent.
COMPARABLE_MIN = 5
# Merchants whose repeat orders are meals, not stock: never "running low".
NOT_A_RHYTHM = frozenset({"Swiggy", "Zomato", "KFC", "Domino's"})

MONEY = frozenset({"subscriptions", "bills", "shopping", "food", "home", "travel", "insurance"})

_SAYS_CHARGE = re.compile(r"\b(paid|payment|pay|total|charge[ds]?|received|renew(s|al|ed)?|amount|invoice|bill|"
                          r"instal?lment|premium|order)\b", re.I)
_NOT_THE_CHARGE = re.compile(r"\b(after the due date|late|before (the )?discount|excluding|excl\.?|subtotal|sub-total|"
                             r"tax|gst|igst|cgst|sgst|vat|discount|savings?|saved|credit|unused|refund|fee|"
                             r"allocation|usage|handling|delivery|platform|convenience|material)\b", re.I)
_SAYS_RECURRING = re.compile(r"\b(subscription|renew(s|al|ed)?|monthly|annual|yearly|plan|membership|period|"
                             r"instal?lment|scheme|premium|statement|bill)\b", re.I)

# What a home service was for, from the words on its invoice.
_SERVICE_KINDS: list[tuple[str, re.Pattern[str]]] = [
    ("plumbing", re.compile(r"plumb", re.I)),
    ("electrical", re.compile(r"electric", re.I)),
    ("air conditioning", re.compile(r"\bac\b|air[- ]?con", re.I)),
    ("washing machine", re.compile(r"washing", re.I)),
    ("refrigerator", re.compile(r"fridge|refrigerat", re.I)),
    ("furniture", re.compile(r"furniture|assembl", re.I)),
    ("cleaning", re.compile(r"clean|pest|sanit", re.I)),
    ("appliance service", re.compile(r"service order|installation|demo|repair", re.I)),
]

# Sender domains a family knows by another name.
_LABELS = {
    # the banks, by the addresses their statements and alerts come from
    "hdfcbank.bank.in": "HDFC Bank", "mailers.hdfcbank.bank.in": "HDFC Bank", "hdfcbank.net": "HDFC Bank",
    "icici.bank.in": "ICICI Bank", "icicibank.com": "ICICI Bank", "idfcfirst.bank.in": "IDFC First Bank",
    "idfcfirstbank.com": "IDFC First Bank", "axis.bank.in": "Axis Bank", "axisbank.com": "Axis Bank",
    "pnbmail.bank.in": "PNB", "pnb.co.in": "PNB", "sbi.co.in": "SBI", "kotak.com": "Kotak", "yesbank.in": "Yes Bank",
    "email.apple.com": "Apple", "apple.com": "Apple", "google.com": "Google", "mail.anthropic.com": "Anthropic",
    "lovable.dev": "Lovable", "venice.ai": "Venice", "airtel.com": "Airtel", "joyalukkas.com": "Joyalukkas",
    "urbancompany.com": "Urban Company", "invoices.croma.com": "Croma", "croma.com": "Croma",
    "bosch-home.com": "Bosch", "swiggy.in": "Swiggy", "instamart.in": "Instamart", "amazon.in": "Amazon",
    "zomato.com": "Zomato", "blinkit.com": "Blinkit", "jio.com": "Jio", "bsesdelhi.com": "BSES",
}
_RECEIPT_FROM = re.compile(r"receipt from ([^#\n]+?)(?:\s*#|\s*$)", re.I)


# ----------------------------------------------------------------------------
# pure: naming, picking, cadence
# ----------------------------------------------------------------------------

_PAYEE = re.compile(r"\b(?:to|towards|at)\s+(?:VPA\s+)?([A-Za-z][A-Za-z0-9 .&'-]{2,40}?)(?=\s+(?:via|using|through|on|from|for|ref|upi|txn|transaction)\b|[,.;()]|\s*$)", re.I)


def payee_of(text: str | None) -> str | None:
    """Whom a bank's alert says the money went to: "paid Rs 1,940.98 to
    BHARTI AIRTEL via UPI" names Airtel, not the bank."""
    m = _PAYEE.search(text or "")
    if not m:
        return None
    name = " ".join(m.group(1).split())
    if "@" in name or name.replace(" ", "").isdigit() or len(name) < 3:
        return None
    return name.title() if name.isupper() else name


def merchant_of(source: dict | None) -> str:
    """Who was paid, as the family would say it: the known name for the
    domain, the name a Stripe receipt subject carries, else the domain's
    own word with a capital."""
    source = source or {}
    domain = categories.sender_domain(source)
    if domain in _LABELS:
        return _LABELS[domain]
    m = _RECEIPT_FROM.search(source.get("subject") or "")
    if m:
        return m.group(1).strip()
    parts = domain.split(".")
    core = parts[-2] if len(parts) >= 2 else domain
    return core.capitalize() if core else "unknown"


def pick_charge(claims: list[dict]) -> dict | None:
    """The one claim that is the charge, among everything with an amount.

    A payment or deadline wins outright; failing that, a line that says
    paid/total/received. Lines about tax, discounts, subtotals or the amount
    after the due date are never it. Ties go to the largest amount, which is
    the grand total rather than one of its parts."""
    with_amount = [c for c in claims if c.get("amount") is not None and float(c["amount"]) > 0
                   and not _NOT_THE_CHARGE.search(c.get("title") or "")]
    if not with_amount:
        return None
    firsts = [c for c in with_amount if c.get("kind") in ("payment", "deadline")]
    if not firsts:
        firsts = [c for c in with_amount if _SAYS_CHARGE.search(c.get("title") or "")]
    pool_ = firsts or with_amount
    return max(pool_, key=lambda c: float(c["amount"]))


def cadence_of(dates: list[dt.date], says_recurring: bool) -> str | None:
    """monthly / yearly from the gaps when there are gaps; "stated" when the
    receipt itself says it recurs and only one has arrived; None otherwise."""
    days = sorted(set(dates))
    gaps = [(b - a).days for a, b in zip(days, days[1:], strict=False)]
    if gaps and all(25 <= g <= 35 for g in gaps):
        return "monthly"
    if gaps and all(355 <= g <= 375 for g in gaps):
        return "yearly"
    if gaps and all(5 <= g <= 9 for g in gaps):
        return "weekly"
    return "stated" if says_recurring else None


def service_kind(text: str) -> str | None:
    for kind, pattern in _SERVICE_KINDS:
        if pattern.search(text or ""):
            return kind
    return None


def _sent_date(source: dict | None) -> dt.date | None:
    try:
        parsed = email.utils.parsedate_to_datetime((source or {}).get("date") or "")
    except (TypeError, ValueError):
        return None
    return parsed.date() if parsed else None


# ----------------------------------------------------------------------------
# the views
# ----------------------------------------------------------------------------

_CLAIMS = f"""
SELECT a.id AS artifact_id, COALESCE(a.parent_id, a.id) AS message_id,
       COALESCE(p.channel, a.channel) AS channel, COALESCE(p.source, a.source) AS source,
       COALESCE(p.received_at, a.received_at) AS received_at,
       c.kind, c.title, c.amount, c.currency, c.date, c.end_date
FROM claims c
JOIN extractions x ON x.id = c.extraction_id AND x.superseded_at IS NULL
JOIN input_artifacts a ON a.id = c.artifact_id
LEFT JOIN input_artifacts p ON p.id = a.parent_id
WHERE {VISIBLE_TO_MEMBER}
  AND COALESCE(p.received_at, a.received_at) > NOW() - make_interval(days => $3)
ORDER BY COALESCE(p.received_at, a.received_at) DESC, c.ordinal
"""


async def charges(p: Principal, *, days: int = 90) -> list[dict]:
    """One charge per message the member can see, in the money categories."""
    from familyos import country
    home = (await country.locale(p.household_id))["currency"]
    rows = await pool().fetch(_CLAIMS, p.household_id, p.member_id, max(1, min(days, 400)))
    by_message: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for r in rows:
        by_message[r["message_id"]].append(dict(r))
    out = []
    for message_id, claims in by_message.items():
        head = claims[0]
        category = categories.category_of(head["channel"], head["source"])
        if category not in MONEY:
            continue
        charge = pick_charge(claims)
        if charge is None:
            continue
        subject = (head["source"] or {}).get("subject") or ""
        words = " | ".join([c["title"] or "" for c in claims] + [subject])
        periods = [c["end_date"] for c in claims if c["end_date"] and _SAYS_RECURRING.search(c["title"] or "")]
        sent = _sent_date(head["source"]) or head["received_at"].date()
        # A bill's due date and a renewal notice's date are ahead of the mail
        # that carries them: that is money expected, not money gone.
        upcoming = bool(charge["date"] and charge["date"] > sent)
        when = sent if upcoming else (charge["date"] or sent)
        out.append({
            "message_id": message_id, "artifact_id": charge["artifact_id"],
            # A bank's alert is about whoever was paid, not the bank.
            "merchant": (payee_of(charge["title"]) or payee_of(subject) if category == "banking" else None) or merchant_of(head["source"]),
            "category": category,
            "amount": float(charge["amount"]), "currency": charge["currency"] or home,
            "date": when, "title": charge["title"], "headline": subject or charge["title"],
            # Judged on this receipt's own words -- the charge line and the
            # subject -- so one membership mail does not make every food
            # order from the same merchant "recurring".
            # ...or the receipt states a billing period, which only a
            # subscription does.
            "says_recurring": bool(periods) or bool(_SAYS_RECURRING.search((charge["title"] or "") + " " + subject)),
            "period_end": max(periods) if periods else None,
            "upcoming": upcoming, "due": charge["date"] if upcoming else None,
            "words": words,
        })
    out.sort(key=lambda c: c["date"], reverse=True)
    return settle(out)


SETTLE_GRACE = dt.timedelta(days=15)   # a payment may land this long after the due date and still be that bill's


def settle(all_charges: list[dict]) -> list[dict]:
    """A bill and the receipt that paid it are one charge, not two. When a
    receipt from the same merchant, for the same amount (to a rupee or one
    per cent), is dated between the bill's arrival and a fortnight past its
    due date, the bill is settled: it leaves the list and the receipt says
    which bill it closed. The Airtel bill of 6 Oct and the "paid ₹1,940.98"
    of 8 Oct were two rows in Every charge until this (9 Oct 2026)."""
    paid = [c for c in all_charges if not c.get("upcoming")]
    settled: set = set()
    for bill in all_charges:
        if not bill.get("upcoming") or bill.get("due") is None:
            continue
        for receipt in paid:
            if receipt.get("settles_message_id") or receipt["merchant"] != bill["merchant"] or receipt["currency"] != bill["currency"]:
                continue
            if not _same_amount(receipt["amount"], bill["amount"]):
                continue
            if not bill["date"] <= receipt["date"] <= bill["due"] + SETTLE_GRACE:
                continue
            receipt["settles_message_id"] = bill["message_id"]
            receipt["settles_due"] = bill["due"]
            settled.add(bill["message_id"])
            break
    return [c for c in all_charges if c["message_id"] not in settled]


def _same_amount(a: float, b: float) -> bool:
    return abs(a - b) <= max(1.0, 0.01 * max(abs(a), abs(b)))


def recurring(all_charges: list[dict], today: dt.date | None = None) -> list[dict]:
    """Merchants that charge again, with what to expect next."""
    today = today or dt.date.today()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in all_charges:
        groups[(c["merchant"], c["currency"])].append(c)
    out = []
    for (merchant, currency), items in groups.items():
        items.sort(key=lambda c: c["date"])
        paid = [c for c in items if not c.get("upcoming")]
        expected = [c for c in items if c.get("upcoming")]
        # Recurring when the gaps say so, or when at least half the receipts
        # say so themselves. One membership mail among nine food orders is
        # neither.
        says = bool(items) and sum(1 for c in items if c["says_recurring"]) * 2 >= len(items)
        cadence = cadence_of([c["date"] for c in paid], says) if paid else ("stated" if says else None)
        if cadence is None:
            continue
        last = paid[-1] if paid else None
        stated_end = max((c["period_end"] for c in items if c["period_end"]), default=None)
        due = max((c["due"] for c in expected if c["due"]), default=None)
        if due and due >= today - dt.timedelta(days=3):
            next_date, next_amount = due, expected[-1]["amount"]
        elif stated_end and stated_end >= today - dt.timedelta(days=3):
            next_date, next_amount = stated_end, (last or expected[-1])["amount"]
        elif last is None:
            continue
        elif cadence == "yearly":
            next_date, next_amount = last["date"].replace(year=last["date"].year + 1), last["amount"]
        elif cadence == "weekly":
            next_date, next_amount = last["date"] + dt.timedelta(days=7), last["amount"]
        else:
            next_date, next_amount = _month_on(last["date"]), last["amount"]
        anchor = last or expected[-1]
        out.append({
            "merchant": merchant, "category": anchor["category"], "currency": currency,
            "cadence": cadence, "manage_url": manage_page(merchant),
            "last_amount": last["amount"] if last else None,
            "last_date": last["date"] if last else None,
            "next_date": next_date, "next_amount": next_amount, "times": len(paid),
            "total": round(sum(c["amount"] for c in paid), 2),
            "artifact_id": (expected[-1] if due else anchor)["artifact_id"],
        })
    out.sort(key=lambda r: (r["next_date"], r["merchant"]))
    return out


def _month_on(day: dt.date) -> dt.date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    last_of_month = (dt.date(year + (month == 12), (month % 12) + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(day.day, last_of_month))


def spend(all_charges: list[dict], *, days: int = 30, today: dt.date | None = None, home: str = "INR") -> dict:
    """Totals for the window, by category and by merchant, per currency, and
    the same window before it, so "₹1,800 more on food than last month" is a
    number and not a feeling. No conversion: S$ stays S$."""
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    before = since - dt.timedelta(days=days)
    window = [c for c in all_charges if since < c["date"] <= today and not c.get("upcoming")]
    prior = [c for c in all_charges if before < c["date"] <= since and not c.get("upcoming")]
    by_cat: dict[tuple[str, str], float] = defaultdict(float)
    prev_cat: dict[tuple[str, str], float] = defaultdict(float)
    by_merchant: dict[tuple[str, str], tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    prev_merchant: dict[tuple[str, str], float] = defaultdict(float)
    for c in window:
        by_cat[(c["category"], c["currency"])] += c["amount"]
        total, n = by_merchant[(c["merchant"], c["currency"])]
        by_merchant[(c["merchant"], c["currency"])] = (total + c["amount"], n + 1)
    for c in prior:
        prev_cat[(c["category"], c["currency"])] += c["amount"]
        prev_merchant[(c["merchant"], c["currency"])] += c["amount"]
    # Who drove each category's change: the merchant whose own change is largest, same sign.
    drivers: dict[tuple[str, str], str | None] = {}
    for (cat, cur), total in by_cat.items():
        change = total - prev_cat.get((cat, cur), 0.0)
        best, best_change = None, 0.0
        for (merchant, mcur), (mtotal, _) in by_merchant.items():
            if mcur != cur or not any(c["merchant"] == merchant and c["category"] == cat for c in window):
                continue
            mchange = mtotal - prev_merchant.get((merchant, mcur), 0.0)
            if (change >= 0 and mchange > best_change) or (change < 0 and mchange < best_change):
                best, best_change = merchant, mchange
        drivers[(cat, cur)] = best
    cats = []
    for k in set(by_cat) | set(prev_cat):
        total, previous = round(by_cat.get(k, 0.0), 2), round(prev_cat.get(k, 0.0), 2)
        cats.append({"category": k[0], "currency": k[1], "total": total, "previous": previous,
                     "delta": round(total - previous, 2), "driver": drivers.get(k)})
    return {
        "days": days, "charges": len(window), "previous_charges": len(prior),
        # A comparison is only worth saying when the window before has enough
        # receipts in it: a mailbox imported last week has no "last month".
        "comparable": len(prior) >= COMPARABLE_MIN,
        "by_category": sorted((c for c in cats if c["total"] or c["previous"]),
                              key=lambda r: (r["currency"] != home, -r["total"])),
        "by_merchant": sorted(({"merchant": k[0], "currency": k[1], "total": round(v[0], 2), "times": v[1],
                                "previous": round(prev_merchant.get(k, 0.0), 2)}
                               for k, v in by_merchant.items()),
                              key=lambda r: (r["currency"] != home, -r["total"])),
    }


# Where a subscription is managed. Public account pages, the same for every
# family; the family cancels there, never us.
MANAGE_PAGES = {
    "Apple": "https://account.apple.com/account/manage",
    "Google": "https://play.google.com/store/account/subscriptions",
    "X": "https://x.com/settings/premium",
    "Anthropic": "https://claude.ai/settings/billing",
    "Netflix": "https://www.netflix.com/cancelplan",
    "Spotify": "https://www.spotify.com/account/subscription/",
    "Lovable": "https://lovable.dev/settings",
    "Venice": "https://venice.ai/settings",
    "Swiggy": "https://www.swiggy.com/my-account",
}


def manage_page(merchant: str) -> str | None:
    return MANAGE_PAGES.get(merchant)


def services(all_charges: list[dict]) -> dict:
    """The home category as a timeline, and when each kind was last done."""
    rows = [c for c in all_charges if c["category"] == "home" and not c.get("upcoming")]
    timeline = []
    last_done: dict[str, dict] = {}
    for c in sorted(rows, key=lambda c: c["date"], reverse=True):
        words = c.get("words") or (c["title"] + " " + c["headline"])
        kind = service_kind(words) or "home service"
        entry = {"date": c["date"], "merchant": c["merchant"], "kind": kind, "what": _what(words, kind, c),
                 "amount": c["amount"], "currency": c["currency"], "artifact_id": c["artifact_id"]}
        timeline.append(entry)
        last_done.setdefault(kind, entry)
    return {"timeline": timeline,
            "last_done": sorted(last_done.values(), key=lambda e: e["date"], reverse=True)}


def _what(words: str, kind: str, charge: dict) -> str:
    """The line on the invoice that names the service, else the charge line."""
    pattern = next((pat for k, pat in _SERVICE_KINDS if k == kind), None)
    if pattern:
        for line in words.split(" | "):
            if pattern.search(line):
                return line.strip()[:80]
    return charge["title"]


# Where to reorder, as a public search on the merchant the family already uses.
_REORDER = {
    "Instamart": "https://www.swiggy.com/instamart/search?custom_back=true&query={q}",
    "Blinkit": "https://blinkit.com/s/?q={q}",
    "Zepto": "https://www.zeptonow.com/search?query={q}",
    "Amazon": "https://www.amazon.in/s?k={q}",
    "BigBasket": "https://www.bigbasket.com/ps/?q={q}",
    # A dish ordered again: the app's own search, which lands on the restaurant.
    "Swiggy": "https://www.swiggy.com/search?query={q}",
    "Zomato": "https://www.zomato.com/search?q={q}",
}


def reorder_url(merchant: str, item: str) -> str | None:
    from urllib.parse import quote_plus
    pattern = _REORDER.get(merchant)
    return pattern.format(q=quote_plus(item)) if pattern else None


def standing(rows: list[dict], today: dt.date | None = None, *, soon_days: int = 3) -> list[dict]:
    """The household's rhythm from receipt lines: an item bought at least
    twice, at a steady enough gap, is expected again at the last date plus
    the typical gap. "Running low" is expected within `soon_days`, or past.

    Pure. `rows` carry item_key, item, merchant, bought_on, quantity, amount,
    currency. No judgement about whether the family *wants* it again -- the
    nudge is a link, and ignoring it costs nothing."""
    import statistics
    today = today or dt.date.today()
    by_key: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[r["item_key"]].append(r)
    out = []
    for key, buys in by_key.items():
        # A restaurant order repeated is a habit, not a cupboard running low.
        if all(b["merchant"] in NOT_A_RHYTHM for b in buys):
            continue
        days = sorted({b["bought_on"] for b in buys})
        if len(days) < 2:
            continue
        gaps = [(b - a).days for a, b in zip(days, days[1:], strict=False) if (b - a).days > 0]
        if not gaps:
            continue
        every = int(round(statistics.median(gaps)))
        if every < 2 or every > 120 or max(gaps) > every * 3:
            continue
        last = days[-1]
        expected = last + dt.timedelta(days=every)
        status = "overdue" if expected < today else "soon" if expected <= today + dt.timedelta(days=soon_days) else "fine"
        latest = max(buys, key=lambda b: b["bought_on"])
        out.append({
            "item": latest["item"], "item_key": key, "merchant": latest["merchant"], "times": len(days),
            "every_days": every, "last_on": last, "expected_on": expected, "status": status,
            "last_amount": float(latest["amount"]) if latest.get("amount") is not None else None,
            "currency": latest.get("currency"), "reorder_url": reorder_url(latest["merchant"], latest["item"]),
            "artifact_id": latest.get("artifact_id"),
        })
    out.sort(key=lambda r: (r["status"] == "fine", r["expected_on"]))
    return out


_ITEMS = f"""
SELECT r.item, r.item_key, r.merchant, r.bought_on, r.quantity, r.amount, r.currency, r.artifact_id
FROM receipt_items r JOIN input_artifacts a ON a.id = r.artifact_id
WHERE {VISIBLE_TO_MEMBER} AND r.bought_on > CURRENT_DATE - make_interval(days => $3)
ORDER BY r.bought_on DESC
"""


async def running_low(p: Principal, *, days: int = 180) -> list[dict]:
    rows = [dict(r) for r in await pool().fetch(_ITEMS, p.household_id, p.member_id, max(30, min(days, 400)))]
    return [r for r in standing(rows) if r["status"] != "fine"]


def usual(rows: list[dict], *, limit: int = 12) -> list[dict]:
    """What the household orders again and again: anything on two or more
    receipts, most often first. The biryani every second Sunday as much as
    the eggs. Pure; no judgement about whether they want it again -- the
    link is to the shop's own search, and ignoring it costs nothing."""
    by_key: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[r["item_key"]].append(r)
    out = []
    for key, buys in by_key.items():
        days = sorted({b["bought_on"] for b in buys})
        if len(days) < 2:
            continue
        latest = max(buys, key=lambda b: b["bought_on"])
        out.append({
            "item": latest["item"], "item_key": key, "merchant": latest["merchant"], "times": len(days),
            "last_on": days[-1], "kind": "meal" if latest["merchant"] in NOT_A_RHYTHM else "grocery",
            "last_amount": float(latest["amount"]) if latest.get("amount") is not None else None,
            "currency": latest.get("currency"), "reorder_url": reorder_url(latest["merchant"], latest["item"]),
        })
    out.sort(key=lambda r: (-r["times"], r["last_on"]), reverse=False)
    out.sort(key=lambda r: (-r["times"], -r["last_on"].toordinal()))
    return out[:limit]


async def usual_orders(p: Principal, *, days: int = 90) -> list[dict]:
    rows = [dict(r) for r in await pool().fetch(_ITEMS, p.household_id, p.member_id, max(30, min(days, 400)))]
    return usual(rows)


async def overview(p: Principal, *, days: int = 90) -> dict:
    from familyos import country
    home = (await country.locale(p.household_id))["currency"]
    all_charges = await charges(p, days=days)
    return {"days": days, "charges": all_charges, "recurring": recurring(all_charges),
            "month": spend(all_charges, days=30, home=home), "services": services(all_charges),
            "running_low": await running_low(p), "usual": await usual_orders(p)}
