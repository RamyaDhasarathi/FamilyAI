"""Offline cross-app integration contract POC. No production I/O or model calls.

The only real vendor-specific operation here is the OpenBot HTTP route mapping.
Transport is injected so the demo can prove policy and response handling without
pretending that a browser deployment or Android device is running.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urlsplit


class Refused(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    household_id: str
    member_id: str
    role: str


@dataclass(frozen=True)
class Source:
    kind: str  # api, web, app_only
    url: str | None
    owner_member_id: str
    household_id: str
    approved_hosts: frozenset[str] = frozenset()
    explicit_mobile_grant: bool = False


class OpenBotTransport(Protocol):
    """Must carry the acting person's authenticated OpenBot session."""

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


def approved_url(url: str, hosts: frozenset[str]) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise Refused("Only approved HTTPS sites can be opened")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise Refused("IP addresses are not approved sources")
    if host not in hosts:
        raise Refused("Site is outside this source grant")
    return url


def require_owner(actor: Member, source: Source) -> None:
    if actor.household_id != source.household_id or actor.member_id != source.owner_member_id:
        raise Refused("This member has no grant for that source")


def _page(response: dict[str, Any], requested_url: str, hosts: frozenset[str],
          *, exact: bool = False) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise Refused("OpenBot returned an invalid page")
    url = response.get("url")
    text = response.get("text")
    if not isinstance(url, str) or not isinstance(text, str) or not isinstance(response.get("truncated"), bool):
        raise Refused("OpenBot returned an incomplete page")
    approved_url(url, hosts)  # A redirect is a new source, not an implicit grant.
    if not isinstance(response.get("title"), str):
        raise Refused("OpenBot returned an incomplete page")
    if exact:
        # Host equality is not enough to tie a read to its navigation: any
        # other page on the same site satisfies it, and an unrelated one then
        # becomes this source's evidence.
        if url != requested_url:
            raise Refused("OpenBot read a different page from the one it navigated to")
    elif urlsplit(url).hostname != urlsplit(requested_url).hostname:
        raise Refused("OpenBot left the approved site")
    return {"url": url, "title": response["title"], "text": text, "truncated": response["truncated"]}


def read_web(actor: Member, source: Source, bot_id: str, transport: OpenBotTransport) -> dict[str, Any]:
    require_owner(actor, source)
    if source.kind != "web" or not source.url or not bot_id or "/" in bot_id:
        raise Refused("A web source and Bot are required")
    url = approved_url(source.url, source.approved_hosts)
    base = f"/api/computers/{quote(bot_id, safe='')}"
    # OpenBot owns the policy decision and audit. The per-person transport must
    # never be replaced with a shared administrator token or direct computer port.
    status = transport.request("GET", base + "/status")
    if status.get("botId") != bot_id or status.get("state") != "ready":
        raise Refused("The member's OpenBot computer is unavailable")
    navigation = transport.request("POST", base + "/navigate", {"url": url})
    landed = _page(navigation, url, source.approved_hosts)
    page = transport.request("GET", base + "/read")
    # Read against where the navigation landed, exactly -- not merely the host
    # it was on. /read returns whatever page the computer is showing now.
    return _page(page, landed["url"], source.approved_hosts, exact=True)


def plan(actor: Member, source: Source, *, android_device_connected: bool = False) -> dict[str, str]:
    require_owner(actor, source)
    if source.kind == "api":
        return {"lane": "api", "state": "requires_connected_provider"}
    if source.kind == "web":
        if not source.url:
            raise Refused("Web source needs a URL")
        approved_url(source.url, source.approved_hosts)
        return {"lane": "openbot_browser", "state": "requires_authenticated_session"}
    if source.kind == "app_only":
        if not source.explicit_mobile_grant:
            return {"lane": "mobile", "state": "requires_member_grant"}
        if not android_device_connected:
            return {"lane": "mobile", "state": "requires_android_device_and_agent"}
        return {"lane": "mobile", "state": "requires_live_agent_verification"}
    raise Refused("Unknown source kind")


REVIEW_EXCERPT_CHARS = 20_000


def evidence_capture(actor: Member, source: Source, page: dict[str, Any]) -> dict[str, Any]:
    """Produce a review candidate, never silently create a FamilyOS artifact."""
    require_owner(actor, source)
    if source.kind != "web" or not source.url:
        raise Refused("Only verified browser reads can form this capture")
    verified = _page(page, source.url, source.approved_hosts)
    if verified["truncated"] or not verified["text"].strip():
        raise Refused("Incomplete page evidence requires human review")
    encoded = verified["text"].encode("utf-8")
    # The hash proves what was captured; it does not let anyone see it. A
    # review screen that cannot show the member what they are approving is a
    # consent button, not a review -- so the text travels with the candidate.
    excerpt = verified["text"][:REVIEW_EXCERPT_CHARS]
    return {
        "candidate_id": str(uuid.uuid4()),
        "household_id": actor.household_id,
        "owner_member_id": actor.member_id,
        "source_url": verified["url"],
        "title": verified["title"],
        "text": excerpt,
        "excerpt_truncated": len(excerpt) < len(verified["text"]),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "media_type": "text/plain",
        "visibility": "private",
        "status": "awaiting_review",
        "bytes": len(encoded),
    }


def openmuse_view(candidate: dict[str, Any]) -> dict[str, Any]:
    """FamilyOS UI view model for a future OpenMuse screen, not AG-UI wire data."""
    return {
        "screen": "source_review",
        "candidate_id": candidate["candidate_id"],
        "source_url": candidate["source_url"],
        "title": candidate["title"],
        "text": candidate["text"],
        "excerpt_truncated": candidate["excerpt_truncated"],
        "status": candidate["status"],
        "actions": ["review", "discard"],
    }


class FixtureOpenBot:
    """Fixture transport for deterministic contract checks; never call it live."""

    def __init__(self, page: dict[str, Any], bot_id: str = "family-bot",
                 read_page: dict[str, Any] | None = None) -> None:
        self.page = page
        # The page /read returns, when it differs from the one navigated to --
        # which is what happens when the computer has moved on in between.
        self.read_page = read_page if read_page is not None else page
        self.bot_id = bot_id
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path))
        if path.endswith("/status"):
            return {"botId": self.bot_id, "state": "ready"}
        if path.endswith("/navigate"):
            return self.page
        if path.endswith("/read"):
            return self.read_page
        raise Refused("Unexpected fixture route")


def demo() -> dict[str, Any]:
    actor = Member("household-demo", "parent-demo", "guardian")
    source = Source("web", "https://school.example/notices/42", actor.member_id,
                    actor.household_id, frozenset({"school.example"}))
    fixture = FixtureOpenBot({"url": source.url, "title": "Sports day", "text":
                              "Sports day is Friday. Return the consent form by Thursday.", "truncated": False})
    page = read_web(actor, source, "family-bot", fixture)
    candidate = evidence_capture(actor, source, page)
    return {"mode": "fixture_contract_only", "browser_calls": fixture.calls,
            "candidate": candidate, "openmuse_view": openmuse_view(candidate),
            "mobile": plan(actor, Source("app_only", None, actor.member_id, actor.household_id,
                                         explicit_mobile_grant=True))}


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2))
