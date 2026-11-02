"""Search by meaning: the nearest notices win, a word that matches is lifted,
nothing a member cannot see is offered, and with the model off it is words."""

import pytest

from familyos import semantic
from familyos.settings import settings

# A tiny hand-made "embedding": three axes (money, school, home service).
AXES = {"fee": (1, 1, 0), "tuition": (1, 1, 0), "school": (0, 1, 0), "plumber": (0, 0, 1), "pipe": (0, 0, 1), "repair": (0, 0, 1),
        "electricity": (1, 0, 0), "bill": (1, 0, 0)}


def _vec(text: str) -> list[float]:
    v = [0.0, 0.0, 0.0]
    for w in text.lower().replace("·", " ").split():
        for i, x in enumerate(AXES.get(w.strip("?.,"), (0, 0, 0))):
            v[i] += x
    return v or [0.0, 0.0, 0.0]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    semantic.forget()
    monkeypatch.setattr(settings, "embed_model", "fake")

    async def embed(texts):
        return [_vec(t.replace(semantic.DOC_PREFIX, "").replace(semantic.QUERY_PREFIX, "")) for t in texts]
    monkeypatch.setattr(semantic, "_embed", embed)
    yield
    semantic.forget()


async def _note(family, headline, who="amma", visibility="shared"):
    r = await family.client.post("/v1/inbound/share", headers={**family.h(who), "X-Visibility": visibility, "content-type": "text/plain"}, content=headline.encode())
    assert r.status_code == 201, r.text


async def test_a_question_finds_the_notice_that_means_it_without_sharing_its_words(family, database):
    await _note(family, "Term 2 tuition due Friday for Lily")
    await _note(family, "Rajesh pipe repair visit on Monday")
    r = await family.client.get("/v1/search", params={"q": "the plumber"}, headers=family.h("amma"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "meaning"
    assert "pipe repair" in body["hits"][0]["notice"]["headline"] and body["hits"][0]["matched"] == "meaning"
    r = await family.client.get("/v1/search", params={"q": "school fee"}, headers=family.h("amma"))
    assert "tuition" in r.json()["hits"][0]["notice"]["headline"]


async def test_a_private_notice_is_not_found_by_someone_it_is_not_for(family, database):
    await _note(family, "Private pipe repair quote", who="amma", visibility="private")
    assert (await family.client.get("/v1/search", params={"q": "plumber"}, headers=family.h("appa"))).json()["hits"] == []
    assert len((await family.client.get("/v1/search", params={"q": "plumber"}, headers=family.h("amma"))).json()["hits"]) == 1


async def test_with_the_model_unreachable_it_falls_back_to_the_questions_words_and_says_so(family, database, monkeypatch):
    await _note(family, "Electricity bill for October")

    async def down(texts):
        raise semantic.EmbedUnavailable("no model")
    monkeypatch.setattr(semantic, "_embed", down)
    r = await family.client.get("/v1/search", params={"q": "electricity bill"}, headers=family.h("amma"))
    assert r.json()["mode"] == "words" and len(r.json()["hits"]) == 1
    assert (await family.client.get("/v1/search", params={"q": "plumber"}, headers=family.h("amma"))).json()["hits"] == []


async def test_nothing_is_stored_and_the_model_can_be_switched_off(family, database, monkeypatch):
    await _note(family, "Electricity bill for October")
    await family.client.get("/v1/search", params={"q": "electricity"}, headers=family.h("amma"))
    assert semantic._cache and all(isinstance(k, str) and len(k) == 64 for k in semantic._cache)   # in memory, keyed by a hash
    tables = {r["tablename"] for r in await database.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert not any("embed" in t or "vector" in t for t in tables)
    monkeypatch.setattr(settings, "embed_model", "")
    assert (await family.client.get("/v1/search", params={"q": "electricity"}, headers=family.h("amma"))).json()["mode"] == "words"
