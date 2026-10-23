"""Class 1: a disposable read of the untrusted web.

The defining property is negative. This code path receives **no credential of
any kind** -- no vault client, no cookie jar, no token, no household key. It
could not authenticate to anything if it tried, which is what makes a page
that tries to talk it into something merely a bad claim rather than a leak.

Everything it returns is *evidence*: a page, hashed, with the URL it actually
landed on. It is never a fact, and it never becomes an artifact on its own.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 20.0
TEXT_LIMIT = 40_000
USER_AGENT = "FamilyOS/0.2 (+household agent; one page, on request; never signed in)"
# RFC 6052: the well-known NAT64 prefix. 64:ff9b::1.2.3.4 is 1.2.3.4 wearing IPv6.
NAT64 = ipaddress.ip_network("64:ff9b::/96")


class Refused(Exception):
    """The fetch was not attempted, or not trusted. Said plainly."""


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    text: str
    sha256: str
    bytes: int
    truncated: bool


def _host_is_public(host: str) -> None:
    """Resolve, then refuse anything that is not a public address.

    Checking the literal is not enough: a hostname an attacker controls can
    resolve to 127.0.0.1 or to the cloud metadata address. Every resolved
    address has to be public, not merely the first.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise Refused(f"that host does not resolve: {host}") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        # An IPv6-only network (most Indian mobile ISPs) hands every public
        # IPv4 back as 64:ff9b::<v4> through NAT64. That is the public address
        # in a different coat, so it is the embedded IPv4 that gets judged.
        if isinstance(addr, ipaddress.IPv6Address) and addr in NAT64:
            addr = ipaddress.ip_address(addr.packed[-4:])
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            raise Refused(f"{host} resolves to an address inside the network ({addr})")


def approved(url: str, allow_hosts: frozenset[str]) -> str:
    """One URL, checked against the grant for this task.

    Syntax and allowlist only -- deliberately no DNS, so a watch can be created
    while a name is briefly unresolvable, and so this stays a pure function.
    The resolution check is in `vet`, which callers use when they mean it.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise Refused("only https is read")
    host = (parts.hostname or "").lower()
    if not host:
        raise Refused("that is not a URL we can read")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise Refused("an address is not a source; name the site")
    if host not in allow_hosts:
        raise Refused(f"{host} is outside this task's allowlist")
    return url


def vet(url: str, allow_hosts: frozenset[str]) -> str:
    """Everything `approved` checks, plus where the name actually points.

    Applied to the first URL, to every redirect hop, and when a member first
    asks for a watch -- because "localhost" is not an address literal and
    passes every syntactic check there is.
    """
    checked = approved(url, allow_hosts)
    _host_is_public((urlsplit(checked).hostname or "").lower())
    return checked


def _text_of(html: str) -> tuple[str, str]:
    """Title and visible-ish text. Deliberately crude: this is evidence for a
    person to read, not a parse anything depends on."""
    import re
    title = ""
    found = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if found:
        title = re.sub(r"\s+", " ", found.group(1)).strip()[:300]
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"), ("&quot;", '"')):
        body = body.replace(entity, char)
    return title, re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n{3,}", "\n\n", body)).strip()


async def read(url: str, allow_hosts: frozenset[str], *, client: httpx.AsyncClient | None = None) -> Page:
    """Fetch one page and hand back what it said.

    Redirects are followed by hand so that every hop is checked against the
    same allowlist: a redirect is a new source, never an implicit grant.
    """
    target = vet(url, allow_hosts)
    owned = client is None
    http = client or httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            response = await http.get(target)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise Refused("a redirect with nowhere to go")
                target = vet(str(httpx.URL(target).join(location)), allow_hosts)
                continue
            if response.status_code >= 400:
                raise Refused(f"that page answered {response.status_code}")
            raw = response.content[:MAX_BYTES]
            truncated = len(response.content) > MAX_BYTES
            title, text = _text_of(raw.decode(response.encoding or "utf-8", "replace"))
            return Page(url=str(response.url), title=title,
                        text=text[:TEXT_LIMIT], sha256=hashlib.sha256(raw).hexdigest(),
                        bytes=len(raw), truncated=truncated or len(text) > TEXT_LIMIT)
        raise Refused("too many redirects")
    except httpx.HTTPError as exc:
        raise Refused(f"that page could not be read: {type(exc).__name__}") from exc
    finally:
        if owned:
            await http.aclose()


def describe() -> str:
    return ("execution class 1 (disposable): reads public pages, holds no credential, "
            f"https only, {MAX_BYTES // 1024}KiB cap")
