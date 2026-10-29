"""One adapter in front of every model: profiles with a trust class, per-household routing, and a floor that refuses rather than leaks."""
import json
import types
import uuid

import pytest

from familyos import chat, modelroute
from familyos.extraction.llm import OpenAIExtractor
from familyos.identity import Invalid
from familyos.settings import settings

PROFILES = json.dumps([
    {"name": "tee", "kind": "openai_compatible", "base_url": "https://llm.family.example/v1", "model": "qwen3-72b", "key_env": "TEE_TEST_KEY", "trust": "own"},
    {"name": "priv", "kind": "openai_compatible", "base_url": "https://priv.example/v1", "model": "llama-3.3-70b", "trust": "confidential"},
    {"name": "bad trust", "kind": "openai_compatible", "base_url": "https://x/v1", "model": "m", "trust": "unbreakable"},
    {"name": "tee", "kind": "openai_compatible", "base_url": "https://dup/v1", "model": "dup", "trust": "own"},
    {"name": "nourl", "kind": "openai_compatible", "model": "m", "trust": "own"},
    {"name": "default", "kind": "openai", "model": "m", "trust": "cloud"},
])


@pytest.fixture(autouse=True)
def _profiles(monkeypatch):
    monkeypatch.setattr(settings, "model_profiles", PROFILES)
    monkeypatch.setattr(settings, "local_model", "")
    monkeypatch.setenv("TEE_TEST_KEY", "sekret-from-env")


def test_profiles_come_from_configuration_and_bad_ones_are_ignored_not_guessed():
    got = modelroute.profiles()
    assert set(got) == {"tee", "priv"}
    assert got["tee"].trust == "own" and got["tee"].api_key == "sekret-from-env" and got["tee"].where() == "llm.family.example"
    assert got["priv"].api_key == "" and got["priv"].trust == "confidential"


def test_the_local_machine_is_a_built_in_own_profile(monkeypatch):
    monkeypatch.setattr(settings, "local_model", "qwen3:8b")
    assert modelroute.profiles()["local"].trust == "own" and modelroute.profiles()["local"].builtin


def test_the_built_in_local_profile_is_own_only_where_it_runs_here_or_the_operator_says_so(monkeypatch):
    """The address is what can be checked: a model on another host is the operator's word, never a default, and a floor of "own" must not be met by a guess."""
    monkeypatch.setattr(settings, "local_model", "qwen3:8b")
    for url in ("http://localhost:11434/v1", "http://127.0.0.1:8000/v1", "http://[::1]:8000/v1"):
        monkeypatch.setattr(settings, "local_model_url", url)
        assert modelroute.profiles()["local"].trust == "own", url
    monkeypatch.setattr(settings, "local_model_url", "https://models.example.org/v1")
    assert modelroute.profiles()["local"].trust == "cloud"                                    # another host: not own until declared
    monkeypatch.setattr(settings, "local_model_trust", "own")
    assert modelroute.profiles()["local"].trust == "own"                                      # the operator's declaration, for hosting they run


def test_a_model_address_that_would_send_text_in_the_clear_to_another_host_is_not_used(monkeypatch):
    monkeypatch.setattr(settings, "local_model", "qwen3:8b")
    monkeypatch.setattr(settings, "local_model_trust", "own")
    monkeypatch.setattr(settings, "local_model_url", "http://models.example.org/v1")
    assert "local" not in modelroute.profiles()                                               # plain http beyond this machine, even if declared own
    monkeypatch.setattr(settings, "model_profiles", json.dumps([
        {"name": "clear", "kind": "openai_compatible", "base_url": "http://llm.family.example/v1", "model": "m", "trust": "own"},
        {"name": "here", "kind": "openai_compatible", "base_url": "http://127.0.0.1:9000/v1", "model": "m", "trust": "own"},
        {"name": "tls", "kind": "openai_compatible", "base_url": "https://llm.family.example/v1", "model": "m", "trust": "own"}]))
    assert set(modelroute.profiles()) == {"here", "tls"}


async def test_a_household_starts_on_the_default_and_a_guardian_routes_extraction_to_its_own_model(family):
    h = family.h("amma")
    got = (await family.client.get("/v1/household/models", headers=h)).json()
    assert got["routing"] == {"extraction": "default", "ask": "default", "floor": "cloud"}
    assert [p["name"] for p in got["profiles"]] == ["default", "tee", "priv"] and "sekret" not in json.dumps(got)
    out = await family.client.put("/v1/household/models", headers=h, json={"extraction": "tee", "ask": "priv"})
    assert out.status_code == 200 and out.json()["routing"]["extraction"] == "tee"
    ex = await modelroute.extractor_for(uuid.UUID(family.household["id"]))
    assert isinstance(ex, OpenAIExtractor) and ex.name == "tee" and ex._base_url == "https://llm.family.example/v1" and ex.effort is None
    asked = await chat.model_for(uuid.UUID(family.household["id"]))
    assert asked.name == "local" and asked.model == "llama-3.3-70b"      # OpenAIModel names a base_url model "local"; its model and address are the profile's


async def test_the_floor_refuses_a_lower_class_and_is_never_bypassed_quietly(family):
    h = family.h("amma")
    hid = uuid.UUID(family.household["id"])
    refused = await family.client.put("/v1/household/models", headers=h, json={"floor": "confidential"})
    assert refused.status_code in (400, 422) and "below the floor" in refused.text          # the default is cloud: setting the floor first would strand it
    assert (await family.client.put("/v1/household/models", headers=h, json={"extraction": "priv", "ask": "tee", "floor": "confidential"})).status_code == 200
    assert (await modelroute.extractor_for(hid)).name == "priv"                               # a confidential profile is read through the compatible adapter and keeps its own name
    low = await family.client.put("/v1/household/models", headers=h, json={"ask": "default"})
    assert low.status_code in (400, 422)
    await family.client.put("/v1/household/models", headers=h, json={"floor": "own", "extraction": "tee", "ask": "tee"})
    with pytest.raises(Invalid, match="below|only on"):
        await modelroute.set_routing(types.SimpleNamespace(is_guardian=True, household_id=hid, member_id=hid), extraction="priv")


async def test_a_profile_that_is_removed_from_configuration_stops_the_household_not_leaks_it(family, monkeypatch):
    hid = uuid.UUID(family.household["id"])
    await family.client.put("/v1/household/models", headers=family.h("amma"), json={"extraction": "tee"})
    monkeypatch.setattr(settings, "model_profiles", "")
    with pytest.raises(Invalid, match="not configured"):
        await modelroute.extractor_for(hid)


async def test_only_a_guardian_chooses_and_the_old_local_switch_still_means_the_local_model(family, database, monkeypatch):
    assert (await family.client.put("/v1/household/models", headers=family.h("paati"), json={"extraction": "tee"})).status_code == 403
    assert (await family.client.put("/v1/household/models", headers=family.h("amma"), json={"extraction": "nope"})).status_code in (400, 422)
    assert (await family.client.put("/v1/household/models", headers=family.h("amma"), json={})).status_code in (400, 422)
    monkeypatch.setattr(settings, "local_model", "qwen3:8b")
    await database.execute("UPDATE households SET local_models = TRUE WHERE id = $1", uuid.UUID(family.household["id"]))
    got = (await family.client.get("/v1/household/models", headers=family.h("amma"))).json()
    assert got["routing"]["extraction"] == "local" and got["routing"]["ask"] == "local"


def test_every_profile_kind_forwards_its_configured_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "model_profiles", json.dumps([
        {"name": "a", "kind": "anthropic", "base_url": "https://a.example", "model": "m", "trust": "own"},
        {"name": "o", "kind": "openai", "base_url": "https://o.example/v1", "model": "m", "trust": "own"}]))
    assert modelroute.extractor_for_profile("a")._base_url == "https://a.example"
    assert modelroute.extractor_for_profile("o")._base_url == "https://o.example/v1"


async def test_an_errand_generalist_is_hosted_so_it_obeys_the_floor(family):
    from familyos import errands
    hid = uuid.UUID(family.household["id"])
    assert await errands._generalist_allowed(hid)
    r = await family.client.put("/v1/household/models", headers=family.h("amma"), json={"extraction": "tee", "ask": "tee", "floor": "own"})
    assert r.status_code == 200
    assert not await errands._generalist_allowed(hid)


async def test_planning_uses_the_households_model_not_the_deployments(family, monkeypatch):
    monkeypatch.setattr(chat, "_model", chat.RefusingModel(), raising=False)
    await family.client.put("/v1/household/models", headers=family.h("amma"), json={"ask": "tee"})
    assert not isinstance(await chat.model_for(uuid.UUID(family.household["id"])), chat.RefusingModel)
