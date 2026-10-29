"""My day: one page for one person, assembled from what is already theirs.

Nothing new is stored here. It reads the member's own brief (what needs them, worst first), their ranked suggestions,
the routines they set, how FamilyOS may reach them (quiet hours, daily cap, the morning message), what it has counted
about which suggestions they accept (feedback.py) and, only if this deployment offers it and they switched it on, their
own Health summary line. Another member's day is never reachable: every read is keyed by the signed-in member.
"""
from __future__ import annotations

import datetime as dt

from familyos import brief, clock, feedback, health, interruptions, routines, suggest
from familyos.identity import Principal

SUGGESTIONS_SHOWN = 3
NEEDS_SHOWN = 8


async def build(p: Principal, on: dt.date | None = None) -> dict:
    on = on or clock.today()
    day = await brief.today(p, on=on, limit=NEEDS_SHOWN)
    ideas = (await suggest.for_member(p, on))[:SUGGESTIONS_SHOWN]
    learned = await feedback.counts(p)
    hs = await health.status(p)
    line = health.line(await health.recent(p, days=7)) if hs["available"] and hs["sync"] and p.role != "child" else None
    return {
        "date": on,
        "display_name": day["display_name"],
        "role": p.role,
        "needs": day["items"],
        "more": day["more"],
        "counts": day["counts"],
        "next_thing": day.get("next_thing"),
        "suggestions": [{k: s[k] for k in ("key", "title", "why", "due_date", "link")} for s in ideas],
        "routines": [{"id": r["id"], "instruction": r["instruction"], "when": r["when"]} for r in await routines.list_for(p)],
        "reach_me": await interruptions.prefs(p.member_id),
        "learned": [{"kind": k, "accepted": v["accepted"], "dismissed": v["dismissed"], "quiet": feedback.muted(v)} for k, v in sorted(learned.items())],
        "health": {"available": hs["available"], "sync": hs["sync"], "line": line},
    }
