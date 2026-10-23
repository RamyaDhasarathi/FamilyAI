"""Accounts a family pays, and the bill that did not arrive.

PayTM and GPay pull: you register a consumer number, they fetch the bill over
BBPS. That needs a licence or an aggregator, and every aggregator earns on the
payment -- which this system structurally cannot do.

Pushing needs none of it. The electricity board emails, the insurer emails, the
gas company texts; those already arrive down the intake ladder, get read, and
become obligations with a quote behind them. A biller row adds the one thing
pulling does badly: noticing that a bill which normally comes on the 5th has
not come at all. A pull model only knows what it managed to fetch.

It is also the instrument that decides whether BBPS is ever worth paying for.
Six months of "the gas bill only ever arrives by SMS" is a business case; a
guess is not.
"""
from __future__ import annotations

import datetime as dt
import hmac
import re
import uuid
from hashlib import sha256

from familyos import artifacts, audit
from familyos.db import pool
from familyos.identity import Invalid, NotFound, Principal

MAX_PER_HOUSEHOLD = 40

# What a biller may be seen in: a bill, and nothing else.
PAY = "pay"

_DIGITS = re.compile(r"[^0-9a-z]")
# Consumer numbers are printed in groups -- "9876 543 210", "1502-7734-0091".
# Closing the gaps *between* digits recovers the number without welding it to
# the words around it; normalising the whole line first would glue every number
# on the page into one run.
# Join only where digits sit on both sides, so "9876 543 210" closes up while
# "Consumer no" does not. Then take runs of at least six digits, which leaves
# an amount like "Rs 18,000" alone.
_JOIN = re.compile(r"(?<=\d)[\s\-/.]+(?=\d)")
_RUN = re.compile(r"(?<![0-9a-z])[0-9a-z]{0,6}\d{6,}[0-9a-z]{0,4}(?![0-9a-z])")


def candidates(text: str) -> list[str]:
    """Things in a notice that could be an account number."""
    joined = _JOIN.sub("", (text or "").lower())
    return list({run for run in _RUN.findall(joined)})


def normalise(identifier: str) -> str:
    """Consumer numbers are written with spaces, slashes and hyphens that mean
    nothing. Compare what is left."""
    return _DIGITS.sub("", (identifier or "").strip().lower())


def _mac(household_key: bytes, identifier: str) -> bytes:
    """An HMAC, not a hash. A ten-digit consumer number falls to a dictionary
    in seconds, so a plain digest would protect nothing; keyed by the household
    it is stable for matching here and meaningless anywhere else."""
    return hmac.new(household_key, normalise(identifier).encode(), sha256).digest()


def _hint(identifier: str) -> str:
    plain = normalise(identifier)
    return plain[-4:] if len(plain) >= 4 else plain


# A biller a member may see: shared, or their own -- the same rule as a notice.
VISIBLE_BILLER = "(b.household_id = $1 AND (b.visibility = 'shared' OR b.member_id = $2))"


async def add(p: Principal, *, label: str, provider: str, identifier: str | None = None,
              every_days: int = 30, grace_days: int = 7, visibility: str = "shared") -> dict:
    name, who = (label or "").strip(), (provider or "").strip()
    if not name or not who:
        raise Invalid("say what it is and who sends it")
    if visibility not in ("private", "shared"):
        raise Invalid("visibility is private or shared")
    if not 1 <= every_days <= 400:
        raise Invalid("a bill arrives somewhere between daily and yearly")
    if not 0 <= grace_days <= 60:
        raise Invalid("grace is between 0 and 60 days")

    async with pool().acquire() as conn, conn.transaction():
        live = await conn.fetchval(
            "SELECT count(*) FROM billers WHERE household_id = $1 AND muted_at IS NULL", p.household_id)
        if live >= MAX_PER_HOUSEHOLD:
            raise Invalid(f"a household tracks at most {MAX_PER_HOUSEHOLD} accounts")
        mac = hint = None
        if identifier and normalise(identifier):
            key = await artifacts.household_key(conn, p.household_id)
            mac, hint = _mac(key, identifier), _hint(identifier)
            clash = await conn.fetchval(
                "SELECT 1 FROM billers WHERE household_id = $1 AND identifier_mac = $2", p.household_id, mac)
            if clash:
                raise Invalid("that account is already being tracked")
        row = await conn.fetchrow(
            "INSERT INTO billers (id, household_id, member_id, visibility, label, provider, "
            "identifier_mac, identifier_hint, every_days, grace_days) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING *",
            uuid.uuid4(), p.household_id, p.member_id, visibility, name, who, mac, hint,
            every_days, grace_days)
        await audit.record(p.household_id, "biller.added", actor_member_id=p.member_id,
                           target_type="biller", target_id=row["id"],
                           # The provider, never the consumer number.
                           detail={"provider": who, "every_days": every_days}, conn=conn)
    return dict(row)


async def forget(p: Principal, biller_id: uuid.UUID) -> dict:
    row = await pool().fetchrow(
        "UPDATE billers SET muted_at = NOW() WHERE id = $1 AND household_id = $2 AND muted_at IS NULL "
        "RETURNING *", biller_id, p.household_id)
    if row is None:
        raise NotFound("biller")
    return dict(row)


async def list_for(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        f"SELECT b.* FROM billers b WHERE {VISIBLE_BILLER} AND b.muted_at IS NULL ORDER BY b.label",
        p.household_id, p.member_id)
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# matching what arrived
# ----------------------------------------------------------------------------

async def note_arrivals(household_id: uuid.UUID, *, since: dt.datetime | None = None) -> int:
    """Mark a biller as seen when a bill it sent has been read.

    Matched on the consumer number when the notice names one, and otherwise on
    the provider's name appearing in the obligation. Deliberately conservative:
    a missed match says "we have not seen your gas bill", which is a nudge. A
    wrong match says nothing at all, which is worse.
    """
    since = since or dt.datetime.now(dt.UTC) - dt.timedelta(days=90)
    seen = 0
    async with pool().acquire() as conn:
        billers = await conn.fetch(
            "SELECT * FROM billers WHERE household_id = $1 AND muted_at IS NULL", household_id)
        if not billers:
            return 0
        key = await artifacts.household_key(conn, household_id)
        bills = await conn.fetch(
            "SELECT o.id, o.created_at, o.title, c.quote FROM obligations o "
            "LEFT JOIN claims c ON c.id = o.claim_id "
            "WHERE o.household_id = $1 AND o.action = $2 AND o.superseded_at IS NULL "
            "AND o.created_at >= $3 ORDER BY o.created_at",
            household_id, PAY, since)
        for biller in billers:
            provider = biller["provider"].strip().lower()
            for bill in bills:
                text = f"{bill['title'] or ''} {bill['quote'] or ''}"
                hit = provider in text.lower()
                if not hit and biller["identifier_mac"]:
                    hit = any(hmac.compare_digest(_mac(key, run), biller["identifier_mac"])
                              for run in candidates(text))
                if not hit:
                    continue
                if biller["last_seen_at"] is None or bill["created_at"] > biller["last_seen_at"]:
                    await conn.execute(
                        "UPDATE billers SET last_seen_at = $2, last_obligation_id = $3 WHERE id = $1",
                        biller["id"], bill["created_at"], bill["id"])
                    seen += 1
    return seen


async def missing(p: Principal, *, now: dt.datetime | None = None) -> list[dict]:
    """Accounts whose bill is later than this one usually is.

    A biller never seen at all says nothing: we have no idea when its bill is
    due, and inventing a date would be worse than silence.
    """
    now = now or dt.datetime.now(dt.UTC)
    rows = await pool().fetch(
        f"SELECT b.* FROM billers b WHERE {VISIBLE_BILLER} AND b.muted_at IS NULL "
        "AND b.last_seen_at IS NOT NULL "
        "AND b.last_seen_at < $3::timestamptz - make_interval(days => b.every_days + b.grace_days) "
        "ORDER BY b.last_seen_at",
        p.household_id, p.member_id, now)
    out = []
    for row in rows:
        late = (now - row["last_seen_at"]).days - row["every_days"]
        out.append({**dict(row), "days_late": max(0, late)})
    return out


async def bills(p: Principal, *, days: int = 60) -> list[dict]:
    """What is owed, grouped by nothing -- the console groups it. Obligations
    the member can already see, narrowed to the ones that are payments."""
    from familyos import grants
    rows = await pool().fetch(
        f"SELECT o.id, o.title, o.due_date, o.status, o.subject_member_id, a.received_at "
        f"FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id "
        f"WHERE {grants.VISIBLE_OBLIGATION} AND o.action = 'pay' AND o.superseded_at IS NULL "
        f"AND (o.due_date IS NULL OR o.due_date >= CURRENT_DATE - make_interval(days => $3)) "
        f"ORDER BY o.due_date NULLS LAST",
        p.household_id, p.member_id, days)
    return [dict(r) for r in rows]


def describe() -> str:
    return ("billers: accounts a family pays, matched from what arrives -- no payment rail, "
            "no consumer number stored, only an HMAC under the household key")
