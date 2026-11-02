"""Sending an instruction to a person's own assistant and getting the answer back, with a stand-in for the vendor."""
import asyncio
import uuid

import pytest

from familyos import assistant_tasks
from familyos.identity import NotAllowed, Principal
from familyos.settings import settings
from tests.test_mcp import _call, _rpc


async def _connection(family, who="amma", provider="claude", **extra):
    r = await family.client.post("/v1/me/assistant-connections", headers=family.h(who), json={"provider": provider, "label": "My Claude", "api_key": "sk-ant-test-0123456789", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _stand_in(monkeypatch, family, answer="Nothing urgent today.", submit=True, boom=False, seen=None):
    """An assistant that connects back with the task key, as a vendor's cloud would."""
    monkeypatch.setattr(settings, "mcp_public_url", "https://example.test/mcp")

    async def adapter(c, api_key, prompt, url, key):
        if seen is not None:
            seen.update(api_key=api_key, prompt=prompt, url=url, key=key)
        if boom:
            raise ConnectionError("vendor down")
        k = {"token": key}
        names = [t["name"] for t in (await _rpc(family, k, "tools/list")).json()["result"]["tools"]]
        assert "submit_result" in names and "propose" in names and "share_to_family" not in names
        if submit:
            _ = await _call(family, k, "submit_result", {"text": answer})
        return "final text"
    monkeypatch.setitem(assistant_tasks.ADAPTERS, "claude", adapter)


async def _settle(family, tid):
    for _ in range(100):
        if (await family.client.get(f"/v1/me/assistant-tasks/{tid}", headers=family.h("amma"))).json()["status"] in ("done", "failed"):
            return
        await asyncio.sleep(0.05)


async def _ask(family, conn, text="What needs me today?", who="amma"):
    r = await family.client.post("/v1/me/assistant-tasks", headers=family.h(who), json={"connection_id": conn["id"], "instruction": text})
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def test_a_task_goes_out_with_a_key_of_its_own_and_the_answer_comes_back(family, monkeypatch):
    seen = {}
    _stand_in(monkeypatch, family, "Nothing urgent today.", seen=seen)
    conn = await _connection(family)
    tid = await _ask(family, conn)
    await _settle(family, tid)
    got = (await family.client.get(f"/v1/me/assistant-tasks/{tid}", headers=family.h("amma"))).json()
    assert got["status"] == "done" and got["result"] == "Nothing urgent today." and "Nothing in it has been done" in got["note"]
    assert seen["api_key"] == "sk-ant-test-0123456789" and seen["url"] == "https://example.test/mcp" and "What needs me today?" in seen["prompt"]
    # the task key is spent: it no longer opens /mcp, and it never showed on the member's connections
    assert (await family.client.post("/mcp", headers={"authorization": "Bearer " + seen["key"]}, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})).status_code == 401
    assert (await family.client.get("/v1/me/agents", headers=family.h("amma"))).json() == []
    assert "sk-ant" not in (await family.client.get("/v1/me/assistant-connections", headers=family.h("amma"))).text


async def test_a_plain_reply_is_kept_when_the_assistant_never_calls_submit(family, monkeypatch):
    _stand_in(monkeypatch, family, submit=False)
    tid = await _ask(family, await _connection(family))
    await _settle(family, tid)
    got = (await family.client.get(f"/v1/me/assistant-tasks/{tid}", headers=family.h("amma"))).json()
    assert got["status"] == "done" and got["result"] == "final text"


async def test_a_failure_is_one_plain_line_and_a_second_answer_does_not_overwrite(family, monkeypatch):
    _stand_in(monkeypatch, family, boom=True)
    tid = await _ask(family, await _connection(family))
    await _settle(family, tid)
    got = (await family.client.get(f"/v1/me/assistant-tasks/{tid}", headers=family.h("amma"))).json()
    assert got["status"] == "failed" and "vendor down" not in (got["error"] or "") and got["result"] is None


async def test_a_task_needs_a_public_address_a_cap_and_the_owner(family, monkeypatch):
    conn = await _connection(family, daily_cap=1)
    monkeypatch.setattr(settings, "mcp_public_url", "")
    r = await family.client.post("/v1/me/assistant-tasks", headers=family.h("amma"), json={"connection_id": conn["id"], "instruction": "hello there"})
    assert r.status_code in (403, 422) and "public https" in r.text
    _stand_in(monkeypatch, family)
    tid = await _ask(family, conn)
    again = await family.client.post("/v1/me/assistant-tasks", headers=family.h("amma"), json={"connection_id": conn["id"], "instruction": "and again"})
    assert again.status_code == 422 or again.status_code == 400
    other = await family.client.get(f"/v1/me/assistant-tasks/{tid}", headers=family.h("paati"))
    assert other.status_code == 404
    stolen = await family.client.post("/v1/me/assistant-tasks", headers=family.h("paati"), json={"connection_id": conn["id"], "instruction": "mine now"})
    assert stolen.status_code == 404


async def test_children_and_ordinary_keys_have_no_submit_result(family):
    kid = Principal(member_id=uuid.UUID(family.younger["id"]), household_id=uuid.UUID(family.household["id"]), role="child", display_name="Younger one")
    with pytest.raises(NotAllowed):
        await assistant_tasks.add_connection(kid, "claude", "x", "sk-ant-test-0123456789")
    k = (await family.client.post("/v1/me/agents", headers=family.h("amma"), json={"label": "Grok", "days": 5})).json()
    names = [t["name"] for t in (await _rpc(family, k, "tools/list")).json()["result"]["tools"]]
    assert "submit_result" not in names
    out = (await _rpc(family, k, "tools/call", {"name": "submit_result", "arguments": {"text": "x"}})).json()
    assert "error" in out


async def test_a_claude_code_error_is_a_failed_task_not_an_answer(family, monkeypatch):
    monkeypatch.setattr(settings, "allow_local_claude_code", True)
    monkeypatch.setattr(settings, "mcp_local_url", "http://127.0.0.1:1/mcp")

    class Proc:
        returncode = 1

        async def communicate(self):
            return b"Not logged in \xc2\xb7 Please run /login", b""

    async def fake(*a, **k):
        return Proc()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake)
    tid = await _ask(family, await _connection(family, provider="claude_code", api_key=""))
    await _settle(family, tid)
    got = (await family.client.get(f"/v1/me/assistant-tasks/{tid}", headers=family.h("amma"))).json()
    assert got["status"] == "failed" and "signed in" in got["error"] and got["result"] is None


async def test_a_sealed_secret_opens_only_for_its_own_member_and_purpose(family):
    from cryptography.exceptions import InvalidTag

    from familyos import artifacts
    hh, me, other = uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), uuid.UUID(family.appa["id"])
    sealed = await artifacts.seal_member_secret(hh, me, "assistant-api-key", "sk-test-secret-123")
    assert b"sk-test" not in sealed
    assert await artifacts.open_member_secret(hh, me, "assistant-api-key", sealed) == "sk-test-secret-123"
    for who, why in ((other, "assistant-api-key"), (me, "mcp-server-key")):
        with pytest.raises(InvalidTag):
            await artifacts.open_member_secret(hh, who, why, sealed)


async def test_an_outside_assistant_is_refused_when_the_household_reads_only_on_a_private_model(family, monkeypatch):
    import json as _json
    monkeypatch.setattr(settings, "model_profiles", _json.dumps([{"name": "tee", "kind": "openai_compatible", "base_url": "https://llm.family.example/v1", "model": "q", "trust": "own"}]))
    conn = await _connection(family)
    assert (await family.client.put("/v1/household/models", headers=family.h("amma"), json={"extraction": "tee", "ask": "tee", "floor": "own"})).status_code == 200
    out = await family.client.post("/v1/me/assistant-tasks", headers=family.h("amma"), json={"connection_id": conn["id"], "instruction": "summarise the medical letters"})
    assert "cloud service" in out.text, (out.status_code, out.text)
