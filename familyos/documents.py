"""The household's documents, with their dates: a passport, a visa, a policy,
a vehicle's RC, its PUC, a driving licence. Read from the notices the family
shares -- a passport's photo page, the policy PDF, the RC -- and kept as one
record each, with the notice it came from.

What a document is for here is its expiry. A renewal becomes a task with a
lead that fits the kind (a passport takes months, a PUC an afternoon), and
a trip's dates are checked against the passports that would travel: most
countries want a passport valid six months past the return, and a family
finds that out at the counter unless something says it earlier.

What is kept of a number is its last four characters, never the whole: the
original is on the notice, and a list of passport numbers is a liability a
family record does not need to carry.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid

from familyos import consent
from familyos.artifacts import VISIBLE_TO_MEMBER
from familyos.db import pool
from familyos.identity import Principal

logger = logging.getLogger(__name__)

KINDS = ("passport", "visa", "insurance", "vehicle_rc", "puc", "driving_licence", "id_card", "other")
LABEL = {"passport": "passport", "visa": "visa", "insurance": "insurance policy", "vehicle_rc": "vehicle RC",
         "puc": "PUC certificate", "driving_licence": "driving licence", "id_card": "ID card", "other": "document"}
# Days before expiry a renewal is proposed: what each kind takes to renew.
LEAD = {"passport": 270, "visa": 45, "insurance": 30, "vehicle_rc": 90, "puc": 14, "driving_licence": 60, "id_card": 60, "other": 30}
# A passport must usually outlive the trip by this much.
TRAVEL_MARGIN = dt.timedelta(days=180)


def lead_for(kind: str | None) -> int:
    return LEAD.get(kind or "other", LEAD["other"])


_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ \-]?){5,}\d(?!\d)")


def mask_numbers(text: str | None) -> str | None:
    """Every run of six or more digits in a text, spaced or not, with all
    but its last four replaced: an Aadhaar, a passport number, a policy
    number quoted from a document is never kept whole."""
    if not text:
        return text

    def one(m):
        s = m.group(0)
        digits = [i for i, ch in enumerate(s) if ch.isdigit()]
        keep = set(digits[-4:])
        return "".join("x" if (ch.isdigit() and i not in keep) else ch for i, ch in enumerate(s))
    return _LONG_NUMBER.sub(one, text)


async def mask_old_quotes(limit: int = 2000) -> int:
    """Document claims kept before quotes were masked: masked now, once."""
    rows = await pool().fetch("SELECT id, quote FROM claims WHERE kind = 'document' AND quote ~ '[0-9]([ -]?[0-9]){5,}' LIMIT $1", limit)
    for r in rows:
        await pool().execute("UPDATE claims SET quote = $2 WHERE id = $1", r["id"], mask_numbers(r["quote"]))
    return len(rows)


def tail(identifier: str | None) -> str | None:
    """The last four characters of a number, and only those."""
    s = "".join(ch for ch in (identifier or "") if ch.isalnum())
    return s[-4:] if len(s) >= 4 else None


async def record(conn, household_id: uuid.UUID, artifact_id: uuid.UUID, claim_ids: list[uuid.UUID], claims) -> int:
    """Keep each document claim of a fresh extraction as a record. The same
    document read again, or a newer one of the same kind for the same
    holder, supersedes the record before it."""
    docs = [(claim_ids[i], c) for i, c in enumerate(claims) if getattr(c, "kind", None) == "document"]
    if not docs:
        return 0
    adults = {r["id"]: r["display_name"] for r in await conn.fetch(
        "SELECT id, display_name FROM members WHERE household_id = $1 AND role <> 'child'", household_id)}
    children = dict(await consent.consented_children(conn, household_id))
    await conn.execute("UPDATE documents SET superseded_at = NOW() WHERE artifact_id = $1 AND superseded_at IS NULL", artifact_id)
    kept = 0
    for claim_id, c in docs:
        kind = c.document_kind if c.document_kind in KINDS else "other"
        holder_id = holder_text = None
        if c.subject_name:
            for member_id, name in {**adults, **children}.items():
                if consent.names_match(c.subject_name, name):
                    holder_id = member_id
                    break
            # A name that is nobody's, or an unconsented child's, is not kept.
        identifier = tail(c.identifier_tail)
        doc_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO documents (id, household_id, artifact_id, claim_id, kind, title, holder_member_id, holder_text, issuer, "
            "identifier_tail, valid_from, expires_on) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)",
            doc_id, household_id, artifact_id, claim_id, kind, c.title[:200], holder_id, holder_text, (c.issuer or None) and c.issuer[:120],
            identifier, c.date, c.end_date)
        # An earlier record of the same thing: the same holder and kind, or the
        # same number, from another notice. The newer reading stands.
        await conn.execute(
            "UPDATE documents SET superseded_at = NOW(), superseded_by = $1 WHERE household_id = $2 AND id <> $1 AND superseded_at IS NULL "
            "AND kind = $3 AND artifact_id <> $4 AND ((holder_member_id IS NOT NULL AND holder_member_id = $5) "
            "OR (identifier_tail IS NOT NULL AND identifier_tail = $6))",
            doc_id, household_id, kind, artifact_id, holder_id, identifier)
        kept += 1
    return kept


def status_of(expires_on: dt.date | None, kind: str, today: dt.date | None = None) -> tuple[str, int | None]:
    today = today or dt.date.today()
    if expires_on is None:
        return "undated", None
    left = (expires_on - today).days
    if left < 0:
        return "expired", left
    if left <= lead_for(kind):
        return "expiring", left
    return "ok", left


_LIST = f"""
SELECT d.id, d.artifact_id, d.kind, d.title, d.holder_member_id, d.holder_text, d.issuer, d.identifier_tail,
       d.valid_from, d.expires_on, d.created_at, m.display_name AS holder_name
FROM documents d JOIN input_artifacts a ON a.id = d.artifact_id LEFT JOIN members m ON m.id = d.holder_member_id
WHERE {VISIBLE_TO_MEMBER} AND d.superseded_at IS NULL
ORDER BY d.expires_on NULLS LAST, d.created_at DESC
"""


async def list_for(p: Principal, today: dt.date | None = None) -> list[dict]:
    out = []
    for r in await pool().fetch(_LIST, p.household_id, p.member_id):
        row = dict(r)
        row["status"], row["days_left"] = status_of(row["expires_on"], row["kind"], today)
        row["label"] = LABEL.get(row["kind"], "document")
        row["holder_name"] = row["holder_name"] or row["holder_text"]
        out.append(row)
    return out


async def checks(p: Principal, docs: list[dict] | None = None, today: dt.date | None = None) -> list[dict]:
    """What the documents say about the plans: a trip whose return date a
    traveller's passport does not outlive by six months."""
    today = today or dt.date.today()
    docs = docs if docs is not None else await list_for(p, today)
    trips = await pool().fetch(
        "SELECT id, title, starts_on, ends_on FROM plans WHERE household_id = $1 AND shape = 'trip' AND status <> 'dropped' "
        "AND ends_on IS NOT NULL AND ends_on >= $2 ORDER BY starts_on NULLS LAST", p.household_id, today)
    out = []
    for trip in trips:
        needed = trip["ends_on"] + TRAVEL_MARGIN
        for d in docs:
            if d["kind"] != "passport" or not d["expires_on"] or d["expires_on"] >= needed:
                continue
            who = d["holder_name"] or "a passport"
            out.append({"kind": "passport_short", "plan_id": trip["id"], "plan_title": trip["title"], "document_id": d["id"],
                        "holder_name": d["holder_name"], "expires_on": d["expires_on"], "needed_until": needed,
                        "title": f"{who}’s passport runs out before {trip['title']} needs it.",
                        "why": f"it expires {d['expires_on'].strftime('%-d %b %Y')}; the trip returns "
                               f"{trip['ends_on'].strftime('%-d %b %Y')} and most countries want six months after that, "
                               f"{needed.strftime('%-d %b %Y')}", "artifact_id": d["artifact_id"]})
    for d in docs:
        if d["status"] == "expired":
            out.append({"kind": "expired", "document_id": d["id"], "holder_name": d["holder_name"], "expires_on": d["expires_on"],
                        "title": f"{(d['holder_name'] + '’s ') if d['holder_name'] else ''}{d['label']} has expired.",
                        "why": f"on {d['expires_on'].strftime('%-d %b %Y')}", "artifact_id": d["artifact_id"]})
    return out


def describe() -> str:
    return "documents: passports, visas, policies, RC and PUC read from the family's own notices; last four of a number only; expiries become renewals and are checked against trips"
