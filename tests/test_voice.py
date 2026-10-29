"""Voice: spoken words in, nothing kept, nothing done from them on their own."""
import uuid

import pytest

from familyos import audit, voice
from familyos.identity import Principal
from familyos.settings import settings


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


@pytest.fixture
def heard(monkeypatch):
    said = {"text": "when is the school fee due?"}

    def fake(data):
        return voice.Transcript(said["text"], "en", 4.0, "local")
    monkeypatch.setattr(voice, "_run_local", fake)
    monkeypatch.setattr(settings, "voice_engine", "local")
    return said


async def test_a_recording_becomes_words_and_the_audit_says_it_happened_not_what_was_said(family, database, heard):
    r = await family.client.post("/v1/voice/transcribe", headers={**family.h("amma"), "content-type": "audio/ogg"}, content=b"OggS" + b"\0" * 400)
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "when is the school fee due?", "language": "en", "seconds": 4.0, "engine": "local"}
    event = await database.fetchrow("SELECT action, detail::text AS d FROM audit_events WHERE action = 'voice.transcribed' ORDER BY id DESC LIMIT 1")
    assert event is not None and "school fee" not in event["d"] and '"words": 6' in event["d"] and '"engine": "local"' in event["d"]
    said = await audit.describe_for(_p(family), 5, None)
    assert any("the audio was not kept" in e["said"] for e in said)


async def test_voice_off_empty_and_oversized_audio_are_refused_plainly(family, database, heard, monkeypatch):
    monkeypatch.setattr(settings, "voice_engine", "off")
    r = await family.client.post("/v1/voice/transcribe", headers=family.h("amma"), content=b"x" * 10)
    assert r.status_code == 503 and "switched off" in r.text
    monkeypatch.setattr(settings, "voice_engine", "local")
    assert (await family.client.post("/v1/voice/transcribe", headers=family.h("amma"), content=b"")).status_code == 422
    monkeypatch.setattr(voice, "MAX_BYTES", 100)
    assert (await family.client.post("/v1/voice/transcribe", headers=family.h("amma"), content=b"x" * 101)).status_code == 422
    # A recording longer than the limit is refused after it is read, and not filed.
    monkeypatch.setattr(voice, "MAX_BYTES", 10_000_000)
    monkeypatch.setattr(settings, "voice_max_seconds", 2)
    assert (await family.client.post("/v1/voice/transcribe", headers=family.h("amma"), content=b"x" * 50)).status_code == 422


async def test_an_engine_that_fails_says_so_and_a_child_account_is_not_special(family, database, heard, monkeypatch):
    def broken(data):
        raise RuntimeError("model missing")
    monkeypatch.setattr(voice, "_run_local", broken)
    r = await family.client.post("/v1/voice/transcribe", headers=family.h("amma"), content=b"x" * 50)
    assert r.status_code == 503 and "could not read that" in r.text and "model missing" not in r.text


async def test_the_cloud_engine_posts_the_audio_to_the_named_endpoint_and_only_there(family, database, monkeypatch):
    monkeypatch.setattr(settings, "voice_engine", "cloud")
    monkeypatch.setattr(settings, "voice_cloud_url", "")
    r = await family.client.post("/v1/voice/transcribe", headers=family.h("amma"), content=b"x" * 50)
    assert r.status_code == 503 and "no address" in r.text
    seen = {}

    async def fake(data, content_type):
        seen["bytes"] = len(data)
        return voice.Transcript("pay the electricity bill", "en", 3.0, "cloud")
    monkeypatch.setattr(voice, "_run_cloud", fake)
    r = await family.client.post("/v1/voice/transcribe", headers={**family.h("amma"), "content-type": "audio/webm"}, content=b"x" * 50)
    assert r.json()["engine"] == "cloud" and seen["bytes"] == 50
    event = await database.fetchval("SELECT detail->>'engine' FROM audit_events WHERE action = 'voice.transcribed' ORDER BY id DESC LIMIT 1")
    assert event == "cloud"
