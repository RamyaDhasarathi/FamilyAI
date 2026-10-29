"""Taught lessons with more than one worker (FAMILYOS_MULTI_WORKER): the count of a member's lessons is shared, and a lesson held by another
worker is said to be, not mistaken for a missing one. The lesson's browser and phone socket stay on the worker that started it."""
import uuid

import pytest

from familyos import taught
from familyos.execution import screens
from familyos.identity import Invalid
from tests.test_taught import Phone, _p


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(screens, "SETTLE_STEP", 0)
    monkeypatch.setattr(screens, "SETTLE_READS", 2)
    monkeypatch.setattr(settings, "multi_worker", True)
    taught._lessons.clear()


async def test_a_lesson_is_a_row_while_it_lasts_and_goes_when_it_ends(family, database):
    shown = await taught.start(_p(family), "web", "https://school.example.com/news", driver=Phone(), release=None)
    row = await database.fetchrow("SELECT owner, kind, target FROM taught_lessons WHERE id = $1", shown["id"])
    assert row["kind"] == "web" and row["owner"]
    await taught.cancel(_p(family), shown["id"])
    assert await database.fetchval("SELECT count(*) FROM taught_lessons") == 0


async def test_the_limit_counts_lessons_held_by_any_worker(family, database):
    for _ in range(taught.MAX_LESSONS):                       # started on other workers: rows, and nothing in this process
        await database.execute(
            "INSERT INTO taught_lessons (id, household_id, member_id, owner, kind, target, expires_at) "
            "VALUES ($1, $2, $3, 'another:1:abc', 'phone', 'com.example.schoolapp', NOW() + INTERVAL '10 minutes')",
            uuid.uuid4(), uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]))
    with pytest.raises(Invalid, match="finish or cancel"):
        await taught.start(_p(family), "phone", "com.example.schoolapp")
    assert await taught.start(_p(family, "appa"), "phone", "com.example.schoolapp")    # another member is not held to amma's count


async def test_a_lesson_on_another_worker_is_said_to_be_and_an_unknown_one_is_not_found(family, database):
    lid = uuid.uuid4()
    await database.execute(
        "INSERT INTO taught_lessons (id, household_id, member_id, owner, kind, target, expires_at) "
        "VALUES ($1, $2, $3, 'another:1:abc', 'phone', 'com.example.schoolapp', NOW() + INTERVAL '10 minutes')",
        lid, uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]))
    with pytest.raises(taught.HeldElsewhere):
        await taught.show(_p(family), lid)
    with pytest.raises(taught.NotFound):
        await taught.show(_p(family, "appa"), lid)            # not appa's lesson: nothing to say about it
    with pytest.raises(taught.NotFound):
        await taught.show(_p(family), uuid.uuid4())
    r = await family.client.get(f"/v1/me/teach/{lid}", headers=family.h("amma"))
    assert r.status_code == 409 and r.json()["error"] == "held_by_another_worker"


async def test_rows_a_dead_worker_left_are_swept_after_they_expire(family, database):
    for minutes in (-10, -2, 10):
        await database.execute(
            "INSERT INTO taught_lessons (id, household_id, member_id, owner, kind, target, expires_at) "
            "VALUES ($1, $2, $3, 'dead:1:abc', 'phone', 'com.example.schoolapp', NOW() + make_interval(mins => $4))",
            uuid.uuid4(), uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), minutes)
    await taught.expire_stale()
    assert await database.fetchval("SELECT count(*) FROM taught_lessons") == 2           # the one expired ten minutes ago is gone; the grace keeps the other


async def test_with_one_worker_no_row_is_written(family, database, monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "multi_worker", False)
    await taught.start(_p(family), "web", "https://school.example.com/news", driver=Phone(), release=None)
    assert await database.fetchval("SELECT count(*) FROM taught_lessons") == 0
