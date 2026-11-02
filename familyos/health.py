"""Health numbers from the phone's Health app, for the member who owns them and nobody else.

- Opt-in is per member and theirs alone. Switching sync off deletes every row kept for them.
- Only one summary per day (steps, sleep, resting heart rate, workouts); never raw samples, never a trail of heartbeats.
- Nobody else sees it: not a guardian, not the household. Ask uses it only for the asker's own questions.
- FamilyOS states what the numbers say. It gives no medical advice and flags nothing as a condition.
"""
from __future__ import annotations

import datetime as dt

from familyos import audit, clock
from familyos.db import pool
from familyos.identity import NotAllowed, NotFound, Principal
from familyos.settings import settings

MAX_DAYS = 400            # one upload may carry a first backfill, no more
KEEP_DAYS = 400           # older rows are dropped on the next sync


def enabled() -> bool:
    return bool(settings.health_enabled)


def require() -> None:
    if not enabled():
        raise NotFound("health")


async def status(p: Principal) -> dict:
    if not enabled():
        return {"available": False, "sync": False, "last_day": None}
    row = await pool().fetchrow("SELECT health_sync FROM members WHERE id = $1", p.member_id)
    last = await pool().fetchval("SELECT max(day) FROM health_daily WHERE member_id = $1", p.member_id)
    return {"available": True, "sync": bool(row and row["health_sync"]), "last_day": last}


async def set_sync(p: Principal, on: bool) -> dict:
    require()
    if p.role == "child":
        raise NotAllowed("children do not sync health data")
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("UPDATE members SET health_sync = $2 WHERE id = $1", p.member_id, on)
        if not on:
            await conn.execute("DELETE FROM health_daily WHERE member_id = $1", p.member_id)
        await audit.record(p.household_id, "health.sync", actor_member_id=p.member_id, target_type="member", target_id=p.member_id,
                           detail={"on": on}, conn=conn)
    return await status(p)


async def upload(p: Principal, days: list[dict]) -> int:
    """Upsert the phone's daily summaries. Refused while the member is not syncing."""
    require()
    today = clock.today()
    rows = [d for d in days[:MAX_DAYS] if today - dt.timedelta(days=KEEP_DAYS) <= d["day"] <= today + dt.timedelta(days=1)]
    async with pool().acquire() as conn, conn.transaction():
        # The switch is read inside the transaction, under a share lock: a switch-off (which deletes every row) either
        # commits first and this upload is refused, or waits for this upload and then deletes what it wrote. Without
        # the lock a late upload could put rows back after "off" had deleted them.
        on = await conn.fetchval("SELECT health_sync FROM members WHERE id = $1 FOR SHARE", p.member_id)
        if not on:
            raise NotAllowed("health sync is off")
        for d in rows:
            await conn.execute(
                """INSERT INTO health_daily (member_id, household_id, day, steps, sleep_minutes, resting_hr, workouts, workout_minutes, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
                   ON CONFLICT (member_id, day) DO UPDATE SET steps = EXCLUDED.steps, sleep_minutes = EXCLUDED.sleep_minutes,
                     resting_hr = EXCLUDED.resting_hr, workouts = EXCLUDED.workouts, workout_minutes = EXCLUDED.workout_minutes, updated_at = now()""",
                p.member_id, p.household_id, d["day"], d.get("steps"), d.get("sleep_minutes"), d.get("resting_hr"),
                d.get("workouts", 0), d.get("workout_minutes", 0))
        await conn.execute("DELETE FROM health_daily WHERE member_id = $1 AND day < $2", p.member_id, today - dt.timedelta(days=KEEP_DAYS))
    return len(rows)


async def recent(p: Principal, days: int = 14) -> list[dict]:
    if not enabled():
        return []
    since = clock.today() - dt.timedelta(days=days - 1)
    rows = await pool().fetch(
        "SELECT day, steps, sleep_minutes, resting_hr, workouts, workout_minutes FROM health_daily WHERE member_id = $1 AND day >= $2 ORDER BY day DESC",
        p.member_id, since)
    return [dict(r) for r in rows]


def line(rows: list[dict]) -> str | None:
    """One sentence of the asker's last week, for Ask to cite. None when there is nothing."""
    week = rows[:7]
    if not week:
        return None
    bits = []
    steps = [r["steps"] for r in week if r["steps"] is not None]
    if steps:
        bits.append(f"averaged {round(sum(steps) / len(steps)):,} steps a day")
    sleep = [r["sleep_minutes"] for r in week if r["sleep_minutes"]]
    if sleep:
        m = round(sum(sleep) / len(sleep))
        bits.append(f"slept {m // 60} h {m % 60:02d} min a night")
    hr = [r["resting_hr"] for r in week if r["resting_hr"]]
    if hr:
        bits.append(f"resting heart rate around {round(sum(hr) / len(hr))}")
    works = sum(r["workouts"] for r in week)
    if works:
        bits.append(f"{works} workout{'s' if works != 1 else ''}")
    return ("In the last " + str(len(week)) + " days with data you " + ", ".join(bits) + ".") if bits else None
