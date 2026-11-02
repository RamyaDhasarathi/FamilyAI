"""The WhatsApp reader with more than one worker: one process at a time on a member's profile, across workers, and only the worker that holds the
profile directories reads. The others say where to ask and take none of the sweeps."""
import uuid

import pytest

from familyos import jobs, whatsapp_watch
from familyos.execution import whatsapp_reader as wr
from familyos.identity import Invalid
from familyos.settings import settings


@pytest.fixture(autouse=True)
def _restore():
    before = wr.current_reader()
    yield
    wr.use_reader(before)


async def test_a_second_worker_cannot_open_a_profile_while_one_has_it(database):
    member = uuid.uuid4()
    async with wr.profile_lock(member):
        with pytest.raises(Invalid, match="another worker"):
            async with wr.profile_lock(member, seconds=0.4):
                raise AssertionError("two browsers on one profile")
        async with wr.profile_lock(uuid.uuid4(), seconds=0.4):       # another member's profile is another lock
            pass
    async with wr.profile_lock(member, seconds=0.4):                  # released: the next one has it
        pass


async def test_a_lock_is_released_when_the_work_inside_it_fails(database):
    member = uuid.uuid4()
    with pytest.raises(RuntimeError):
        async with wr.profile_lock(member):
            raise RuntimeError("the browser died")
    async with wr.profile_lock(member, seconds=0.4):
        pass


def test_only_the_worker_told_to_holds_the_profiles(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_watch_enabled", True)
    monkeypatch.setattr(settings, "multi_worker", False)
    assert wr.runs_here() and wr.configure() and isinstance(wr.current_reader(), wr.PlaywrightReader)      # one worker: it reads, flag or not
    monkeypatch.setattr(settings, "multi_worker", True)
    monkeypatch.setattr(settings, "whatsapp_worker", False)
    assert not wr.runs_here() and wr.configure() and isinstance(wr.current_reader(), wr.OtherWorkerReader)
    monkeypatch.setattr(settings, "whatsapp_worker", True)
    wr.configure()
    assert isinstance(wr.current_reader(), wr.PlaywrightReader)
    monkeypatch.setattr(settings, "whatsapp_watch_enabled", False)
    wr.configure()
    assert isinstance(wr.current_reader(), wr.NoReader)


async def test_a_worker_that_does_not_hold_the_profiles_says_where_to_ask():
    reader = wr.OtherWorkerReader()
    for call in (reader.start_link(uuid.uuid4(), "+10000000000"), reader.linked(uuid.uuid4()), reader.qr(uuid.uuid4()),
                 reader.read(uuid.uuid4(), ["Class parents"]), reader.forget(uuid.uuid4())):
        with pytest.raises(Invalid, match="FAMILYOS_WHATSAPP_WORKER"):
            await call


async def test_a_worker_that_declines_a_kind_does_not_see_its_jobs(family, monkeypatch):
    monkeypatch.setattr(jobs, "_declined", set())
    made = await jobs.create(whatsapp_watch.KIND, {}, household_id=uuid.UUID(family.household["id"]), member_id=None)
    assert made["id"] in [j["id"] for j in await jobs.due()]
    jobs.decline(whatsapp_watch.KIND)
    assert made["id"] not in [j["id"] for j in await jobs.due()]
