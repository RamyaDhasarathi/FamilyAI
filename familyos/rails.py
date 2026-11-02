"""Outcome-scored rails: which way a school's notices actually arrive.

The same notice reaches a household by several rails: the school app read
by the phone's own hands, a WhatsApp forward, a circular photographed and
shared, mail. Each notice is recorded with the rail it came by and whether
it was the first to carry its dates or an echo of a notice already in. The
score per rail is the Beta-smoothed share of its deliveries that were first
and carried something, (first + 1) / (deliveries + 2), the way Orbit scores
a data provider by whether its results were usable: a rail that keeps
echoing or bringing nothing ranks down on its own, and one that was never
seen sits at the prior. The household is shown the numbers, not the score:
"the app read brought 9 of 11 notices first; WhatsApp echoed them a day
later." Nothing is fetched or sent because of a score; it says where the
notices come from, and when the reliable rail goes quiet, that is said once.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid

from familyos import origin
from familyos.db import pool
from familyos.identity import Principal

logger = logging.getLogger(__name__)

RAILS = {"school_app": "the school app, read by the phone", "whatsapp": "WhatsApp", "share": "the share sheet",
         "mail": "mail", "telegram": "Telegram", "portal": "the school portal", "console": "the console"}
ECHO_WINDOW = dt.timedelta(days=21)   # a notice carrying a date already in, this long after the first, is an echo
_WORD = re.compile(r"[a-z0-9]{3,}")
_FILLER = {"the", "and", "for", "this", "that", "with", "from", "your", "our", "all", "dear", "parents", "parent", "students", "please", "kindly", "note"}


def rail_of(channel: str | None, source: dict | None) -> str | None:
    """The rail a notice came by, from how it arrived. A share from the phone
    is the school app when the phone's own hands read it, else the share sheet."""
    source = source or {}
    ch = channel or ""
    if ch == "share":
        note, headline = str(source.get("note") or ""), str(source.get("headline") or "")
        if note.startswith("read from ") or headline.startswith("read from ") or re.match(r"screen \d+ of ", headline):
            return "school_app"
        return "share"
    if ch.startswith("whatsapp"):
        return "whatsapp"
    if ch.startswith(("gmail", "email")):
        return "mail"
    if ch.startswith("telegram"):
        return "telegram"
    if ch == "harvest":
        return "portal"
    if ch == "upload":
        return "console"
    return None   # an errand's step pictures and the like: not a notice rail


def _tokens(title: str | None) -> set[str]:
    return set(_WORD.findall((title or "").casefold())) - _FILLER


def similar(a: str | None, b: str | None) -> bool:
    """Two titles for the same thing, as a parent would see it: most of the
    shorter title's words are in the longer one ("PTM this Friday, Grade 4"
    against "Parent-Teacher Meeting (PTM) on Friday"). Filler words do not count."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.6


async def school_of(conn, household_id: uuid.UUID, artifact: dict, subjects: list[uuid.UUID]) -> uuid.UUID | None:
    """The school a notice belongs to: the subjects' school, else the one the
    household said this source belongs to."""
    if subjects:
        sid = await conn.fetchval("SELECT school_id FROM members WHERE id = ANY($1::uuid[]) AND school_id IS NOT NULL LIMIT 1", subjects)
        if sid:
            return sid
    name = await origin.school_for(conn, household_id, origin.source_key(artifact.get("channel"), artifact.get("source")))
    if name:
        return await conn.fetchval("SELECT id FROM schools WHERE household_id = $1 AND lower(name) = lower($2)", household_id, name)
    return None


async def record(conn, household_id: uuid.UUID, artifact: dict, subjects: list[uuid.UUID], obligations: list[tuple]) -> dict | None:
    """Write the notice's delivery once its obligations exist. `obligations`
    are the rows just inserted (title at index 7, due_date at 8). Only a
    notice that belongs to a school, or came by the school-app rail, counts."""
    rail = rail_of(artifact.get("channel"), artifact.get("source"))
    if rail is None:
        return None
    school_id = await school_of(conn, household_id, artifact, subjects)
    if school_id is None and rail != "school_app":
        return None
    delivered_at = artifact.get("received_at") or dt.datetime.now(dt.UTC)
    dated = [(o[7], o[8]) for o in obligations if o[8] is not None]
    outcome, echo_of = "first", None
    if not obligations:
        outcome = "empty"
    elif dated:
        earlier = await conn.fetch(
            "SELECT o.title, o.due_date, o.artifact_id, d.rail FROM obligations o "
            "JOIN rail_deliveries d ON d.artifact_id = o.artifact_id "
            "WHERE o.household_id = $1 AND d.school_id IS NOT DISTINCT FROM $2 AND o.artifact_id <> $3 "
            "AND o.superseded_at IS NULL AND o.due_date = ANY($4::date[]) AND d.delivered_at BETWEEN $5 AND $6 "
            "ORDER BY d.delivered_at",
            household_id, school_id, artifact["id"], [d for _, d in dated], delivered_at - ECHO_WINDOW, delivered_at)
        for title, due, earlier_artifact, _rail in earlier:
            if any(due == d and similar(title, t) for t, d in dated):
                outcome, echo_of = "echo", earlier_artifact
                break
    await conn.execute(
        "INSERT INTO rail_deliveries (artifact_id, household_id, school_id, rail, outcome, echo_of, delivered_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (artifact_id) DO UPDATE SET outcome = EXCLUDED.outcome, echo_of = EXCLUDED.echo_of",
        artifact["id"], household_id, school_id, rail, outcome, echo_of, delivered_at)
    return {"rail": rail, "outcome": outcome, "school_id": school_id, "echo_of": echo_of}


def score(first: int, echo: int, empty: int) -> float:
    return round((first + 1) / (first + echo + empty + 2), 3)


async def for_school(p: Principal, school_id: uuid.UUID | None) -> list[dict]:
    rows = await pool().fetch(
        "SELECT rail, count(*) FILTER (WHERE outcome = 'first') AS first, count(*) FILTER (WHERE outcome = 'echo') AS echo, "
        "count(*) FILTER (WHERE outcome = 'empty') AS empty, max(delivered_at) AS last_delivered_at, count(*) AS deliveries "
        "FROM rail_deliveries WHERE household_id = $1 AND school_id IS NOT DISTINCT FROM $2 GROUP BY rail", p.household_id, school_id)
    out = [{"rail": r["rail"], "label": RAILS.get(r["rail"], r["rail"]), "first": r["first"], "echo": r["echo"], "empty": r["empty"],
            "deliveries": r["deliveries"], "score": score(r["first"], r["echo"], r["empty"]), "last_delivered_at": r["last_delivered_at"]}
           for r in rows]
    return sorted(out, key=lambda x: (-x["score"], -x["deliveries"]))


async def summary(p: Principal) -> list[dict]:
    """Per school: the rails, the source rail, and the numbers a family is shown."""
    schools = await pool().fetch("SELECT id, name FROM schools WHERE household_id = $1 ORDER BY name", p.household_id)
    out = []
    for s in schools:
        rails = await for_school(p, s["id"])
        total = sum(r["deliveries"] for r in rails)
        firsts = sum(r["first"] for r in rails)
        out.append({"school_id": s["id"], "school": s["name"], "notices": total, "first": firsts, "rails": rails,
                    "source": rails[0]["rail"] if rails and rails[0]["first"] else None,
                    "said": _said(s["name"], rails)})
    return out


def _said(school: str, rails: list[dict]) -> str | None:
    """The sentence: where this school's notices come from."""
    with_first = [r for r in rails if r["first"]]
    if not with_first:
        return None
    top = with_first[0]
    total = sum(r["deliveries"] for r in rails)
    line = f"For {school}, {top['label']} brought {top['first']} of {total} notice{'s' if total != 1 else ''} first"
    echoes = [r for r in rails if r["rail"] != top["rail"] and r["echo"]]
    if echoes:
        line += "; " + " and ".join(f"{r['label']} echoed {r['echo']}" for r in echoes[:2])
    empty = sum(r["empty"] for r in rails)
    if empty:
        line += f"; {empty} carried no date"
    return line + "."


async def backfill(household_id: uuid.UUID) -> dict:
    """Write deliveries for the notices already in, oldest first, so the
    ledger starts from the record rather than from today. Safe to run again:
    a notice already recorded is rewritten with the same outcome."""
    counts = {"recorded": 0, "skipped": 0}
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT a.*, COALESCE((SELECT array_agg(s.member_id) FROM artifact_subjects s WHERE s.artifact_id = a.id), '{}') AS subjects "
            "FROM input_artifacts a WHERE a.household_id = $1 AND a.parent_id IS NULL AND a.status = 'accepted' ORDER BY a.received_at", household_id)
        for a in rows:
            obligations = await conn.fetch(
                "SELECT id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, end_date, due_time, optional, pay_url "
                "FROM obligations WHERE artifact_id = $1 AND superseded_at IS NULL", a["id"])
            async with conn.transaction():
                out = await record(conn, household_id, dict(a), list(a["subjects"]), [tuple(o) for o in obligations])
            counts["recorded" if out else "skipped"] += 1
    return counts
