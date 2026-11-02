"""Ranking what is suggested to a person by what that person actually accepts.

No model and no learning rate: counts over the last 90 days, per member and per kind of suggestion ("gift", "ptm",
"closes"). A kind they accept more than they dismiss comes first; a kind they have dismissed three times without ever
accepting goes quiet, except when its date is a day away, because a missed exam is worse than a nagging one. Only the
kind and the outcome are kept, never what was suggested. The member can read the counts and clear them.

Not a profile and not a twin: a few integers that an erasure deletes with the member, and that can be thrown away
without losing a single fact about the household.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from familyos import clock
from familyos.db import pool
from familyos.identity import Principal

WINDOW_DAYS = 90
MUTE_AFTER = 3          # dismissals with no acceptance in the window
URGENT_DAYS = 1         # a date this near is shown whatever the history says


async def record(p: Principal, kind: str, outcome: str) -> None:
    await pool().execute("INSERT INTO suggestion_feedback (member_id, household_id, kind, outcome) VALUES ($1, $2, $3, $4)",
                         p.member_id, p.household_id, kind[:40], outcome)


async def counts(p: Principal) -> dict[str, dict[str, int]]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=WINDOW_DAYS)
    rows = await pool().fetch(
        "SELECT kind, outcome, count(*) AS n FROM suggestion_feedback WHERE member_id = $1 AND created_at >= $2 GROUP BY kind, outcome",
        p.member_id, since)
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["kind"], {"accepted": 0, "dismissed": 0})[r["outcome"]] = r["n"]
    return out


async def clear(p: Principal) -> int:
    done = await pool().execute("DELETE FROM suggestion_feedback WHERE member_id = $1", p.member_id)
    return int(done.split()[-1])


def score(c: dict[str, int] | None) -> float:
    """Share accepted, with a prior so one tap does not swing it: 0.5 with no history."""
    a, d = (c or {}).get("accepted", 0), (c or {}).get("dismissed", 0)
    return (a + 1) / (a + d + 2)


def muted(c: dict[str, int] | None) -> bool:
    c = c or {}
    return c.get("dismissed", 0) >= MUTE_AFTER and c.get("accepted", 0) == 0


async def rank(p: Principal, items: list[dict], *, kind: Callable[[dict], str],
               due: Callable[[dict], dt.date | None] = lambda i: i.get("due_date"), today: dt.date | None = None) -> list[dict]:
    """The items in the order this person would want them, a muted kind left out unless it is urgent. Stable: items of
    equal standing keep the order they came in (soonest first)."""
    if not items:
        return items
    today = today or clock.today()
    c = await counts(p)
    out = []
    for position, it in enumerate(items):
        kc = c.get(kind(it))
        d = due(it)
        urgent = d is not None and (d - today).days <= URGENT_DAYS
        if muted(kc) and not urgent:
            continue
        out.append((0 if urgent else 1, -score(kc), position, it))
    out.sort(key=lambda t: t[:3])
    return [t[3] for t in out]
