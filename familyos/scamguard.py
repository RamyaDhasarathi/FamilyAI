"""Scam guard: a message or a reported call that looks like a scam, said so
in plain words, before anyone acts on it.

Most of the harm in a parent's life from far away is not a missed deadline but
a phone call: a "CBI officer" on a video call, a "bank" that needs an OTP, a
KYC link, a "relative" with a new number. None of them is a notice, and a
reader that proposes a task from them ("pay the verification amount by 5 pm")
does the scammer's work. So a high reading proposes nothing, and the people
who can act are told once, with what to do.

How it reads: patterns, not a model. Each pattern that matches adds its weight
and a reason in words a parent would use; a high score is six or more, a
medium one is three. A genuine message from a bank or an office says "never
share your OTP" and mentions a block or a KYC: so a request to share is only
a request when it is not negated, an OTP message is only an OTP message, and a
sender the mail provider vouched for, from a bank or government domain, is
discounted. What it cannot do is know a number is a scammer's; it says
"matches" and "worth a second look", never "is".

What the advice says is from the sources it names (checked 12 Oct 2026):
  * RBI's advisories: a bank never asks for a PIN, OTP, CVV or full card
    number, by call, SMS, email or link. https://taxguru.in/rbi/rbi-advisory-cyber-threats-frauds.html
  * The Indian Cyber Crime Coordination Centre and the Ministry of Home
    Affairs: there is no "digital arrest"; police, CBI and courts do not
    arrest anyone or demand money over a video call; report at the helpline
    1930 or https://cybercrime.gov.in. https://www.etvbharat.com/en/!bharat/cbi-ed-police-dont-arrest-people-through-video-calls-indian-cyber-crime-coordination-centre-enn24100602996
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid

from familyos import audit, notify
from familyos.db import pool

logger = logging.getLogger(__name__)

HIGH = 6
MEDIUM = 3

_AUTHORITY = re.compile(r"\b(cbi|cid|ncb|narcotics|customs|enforcement directorate|ed officer|cyber ?crime|trai|rbi|income[- ]tax|"
                        r"supreme court|high court|police|court|inspector|officer|department)\b", re.I)
_THREAT = re.compile(r"\b(arrest(?:ed)?|warrant|fir\b|case (?:has been|is|was) (?:registered|filed)|money laundering|"
                     r"illegal|legal action|seized|parcel|contraband|blocked|suspended|disconnected)\b", re.I)
_REQUEST = re.compile(r"\b(share|send|tell|give|provide|read out|forward|enter|disclose)\b[^.\n]{0,40}"
                      r"\b(otp|one[- ]time password|pin|upi[- ]pin|cvv|password|passcode|card number|net ?banking|aadhaar|pan card)\b", re.I)
_NEGATION = re.compile(r"(do not|don't|never|not to|without|won't|will not|shall not|no one)\W+(?:\w+\W+){0,3}$", re.I)
_OTP_MESSAGE = re.compile(r"\b(otp|one[- ]time password)\b[^.\n]{0,25}(?:is|:)\s*\d{4,8}\b", re.I)
_URL = re.compile(r"https?://[^\s)>\]]+", re.I)
_SHORT = re.compile(r"https?://(?:bit\.ly|tinyurl\.com|cutt\.ly|rb\.gy|is\.gd|shorturl\.at|t\.ly|tiny\.cc)/", re.I)
_BADTLD = re.compile(r"https?://[^/\s]+\.(?:xyz|top|icu|click|vip|cfd|sbs|buzz|live|shop|work)(?:[/:\s]|$)", re.I)
_IPURL = re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}", re.I)

# (key, weight, pattern, the reason in a parent's words)
_SIGNALS: list[tuple[str, int, re.Pattern, str]] = [
    ("digital_arrest", 5, re.compile(r"digital arrest|video[- ]call[^.\n]{0,40}(?:arrest|investigation|statement)|"
                                     r"(?:cbi|ed|customs|police|narcotics)[^.\n]{0,60}video call", re.I),
     "talks of a “digital arrest” or an investigation by video call, which does not exist"),
    ("secrecy", 3, re.compile(r"do not (?:tell|inform|disconnect|hang up)|don't (?:tell|inform|disconnect)|stay on (?:the )?(?:call|line)|"
                              r"keep (?:this )?(?:confidential|secret)|do not (?:discuss|share) (?:this )?with (?:anyone|family)", re.I),
     "asks you to stay on the line or tell nobody"),
    ("safe_account", 4, re.compile(r"safe account|rbi (?:safe )?account|verification (?:amount|deposit)|refundable (?:deposit|amount)|"
                                   r"security deposit to (?:clear|release|avoid)|clearance (?:fee|amount)", re.I),
     "asks you to move money to a “safe” or “verification” account"),
    ("remote_tool", 4, re.compile(r"\b(?:anydesk|teamviewer|quick ?support|rustdesk|ammyy|alpemix)\b", re.I),
     "asks you to install a remote-control app"),
    ("kyc", 3, re.compile(r"\bkyc\b[^.\n]{0,80}(?:expire|expired|update|updating|verif|suspend|block|pending)|"
                          r"(?:update|complete|verify)[^.\n]{0,30}\bkyc\b", re.I),
     "says your KYC needs updating or your account will be blocked"),
    ("prize", 3, re.compile(r"\b(?:lottery|lucky draw|you have won|you['’]ve won|kbc|gift card|cashback of|guaranteed returns?|double your money|"
                            r"work from home[^.\n]{0,60}(?:per day|earn|daily))\b", re.I),
     "promises a prize, a job that pays too well, or guaranteed returns"),
    ("relative", 3, re.compile(r"\b(?:new number|changed my number|lost my phone|save this number|this is my new)\b[\s\S]{0,120}"
                               r"\b(?:send|transfer|pay|urgent|money|help)\b", re.I),
     "a “relative” on a new number asking for money"),
    ("utility", 3, re.compile(r"\b(?:electricity|power|gas|sim|mobile number|aadhaar|bank account|account)\b[^.\n]{0,50}"
                              r"\b(?:will be|is going to be|shall be)\s+(?:disconnected|blocked|deactivated|suspended|cancelled)\b", re.I),
     "threatens to cut off a service tonight unless you call or pay"),
    ("pay_to_avoid", 3, re.compile(r"\b(?:pay|transfer|send|deposit)\b[^.\n]{0,50}\b(?:to avoid|to clear|immediately|right now|within \d+ ?(?:hours?|minutes?))\b", re.I),
     "demands money at once to avoid a penalty"),
]
_URGENT = re.compile(r"\b(?:immediately|within \d+ ?(?:hours?|minutes?)|today itself|last warning|final notice|urgent(?:ly)?|right now)\b", re.I)
# Domains a bank, a government office or a school really writes from.
_INSTITUTIONAL = {"government", "banking", "bills", "insurance", "trading", "school", "medical", "subscriptions"}


def _unnegated(pattern: re.Pattern, text: str) -> bool:
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if not _NEGATION.search(before):
            return True
    return False


def advice(level: str, country: str | None) -> list[str]:
    india = (country or "IN").upper() == "IN"
    out = []
    if level == "high":
        out.append("Do not call back, click anything or pay. Hang up or stop replying.")
        out.append("No police officer, CBI, court or bank arrests anyone, or asks for money, over a phone or video call.")
    else:
        out.append("Check with the bank or office using the number on your card or its own website, not the number in this message.")
    out.append("Never share an OTP, PIN, CVV or password, even with someone who says they are from the bank.")
    if india:
        out.append("If money was sent or details were shared, call 1930 at once, and report at cybercrime.gov.in.")
    else:
        out.append("If money was sent or details were shared, call your bank at once and report it to the local police.")
    return out


def assess(text: str | None, *, channel: str | None = None, source: dict | None = None, category: str | None = None,
           country: str | None = "IN") -> dict | None:
    """None when nothing matches; otherwise {level, score, reasons, advice}."""
    body = " ".join((text or "").split())
    if len(body) < 12:
        return None
    score, reasons = 0, []

    def add(weight: int, reason: str) -> None:
        nonlocal score
        score += weight
        if reason not in reasons:
            reasons.append(reason)

    for _key, weight, pattern, reason in _SIGNALS:
        if pattern.search(body):
            add(weight, reason)
    if _AUTHORITY.search(body) and _THREAT.search(body):
        add(3, "someone in authority threatens arrest, a case or a block")
    if _unnegated(_REQUEST, body):
        add(4, "asks you to share an OTP, PIN, password or card details")
    urls = _URL.findall(body)
    if any(_SHORT.match(u) for u in urls):
        add(2, "a shortened link hides where it goes")
    if any(_BADTLD.match(u) or _IPURL.match(u) for u in urls):
        add(2, "a link to an unusual address")
    if len(_URGENT.findall(body)) >= 2:
        add(1, "pushes you to act immediately")
    # What a genuine message looks like.
    if _OTP_MESSAGE.search(body) and re.search(r"do not share|never share|don['’]t share", body, re.I):
        score -= 3
    sender = ((source or {}).get("from") or "").lower()
    if channel in ("gmail", "gmail_attachment", "email", "email_attachment") and (source or {}).get("sender_authenticated") \
            and (category in _INSTITUTIONAL or re.search(r"\.(?:gov\.in|bank\.in|nic\.in)>?$", sender)):
        score -= 4
    if score < MEDIUM or not reasons:
        return None
    level = "high" if score >= HIGH else "medium"
    return {"level": level, "score": score, "reasons": reasons[:5], "advice": advice(level, country),
            "assessed_at": dt.datetime.now(dt.UTC).isoformat()}


async def keep(artifact_id: uuid.UUID, found: dict | None, *, conn=None) -> None:
    """Remember the reading on the notice and on its attachments' message."""
    db = conn or pool()
    # A later reading keeps the mark that the guardians were already told.
    await db.execute(
        "UPDATE input_artifacts SET suspicion = CASE WHEN $2::jsonb IS NULL THEN NULL ELSE $2::jsonb || "
        "CASE WHEN suspicion ? 'alerted' THEN jsonb_build_object('alerted', suspicion->'alerted') ELSE '{}'::jsonb END END "
        "WHERE id = $1 OR parent_id = $1", artifact_id, found)


async def alert(household_id: uuid.UUID, artifact_id: uuid.UUID, found: dict) -> int:
    """Tell the guardians once, on Telegram or by mail, with what to do. Said
    once per notice: the first reading marks it."""
    mark = await pool().fetchval(
        "UPDATE input_artifacts SET suspicion = suspicion || '{\"alerted\": true}'::jsonb "
        "WHERE id = $1 AND household_id = $2 AND suspicion IS NOT NULL AND NOT COALESCE((suspicion->>'alerted')::boolean, FALSE) "
        "RETURNING id", artifact_id, household_id)
    if mark is None:
        return 0
    told = 0
    body = ("This looks like a scam: " + "; ".join(found["reasons"][:3]) + ".\n\n" + "\n".join("• " + a for a in found["advice"])
            + "\n\nNothing was done about it, and it is in the Inbox if you want to look.")
    for g in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role = 'guardian'", household_id):
        try:
            if await notify.member(g["id"], "A message may be a scam", body):
                told += 1
        except Exception:  # noqa: BLE001 - a courtesy
            logger.warning("could not tell guardian %s about a scam", g["id"], exc_info=True)
    await audit.record(household_id, "scam.flagged", actor_kind="system", target_type="artifact", target_id=artifact_id,
                       detail={"level": found["level"], "told": told})
    return told
