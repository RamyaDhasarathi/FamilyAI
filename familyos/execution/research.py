"""Reading the public web through a research provider, when one is configured.

Class 1 has a second implementation. `disposable.read` fetches a page with
plain HTTP and no credential; that is right for a fee schedule and wrong for
a fare page, which is a JavaScript application that returns an empty shell
to anything that is not a browser. A research provider -- Parallel today --
keeps its own index of the open web and renders pages, and answers a
natural-language objective with ranked pages and excerpts, each with a URL
we can re-read ourselves.

The rule that makes it the same class as a plain fetch:

  * **Nothing of the family's goes out.** A query is built from a plan
    option's own words -- "Chennai to Zurich return, four passengers" -- and
    scrubbed of every member's name before it leaves. No notice text, no
    amounts, no child.
  * **Public pages only.** The provider makes no claim to pages behind a
    login, and neither do we. A URL is vetted the same way a watch's is.
  * **Evidence, never fact.** What comes back is a URL, a title, an excerpt
    and the time it was read. It is shown with its source. It never becomes
    a claim on its own.

Off unless FAMILYOS_WEB_RESEARCH names a provider and its key is present;
then plans get evidence under each option and watches read JavaScript pages.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from familyos.settings import settings

logger = logging.getLogger(__name__)

PARALLEL = "https://api.parallel.ai/v1"
TIMEOUT = 45.0
MAX_EXCERPT = 600


@dataclass
class Hit:
    url: str
    title: str | None
    excerpt: str
    read_at: dt.datetime
    via: str
    publish_date: str | None = None


@dataclass
class Extracted:
    url: str
    title: str | None
    text: str
    read_at: dt.datetime
    via: str
    excerpts: list[str] = field(default_factory=list)


class Researcher(Protocol):
    name: str

    async def search(self, objective: str, queries: list[str], *, limit: int = 5) -> list[Hit]: ...

    async def extract(self, url: str, objective: str | None = None) -> Extracted: ...


class NoResearcher:
    name = "none"

    async def search(self, objective: str, queries: list[str], *, limit: int = 5) -> list[Hit]:
        return []

    async def extract(self, url: str, objective: str | None = None) -> Extracted:
        raise RuntimeError("no web research provider is configured")


class ParallelResearcher:
    """Parallel's Search and Extract APIs. One round trip each."""
    name = "parallel"

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None, mode: str = "fast"):
        self._key, self._transport, self.mode = api_key, transport, mode

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=PARALLEL, timeout=TIMEOUT, transport=self._transport,
                                 headers={"x-api-key": self._key, "Content-Type": "application/json"})

    async def search(self, objective: str, queries: list[str], *, limit: int = 5) -> list[Hit]:
        now = dt.datetime.now(dt.UTC)
        # The live API takes objective and queries and nothing else; limits
        # are applied here. (Its docs list more fields; it refuses them.)
        async with self._client() as c:
            r = await c.post("/search", json={"objective": objective[:500], "search_queries": [q[:200] for q in queries[:5]]})
            r.raise_for_status()
            body = r.json()
        out = []
        for item in (body.get("results") or [])[:max(1, min(limit, 10))]:
            if not (item.get("url") or "").startswith("https://"):
                continue
            excerpt = " ".join((item.get("excerpts") or [])[:2]).strip()
            out.append(Hit(url=item["url"], title=item.get("title"), excerpt=excerpt[:MAX_EXCERPT],
                           read_at=now, via=self.name, publish_date=item.get("publish_date")))
        return out

    async def extract(self, url: str, objective: str | None = None) -> Extracted:
        now = dt.datetime.now(dt.UTC)
        # Excerpts always come back; full_content is asked for under
        # advanced_settings, which is the one field the live API accepts there.
        payload: dict = {"urls": [url], "objective": (objective or "the page's main content")[:500],
                         "advanced_settings": {"full_content": True}}
        async with self._client() as c:
            r = await c.post("/extract", json=payload)
            r.raise_for_status()
            body = r.json()
        results = body.get("results") or []
        if not results:
            raise RuntimeError("the page could not be read")
        item = results[0]
        text = item.get("full_content") or "\n\n".join(item.get("excerpts") or [])
        return Extracted(url=item.get("url") or url, title=item.get("title"), text=text or "", read_at=now,
                         via=self.name, excerpts=list(item.get("excerpts") or []))


_researcher: Researcher = NoResearcher()


def use(r: Researcher) -> None:
    global _researcher
    _researcher = r


def current() -> Researcher:
    return _researcher


def configured() -> bool:
    return not isinstance(_researcher, NoResearcher)


def configure() -> None:
    """Named in configuration, never inferred from a key lying around."""
    provider = (settings.web_research or "").strip().lower()
    if provider == "parallel" and settings.parallel_api_key:
        use(ParallelResearcher(settings.parallel_api_key))
    else:
        use(NoResearcher())


def describe() -> str:
    if not configured():
        return "Web research is off: plans show links and watches read pages with plain HTTP (FAMILYOS_WEB_RESEARCH)."
    return (f"Web research is on ({_researcher.name}): public pages only, queries scrubbed of the family's names, "
            "results shown as evidence with their source.")


def scrub(text: str, names: list[str]) -> str:
    """Take every member's name out of a query before it leaves. The query is
    about a trip, not about who is going."""
    out = text or ""
    for name in sorted({n for n in names if n and len(n) >= 2}, key=len, reverse=True):
        out = re.sub(r"\b" + re.escape(name) + r"\b", "the family", out, flags=re.I)
    return " ".join(out.split())
