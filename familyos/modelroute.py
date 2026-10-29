"""One way to reach any language model, and a household's say over which one reads its words.

A *profile* is a named place a model runs: the deployment's default cloud model, the model on this machine, or any OpenAI-compatible
endpoint added in configuration (a confidential-inference provider, the family's own TEE-hosted server). Each profile carries a *trust
class*, which is what the family is told about where its words go:
  cloud         a model provider sees the text it is sent (Anthropic, OpenAI, any ordinary hosted API)
  confidential  the text is processed inside a verified trusted-execution environment run by a third party
  own           a machine the family or its operator controls (this one, or its own TEE hosting)
A household routes each task (extraction, ask) to a profile and may set a *floor*: the least private class its words may ever reach. A task
that would go below the floor is refused with a plain message, never quietly sent somewhere else. With nothing set, behaviour is exactly
what it was: the deployment's default, or the household's own machine if it had switched to one (the older local_models switch).

Profiles beyond the built-in two come from FAMILYOS_MODEL_PROFILES, a JSON list, with the secret named by `key_env` (an environment
variable) so no key sits in the setting itself:
  [{"name": "tee", "kind": "openai_compatible", "base_url": "https://llm.example.org/v1", "model": "qwen3-72b", "key_env": "TEE_KEY", "trust": "own"}]
kind is openai_compatible, openai or anthropic. A profile with an unknown trust class, a missing field or a name already taken is ignored
and logged, not guessed at.
"""
from __future__ import annotations

import functools
import json
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from familyos import audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

TRUST = {"cloud": 0, "confidential": 1, "own": 2}
TASKS = ("extraction", "ask")
KINDS = ("openai_compatible", "openai", "anthropic")
DEFAULT = "default"


@dataclass(frozen=True)
class Profile:
    name: str
    kind: str
    model: str
    trust: str
    base_url: str | None = None
    api_key: str = ""
    builtin: bool = False

    def where(self) -> str:
        return (urlsplit(self.base_url).hostname or "") if self.base_url else {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}.get(self.kind, "")


def _loopback(url: str | None) -> bool:
    """An address on this machine: where "own" can be seen to be true rather than said."""
    return (urlsplit(url or "").hostname or "").lower() in ("localhost", "127.0.0.1", "::1", "")


def _transport_ok(url: str | None) -> bool:
    """https anywhere, or http only to this machine: family text never crosses a network in the clear."""
    return not url or urlsplit(url).scheme == "https" or (urlsplit(url).scheme == "http" and _loopback(url))


@functools.lru_cache(maxsize=8)
def _specs(raw_json: str) -> tuple[dict, ...]:
    """The configured profiles that are usable, parsed once per distinct setting; the rest are logged once and dropped."""
    try:
        listed = json.loads(raw_json) if raw_json.strip() else []
    except ValueError:
        logger.warning("FAMILYOS_MODEL_PROFILES is not valid JSON; ignored")
        return ()
    kept: list[dict] = []
    seen = {"local", DEFAULT}
    for raw in listed if isinstance(listed, list) else []:
        try:
            name = str(raw["name"]).strip().lower()
            kind, model, trust = raw["kind"], str(raw["model"]), raw["trust"]
            if not name or name in seen or kind not in KINDS or trust not in TRUST or not model:
                raise ValueError("unusable profile")
            if kind == "openai_compatible" and not raw.get("base_url"):
                raise ValueError("an openai_compatible profile needs a base_url")
            if not _transport_ok(raw.get("base_url")):
                raise ValueError("a model address must be https unless it is on this machine")
            seen.add(name)
            kept.append({"name": name, "kind": kind, "model": model, "trust": trust, "base_url": raw.get("base_url") or None, "key_env": raw.get("key_env") or ""})
        except (KeyError, ValueError, TypeError):
            logger.warning("a model profile was ignored: %r", {k: v for k, v in raw.items() if k not in ("api_key", "key_env")} if isinstance(raw, dict) else raw)
    return tuple(kept)


def profiles() -> dict[str, Profile]:
    out: dict[str, Profile] = {}
    if settings.local_model and _transport_ok(settings.local_model_url):
        # "own" is true where it can be seen (this machine) or where the operator declares it (FAMILYOS_LOCAL_MODEL_TRUST=own, for hosting they run);
        # an address that is neither is an ordinary provider as far as a household's privacy floor is concerned.
        trust = "own" if _loopback(settings.local_model_url) or settings.local_model_trust == "own" else "cloud"
        out["local"] = Profile("local", "openai_compatible", settings.local_model, trust, settings.local_model_url, settings.local_model_key or "local", builtin=True)
    elif settings.local_model:
        logger.warning("FAMILYOS_LOCAL_MODEL_URL is plain http to another host; the local model is not offered")
    for x in _specs(settings.model_profiles):
        out[x["name"]] = Profile(x["name"], x["kind"], x["model"], x["trust"], x["base_url"], os.environ.get(x["key_env"], "") if x["key_env"] else "")
    return out


def default_trust() -> str:
    """The deployment's default is an ordinary hosted provider unless it has been pointed at a model on this machine."""
    return "cloud"


async def routing(household_id) -> dict:
    row = await pool().fetchrow("SELECT model_routing, local_models FROM households WHERE id = $1", household_id)
    saved = row["model_routing"] if isinstance(row["model_routing"], dict) else json.loads(row["model_routing"] or "{}")
    legacy = "local" if row["local_models"] and "local" in profiles() else DEFAULT
    return {"extraction": saved.get("extraction") or legacy, "ask": saved.get("ask") or legacy, "floor": saved.get("floor") or "cloud"}


def trust_of(name: str) -> str:
    if name == DEFAULT:
        return default_trust()
    prof = profiles().get(name)
    if prof is None:
        raise Invalid(f"there is no model profile called {name}")
    return prof.trust


def allowed(name: str, floor: str) -> bool:
    return TRUST[trust_of(name)] >= TRUST.get(floor, 0)


async def chosen(household_id, task: str) -> str:
    """The profile this household's task goes to, or Invalid if that would be below the household's floor."""
    r = await routing(household_id)
    name = r[task]
    if name != DEFAULT and name not in profiles():
        raise Invalid(f"this household's {task} model, {name}, is not configured on this server")
    if not allowed(name, r["floor"]):
        raise Invalid(f"this household reads its words only on a {r['floor']} model or better, and {name} is {trust_of(name)}; choose another model for {task} or lower the floor")
    return name


async def listing(p: Principal) -> dict:
    r = await routing(p.household_id)
    out = [{"name": DEFAULT, "kind": "deployment default", "model": settings.chat_model or settings.extraction_model, "trust": default_trust(), "where": "the hosted provider", "available": True}]
    out += [{"name": x.name, "kind": x.kind, "model": x.model, "trust": x.trust, "where": x.where(), "available": True} for x in profiles().values()]
    return {"profiles": out, "routing": r, "trust": {"cloud": "a model provider sees the text it is sent", "confidential": "processed inside a verified trusted-execution environment run by a third party",
                                                     "own": "a machine the family or its operator controls"}}


async def set_routing(p: Principal, *, extraction: str | None = None, ask: str | None = None, floor: str | None = None) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian chooses where the household's words are read")
    changes: dict = {}
    for task, name in (("extraction", extraction), ("ask", ask)):
        if name is not None:
            if name != DEFAULT and name not in profiles():
                raise Invalid(f"there is no model profile called {name}")
            changes[task] = name
    if floor is not None:
        if floor not in TRUST:
            raise Invalid("the floor is cloud, confidential or own")
        changes["floor"] = floor
    if not changes:
        raise Invalid("say what to change")
    now = {**await routing(p.household_id), **changes}
    for task in TASKS:
        if not allowed(now[task], now["floor"]):
            raise Invalid(f"{task} would go to {now[task]} ({trust_of(now[task])}), below the floor {now['floor']}; change that first")
    await pool().execute("UPDATE households SET model_routing = model_routing || $2::jsonb WHERE id = $1", p.household_id, changes)
    await audit.record(p.household_id, "household.models_set", actor_member_id=p.member_id, detail=changes)
    return await listing(p)


def extractor_for_profile(name: str):
    """A ready extractor for a named profile (the default is made by pipeline.make_extractor)."""
    from familyos.extraction.llm import ClaudeExtractor, OpenAIExtractor
    prof = profiles()[name]
    if prof.kind == "anthropic":
        out = ClaudeExtractor(api_key=prof.api_key, model="anthropic/" + prof.model, effort=settings.extraction_effort, base_url=prof.base_url)
    elif prof.kind == "openai":
        out = OpenAIExtractor(api_key=prof.api_key, model="openai/" + prof.model, effort=settings.extraction_effort, base_url=prof.base_url)
    else:
        out = OpenAIExtractor(api_key=prof.api_key or "none", model="x/" + prof.model, effort=None, base_url=prof.base_url)
    out.name = prof.name if prof.builtin or prof.kind == "openai_compatible" else out.name
    return out


async def extractor_for(household_id):
    from familyos.extraction import pipeline
    name = await chosen(household_id, "extraction")
    if name == DEFAULT:
        return pipeline.make_extractor()
    return extractor_for_profile(name)


async def model_for_ask(household_id):
    """The chat model for this household's Ask, honouring its routing and floor."""
    from familyos import chat
    name = await chosen(household_id, "ask")
    if name == DEFAULT:
        return chat.current_model()
    prof = profiles()[name]
    if prof.kind == "anthropic":
        return chat.AnthropicModel(api_key=prof.api_key, model=prof.model, base_url=prof.base_url)
    return chat.OpenAIModel(api_key=prof.api_key or "none", model=prof.model, base_url=prof.base_url) if prof.kind == "openai_compatible" else chat.OpenAIModel(api_key=prof.api_key, model=prof.model, base_url=prof.base_url)
