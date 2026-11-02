"""The durable job engine copied from Orbit: resume from checkpoints, never repeat a cached call."""
from familyos import jobs

calls = []


async def _two_steps(job, ctx):
    await ctx.plan(["fetch", "finish"])
    if not ctx.done("0"):
        await ctx.step("0")
        value = await ctx.call("fetch", lambda: calls.append("fetch") or 41)
        await ctx.checkpoint(state={"value": value})
        await ctx.finish_step("0")
        if job["spec"].get("crash_once") and job["attempts"] == 1:
            raise RuntimeError("crash after step 0")
    await ctx.step("1")
    await ctx.finish_step("1")
    return {"answer": ctx.job["state"]["value"] + 1}


async def _asks(job, ctx):
    if not (ctx.job.get("state") or {}).get("answer"):
        await ctx.ask("Which child is this for?")
    return {"for": ctx.job["state"]["answer"]}


async def test_a_job_resumes_from_its_checkpoint_without_repeating_calls(database):
    calls.clear()
    jobs.register("two_steps", _two_steps)
    job = await jobs.create("two_steps", {"crash_once": True})
    first = await jobs.attach(job["id"])
    assert first["status"] == "queued" and "crash after step 0" in first["error"]
    second = await jobs.attach(job["id"])
    assert second["status"] == "succeeded" and second["result"] == {"answer": 42}
    assert calls == ["fetch"]
    kinds = [e["kind"] for e in await jobs.events(job["id"])]
    assert kinds[:2] == ["created", "started"] and "resumed" in kinds and kinds[-1] == "settled"


async def test_two_workers_cannot_claim_the_same_job(database):
    jobs.register("two_steps", _two_steps)
    job = await jobs.create("two_steps", {})
    assert await jobs.claim(job) is not None
    assert await jobs.claim(job) is None


async def test_a_job_can_wait_for_a_member(family):
    jobs.register("asks", _asks)
    job = await jobs.create("asks", {}, household_id=family.household["id"], member_id=family.amma["id"])
    paused = await jobs.attach(job["id"])
    assert paused["status"] == "waiting_input" and paused["question"] == "Which child is this for?"
    assert await jobs.answer(job["id"], family.appa["id"], "older") is None     # not asked of Appa
    await jobs.answer(job["id"], family.amma["id"], "older")
    assert (await jobs.attach(job["id"]))["result"] == {"for": "older"}


async def test_ensure_recurring_makes_exactly_one_live_job_even_when_called_at_once(database):
    import asyncio
    jobs.register("tidy_sweep", _two_steps)
    made = await asyncio.gather(*[jobs.ensure_recurring("tidy_sweep") for _ in range(8)])
    assert len([m for m in made if m]) == 1
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = 'tidy_sweep'") == 1
    assert await jobs.ensure_recurring("tidy_sweep") is None
    await database.execute("UPDATE jobs SET status = 'cancelled' WHERE kind = 'tidy_sweep'")
    assert await jobs.ensure_recurring("tidy_sweep") is not None       # a finished one is replaced


async def test_the_database_refuses_a_second_live_recurring_job(database):
    import asyncpg
    import pytest
    jobs.register("tidy_sweep", _two_steps)
    await jobs.create("tidy_sweep", {}, recurring=True)
    with pytest.raises(asyncpg.UniqueViolationError):
        await jobs.create("tidy_sweep", {}, recurring=True)


async def test_the_migration_dedupes_a_table_that_already_has_duplicates_and_can_run_twice(database):
    from pathlib import Path

    import familyos
    sql = (Path(familyos.__file__).parent / "migrations" / "0089_recurring_jobs.sql").read_text()
    await database.execute("DROP INDEX jobs_one_live_recurring_idx")
    jobs.register("nudges_sweep", _two_steps)
    for _ in range(3):
        await jobs.create("nudges_sweep", {})
    await database.execute(sql)
    live = await database.fetch("SELECT recurring FROM jobs WHERE kind = 'nudges_sweep' AND status NOT IN ('cancelled')")
    assert len(live) == 1 and live[0]["recurring"] is True
    await database.execute(sql)                                       # idempotent
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = 'nudges_sweep' AND status = 'cancelled'") == 2
