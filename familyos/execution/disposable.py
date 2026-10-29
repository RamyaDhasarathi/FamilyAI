"""Class 1: a disposable read of the untrusted web.

The defining property is negative. This code path receives **no credential of
any kind** -- no vault client, no cookie jar, no token, no household key. It
could not authenticate to anything if it tried, which is what makes a page
that tries to talk it into something merely a bad claim rather than a leak.

Everything it returns is *evidence*: a page, hashed, with the URL it actually
landed on. It is never a fact, and it never becomes an artifact on its own.
"""
from __future__ import annotations

import asyncio
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


async def _resolve(host: str) -> list[str]:
    """Every address the name points at, resolved off the event loop (a slow
    resolver must not stall the server). Tests replace this function."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise Refused(f"that host does not resolve: {host}") from exc
    return list(dict.fromkeys(info[4][0] for info in infos))


def _judge(host: str, address: str) -> None:
    addr = ipaddress.ip_address(address.split("%")[0])
    # An IPv6-only network (most Indian mobile ISPs) hands every public
    # IPv4 back as 64:ff9b::<v4> through NAT64. That is the public address
    # in a different coat, so it is the embedded IPv4 that gets judged.
    if isinstance(addr, ipaddress.IPv6Address) and addr in NAT64:
        addr = ipaddress.ip_address(addr.packed[-4:])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
        raise Refused(f"{host} resolves to an address inside the network ({addr})")


async def _public_addresses(host: str) -> list[str]:
    """Resolve once, and refuse unless every returned address is public.

    The caller connects to one of these exact addresses, so the name is never
    resolved a second time between the check and the connection (DNS rebinding).
    """
    addresses = await _resolve(host)
    if not addresses:
        raise Refused(f"that host does not resolve: {host}")
    for address in addresses:
        _judge(host, address)
    return addresses


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


async def vet(url: str, allow_hosts: frozenset[str]) -> str:
    """Everything `approved` checks, plus where the name actually points.

    Used when a member first asks for a watch -- because "localhost" is not an
    address literal and passes every syntactic check there is. `read` does the
    same check per hop and then connects to the address it vetted.
    """
    checked = approved(url, allow_hosts)
    await _public_addresses((urlsplit(checked).hostname or "").lower())
    return checked


def _text_of(html: str) -> tuple[str, str]:
    """Title and visible-ish text. Deliberately crude: this is evidence for a
    person to read, not a parse anything depends on."""
    import re

    from familyos import htmltext
    title = ""
    start = re.search(r"<title\b", html, re.I)
    if start:
        # The tag's own end, then its closer: str.find and one anchored search, never a pattern that rescans from every opener.
        gt = html.find(">", start.end())
        end = re.compile(r"</title", re.I).search(html, gt + 1) if gt >= 0 else None
        if end:
            title = re.sub(r"\s+", " ", htmltext.text_of(html[gt + 1:end.start()])).strip()[:300]
    body = htmltext.text_of(html)
    return title, re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n{3,}", "\n\n", body)).strip()


async def _fetch_hop(http: httpx.AsyncClient, target: str, addresses: list[str]) -> tuple[httpx.Response, bytes, bool]:
    """One request to a vetted address, streamed and cut at MAX_BYTES.

    The URL carries the IP; Host and the TLS server name carry the real name,
    so the certificate is still checked against the name the family typed.
    """
    url = httpx.URL(target)
    host = url.host
    host_header = host if url.port is None else f"{host}:{url.port}"
    last: Exception | None = None
    for address in addresses:
        pinned = url.copy_with(host=address)
        try:
            async with http.stream("GET", pinned, headers={"Host": host_header},
                                   extensions={"sni_hostname": host}) as response:
                if response.status_code in (301, 302, 303, 307, 308) or response.status_code >= 400:
                    return response, b"", False
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        chunks.append(chunk[: len(chunk) - (size - MAX_BYTES)])
                        return response, b"".join(chunks), True
                    chunks.append(chunk)
                return response, b"".join(chunks), False
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last = exc
    raise last or Refused("that host could not be reached")


async def read(url: str, allow_hosts: frozenset[str], *, client: httpx.AsyncClient | None = None) -> Page:
    """Fetch one page and hand back what it said.

    Redirects are followed by hand so that every hop is checked against the
    same allowlist: a redirect is a new source, never an implicit grant. Each
    hop resolves the name once, vets every address, and connects to the vetted
    address; the body is streamed and never held beyond MAX_BYTES.
    """
    target = approved(url, allow_hosts)
    owned = client is None
    http = client or httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            addresses = await _public_addresses((urlsplit(target).hostname or "").lower())
            response, raw, truncated = await _fetch_hop(http, target, addresses)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise Refused("a redirect with nowhere to go")
                target = approved(str(httpx.URL(target).join(location)), allow_hosts)
                continue
            if response.status_code >= 400:
                raise Refused(f"that page answered {response.status_code}")
            title, text = _text_of(raw.decode(response.encoding or "utf-8", "replace"))
            return Page(url=target, title=title,
                        text=text[:TEXT_LIMIT], sha256=hashlib.sha256(raw).hexdigest(),
                        bytes=len(raw), truncated=truncated or len(text) > TEXT_LIMIT)
        raise Refused("too many redirects")
    except httpx.HTTPError as exc:
        raise Refused(f"that page could not be read: {type(exc).__name__}") from exc
    finally:
        if owned:
            await http.aclose()
