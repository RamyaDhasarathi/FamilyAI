"""A one-time code out of a message, so the browser agent can sign in with it (ported line for line from the collector
app's backend/src/services/otp.js, decided 2 Nov 2026: every SMS is kept, codes included, and the code is pulled out).

Conservative on purpose -- a wrong code wastes a sign-in:
  - only a message with an OTP-ish keyword yields a code (order numbers, amounts and phone numbers in ordinary texts never
    come back as codes),
  - currency amounts and years are ignored,
  - of what is left, a 6-digit group, then 4 or 8, then one after the keyword, then the nearest to it, is preferred.
Runs of digits may be split by single spaces or hyphens: "492013", "123 456", "12 34 56".
"""
from __future__ import annotations

import re

OTP_KEYWORDS = re.compile(
    r"\b(otp|one[\s-]?time|verification|verify|verified|code|passcode|pass\s?code|pin|2fa|two[\s-]?factor|security\s?code|"
    r"login\s?code|log\s?in\s?code|auth(?:entication)?|access\s?code|confirmation\s?code)\b", re.I)
GROUP_RE = re.compile(r"\d[\d\s-]{2,12}\d|\d{4,8}")
AMOUNT_PREFIX = re.compile(r"(?:rs\.?|inr|₹|\$|usd|rupees?|amount|#|a/c|acct|account|ref)\s*$", re.I)


def _looks_like_year(digits: str) -> bool:
    return len(digits) == 4 and re.fullmatch(r"(19|20)\d{2}", digits) is not None


def _candidates(body: str) -> list[tuple[str, int]]:
    out = []
    for m in GROUP_RE.finditer(body):
        digits = re.sub(r"[\s-]", "", m.group(0))
        if len(digits) < 4 or len(digits) > 8 or _looks_like_year(digits):
            continue
        if AMOUNT_PREFIX.search(body[max(0, m.start() - 8):m.start()]):
            continue
        out.append((digits, m.start()))
    return out


def _length_score(digits: str) -> int:
    return {6: 3, 4: 2, 8: 2}.get(len(digits), 1)


def extract_otp(body: object) -> str | None:
    """The code (leading zeros kept), or None when the message is not a verification message or has no code."""
    if not isinstance(body, str) or not body:
        return None
    keyword = OTP_KEYWORDS.search(body)
    if not keyword:
        return None
    found = _candidates(body)
    if not found:
        return None
    at = keyword.start()
    return sorted(found, key=lambda c: (-_length_score(c[0]), 0 if c[1] >= at else 1, abs(c[1] - at)))[0][0]
