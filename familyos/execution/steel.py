"""Steel as the browser behind an assisted harvest.

Steel is Apache-2.0 and self-hostable, which is why it is the one bought
rather than built: fingerprint consistency and a live view are tedious work
that changes nothing about the architecture, and running it ourselves keeps a
family's portal session out of anyone else's cloud.

What it supplies is a session with a `debuggerUrl` -- a DevTools view the
member can watch and drive. It supplies no credential and holds nothing of
ours; when the sitting ends the session is released and the browser is gone.

Verified against steel-browser-api: POST /v1/sessions opens one,
POST /v1/sessions/release closes it, GET /v1/sessions/{id}/context reads what
the browser holds (cookies, localStorage, sessionStorage), and a session may
be opened with `sessionContext` to hold it again.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

import httpx

from familyos.execution.agent import announce
from familyos.execution.harvest import NoCollector
from familyos.settings import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _reachable(url: str | None, base_url: str) -> str | None:
    """Steel reports its own URLs as 0.0.0.0, a bind address and nowhere a
    browser can go. Put back the host we actually reach it on, keeping the
    port Steel named -- the DevTools frontend lives on a different one.

    The query is rewritten too: the inspector carries its websocket as
    `?ws=//0.0.0.0:9223/...`, and a frame pointed at a bind address fails
    exactly as silently as the page itself would.
    """
    if not url:
        return None
    host = urlsplit(base_url).hostname or "localhost"
    target = urlsplit(url.replace("0.0.0.0", host))
    if target.hostname in ("", None):
        return None
    return urlunsplit((target.scheme or "http", target.netloc, target.path, target.query, target.fragment))


class SteelCollector:
    """One Steel session per sitting, released when it ends."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.steel_url).rstrip("/")

    async def open(self, *, allow_hosts: frozenset[str], minutes: int) -> dict:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                response = await http.post(
                    f"{self.base_url}/v1/sessions",
                    json={"timeout": minutes * 60_000,
                          # Said for the record even though Steel does not
                          # enforce it: every page is checked against the grant
                          # again on the way in.
                          "dimensions": {"width": 1280, "height": 800}})
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise NoCollector(f"the browser service could not start a session: {type(exc).__name__}") from exc
        return {"session_id": body.get("id"),
                "live_url": await self._live_view(body.get("debuggerUrl")),
                "websocket_url": _reachable(body.get("websocketUrl"), self.base_url)}

    async def _live_view(self, debugger_url: str | None) -> str | None:
        """Follow the inspector's redirect ourselves.

        `/v1/devtools/inspector.html` is a 302 to the DevTools frontend on
        another port, with the websocket in the query. Resolving it here means
        the console is handed a URL that already works, rather than a redirect
        into a bind address that fails inside an iframe with nothing to say.
        """
        first = _reachable(debugger_url, self.base_url)
        if not first:
            return None
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
                response = await http.get(first)
            if response.status_code in (301, 302, 303, 307, 308):
                return _reachable(response.headers.get("location"), self.base_url)
        except httpx.HTTPError:
            logger.warning("could not resolve the browser's live view", exc_info=True)
        return first

    async def close(self, session: dict) -> None:
        if not session or not session.get("session_id"):
            return
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                await http.post(f"{self.base_url}/v1/sessions/release", json={})
        except httpx.HTTPError:
            # The session times out on its own; a failure to release is worth
            # a line in the log and nothing more.
            logger.warning("could not release browser session %s", session.get("session_id"), exc_info=True)


def configure() -> bool:
    """Install the browser a deployment has: Steel when it says so, else the
    one on this machine when Playwright's Chromium is here. Returns whether
    a browser was installed, for the boot line."""
    from familyos.execution import harvest, local
    want = (settings.browser or "auto").lower()
    if want in ("steel", "auto") and settings.steel_url:
        harvest.use_collector(SteelCollector())
        use_browser(SteelBrowser())
        return True
    if want in ("local", "auto") and local.available():
        use_browser(local.LocalBrowser())
        return True
    return False


# ----------------------------------------------------------------------------
# a browser for a sign-in sitting, and for the tasks that use its session
# ----------------------------------------------------------------------------

class SteelBrowser:
    """A Steel session a person can drive and FamilyOS can read and refill.

    `open_at` starts a session on a page; `context` reads what the browser
    holds; `release` ends it. `open_with` starts a session already holding a
    sealed session's state, for a task. The live view is the same DevTools
    page the harvest sitting uses.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.steel_url).rstrip("/")
        self._collector = SteelCollector(self.base_url)

    async def _create(self, body: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                response = await http.post(f"{self.base_url}/v1/sessions", json=body)
                response.raise_for_status()
                made = response.json()
        except httpx.HTTPError as exc:
            raise NoCollector(f"the browser service could not start a session: {type(exc).__name__}") from exc
        return {"session_id": made.get("id"),
                "live_url": await self._collector._live_view(made.get("debuggerUrl")),
                "websocket_url": _reachable(made.get("websocketUrl"), self.base_url),
                "user_agent": made.get("userAgent"), "dimensions": made.get("dimensions") or {}}

    _true_agent: str | None = None

    async def true_user_agent(self) -> str | None:
        """What the browser really is, from its own Browser.getVersion.

        Left to itself Steel gives each session a made-up user agent, and the
        page then tells two stories -- a Chrome in the string, another in the
        client hints -- which is exactly what a bot check looks for; Urban
        Company's Turnstile spun forever on it. Told its own truth, the
        browser is offered the checkbox instead.
        """
        if self._true_agent:
            return self._true_agent
        try:
            import json

            import websockets
            ws_url = _reachable("ws://0.0.0.0:3000/", self.base_url) if self.base_url else None
            if not ws_url:
                return None
            # The socket is wherever the API is; Steel reports it per session,
            # but the browser behind it is one and the same.
            ws_url = "ws://" + (urlsplit(self.base_url).netloc) + "/"
            async with websockets.connect(ws_url, additional_headers={"Origin": self.base_url}, open_timeout=10) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
                reply = json.loads(await ws.recv())
            agent = (reply.get("result") or {}).get("userAgent") or ""
            self._true_agent = agent.replace("HeadlessChrome", "Chrome") or None
        except Exception:  # noqa: BLE001 - then Steel's own default stands
            logger.warning("could not read the browser's user agent", exc_info=True)
            self._true_agent = None
        return self._true_agent

    async def open_at(self, url: str, *, minutes: int) -> dict:
        body = {"timeout": minutes * 60_000, "dimensions": {"width": 1280, "height": 800}}
        agent = announce(await self.true_user_agent())
        if agent:
            body["userAgent"] = agent
        session = await self._create(body)
        await self._goto(session, url)
        return session


    async def _goto(self, session: dict, url: str) -> None:
        """Steer the live browser to a page through its DevTools socket."""
        ws = session.get("websocket_url")
        if not ws:
            return
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(ws, timeout=15_000)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:  # noqa: BLE001 - the person can type the address; the sitting still works
            logger.warning("could not steer the browser to %s", url, exc_info=True)

    # ------------------------------------------------------------------
    # what the browser holds, read and written over its own socket
    #
    # Steel's context endpoint returns only the cookies a page's script can
    # see; a site's sign-in cookie is usually httpOnly, so a session sealed
    # from it would not sign anybody in. The browser's own socket returns
    # every cookie, and takes them back. And because Steel's one browser
    # keeps its profile between sessions, what a sitting leaves in it is
    # cleared on release: the next session starts with nothing of this one.
    # ------------------------------------------------------------------

    def _socket(self) -> str:
        return "ws://" + urlsplit(self.base_url).netloc + "/"

    async def _cdp(self, calls):
        """Run a few CDP calls on the current page, in one connection.
        `calls` is an async function taking (call, sid)."""
        import json

        import websockets
        async with websockets.connect(self._socket(), additional_headers={"Origin": self.base_url}, max_size=32 * 1024 * 1024,
                                      open_timeout=15) as ws:
            counter = [0]

            async def call(method, params=None, sid=None):
                counter[0] += 1
                m = {"id": counter[0], "method": method, "params": params or {}}
                if sid:
                    m["sessionId"] = sid
                await ws.send(json.dumps(m))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == counter[0]:
                        if r.get("error"):
                            raise RuntimeError(f"{method}: {r['error'].get('message')}")
                        return r.get("result") or {}
            targets = await call("Target.getTargets")
            page = next((t for t in targets.get("targetInfos", []) if t["type"] == "page" and not t["url"].startswith(("devtools:", "chrome:"))), None)
            sid = None
            if page:
                sid = (await call("Target.attachToTarget", {"targetId": page["targetId"], "flatten": True})).get("sessionId")
            return await calls(call, sid)

    async def context(self, session_id: str) -> dict:
        async def read(call, sid):
            cookies = (await call("Storage.getCookies")).get("cookies", [])
            storage = {"localStorage": {}, "sessionStorage": {}}
            if sid:
                got = await call("Runtime.evaluate", {"returnValue": True, "expression":
                    "JSON.stringify({origin: location.origin, local: Object.fromEntries(Object.entries(localStorage)), "
                    "session: Object.fromEntries(Object.entries(sessionStorage))})"}, sid)
                import json as _json
                try:
                    found = _json.loads(got["result"]["value"])
                    storage["localStorage"][found["origin"]] = found["local"]
                    storage["sessionStorage"][found["origin"]] = found["session"]
                except Exception:  # noqa: BLE001 - a page with no storage to speak of
                    pass
            version = await call("Browser.getVersion")
            return {"cookies": cookies, **storage, "userAgent": version.get("userAgent")}
        try:
            return await self._cdp(read)
        except Exception as exc:  # noqa: BLE001
            raise NoCollector(f"the browser's session could not be read: {type(exc).__name__}") from exc

    async def open_with(self, context: dict, *, user_agent: str | None, minutes: int) -> dict:
        body = {"timeout": minutes * 60_000, "dimensions": {"width": 1280, "height": 800}}
        agent = announce(user_agent or await self.true_user_agent())
        if agent:
            body["userAgent"] = agent
        session = await self._create(body)
        cookies = [self._cookie_param(c) for c in (context.get("cookies") or [])]
        if cookies:
            async def put(call, sid):
                await call("Network.clearBrowserCookies", {}, sid) if sid else None
                await call("Storage.setCookies", {"cookies": cookies})
                return None
            try:
                await self._cdp(put)
            except Exception as exc:  # noqa: BLE001
                raise NoCollector(f"the session could not be put into the browser: {type(exc).__name__}") from exc
        session["storage"] = {k: context.get(k) or {} for k in ("localStorage", "sessionStorage")}
        return session

    @staticmethod
    def _cookie_param(c: dict) -> dict:
        out = {"name": c.get("name"), "value": c.get("value"), "domain": c.get("domain"), "path": c.get("path") or "/",
               "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly"))}
        if c.get("expires") and c["expires"] > 0:
            out["expires"] = c["expires"]
        if c.get("sameSite") in ("Strict", "Lax", "None"):
            out["sameSite"] = c["sameSite"]
        return out

    async def release(self, session_id: str | None) -> None:
        # Nothing of this session stays in the shared profile.
        async def wipe(call, sid):
            await call("Storage.clearCookies")
            if sid:
                try:
                    await call("Storage.clearDataForOrigin", {"origin": "*", "storageTypes": "all"}, sid)
                except Exception:  # noqa: BLE001
                    pass
            return None
        try:
            await self._cdp(wipe)
        except Exception:  # noqa: BLE001 - the release still happens; the next open_with clears again
            logger.warning("could not clear the browser after the session", exc_info=True)
        await self._collector.close({"session_id": session_id})


class NoBrowser:
    """A deployment without Steel: a sign-in sitting cannot open."""

    async def open_at(self, url: str, *, minutes: int) -> dict:
        raise NoCollector("no browser is configured on this deployment (FAMILYOS_STEEL_URL)")

    async def open_with(self, context: dict, *, user_agent: str | None, minutes: int) -> dict:
        raise NoCollector("no browser is configured on this deployment (FAMILYOS_STEEL_URL)")

    async def context(self, session_id: str) -> dict:
        raise NoCollector("no browser is configured on this deployment")

    async def release(self, session_id: str | None) -> None:
        return None


_browser = NoBrowser()


def use_browser(browser) -> None:
    global _browser
    _browser = browser


def current_browser():
    return _browser
