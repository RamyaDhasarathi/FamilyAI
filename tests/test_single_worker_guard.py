"""The one-worker guard names the state held in memory and what breaks, and passes one worker (or none set). Workers under one server stay refused
even with FAMILYOS_MULTI_WORKER: they cannot be routed to the process that holds a phone socket, and cannot be told apart for the WhatsApp reader."""
import pytest

from familyos import main
from familyos.settings import settings


def test_more_than_one_worker_is_refused_with_the_state_named():
    with pytest.raises(RuntimeError) as err:
        main.check_single_worker("2")
    said = str(err.value)
    for needle in ("unlocked state", "taught lessons", "phone-driver sockets", "WhatsApp reader", "assistant",
                   "WEB_CONCURRENCY", "FAMILYOS_MULTI_WORKER", "separate single-worker processes", "docs/deploy.md"):
        assert needle in said, needle


def test_the_multi_worker_setting_does_not_open_the_door_to_workers_under_one_server(monkeypatch):
    monkeypatch.setattr(settings, "multi_worker", True)
    monkeypatch.setattr(settings, "whatsapp_worker", True)
    with pytest.raises(RuntimeError, match="route"):
        main.check_single_worker("4")
    assert main.check_single_worker("1") == 1


@pytest.mark.parametrize("raw", [None, "", "1", "junk"])
def test_one_worker_or_an_unreadable_value_starts(raw):
    assert main.check_single_worker(raw) == 1
