"""A recurring sweep comes back after a bad pass: one exception reschedules the job instead of ending it, and one person's failure
does not stop the rest of the pass."""
import datetime as dt

from familyos import nudges, whatsapp_watch
from tests.test_nudges import _capture, _pile


async def test_a_failed_heads_up_pass_still_reschedules(monkeypatch):
    async def broken(now=None):
        raise RuntimeError("the database blinked")
    monkeypatch.setattr(nudges, "sweep", broken)
    out = await nudges._handle({}, None)
    assert out["failed_pass"] == 1
    assert dt.datetime.fromisoformat(out["next_run_at"]) > dt.datetime.now(dt.UTC)


async def test_a_failed_whatsapp_pass_still_reschedules(monkeypatch):
    async def broken():
        raise RuntimeError("the reader fell over")
    monkeypatch.setattr(whatsapp_watch, "sweep", broken)
    out = await whatsapp_watch._handle({}, None)
    assert out["failed_pass"] == 1
    assert dt.datetime.fromisoformat(out["next_run_at"]) > dt.datetime.now(dt.UTC)


async def test_a_stale_lesson_sweep_that_breaks_does_not_stop_the_heads_ups(monkeypatch):
    from familyos import taught

    async def broken():
        raise RuntimeError("could not release")
    monkeypatch.setattr(taught, "expire_stale", broken)
    ran = []

    async def fine(now=None):
        ran.append(1)
        return {"told": 0}
    monkeypatch.setattr(nudges, "sweep", fine)
    out = await nudges._handle({}, None)
    assert ran == [1] and out["told"] == 0 and "next_run_at" in out


async def test_one_persons_failure_in_a_pass_does_not_stop_the_others(family, database, monkeypatch):
    await _pile(family, database)
    sent = _capture(monkeypatch)
    real = nudges.fresh_for
    calls = []

    async def first_fails(p, today):
        calls.append(p.member_id)
        if len(calls) == 1:
            raise RuntimeError("one bad record")
        return await real(p, today)
    monkeypatch.setattr(nudges, "fresh_for", first_fails)
    out = await nudges.sweep()
    assert out["failed"] == 1 and len(calls) >= 2
    assert out["told"] + out["nothing"] + out["waited"] == len(calls) - 1
    assert out["told"] >= 1 and len(sent) >= 1
