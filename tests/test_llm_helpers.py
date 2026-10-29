"""The provider fixes carried over from the old app: the Anthropic workspace
header, schemas told in words to a server that does not enforce them, a
schema Anthropic will not compile sent as instructions instead, and JSON
answers wrapped in a code fence."""
import datetime as dt
import json
from types import SimpleNamespace

import pytest

from familyos import chat
from familyos.extraction import llm
from familyos.extraction.parse import Page, ParsedDocument
from familyos.settings import settings

NOTICE = ParsedDocument(media_type="text/plain", pages=[Page(number=1, text="The trip fee of Rs. 850 must be paid by 31/10/2026.")])
ANSWER = {"actionable": True, "non_actionable_reason": None, "claims": []}


# ----------------------------------------------------------------------------
# JSON answers
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '  {"a": 1}\n',
    '```json\n{"a": 1}\n```',
    '```\n{"a": 1}\n```',
])
def test_an_answer_is_read_with_or_without_a_code_fence(text):
    assert llm.loads_answer(text) == {"a": 1}


def test_an_answer_that_is_not_json_still_fails():
    with pytest.raises(json.JSONDecodeError):
        llm.loads_answer("Sure! Here is the answer.")


# ----------------------------------------------------------------------------
# the Anthropic workspace header
# ----------------------------------------------------------------------------

def test_no_workspace_means_no_header(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_workspace_id", "")
    assert llm.anthropic_headers() is None
    client = llm.ClaudeExtractor(api_key="sk-ant-test", model="claude-opus-5-5")._get_client()
    assert "anthropic-workspace-id" not in client.default_headers


def test_a_workspace_is_named_on_every_anthropic_client(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_workspace_id", " wrkspc_test ")
    assert llm.anthropic_headers() == {"anthropic-workspace-id": "wrkspc_test"}
    extractor = llm.ClaudeExtractor(api_key="sk-ant-test", model="claude-opus-5-5")._get_client()
    chat_model = chat.AnthropicModel(api_key="sk-ant-test", model="claude-sonnet-5-5")._get_client()
    for client in (extractor, chat_model):
        assert client.default_headers["anthropic-workspace-id"] == "wrkspc_test"


# ----------------------------------------------------------------------------
# schemas Anthropic will not compile, and servers that do not enforce them
# ----------------------------------------------------------------------------

def test_the_chat_turn_is_sent_as_instructions_to_anthropic():
    shape = chat._anthropic_shape("SYSTEM", chat.OUTPUT_SCHEMA)
    assert chat._unions(chat.OUTPUT_SCHEMA) > chat.ANTHROPIC_MAX_UNIONS
    assert "output_config" not in shape
    assert shape["system"].startswith("SYSTEM") and '"proposals"' in shape["system"]


def test_a_small_schema_is_still_enforced_by_anthropic():
    schema = {"type": "object", "properties": {"index": {"type": ["integer", "null"]}}, "required": ["index"]}
    shape = chat._anthropic_shape("SYSTEM", schema)
    assert shape == {"system": "SYSTEM", "output_config": {"format": {"type": "json_schema", "schema": schema}}}


def test_nullable_choices_in_the_chat_turn_are_written_the_way_anthropic_accepts():
    item = chat.OUTPUT_SCHEMA["properties"]["proposals"]["items"]["properties"]
    for name in ("part", "shape", "status"):
        assert "enum" not in item[name] and {"type": "null"} in item[name]["anyOf"], name
    assert "morning" in item["part"]["anyOf"][0]["enum"] and None not in item["part"]["anyOf"][0]["enum"]


def test_a_cloud_openai_model_is_not_told_the_schema_in_words():
    model = chat.OpenAIModel(api_key="sk-test", model="gpt-5.6-sol")
    assert model._system("SYSTEM", None) == "SYSTEM"


def test_a_model_of_ones_own_is_told_the_schema_in_words():
    model = chat.OpenAIModel(api_key="local", model="qwen", base_url="http://127.0.0.1:8080/v1")
    told = model._system("SYSTEM", None)
    assert told.startswith("SYSTEM") and '"proposals"' in told


class FakeStream:
    """An OpenAI-compatible server streaming its answer, as mlx_lm.server does."""

    def __init__(self, text: str):
        self.text = text
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **request):
        self.calls.append(request)
        chunks = [SimpleNamespace(model="qwen", usage=None,
                                  choices=[SimpleNamespace(delta=SimpleNamespace(content=self.text), finish_reason=None)]),
                  SimpleNamespace(model="qwen", usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
                                  choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")])]

        async def gen():
            for c in chunks:
                yield c
        return gen()


async def test_a_notice_read_by_a_server_of_ones_own_carries_the_schema_and_survives_a_fence():
    client = FakeStream("```json\n" + json.dumps(ANSWER) + "\n```")
    extractor = llm.OpenAIExtractor(api_key="local", model="local/qwen", effort=None, client=client,
                                    base_url="http://127.0.0.1:8080/v1")
    out = await extractor.call(NOTICE, dt.date(2026, 10, 20), country="IN")
    system = client.calls[0]["messages"][0]["content"]
    assert '"non_actionable_reason"' in system and "Write the JSON compactly" in system
    assert out["answer"] == ANSWER


async def test_a_notice_read_by_a_cloud_openai_model_is_unchanged():
    class FakeOpenAI:
        def __init__(self):
            self.calls = []
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        async def _create(self, **request):
            self.calls.append(request)
            message = SimpleNamespace(content=json.dumps(ANSWER), refusal=None)
            return SimpleNamespace(model="gpt-5.6-sol", choices=[SimpleNamespace(message=message, finish_reason="stop")],
                                   usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    client = FakeOpenAI()
    await llm.OpenAIExtractor(api_key=None, model="openai/gpt-5.6-sol", client=client).call(NOTICE, dt.date(2026, 10, 20))
    assert '"non_actionable_reason"' not in client.calls[0]["messages"][0]["content"]
