"""A browser on this machine, for errands, looks and sign-in sittings.

Steel is a browser rented in a datacenter: every run costs a session, and
sites that distrust datacenter addresses challenge it. When FamilyOS runs
on the family's own Mac, the family's own browser is the better one: their
IP, no bill per run, nothing leaves the house. This is Playwright's
Chromium launched here, with the same contract SteelBrowser keeps --
open_at, open_with, context, release -- so the runbooks, the generalist
and the sittings do not know which one they got.

A sitting opens a visible window on this machine: the person signs in
there, and the console says so instead of embedding a live view. A task
runs headless. Each session is its own browser process with its own
profile, thrown away at release, so nothing of one run reaches the next.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from familyos.execution import agent

logger = logging.getLogger(__name__)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _browsers_dir():
    import os
    import pathlib
    import sys
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return pathlib.Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    home = pathlib.Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    if sys.platform.startswith("win"):
        return pathlib.Path(os.environ.get("LOCALAPPDATA", home)) / "ms-playwright"
    return home / ".cache" / "ms-playwright"


def available() -> bool:
    """Whether Playwright and a Chromium it can launch are on this machine."""
    try:
        import playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    d = _browsers_dir()
    return d.is_dir() and any(x.name.startswith("chromium-") for x in d.iterdir())


class LocalBrowser:
    """Chromium on this machine, one process per session."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    async def _launch(self, *, headed: bool, minutes: int, user_agent: str | None) -> dict:
        from playwright.async_api import async_playwright
        port = _free_port()
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(headless=not headed, args=[f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1"])
        except Exception as exc:  # noqa: BLE001 - no Chromium here
            await pw.stop()
            from familyos.execution.steel import NoCollector
            raise NoCollector(f"the local browser could not start ({type(exc).__name__}); run: python -m playwright install chromium") from exc
        if user_agent is None:
            # The browser's own user agent, read from itself, so the token
            # rides on the truth (a made-up one is what a bot check sees).
            probe = await browser.new_context()
            try:
                user_agent = await (await probe.new_page()).evaluate("navigator.userAgent")
            finally:
                await probe.close()
        user_agent = agent.announce(user_agent)
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=user_agent)
        page = await context.new_page()
        session_id = "local-" + uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"pw": pw, "browser": browser, "context": context, "page": page,
                                      "timer": asyncio.get_running_loop().call_later(minutes * 60, lambda: asyncio.ensure_future(self.release(session_id)))}
        return {"session_id": session_id, "websocket_url": f"http://127.0.0.1:{port}", "live_url": None,
                "user_agent": user_agent, "dimensions": {"width": 1280, "height": 800}, "local": True}

    async def true_user_agent(self) -> str | None:
        return None

    async def open_at(self, url: str, *, minutes: int) -> dict:
        """A visible window on this machine, on the sign-in page."""
        session = await self._launch(headed=True, minutes=minutes, user_agent=None)
        page = self._sessions[session["session_id"]]["page"]
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception:  # noqa: BLE001 - the person can navigate themselves
            logger.warning("local browser could not open %s", url, exc_info=True)
        return session

    async def open_with(self, context: dict, *, user_agent: str | None, minutes: int) -> dict:
        """A headless browser already holding a sealed session's state."""
        session = await self._launch(headed=False, minutes=minutes, user_agent=user_agent)
        held = self._sessions[session["session_id"]]
        cookies = []
        for c in context.get("cookies") or []:
            cookie = {"name": c.get("name"), "value": c.get("value"), "domain": c.get("domain"), "path": c.get("path") or "/",
                      "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly"))}
            if c.get("expires") and c["expires"] > 0:
                cookie["expires"] = c["expires"]
            if c.get("sameSite") in ("Strict", "Lax", "None"):
                cookie["sameSite"] = c["sameSite"]
            if cookie["domain"]:
                cookies.append(cookie)
        if cookies:
            try:
                await held["context"].add_cookies(cookies)
            except Exception as exc:  # noqa: BLE001
                from familyos.execution.steel import NoCollector
                raise NoCollector(f"the session could not be put into the local browser: {type(exc).__name__}") from exc
        session["storage"] = {k: context.get(k) or {} for k in ("localStorage", "sessionStorage")}
        return session

    async def context(self, session_id: str) -> dict:
        """What the browser holds: cookies, and the storage of the page it is on."""
        held = self._sessions.get(session_id)
        if held is None:
            from familyos.execution.steel import NoCollector
            raise NoCollector("that browser session is gone")
        state = await held["context"].storage_state()
        storage = {"localStorage": {}, "sessionStorage": {}}
        for origin in state.get("origins") or []:
            storage["localStorage"][origin["origin"]] = {i["name"]: i["value"] for i in origin.get("localStorage") or []}
        try:
            page = held["context"].pages[-1] if held["context"].pages else held["page"]
            found = await page.evaluate("() => ({origin: location.origin, session: Object.fromEntries(Object.entries(sessionStorage))})")
            storage["sessionStorage"][found["origin"]] = found["session"]
        except Exception:  # noqa: BLE001
            pass
        version = held["browser"].version
        agent = await held["page"].evaluate("() => navigator.userAgent") if held["page"] else None
        return {"cookies": state.get("cookies") or [], **storage, "userAgent": agent or f"Chrome/{version}"}

    async def release(self, session_id: str | None) -> None:
        held = self._sessions.pop(session_id or "", None)
        if held is None:
            return
        held["timer"].cancel()
        for step in (held["context"].close, held["browser"].close, held["pw"].stop):
            try:
                await step()
            except Exception:  # noqa: BLE001
                pass


def describe() -> str:
    return "browser: local (Playwright's Chromium on this machine: the family's own address, no session bill; a sitting opens a window here)"
