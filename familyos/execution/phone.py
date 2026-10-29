"""The phone as the errand's browser.

The app has a WKWebView. While a person holds "Run on this phone" open,
the app keeps a socket to the server and answers the same questions a
runbook asks of any browser: go here, what does the page say, which
buttons say Add, press the second one. The page renders on the phone, in
front of the person, with the family's own sign-ins and the family's own
address; a needs_you is not a hand-over to a rented browser somewhere, it
is the same screen, touched.

The server never sees a password and the model never sees the page except
through these questions, as everywhere else. A phone that goes away mid-run
ends the run as needs_you, and the commit marks (runbooks.Run.commit) say
whether a step may have landed.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import uuid

logger = logging.getLogger(__name__)

ANSWER_SECONDS = 60          # the phone has this long to answer one question
_phones: dict[uuid.UUID, PhoneDriver] = {}


class PhoneGone(RuntimeError):
    """The phone stopped answering."""


class TapRefused(RuntimeError):
    """The phone would not tap: the label names more than one thing on the screen, so a tap would be a guess."""


class PhoneDriver:
    """runbooks.Driver over a question-and-answer channel to the app.

    `send` is given by whoever holds the socket; answers arrive through
    `answer`. Each question carries an id; the reply must carry it back."""

    def __init__(self, errand_id: uuid.UUID, send, household_id: uuid.UUID | None = None) -> None:
        self.errand_id = errand_id
        self.household_id = household_id
        self._send = send
        self._waiting: dict[str, asyncio.Future] = {}
        self.gone = False
        self.steps = 0

    async def _ask(self, op: str, **args):
        if self.gone:
            raise PhoneGone("the phone is no longer connected")
        qid = uuid.uuid4().hex[:10]
        fut = asyncio.get_running_loop().create_future()
        self._waiting[qid] = fut
        try:
            await self._send({"id": qid, "op": op, **args})
            self.steps += 1
            return await asyncio.wait_for(fut, ANSWER_SECONDS)
        except (TimeoutError, Exception) as exc:  # noqa: BLE001
            self._waiting.pop(qid, None)
            if isinstance(exc, PhoneGone):
                raise
            raise PhoneGone(f"the phone did not answer ({type(exc).__name__})") from exc

    def answer(self, message: dict) -> None:
        fut = self._waiting.pop(str(message.get("id") or ""), None)
        if fut is not None and not fut.done():
            if message.get("error"):
                fut.set_exception(PhoneGone(str(message["error"])[:200]))
            else:
                fut.set_result(message.get("result"))

    def disconnect(self) -> None:
        self.gone = True
        for fut in self._waiting.values():
            if not fut.done():
                fut.set_exception(PhoneGone("the phone disconnected"))
        self._waiting.clear()

    # -- the Driver protocol --------------------------------------------------

    async def goto(self, url: str) -> None:
        await self._ask("goto", url=url)

    async def swipe(self, direction: str = "up") -> bool:
        """One screen of a list (the XCTest driver only)."""
        return bool(await self._ask("swipe", direction=direction))

    async def open(self, bundle: str, *, fresh: bool = False) -> str:
        """An app on the phone, by bundle id (the XCTest driver only). `fresh` quits it first, so a read starts from the app's own
        first screen and not wherever it was left (a child's page, scrolled to the bottom)."""
        return str(await self._ask("open", bundle=bundle, **({"fresh": True} if fresh else {})) or "")

    async def url(self) -> str:
        return str(await self._ask("url") or "")

    async def text(self) -> str:
        return str(await self._ask("text") or "")[:6000]

    async def screenshot(self) -> bytes:
        got = await self._ask("screenshot")
        try:
            return base64.b64decode(got or "")
        except Exception:  # noqa: BLE001
            return b""

    async def buttons(self, label: str) -> list[dict]:
        from familyos.execution.runbooks import parse_price
        got = await self._ask("buttons", label=label) or []
        return [{"index": int(b.get("index", i)), "near": str(b.get("near") or "")[:160], "price": parse_price(str(b.get("near") or ""))}
                for i, b in enumerate(got[:30])]

    async def links(self) -> list[dict]:
        got = await self._ask("links") or []
        return [{"text": str(a.get("text") or "")[:80], "href": str(a.get("href") or "")} for a in got[:60] if str(a.get("href") or "").startswith("https://")]

    async def press(self, label: str, index: int) -> bool:
        return bool(await self._ask("press", label=label, index=index))

    async def click_text(self, text: str, *, contains: bool = False) -> bool:
        """Tap the one element whose whole visible label is `text` (whitespace folded, any case). The XCTest driver answers
        {"tapped": bool, "matches": n}: no match is False, several is refused (never the first of them). A bare bool, from
        the app's web view, is taken as it is."""
        wanted = " ".join((text or "").split())
        # contains: the words as whole words inside one label ("Noah" in "Noah Rivera, 4-A"). For reading an app only; a
        # taught step that commits something never asks for it. Still exactly one element, or nothing is tapped.
        got = await self._ask("click_text", text=wanted, **({"contains": True} if contains else {}))
        if isinstance(got, dict):
            matches = int(got.get("matches") or 0)
            if matches > 1:
                raise TapRefused(f"{matches} things on the screen are labelled “{wanted}”; not tapping a guess")
            return bool(got.get("tapped")) and matches == 1
        return bool(got)

    async def close(self) -> None:
        try:
            await self._ask("close")
        except PhoneGone:
            pass


class PhoneBusy(RuntimeError):
    """Another household's phone is holding this id: it is never displaced by a stranger's."""


def attach(errand_id: uuid.UUID, send, household_id: uuid.UUID | None = None) -> PhoneDriver:
    """A phone is holding this errand open. One phone per errand; a second
    replaces the first, if it is the same household's (callers on the sockets
    check ownership first and pass the household; the refusal here is the second lock)."""
    old = _phones.get(errand_id)
    if old is not None:
        if household_id is not None and old.household_id is not None and old.household_id != household_id:
            raise PhoneBusy("that id is held by another household's phone")
        old.disconnect()
    driver = PhoneDriver(errand_id, send, household_id)
    _phones[errand_id] = driver
    return driver


def detach(errand_id: uuid.UUID, driver: PhoneDriver | None = None) -> None:
    held = _phones.get(errand_id)
    if held is not None and (driver is None or held is driver):
        held.disconnect()
        _phones.pop(errand_id, None)


def connected(errand_id: uuid.UUID) -> PhoneDriver | None:
    held = _phones.get(errand_id)
    return held if held is not None and not held.gone else None
