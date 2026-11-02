"""Startup and the schema: a deployment whose schema is managed elsewhere
(our database role may not run DDL) starts without migrating; every other
deployment migrates as before. Development sign-in is said out loud."""
import logging

import pytest

from familyos import main
from familyos.settings import settings


class Stop(Exception):
    """Ends startup right after the schema step, before jobs and workers."""


@pytest.fixture
def startup(monkeypatch):
    calls = []

    async def connect(*args, **kwargs):
        return None

    async def migrate(*args, **kwargs):
        calls.append("migrate")
        return []

    def stop():
        raise Stop

    monkeypatch.setattr(main.db, "connect", connect)
    monkeypatch.setattr(main.db, "migrate", migrate)
    monkeypatch.setattr(main, "register_job_handlers", stop)

    async def run():
        with pytest.raises(Stop):
            async with main.lifespan(main.create_app(with_lifespan=False)):
                pass
        return calls
    return run


async def test_startup_migrates_by_default(startup, monkeypatch):
    monkeypatch.setattr(settings, "auto_migrate", True)
    assert await startup() == ["migrate"]


async def test_startup_skips_migrations_when_the_schema_is_managed_elsewhere(startup, monkeypatch, caplog):
    monkeypatch.setattr(settings, "auto_migrate", False)
    with caplog.at_level(logging.WARNING, logger="familyos"):
        assert await startup() == []
    assert "FAMILYOS_AUTO_MIGRATE=false" in caplog.text


async def test_development_sign_in_is_announced_at_startup(startup, monkeypatch, caplog):
    monkeypatch.setattr(settings, "dev_sign_in", True)
    with caplog.at_level(logging.WARNING, logger="familyos"):
        await startup()
    assert "FAMILYOS_DEV_SIGN_IN is ON" in caplog.text


async def test_nothing_is_announced_when_development_sign_in_is_off(startup, monkeypatch, caplog):
    monkeypatch.setattr(settings, "dev_sign_in", False)
    with caplog.at_level(logging.WARNING, logger="familyos"):
        await startup()
    assert "FAMILYOS_DEV_SIGN_IN" not in caplog.text
