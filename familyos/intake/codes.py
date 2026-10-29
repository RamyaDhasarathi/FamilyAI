"""One-time codes: a mail whose whole purpose is a number to type once.

"Your one-time verification code: 19496094, valid for 30 minutes." It asks nothing
of the family, it is useless in an hour, and it is a secret: a code that opens an
account is the last thing to keep in a household's record, show on a front page,
or send to a reader. So it is discarded at the door: not stored, not read, not
shown, counted as refused. A short mail only: a long statement that mentions a
verification code in passing is not one.
"""
from __future__ import annotations

import re

_CODE_PHRASE = re.compile(
    r"\b(otp|one[- ]time (?:password|passcode|code|pin)|verification code|security code|login code|sign[- ]?in code|"
    r"authentication code|confirmation code|access code|activation code)\b[^0-9]{0,40}(\d{4,8})\b", re.I)
_SUBJECT = re.compile(r"\b(otp|verification code|security code|login code|sign[- ]?in code|one[- ]time (?:password|code)|"
                      r"your code|code is)\b", re.I)
_NUMBER = re.compile(r"(?<![\d.,])\d{4,8}(?![\d.,])")
MAX_CHARS = 4000


def is_one_time_code(subject: str | None, text: str | None) -> bool:
    body = " ".join((text or "").split())
    if len(body) > MAX_CHARS:
        return False
    if _CODE_PHRASE.search(body):
        return True
    return bool(_SUBJECT.search(subject or "") and _NUMBER.search(body))
