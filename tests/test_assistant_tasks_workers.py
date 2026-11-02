"""Assistant tasks with more than one worker: a running task names its worker and keeps a heartbeat in its row, so any worker can tell a task whose
worker died from one still running on another, and a task that was failed for a stalled heartbeat is not brought back by a late answer."""
import asyncio
import datetime as dt
import uuid

from familyos import assistant_tasks
from familyos.settings import settings
from familyos.worker import WORKER_ID
from tests.test_assistant_tasks import _ask, _connection, _settle


async def _task(database, family, status, *, started_at=None, heartbeat_at=None, created_at=None):
    conn = await _connection(family)
    tid = uuid.uuid4()
    await database.execute(
        "INSERT INTO assistant_tasks (id, household_id, member_id, connection_id, instruction, status, owner, started_at, heartbeat_at, created_at) "
        "VALUES ($1, $2, $3, $4, 'What needs me today?', $5, 'another:1:abc', $6, $7, COALESCE($8, NOW()))",
        tid, uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), uuid.UUID(str(conn["id"])), status, started_at, heartbeat_at, created_at)
    return tid


async def test_a_task_names_its_worker_and_beats_while_it_runs(family, database, monkeypatch):
    monkeypatch.setattr(assistant_tasks, "HEARTBEAT_SECONDS", 0.05)
    seen = {}

    async def slow(c, api_key, prompt, url, key):
        await asyncio.sleep(0.4)
        row = await database.fetchrow("SELECT owner, heartbeat_at, started_at FROM assistant_tasks WHERE status = 'running'")
        seen.update(owner=row["owner"], beats=row["heartbeat_at"] > row["started_at"])
        return "All quiet."
    monkeypatch.setattr(settings, "mcp_public_url", "https://example.test/mcp")
    monkeypatch.setitem(assistant_tasks.ADAPTERS, "claude", slow)
    tid = await _ask(family, await _connection(family))
    await _settle(family, tid)
    assert seen == {"owner": WORKER_ID, "beats": True}


async def test_a_task_with_a_fresh_heartbeat_on_another_worker_is_left_alone_and_a_silent_one_is_failed(family, database):
    now = await database.fetchval("SELECT NOW()")
    live = await _task(database, family, "running", started_at=now, heartbeat_at=now)
    dead = await _task(database, family, "running", started_at=now - dt.timedelta(minutes=5), heartbeat_at=now - dt.timedelta(minutes=4))
    never = await _task(database, family, "queued", created_at=now - dt.timedelta(minutes=11))
    waiting = await _task(database, family, "queued", created_at=now - dt.timedelta(minutes=1))
    assert await assistant_tasks.recover_stale() == 2
    status = {r["id"]: r["status"] for r in await database.fetch("SELECT id, status FROM assistant_tasks")}
    assert status[live] == "running" and status[waiting] == "queued" and status[dead] == "failed" and status[never] == "failed"
    assert "stopped" in await database.fetchval("SELECT error FROM assistant_tasks WHERE id = $1", dead)


async def test_a_late_answer_does_not_bring_back_a_task_that_was_failed(family, database, monkeypatch):
    monkeypatch.setattr(settings, "mcp_public_url", "https://example.test/mcp")

    async def stalls(c, api_key, prompt, url, key):
        await database.execute("UPDATE assistant_tasks SET heartbeat_at = NOW() - INTERVAL '5 minutes' WHERE status = 'running'")
        assert await assistant_tasks.recover_stale() == 1                      # another worker's sweep gives up on it
        return "Too late."
    monkeypatch.setitem(assistant_tasks.ADAPTERS, "claude", stalls)
    tid = await _ask(family, await _connection(family))
    await _settle(family, tid)
    row = await database.fetchrow("SELECT status, result FROM assistant_tasks WHERE id = $1", uuid.UUID(str(tid)))
    assert row["status"] == "failed" and row["result"] is None
