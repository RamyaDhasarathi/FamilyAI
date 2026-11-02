"""Routines: "every Sunday at six, tell me next week's school items", said in chat, answered in chat.

A routine is one instruction and the time to run it, in the household's own time zone. It runs as the member who set it,
so it sees exactly what they see and nothing else, through the same Ask a typed question goes through. It answers in at
most a few lines; with nothing to report it says nothing at all. What it says counts against that member's interruption
budget (quiet hours and a cap a day), and over the budget it waits for the next sweep.

A routine only reads and says. It cannot act: if the answer suggests something, it is a suggestion like any other.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid
from zoneinfo import ZoneInfo

from familyos import audit, chat, clock, interruptions, jobs, notify
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "routines_sweep"
HANDLER_VERSION = "1"
SWEEP_SECONDS = 600
MAX_PER_MEMBER = 10
WRAP = ("{instruction}\n\n(This is a scheduled routine. Answer in at most five short lines, from the facts only. "
        "If there is nothing to report, answer exactly: NOTHING)")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def when_words(weekday: int | None, hour: int) -> str:
    return f"{'every day' if weekday is None else 'every ' + DAYS[weekday]} at {hour % 12 or 12}{'am' if hour < 12 else 'pm'}"


TRIGGERS = {
    "time": "on a day and hour",
    "bill_arrived": "when a bill arrives",
    "date_changed": "when a notice changes a date",
    "trip_soon": "some days before travel",
    "conflict": "when two things clash",
}


async def create(p: Principal, instruction: str, weekday: int | None, hour: int, *, trigger: str = "time",
                 trigger_days: int | None = None, policy: str = "tell") -> dict:
    if p.role == "child":
        raise NotAllowed("children cannot set routines")
    instruction = " ".join((instruction or "").split())
    if not 3 <= len(instruction) <= 400:
        raise Invalid("say what the routine should do, in a sentence")
    if trigger not in TRIGGERS:
        raise Invalid("a routine fires on a time, a bill arriving, a changed date, travel coming up, or a clash")
    if policy not in ("tell", "prepare"):
        raise Invalid("a routine either tells you or prepares what you can confirm")
    if trigger == "time":
        if not 0 <= hour <= 23 or (weekday is not None and not 0 <= weekday <= 6):
            raise Invalid("a routine runs on a day (or every day) at an hour from 0 to 23")
    else:
        weekday, hour = None, 0
        if trigger == "trip_soon":
            if trigger_days is None or not 0 <= trigger_days <= 60:
                raise Invalid("say how many days before travel, from 0 to 60")
        else:
            trigger_days = None
    if await pool().fetchval("SELECT count(*) FROM routines WHERE member_id = $1 AND active", p.member_id) >= MAX_PER_MEMBER:
        raise Invalid(f"that is {MAX_PER_MEMBER} routines; stop one first")
    row = dict(await pool().fetchrow(
        "INSERT INTO routines (id, household_id, member_id, instruction, weekday, hour, trigger, trigger_days, policy) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *",
        uuid.uuid4(), p.household_id, p.member_id, instruction, weekday, hour, trigger, trigger_days, policy))
    when = _when(row)
    await audit.record(p.household_id, "routine.created", actor_member_id=p.member_id, target_type="member", target_id=p.member_id,
                       detail={"when": when, "trigger": trigger, "policy": policy})
    return {**row, "when": when}


def _when(r: dict) -> str:
    if r["trigger"] == "time":
        return when_words(r["weekday"], r["hour"])
    if r["trigger"] == "trip_soon":
        return f"{r['trigger_days']} days before travel" if r["trigger_days"] else "on the day of travel"
    return TRIGGERS[r["trigger"]]


async def list_for(p: Principal) -> list[dict]:
    """A member's own routines; no one sees another's."""
    rows = await pool().fetch(
        "SELECT r.*, (SELECT outcome FROM routine_runs x WHERE x.routine_id = r.id ORDER BY x.id DESC LIMIT 1) AS last_outcome, "
        "(SELECT ran_at FROM routine_runs x WHERE x.routine_id = r.id ORDER BY x.id DESC LIMIT 1) AS last_ran_at "
        "FROM routines r WHERE r.member_id = $1 AND r.active ORDER BY r.created_at", p.member_id)
    return [{**dict(r), "when": _when(dict(r))} for r in rows]


async def pause(p: Principal, routine_id: uuid.UUID, paused: bool) -> dict:
    done = await pool().fetchrow("UPDATE routines SET paused = $3 WHERE id = $1 AND member_id = $2 AND active RETURNING id, paused", routine_id, p.member_id, paused)
    if done is None:
        raise NotFound("routine")
    await audit.record(p.household_id, "routine.paused" if paused else "routine.resumed", actor_member_id=p.member_id, target_type="member", target_id=p.member_id)
    return dict(done)


async def history(p: Principal, routine_id: uuid.UUID, limit: int = 30) -> list[dict]:
    if not await pool().fetchval("SELECT 1 FROM routines WHERE id = $1 AND member_id = $2", routine_id, p.member_id):
        raise NotFound("routine")
    rows = await pool().fetch("SELECT ran_at, trigger, event_ref, outcome, said FROM routine_runs WHERE routine_id = $1 ORDER BY id DESC LIMIT $2", routine_id, max(1, min(limit, 100)))
    return [dict(r) for r in rows]


async def stop(p: Principal, routine_id: uuid.UUID) -> None:
    done = await pool().execute("UPDATE routines SET active = FALSE WHERE id = $1 AND member_id = $2 AND active", routine_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("routine")
    await audit.record(p.household_id, "routine.stopped", actor_member_id=p.member_id, target_type="member", target_id=p.member_id)


def _local(now: dt.datetime, tz: str | None) -> dt.datetime:
    try:
        return now.astimezone(ZoneInfo(tz or settings.timezone))
    except Exception:  # noqa: BLE001 - a zone the system does not know: the server's own
        return now.astimezone(ZoneInfo(settings.timezone))


async def _log(row: dict, trigger: str, outcome: str, said: str | None, ref: str | None = None) -> None:
    await pool().execute("INSERT INTO routine_runs (routine_id, member_id, trigger, event_ref, outcome, said) VALUES ($1, $2, $3, $4, $5, $6) "
                         "ON CONFLICT DO NOTHING", row["id"], row["member_id"], trigger, ref, outcome, (said or "")[:500] or None)


async def _prepare_buttons(p: Principal, proposals: list[dict]) -> int:
    """Policy "prepare": what the routine would do, staged as buttons the person presses. Nothing runs by itself."""
    from familyos import chat_actions
    from familyos.intake import telegram
    row = await pool().fetchrow("SELECT telegram_chat_id FROM members WHERE id = $1", p.member_id)
    shown = 0
    for proposal in proposals[:3]:
        staged = await chat_actions.stage(p, proposal)
        if not staged:
            continue
        shown += 1
        if row and row["telegram_chat_id"] and settings.telegram_bot_token:
            try:
                await telegram.send_message(row["telegram_chat_id"], staged["summary"][:300].capitalize() + "?",
                                            buttons=[[("Confirm", f"act:{staged['id']}:y"), ("Not now", f"act:{staged['id']}:n")]],
                                            bot_token=settings.telegram_bot_token, api_base=settings.telegram_api_base)
            except Exception:  # noqa: BLE001 - the staged action is still there to confirm in the app
                logger.warning("routine button to %s failed", p.member_id, exc_info=True)
    return shown


async def _run(row: dict, local: dt.datetime, *, context: str | None = None, ref: str | None = None) -> str:
    """One run of one routine: once for the day (a clock routine) or once for the event (an event routine). Returns what
    happened: sent, silent, waited, failed or already."""
    ok, why = await interruptions.allow(row["member_id"], local)
    if not ok:
        return "waited"
    if ref is None:
        claimed = await pool().fetchval("UPDATE routines SET last_run_on = $2 WHERE id = $1 AND last_run_on IS DISTINCT FROM $2 RETURNING id", row["id"], local.date())
    else:
        claimed = await pool().fetchval("INSERT INTO routine_runs (routine_id, member_id, trigger, event_ref, outcome) VALUES ($1, $2, $3, $4, 'silent') "
                                        "ON CONFLICT DO NOTHING RETURNING id", row["id"], row["member_id"], row["trigger"], ref)
    if claimed is None:
        return "already"
    m = await pool().fetchrow("SELECT id, household_id, role, display_name FROM members WHERE id = $1", row["member_id"])
    p = Principal(member_id=m["id"], household_id=m["household_id"], role=m["role"], display_name=m["display_name"])
    text = WRAP.format(instruction=(f"Trigger: {context}\n" if context else "") + row["instruction"])

    async def finish(outcome: str, said: str | None = None) -> str:
        if ref is None:
            await _log(row, row["trigger"], outcome, said)
        else:
            await pool().execute("UPDATE routine_runs SET outcome = $3, said = $4 WHERE routine_id = $1 AND event_ref = $2", row["id"], ref, outcome, (said or "")[:500] or None)
        return outcome

    try:
        turn = await chat.turn(p, text)
    except Exception:  # noqa: BLE001 - one routine must not stop the rest; a clock routine tries again tomorrow
        logger.warning("routine %s failed", row["id"], exc_info=True)
        return await finish("failed")
    say = (turn.get("say") or "").strip()
    if not say or say.upper().startswith("NOTHING"):
        return await finish("silent")
    sent = await notify.member(p.member_id, f"Routine: {row['instruction'][:60]}", say + "\n\nYou set this routine in FamilyOS. Pause or stop it any time.")
    if sent is None:
        return await finish("failed", say)
    await interruptions.record(p.household_id, p.member_id, "routine")
    if row.get("policy") == "prepare":
        await _prepare_buttons(p, [x for x in turn.get("proposals") or [] if x.get("ok")])
    return await finish("sent", say)


# ----------------------------------------------------------------------------
# event triggers: found by plain rules, once per event
# ----------------------------------------------------------------------------

MAX_EVENTS_PER_SWEEP = 3

_BILLS = """
SELECT o.id, o.title, o.due_date FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id
WHERE {vis} AND o.action = 'pay' AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed') AND o.created_at > $3
ORDER BY o.created_at LIMIT 10
"""

_TRIPS = """
SELECT o.id, o.title, o.due_date FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id
WHERE {vis} AND o.superseded_at IS NULL AND o.status IN ('accepted', 'proposed') AND o.due_date = $3::date
ORDER BY o.created_at
"""

# The words were a Postgres regex on the title; titles are sealed now, so the match is made after the rows are opened.
_TRIP_WORDS = re.compile(r"\b(trip|flight|travel|holiday|vacation|tour)\b", re.I)

_CHANGED = """
SELECT am.id, am.amends_title AS title, am.amends_date AS due_date FROM amendments am
WHERE am.household_id = $1 AND am.status = 'proposed' AND am.created_at > $3 ORDER BY am.created_at LIMIT 10
"""


async def _events(r: dict, local: dt.datetime) -> list[tuple[str, str]]:
    """(ref, words) for each event this routine's trigger sees now and has not run for."""
    from familyos import calendar, grants
    vis = grants.VISIBLE_OBLIGATION
    out: list[tuple[str, str]] = []
    if r["trigger"] == "bill_arrived":
        for x in await pool().fetch(_BILLS.format(vis=vis), r["household_id"], r["member_id"], r["created_at"]):
            out.append((f"bill:{x['id']}", f"a bill arrived: {x['title']}" + (f", due {x['due_date']:%-d %b}" if x["due_date"] else "")))
    elif r["trigger"] == "date_changed":
        for x in await pool().fetch(_CHANGED, r["household_id"], r["member_id"], r["created_at"]):
            out.append((f"amend:{x['id']}", f"a later notice may have changed a date: {x['title']}" + (f" (was {x['due_date']:%-d %b})" if x["due_date"] else "")))
    elif r["trigger"] == "trip_soon":
        day = local.date() + dt.timedelta(days=r["trigger_days"] or 0)
        trips = [x for x in await pool().fetch(_TRIPS.format(vis=vis), r["household_id"], r["member_id"], day) if _TRIP_WORDS.search(x["title"] or "")]
        for x in trips[:10]:
            out.append((f"trip:{x['id']}:{day}", f"travel starts in {r['trigger_days']} days: {x['title']}"))
    elif r["trigger"] == "conflict":
        p = Principal(member_id=r["member_id"], household_id=r["household_id"], role="adult", display_name="")
        soon = await pool().fetch(
            "SELECT o.id, o.title FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id WHERE " + vis + " AND o.superseded_at IS NULL "
            "AND o.status IN ('accepted', 'proposed') AND o.due_date BETWEEN $3::date AND $4::date ORDER BY o.due_date LIMIT 40",
            r["household_id"], r["member_id"], local.date(), local.date() + dt.timedelta(days=7))
        clashes = await calendar.clashes_for(p, [x["id"] for x in soon])
        titles = {x["id"]: x["title"] for x in soon}
        for oid, against in clashes.items():
            out.append((f"clash:{oid}", f"{titles[oid]} clashes with {against[0]['summary']}"))
    return out


async def sweep(now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    out = {"sent": 0, "silent": 0, "waited": 0, "failed": 0, "already": 0}
    rows = await pool().fetch(
        "SELECT r.*, h.timezone FROM routines r JOIN households h ON h.id = r.household_id JOIN members m ON m.id = r.member_id "
        "WHERE r.active AND NOT r.paused AND h.status = 'active' AND m.role <> 'child'")
    for r in rows:
        local = _local(now, r["timezone"])
        row = dict(r)
        if row["trigger"] == "time":
            if local.hour < row["hour"] or (row["weekday"] is not None and local.weekday() != row["weekday"]) or row["last_run_on"] == local.date():
                continue
            async with clock.household(row["household_id"], row["member_id"]):
                out[await _run(row, local)] += 1
            continue
        try:
            async with clock.household(row["household_id"], row["member_id"]):
                found = await _events(row, local)
        except Exception:  # noqa: BLE001 - one routine's trigger must not stop the others
            logger.warning("routine %s could not look for its trigger", row["id"], exc_info=True)
            continue
        done = {x["event_ref"] for x in await pool().fetch("SELECT event_ref FROM routine_runs WHERE routine_id = $1 AND event_ref IS NOT NULL", row["id"])}
        for ref, words in [f for f in found if f[0] not in done][:MAX_EVENTS_PER_SWEEP]:
            async with clock.household(row["household_id"], row["member_id"]):
                out[await _run(row, local, context=words, ref=ref)] += 1
    return out


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    result = await sweep(now)
    return {**result, "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled() -> dict | None:
    return await jobs.ensure_recurring(KIND)


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("timezone",))


def describe() -> str:
    return f"Routines run from a sweep every {SWEEP_SECONDS // 60} minutes, inside each member's quiet hours and daily cap."
