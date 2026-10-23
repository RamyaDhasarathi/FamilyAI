"""Who the arriving work actually lands on.

Every family organiser measures the mental load by asking. Maple runs a nine
question quiz; Tribe scores the tasks a family typed in, which measures their
diligence at data entry as much as their burden -- the parent who enters more
looks like they carry more.

Nothing here is entered. The obligations counted below were read out of
notices somebody else sent, and the three things a member can do about one are
already recorded for other reasons:

  * **noticed** -- they brought it in (forwarded it, uploaded it, vouched for it)
  * **decided** -- they accepted or dismissed it
  * **acted**   -- they approved the reply that answered it

So this is a count of recorded work, which is a real limitation and a
different one from everybody else's: it misses what a family did outside the
system, and it cannot miss what they did inside it by forgetting to log it.

It is not a judgement, and the API says so in the payload rather than leaving
it to a designer to remember.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import grants
from familyos.db import pool
from familyos.identity import Principal

DEFAULT_DAYS = 90

# Each obligation the asking member can see, with the members who touched it.
# One row per (obligation, member, how), so a member who both decided and acted
# counts once for carrying it and twice in the breakdown.
_TOUCHES = f"""
WITH seen AS (
    SELECT o.id, o.status, o.due_date, o.decided_by, a.submitted_by
    FROM obligations o
    JOIN input_artifacts a ON a.id = o.artifact_id
    WHERE {grants.VISIBLE_OBLIGATION}
      AND o.superseded_at IS NULL
      AND o.created_at >= $3::timestamptz
),
touches AS (
    SELECT id, submitted_by AS member_id, 'noticed' AS how FROM seen WHERE submitted_by IS NOT NULL
    UNION ALL
    SELECT id, decided_by, 'decided' FROM seen WHERE decided_by IS NOT NULL
    UNION ALL
    SELECT s.id, act.approved_by, 'acted' FROM seen s
      JOIN actions act ON act.obligation_id = s.id AND act.approved_by IS NOT NULL
)
SELECT m.id AS member_id, m.display_name, t.how, count(DISTINCT t.id) AS n
FROM touches t JOIN members m ON m.id = t.member_id
GROUP BY 1, 2, 3
"""

_TOTALS = f"""
SELECT count(*) AS total,
       count(*) FILTER (WHERE o.status = 'proposed') AS undecided,
       count(*) FILTER (WHERE o.status = 'proposed' AND o.due_date < CURRENT_DATE) AS missed
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL AND o.created_at >= $3::timestamptz
"""

_CARRIERS = f"""
WITH seen AS (
    SELECT o.id, o.decided_by, a.submitted_by
    FROM obligations o
    JOIN input_artifacts a ON a.id = o.artifact_id
    WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL AND o.created_at >= $3::timestamptz
),
touches AS (
    SELECT id, submitted_by AS member_id FROM seen WHERE submitted_by IS NOT NULL
    UNION
    SELECT id, decided_by FROM seen WHERE decided_by IS NOT NULL
    UNION
    SELECT s.id, act.approved_by FROM seen s
      JOIN actions act ON act.obligation_id = s.id AND act.approved_by IS NOT NULL
)
SELECT member_id, count(DISTINCT id) AS carried FROM touches GROUP BY 1
"""


async def share(p: Principal, *, days: int = DEFAULT_DAYS) -> dict:
    """How the work that arrived was divided, over the last `days`."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=max(1, days))
    async with pool().acquire() as conn:
        touches = await conn.fetch(_TOUCHES, p.household_id, p.member_id, since)
        totals = await conn.fetchrow(_TOTALS, p.household_id, p.member_id, since)
        carriers = await conn.fetch(_CARRIERS, p.household_id, p.member_id, since)

    carried = {r["member_id"]: r["carried"] for r in carriers}
    names: dict[uuid.UUID, str] = {}
    detail: dict[uuid.UUID, dict[str, int]] = {}
    for row in touches:
        names[row["member_id"]] = row["display_name"]
        detail.setdefault(row["member_id"], {"noticed": 0, "decided": 0, "acted": 0})[row["how"]] = row["n"]

    attended = sum(carried.values())
    members = sorted(
        ({"member_id": member_id,
          "display_name": names.get(member_id, ""),
          "carried": n,
          # Of the work somebody attended to, this is their part. Not a
          # fraction of the household's life.
          "share": round(100 * n / attended) if attended else 0,
          **detail.get(member_id, {"noticed": 0, "decided": 0, "acted": 0})}
         for member_id, n in carried.items()),
        key=lambda m: -m["carried"])

    return {
        "days": days,
        "since": since.date(),
        "total": totals["total"],
        # The number that matters most, and the one nobody else can report:
        # work that arrived and that nobody has touched.
        "undecided": totals["undecided"],
        "missed": totals["missed"],
        "members": members,
        "note": ("Counted from notices that arrived, not from anything anyone typed in. "
                 "It measures recorded work and is not a judgement about anyone."),
    }


def describe() -> str:
    return "mental load: counted from what arrived and who attended to it, never self-reported"
