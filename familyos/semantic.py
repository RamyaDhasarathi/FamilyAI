"""Search by meaning, over the notices a member can see.

"The plumber" should find "Rajesh, pipe repair"; "school fee" should find
"Term 2 tuition due Friday". Words alone miss both. A small embedding model on
this machine (EmbeddingGemma through Ollama, by default) turns each notice's
headline, sender and preview into a vector and the question into one, and the
nearest win; a notice that also contains the question's own words is lifted.

What it never does: send a notice anywhere (the model is local, the endpoint is
`embed_url`); keep a vector (they live in memory, keyed by the text's hash, and
are rebuilt after a restart, so the household-key erasure still leaves nothing
readable); show a member a notice the inbox would not (the candidates are
`inbox.feed`, the same visibility as every other read). If the model is off or
unreachable, search falls back to the question's words and says so.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import uuid

from familyos import inbox
from familyos.identity import Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

# EmbeddingGemma's documented prompt shapes: a query and a document are
# embedded differently, which is most of why it retrieves well.
QUERY_PREFIX = "task: search result | query: "
DOC_PREFIX = "title: none | text: "
CANDIDATES = 400
BATCH = 32
MIN_SCORE = 0.30        # below this a vector match is a coincidence, not an answer
_cache: dict[str, list[float]] = {}
_CACHE_MAX = 20000


class EmbedUnavailable(RuntimeError):
    pass


async def _embed(texts: list[str]) -> list[list[float]]:
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(settings.embed_url.rstrip("/") + "/embeddings",
                              headers={"Authorization": f"Bearer {settings.embed_key}"},
                              json={"model": settings.embed_model, "input": texts})
    if r.status_code >= 400:
        raise EmbedUnavailable(f"the embedding model answered {r.status_code}")
    data = sorted(r.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def _text_of(row: dict) -> str:
    parts = [row.get("headline") or row.get("filename") or "", row.get("from_label") or "", " ".join(row.get("preview") or [])]
    return " · ".join(x for x in parts if x)[:1200]


def _key(text: str) -> str:
    return hashlib.sha256(f"{settings.embed_model}|{text}".encode()).hexdigest()


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


_WORD = re.compile(r"[a-z0-9₹]+")


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def _keyword_score(q: set[str], text: str) -> float:
    have = _words(text)
    return len(q & have) / len(q) if q else 0.0


async def search(p: Principal, query: str, limit: int = 12) -> dict:
    """Ranked notices for a question, with how they were matched."""
    query = " ".join((query or "").split())[:300]
    if not query:
        return {"mode": "words", "hits": []}
    rows = await inbox.feed(p, days=400, limit=CANDIDATES)
    q_words = _words(query)
    texts = {str(r["id"]): _text_of(r) for r in rows}
    scores: dict[str, float] = {}
    mode = "words"
    if settings.embed_model:
        try:
            need = [(i, t) for i, t in texts.items() if _key(t) not in _cache]
            for start in range(0, len(need), BATCH):
                chunk = need[start:start + BATCH]
                for (_, t), vec in zip(chunk, await _embed([DOC_PREFIX + t for _, t in chunk]), strict=True):
                    if len(_cache) >= _CACHE_MAX:
                        _cache.pop(next(iter(_cache)))
                    _cache[_key(t)] = vec
            [qv] = await _embed([QUERY_PREFIX + query])
            scores = {i: _cos(qv, _cache[_key(t)]) for i, t in texts.items() if _key(t) in _cache}
            mode = "meaning"
        except Exception as exc:  # noqa: BLE001 - the model is a helper; words still work
            logger.info("semantic search fell back to words: %s", exc)
            scores, mode = {}, "words"
    ranked = []
    for r in rows:
        i = str(r["id"])
        kw = _keyword_score(q_words, texts[i])
        if mode == "meaning":
            sem = scores.get(i, 0.0)
            if sem < MIN_SCORE and kw == 0:
                continue
            score, how = sem + 0.4 * kw, ("words" if kw == 1.0 and sem < MIN_SCORE else "meaning")
        else:
            if kw == 0:
                continue
            score, how = kw, "words"
        ranked.append({"score": round(score, 4), "matched": how, "notice": r})
    ranked.sort(key=lambda h: (h["score"], h["notice"]["received_at"]), reverse=True)
    return {"mode": mode, "hits": ranked[:max(1, min(limit, 40))]}


def forget(household_id: uuid.UUID | None = None) -> None:  # noqa: ARG001 - the cache is content-keyed, not per household
    """Drop every vector: after an erasure, or a change of model."""
    _cache.clear()
