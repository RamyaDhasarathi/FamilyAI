"""Telling a person what the household graph noticed, when it first becomes true, not when they next open the app.

A sweep every half hour asks the graph (graph.insights) what is worth saying to each adult: a pile of dated things for one person, a
prescription or document tied to no one, a warranty about to end. Each is sent once, as one short message that names up to three,
by the person's own channel (Telegram if linked, else email), inside their own quiet hours and under their daily cap
(interruptions.py). A heads-up they dismissed is never sent; one held back by quiet hours or the cap waits and goes later, not dropped.
Nothing here acts for anyone; it points at the Needs you page and the map.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from familyos import clock, graph, interruptions, jobs, notify
from familyos.db import pool
from familyos.identity import Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "nudges_sweep"
HANDLER_VERSION = "1"
SWEEP_SECONDS = 1800
MAX_NAMED = 3


async def fresh_for(p: Principal, today: dt.date) -> list[dict]:
    """Heads-ups this person has not been told and has not dismissed."""
    found = await graph.insights(p, today)
    if not found:
        return []
    keys = [x["key"] for x in found]
    told = {r["key"] for r in await pool().fetch("SELECT key FROM insight_notified WHERE member_id = $1 AND key = ANY($2::text[])", p.member_id, keys)}
    gone = {r["source_key"] for r in await pool().fetch("SELECT source_key FROM suggestion_dismissals WHERE household_id = $1 AND source_key = ANY($2::text[])",
                                                         p.household_id, [f"insight:{k}" for k in keys])}
    return [x for x in found if x["key"] not in told and f"insight:{x['key']}" not in gone]


async def sweep(now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    out = {"told": 0, "waited": 0, "nothing": 0, "failed": 0}
    rows = await pool().fetch(
        "SELECT m.id, m.household_id, m.role, m.display_name, COALESCE(m.timezone, h.timezone) AS timezone, h.key_mode FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE h.status = 'active' AND m.role <> 'child'")
    for r in rows:
        try:
            local = now.astimezone(ZoneInfo(r["timezone"] or settings.timezone))
        except Exception:  # noqa: BLE001 - a zone the system does not know: the server's own
            local = now.astimezone(ZoneInfo(settings.timezone))
        p = Principal(member_id=r["id"], household_id=r["household_id"], role=r["role"], display_name=r["display_name"])
        try:
            async with clock.household(p.household_id, p.member_id):
                fresh = await fresh_for(p, local.date())
            if not fresh:
                out["nothing"] += 1
                continue
            ok, _why = await interruptions.allow(r["id"], local)
            if not ok:
                out["waited"] += 1
                continue
            named = fresh[:MAX_NAMED]
            if r["key_mode"] == "family":
                # A family that holds its own key has asked for less to leave the app: no drug names or children's names in an email or a chat.
                subject = f"{len(fresh)} thing{'s' if len(fresh) != 1 else ''} worth a look"
                sent = await notify.member(r["id"], subject, "Nobody asked, but your record shows something worth a look.\n\nOpen Needs you in FamilyOS.")
            else:
                lines = [f"- {x['title']}" for x in named] + ([f"and {len(fresh) - MAX_NAMED} more"] if len(fresh) > MAX_NAMED else [])
                subject = named[0]["title"] if len(fresh) == 1 else f"{len(fresh)} things worth a look"
                sent = await notify.member(r["id"], subject, "Nobody asked, but your record shows:\n" + "\n".join(lines) + "\n\nOpen Needs you in FamilyOS to see how each connects.")
            if sent is None:
                out["failed"] += 1
                continue
            for x in fresh:
                await pool().execute("INSERT INTO insight_notified (member_id, key, household_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", r["id"], x["key"], r["household_id"])
            await interruptions.record(r["household_id"], r["id"], "heads_up")
            out["told"] += 1
        except Exception:  # noqa: BLE001 - one person's failure is not everyone's
            logger.warning("heads-up sweep failed for %s", r["id"], exc_info=True)
            out["failed"] += 1
    return out


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    try:
        from familyos import taught
        await taught.expire_stale()          # a taught lesson left behind by an aborted run gives its browser back here
    except Exception:  # noqa: BLE001 - housekeeping must not stop the heads-ups
        logger.warning("could not expire stale taught lessons", exc_info=True)
    try:
        from familyos import assistant_tasks
        await assistant_tasks.recover_stale()          # an assistant task whose worker died is failed here, whichever worker notices
    except Exception:  # noqa: BLE001
        logger.warning("could not recover stale assistant tasks", exc_info=True)
    try:
        result = await sweep(now)
    except Exception:  # noqa: BLE001 - a recurring sweep must come back: one bad pass is not the end of heads-ups
        logger.warning("the heads-up sweep failed; it will run again", exc_info=True)
        result = {"failed_pass": 1}
    return {**result, "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled() -> dict | None:
    return await jobs.ensure_recurring(KIND)


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=())
