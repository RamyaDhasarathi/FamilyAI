"""Where a household lives, and what follows from it.

Three facts on the household -- country, time zone, home currency -- asked
once at founding and changed by a guardian. The country picks a profile
here: when the school year starts, which payment rails to look for, what
the money symbol is. India is the profile that exists in full; the UAE has
the facts a Dubai family needs on day one. What does not depend on country
is not here: consent, visibility, the audit, the walls on cards and
credentials, the reading itself.
"""
from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from familyos.db import pool

PROFILES: dict[str, dict] = {
    "IN": {"name": "India", "timezone": "Asia/Kolkata", "currency": "INR",
           # Indian schools promote in April or June.
           "school_year_months": (4, 5, 6, 7), "payment_rails": ("upi", "page")},
    "AE": {"name": "United Arab Emirates", "timezone": "Asia/Dubai", "currency": "AED",
           # September for most schools; Indian-curriculum schools in April.
           "school_year_months": (4, 8, 9, 10), "payment_rails": ("page", "card")},
}
DEFAULT = "IN"
SYMBOLS = {"INR": "₹", "USD": "$", "SGD": "S$", "GBP": "£", "EUR": "€", "AED": "AED "}


def profile(country: str | None) -> dict:
    return PROFILES.get((country or DEFAULT).upper(), PROFILES[DEFAULT])


def symbol(currency: str | None) -> str:
    code = (currency or "").upper()
    return SYMBOLS.get(code, (code + " ") if code else "")


def money(amount: float, currency: str | None) -> str:
    """₹1,940.98, AED 350, $43: the symbol the currency has, else its code."""
    text = f"{amount:,.2f}".rstrip("0").rstrip(".") if amount != int(amount) else f"{int(amount):,}"
    return f"{symbol(currency)}{text}"


def check(country: str | None, timezone: str | None, currency: str | None) -> tuple[str, str, str]:
    """The three facts, validated: a two-letter country, a zone the system
    knows, a three-letter currency. A country without a profile is kept as
    said; it gets the default profile until one is written."""
    c = (country or "").strip().upper()
    if len(c) != 2 or not c.isalpha():
        raise ValueError("country is a two-letter code, like IN or AE")
    tz = (timezone or "").strip()
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError("timezone must be a zone name, like Asia/Kolkata or Asia/Dubai") from None
    cur = (currency or "").strip().upper()
    if len(cur) != 3 or not cur.isalpha():
        raise ValueError("currency is a three-letter code, like INR or AED")
    return c, tz, cur


async def locale(household_id: uuid.UUID, conn=None) -> dict:
    """country, timezone, currency for a household."""
    row = await (conn or pool()).fetchrow("SELECT country, timezone, currency FROM households WHERE id = $1", household_id)
    if row is None:
        p = PROFILES[DEFAULT]
        return {"country": DEFAULT, "timezone": p["timezone"], "currency": p["currency"]}
    return dict(row)


async def set_locale(p, country: str, timezone: str, currency: str) -> dict:
    from familyos import audit
    from familyos.identity import NotAllowed
    if not p.is_guardian:
        raise NotAllowed("only a guardian can say where the household lives")
    c, tz, cur = check(country, timezone, currency)
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("UPDATE households SET country = $2, timezone = $3, currency = $4 WHERE id = $1 RETURNING *",
                                  p.household_id, c, tz, cur)
        await audit.record(p.household_id, "household.locale_set", actor_member_id=p.member_id, target_type="household",
                           target_id=p.household_id, detail={"country": c, "timezone": tz, "currency": cur}, conn=conn)
    return dict(row)


def describe() -> str:
    return "country: " + ", ".join(f"{k} ({v['name']})" for k, v in PROFILES.items()) + "; a household's time zone and home currency come from it"
