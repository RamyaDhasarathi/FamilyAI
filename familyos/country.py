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


import re  # noqa: E402

_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def check_language(language: str | None) -> str:
    """A BCP 47 tag, like en, ta, hi, ar or en-IN. Stored as said (lower-cased language, the rest as written); whether the app has the words yet is
    a different question (docs/i18n.md): an unknown tag falls back to English at the edge."""
    head, _, rest = (language or "").strip().partition("-")
    tag = head.lower() + (("-" + rest) if rest else "")
    if not _LANGUAGE.match(tag) or len(tag) > 35:
        raise ValueError("language is a tag like en, ta, hi, ar or en-IN")
    return tag


def check_zone(timezone: str | None) -> str:
    tz = (timezone or "").strip()
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError("timezone must be a zone name, like Asia/Kolkata or Asia/Dubai") from None
    return tz


async def my_locale(p) -> dict:
    """The person's own zone and language where they set them, else the household's; both, so a client can show which it is."""
    row = await pool().fetchrow(
        "SELECT m.timezone AS own_timezone, m.language AS own_language, h.timezone, h.language FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE m.id = $1", p.member_id)
    return {"timezone": row["own_timezone"] or row["timezone"], "language": row["own_language"] or row["language"],
            "own_timezone": row["own_timezone"], "own_language": row["own_language"],
            "household_timezone": row["timezone"], "household_language": row["language"]}


async def set_my_locale(p, timezone: str | None, language: str | None, *, clear: bool = False) -> dict:
    """A person's own zone and language. Theirs alone; `clear` goes back to the household's."""
    tz = None if clear or not timezone else check_zone(timezone)
    lang = None if clear or not language else check_language(language)
    await pool().execute("UPDATE members SET timezone = COALESCE($2, CASE WHEN $4 THEN NULL ELSE timezone END), "
                         "language = COALESCE($3, CASE WHEN $4 THEN NULL ELSE language END) WHERE id = $1", p.member_id, tz, lang, clear)
    from familyos import clock
    clock.forget(p.household_id)
    return await my_locale(p)


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


async def set_locale(p, country: str, timezone: str, currency: str, language: str | None = None) -> dict:
    from familyos import audit
    from familyos.identity import NotAllowed
    if not p.is_guardian:
        raise NotAllowed("only a guardian can say where the household lives")
    c, tz, cur = check(country, timezone, currency)
    async with pool().acquire() as conn, conn.transaction():
        lang = check_language(language) if language else None
        row = await conn.fetchrow("UPDATE households SET country = $2, timezone = $3, currency = $4, language = COALESCE($5, language) WHERE id = $1 RETURNING *",
                                  p.household_id, c, tz, cur, lang)
        await audit.record(p.household_id, "household.locale_set", actor_member_id=p.member_id, target_type="household",
                           target_id=p.household_id, detail={"country": c, "timezone": tz, "currency": cur, **({"language": lang} if lang else {})}, conn=conn)
    return dict(row)
