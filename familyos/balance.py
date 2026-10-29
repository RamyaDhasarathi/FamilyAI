"""Mental-load balancing: a gentle word to the person carrying most of one kind of thing, never a score.

Off until a guardian switches it on. When it is on, over the last 60 days FamilyOS counts, per kind of thing (school,
health, money, home, travel), who closed it: marked a notice handled, accepted a date, or took a hand-off. If one adult has
closed at least 70% of a kind with at least six closed in all, and another adult has closed fewer, it says so to that one
person, privately, in one sentence, and offers to hand the next one to the other. It names no one else's count, ranks no
one, and a nudge that is waved away stays quiet for a month.

The household's other adults see the same plain open-hand-off counts as everyone (handoffs.workload) and nothing more.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import audit, categories, feedback
from familyos.db import pool
from familyos.identity import NotAllowed, Principal

WINDOW_DAYS = 60
MIN_TOTAL = 6
SHARE = 0.7
QUIET_DAYS = 30

DOMAIN_OF = {"school": "school", "medical": "health", "insurance": "health", "bills": "money", "banking": "money", "government": "money",
             "subscriptions": "money", "trading": "money", "home": "home", "food": "home", "shopping": "home", "travel": "travel"}
WORDS = {"school": "school things", "health": "health things", "money": "money things", "home": "home things", "travel": "travel things", "other": "things"}


async def set_enabled(p: Principal, enabled: bool) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian switches this on")
    await pool().execute("UPDATE households SET balance_enabled = $2 WHERE id = $1", p.household_id, enabled)
    await audit.record(p.household_id, "household.balance_set", actor_member_id=p.member_id, detail={"enabled": enabled})
    return {"enabled": enabled}


async def _domain(artifact_id) -> str:
    r = await pool().fetchrow("SELECT a.channel, a.source, EXISTS (SELECT 1 FROM artifact_subjects s JOIN members m ON m.id = s.member_id WHERE s.artifact_id = a.id AND m.role = 'child') AS about_child "
                              "FROM input_artifacts a WHERE a.id = $1", artifact_id)
    if r is None:
        return "other"
    import json
    src = r["source"] if isinstance(r["source"], dict) else json.loads(r["source"] or "{}")
    cat = categories.category_of(r["channel"], src)
    if cat in DOMAIN_OF:
        return DOMAIN_OF[cat]
    return "school" if r["about_child"] else "other"


async def counts(household_id: uuid.UUID, days: int = WINDOW_DAYS) -> dict[str, dict[uuid.UUID, int]]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    rows = await pool().fetch(
        "SELECT e.actor_member_id AS who, e.action, e.target_type, e.target_id, e.detail FROM audit_events e "
        "WHERE e.household_id = $1 AND e.at >= $2 AND e.actor_member_id IS NOT NULL AND e.actor_kind <> 'system' "
        "AND e.action IN ('artifact.handled', 'obligation.accepted', 'handoff.accepted')", household_id, since)
    adults = {r["id"] for r in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role IN ('guardian', 'adult')", household_id)}
    out: dict[str, dict[uuid.UUID, int]] = {}
    for r in rows:
        if r["who"] not in adults or not r["target_id"]:
            continue
        aid = r["target_id"]
        if r["target_type"] == "obligation":
            aid = await pool().fetchval("SELECT artifact_id FROM obligations WHERE id = $1", r["target_id"])
            if aid is None:
                continue
        d = await _domain(aid)
        out.setdefault(d, {})
        out[d][r["who"]] = out[d].get(r["who"], 0) + 1
    return out


async def nudges(p: Principal) -> dict:
    enabled = await pool().fetchval("SELECT balance_enabled FROM households WHERE id = $1", p.household_id)
    if not enabled or p.role == "child":
        return {"enabled": bool(enabled), "nudges": []}
    quiet = {r["kind"] for r in await pool().fetch(
        "SELECT DISTINCT kind FROM suggestion_feedback WHERE member_id = $1 AND outcome = 'dismissed' AND kind LIKE 'balance:%' AND created_at >= NOW() - make_interval(days => $2)",
        p.member_id, QUIET_DAYS)}
    names = {r["id"]: r["display_name"] for r in await pool().fetch("SELECT id, display_name FROM members WHERE household_id = $1 AND role IN ('guardian', 'adult')", p.household_id)}
    out = []
    for domain, by in (await counts(p.household_id)).items():
        total = sum(by.values())
        my = by.get(p.member_id, 0)
        if total < MIN_TOTAL or my / total < SHARE or len(names) < 2:
            continue
        if "balance:" + domain in quiet:
            continue
        others = sorted((m for m in names if m != p.member_id), key=lambda m: by.get(m, 0))
        offer = others[0]
        out.append({"domain": domain, "text": f"You've closed {my} of the last {total} {WORDS[domain]}. Would you like to offer the next one to {names[offer]}?",
                    "offer_to": {"member_id": offer, "name": names[offer]}})
    return {"enabled": True, "nudges": out}


async def dismiss(p: Principal, domain: str) -> dict:
    await feedback.record(p, "balance:" + domain[:30], "dismissed")       # quiet for QUIET_DAYS, read back in nudges()
    return {"dismissed": domain}
