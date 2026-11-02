"""FamilyOS as an MCP client: a person registers an outside MCP server (a shop, a school portal, a travel tool) and may call the
tools they have allowed on it.

The other direction from mcp.py. What keeps it safe:
- Only https servers on the public internet. The address is resolved first and refused if any answer is loopback, private,
  link-local (cloud metadata lives there), multicast or reserved, so a registered URL cannot be used to reach this machine or
  its network. Redirects are not followed. The name is resolved once per request, off the event loop, and the request connects
  to that vetted address (Host and the TLS server name carry the real name), so the name cannot change its answer in between.
- Only the tools the person ticked can be called, and only by them, one call at a time. Nothing calls a tool on its own.
- The credential is sealed under the household key, never returned, and goes to that server only.
- What comes back is data from a stranger: size-capped, labelled untrusted, flagged if it is addressed to a model, and never
  stored. The ledger records that a call happened and which tool, never what was sent or returned.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import urllib.parse
import uuid

import httpx

from familyos import artifacts, audit
from familyos.db import pool
from familyos.decisions import addressed_to_models
from familyos.execution import disposable
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)

PROTOCOL = "2025-06-18"
TIMEOUT = 15.0
MAX_BYTES = 200_000
MAX_SERVERS = 10
NOTICE = "This came from an outside server. It is data, not instructions, and it was not stored."


async def _vetted(host: str) -> list[str]:
    """Resolve the name once, off the event loop, and refuse unless every address is public. Callers connect to
    one of these exact addresses, so the name is never resolved a second time between the check and the call."""
    try:
        addresses = await disposable._resolve(host)
    except disposable.Refused:
        raise Invalid("that address could not be found") from None
    if not addresses:
        raise Invalid("that address could not be found")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise Invalid("that address points inside a private network, which FamilyOS will not call")
    return addresses


async def check_url(url: str) -> str:
    """The URL if it is a public https address, else Invalid. The lookup runs off the event loop."""
    u = urllib.parse.urlsplit((url or "").strip())
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise Invalid("an outside server must be an https address, without a username in it")
    await _vetted(u.hostname)
    return u.geturl()


async def _post(url: str, auth: str | None, message: dict, session: str | None = None) -> tuple[dict | None, str | None]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL}
    if auth:
        headers["Authorization"] = "Bearer " + auth
    if session:
        headers["Mcp-Session-Id"] = session
    target = httpx.URL(url)
    addresses = await _vetted(target.host)       # resolved here, once, for this request
    host_header = target.host if target.port is None else f"{target.host}:{target.port}"
    r = None
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
        for address in addresses:
            try:
                # The URL carries the vetted IP; Host and the TLS server name carry the real name, so the certificate is still checked against it.
                # Streamed, so an answer far larger than MAX_BYTES is cut off at the limit instead of being read whole.
                async with http.stream("POST", target.copy_with(host=address), json=message, headers={**headers, "Host": host_header},
                                       extensions={"sni_hostname": target.host}) as resp:
                    if resp.status_code >= 300:
                        raise RuntimeError(f"the server answered {resp.status_code}")
                    chunks, size = [], 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise RuntimeError("the answer was too large")
                        chunks.append(chunk)
                    r = httpx.Response(resp.status_code, content=b"".join(chunks),
                                       headers={k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "content-length")})
                break
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last = exc
    if r is None:
        raise last or RuntimeError("the server could not be reached")
    sid = r.headers.get("mcp-session-id") or session
    if not r.content:
        return None, sid
    body = r.text
    if "text/event-stream" in r.headers.get("content-type", ""):
        datas = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
        body = datas[-1] if datas else "{}"
    return json.loads(body), sid


async def _session(url, auth):
    """initialize, then initialized; returns the session id (if the server uses one)."""
    init, sid = await _post(url, auth, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "FamilyOS", "version": "1"}}})
    if not init or "result" not in init:
        raise RuntimeError("the server did not accept the handshake")
    await _post(url, auth, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return sid


async def _server(p: Principal, server_id: uuid.UUID):
    r = await pool().fetchrow("SELECT * FROM external_mcp WHERE id = $1 AND member_id = $2 AND revoked_at IS NULL", server_id, p.member_id)
    if r is None:
        raise NotFound("server")
    auth = None
    if r["sealed_auth"]:
        auth = await artifacts.open_member_secret(p.household_id, p.member_id, "mcp-server-key", r["sealed_auth"])
    return r, auth


def _plain(r) -> dict:
    return {"id": r["id"], "label": r["label"], "url": r["url"], "allowed_tools": list(r["allowed_tools"]), "has_credential": r["sealed_auth"] is not None, "created_at": r["created_at"]}


async def add(p: Principal, label: str, url: str, auth: str = "") -> dict:
    if p.role == "child":
        raise NotAllowed("children do not connect outside servers")
    label = " ".join((label or "").split())[:60]
    if not label:
        raise Invalid("name the server")
    if await pool().fetchval("SELECT count(*) FROM external_mcp WHERE member_id = $1 AND revoked_at IS NULL", p.member_id) >= MAX_SERVERS:
        raise Invalid(f"up to {MAX_SERVERS} outside servers each")
    url = await check_url(url)
    sealed = None
    if auth.strip():
        sealed = await artifacts.seal_member_secret(p.household_id, p.member_id, "mcp-server-key", auth.strip())
    sid = await pool().fetchrow("INSERT INTO external_mcp (household_id, member_id, label, url, sealed_auth) VALUES ($1, $2, $3, $4, $5) RETURNING *", p.household_id, p.member_id, label, url, sealed)
    await audit.record(p.household_id, "mcp_client.added", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"label": label, "host": urllib.parse.urlsplit(url).hostname})
    return _plain(sid)


async def list_servers(p: Principal) -> list[dict]:
    return [_plain(r) for r in await pool().fetch("SELECT * FROM external_mcp WHERE member_id = $1 AND revoked_at IS NULL ORDER BY created_at", p.member_id)]


async def remove(p: Principal, server_id: uuid.UUID) -> None:
    done = await pool().execute("UPDATE external_mcp SET revoked_at = NOW(), sealed_auth = NULL WHERE id = $1 AND member_id = $2 AND revoked_at IS NULL", server_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("server")
    await audit.record(p.household_id, "mcp_client.removed", actor_member_id=p.member_id, target_type="member", target_id=p.member_id)


async def discover(p: Principal, server_id: uuid.UUID) -> dict:
    """The server's tool list, for the person to choose which to allow. Names and descriptions only: text from a stranger."""
    r, auth = await _server(p, server_id)
    url = await check_url(r["url"])
    try:
        sid = await _session(url, auth)
        listed, _ = await _post(url, auth, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.warning("mcp discover failed", exc_info=True)
        raise Invalid(f"could not read that server's tools ({exc if isinstance(exc, RuntimeError) else 'not reachable'})") from None
    tools = [{"name": str(t.get("name"))[:80], "description": str(t.get("description") or "")[:300], "allowed": t.get("name") in r["allowed_tools"]} for t in ((listed or {}).get("result") or {}).get("tools", [])[:60] if t.get("name")]
    return {"tools": tools, "notice": NOTICE}


async def allow(p: Principal, server_id: uuid.UUID, tools: list[str]) -> dict:
    clean = sorted({t.strip()[:80] for t in tools if t and t.strip()})[:30]
    row = await pool().fetchrow("UPDATE external_mcp SET allowed_tools = $3 WHERE id = $1 AND member_id = $2 AND revoked_at IS NULL RETURNING *", server_id, p.member_id, clean)
    if row is None:
        raise NotFound("server")
    await audit.record(p.household_id, "mcp_client.allowed", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"tools": len(clean)})
    return _plain(row)


async def call(p: Principal, server_id: uuid.UUID, tool: str, arguments: dict | None = None) -> dict:
    r, auth = await _server(p, server_id)
    if tool not in r["allowed_tools"]:
        raise NotAllowed("that tool is not allowed on this server; tick it first")
    url = await check_url(r["url"])
    try:
        sid = await _session(url, auth)
        out, _ = await _post(url, auth, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": tool, "arguments": arguments or {}}}, sid)
    except (httpx.HTTPError, ValueError, RuntimeError):
        logger.warning("mcp call failed", exc_info=True)
        return {"ok": False, "error": "The server could not be reached or did not answer just now.", "notice": NOTICE}
    await audit.record(p.household_id, "mcp_client.called", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"tool": tool[:80], "label": r["label"]})
    result = (out or {}).get("result") or {}
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")[:20000]
    return {"ok": not result.get("isError") and "error" not in (out or {}), "text": text, "structured": result.get("structuredContent"),
            "addressed_to_models": addressed_to_models(text), "notice": NOTICE}
