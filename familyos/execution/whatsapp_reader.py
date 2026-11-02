"""Reading a member's own WhatsApp Web, for the chats they named, and nothing else.

A linked WhatsApp Web session keeps its sign-in in the browser's own storage, in keys the page cannot export, so it cannot be sealed
and restored the way a cookie jar is (execution/sessions.py). The only thing that holds it is the browser's profile directory, kept
on this machine under the member's id. That is a credential on disk, the weaker pattern sessions.py argues against, and it is the
reason this is off by default, one profile per member, and deleted by `forget`.

What this module may do: open web.whatsapp.com, show the link code, search for a chat by name and read the messages on screen.
What it must never do: type into a message box, send, react, forward, delete or open a chat nobody named. There is no method here
that writes a message, on purpose. Opening a chat marks it read on the sender's side; the member is told so before they say yes.

The page's markup is WhatsApp's and moves without notice. The selectors are kept together at the top; a layout that stops matching
reports `needs_link` or an error, never a guess. They were written from the markup public scrapers rely on and have not yet been run
against the member's own account.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from familyos.identity import Invalid
from familyos.settings import settings

logger = logging.getLogger(__name__)

URL = "https://web.whatsapp.com/"
# WhatsApp Web turns away a browser whose user agent says "HeadlessChrome" ("works with Google Chrome 100+"), so the headless one says it is Chrome.
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MAX_CHATS = 8
SYNC_SECONDS = 150           # how long to wait for a newly linked device to finish its first history sync
MAX_IMAGES = 6              # pictures opened per chat per pass (the newest ones not already taken); each is opened full size, which takes a few seconds
MAX_PER_CHAT = 30            # the newest messages on screen, per chat, per pass
LINK_MINUTES = 3
LINK_SECONDS = 100          # the whole link attempt, so a page that stops answering is an error, not a spinner (the code itself can take a minute to appear)

SEL_CHAT_LIST = "#pane-side"
SEL_SEARCH = 'input[aria-label="Search or start a new chat"], input[data-tab="3"], div[contenteditable="true"][data-tab="3"]'
SEL_MESSAGE = "div[data-pre-plain-text]"
SEL_TEXT = "span.selectable-text, [data-testid='selectable-text']"
# The sign-in page words this differently by moment: a hidden heading ("Link with phone number instead.") and a visible button ("Log in with phone number"),
# and the button can take several seconds to appear after the QR code.
LINK_WITH_PHONE = re.compile(r"(log in|link) with phone number", re.I)
CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b")


class AmbiguousChat(Invalid):
    """Two or more chats on the account carry the name given. Anyone can start a group with any name, so the first match is not taken."""


class NeedsLink(Invalid):
    """The profile is not signed in: the member links again. Nothing here does it for them."""


@dataclass
class Message:
    chat: str
    id: str
    stamp: str              # WhatsApp's own "[10:09, 14/10/2026]", in the account's locale; never parsed for ordering
    author: str
    text: str
    is_group: bool = False
    media_b64: str | None = None     # a picture, full size, as the page holds it; read by the household's own model, never by a cloud one unless that is its choice
    media_type: str | None = None


@dataclass
class Read:
    messages: list[Message] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)       # named chats that were not found on this account
    ambiguous: list[str] = field(default_factory=list)     # named chats that two or more chats answer to: not read, the member says which


class Reader(Protocol):
    async def start_link(self, member_id: uuid.UUID, phone: str) -> dict: ...
    async def linked(self, member_id: uuid.UUID) -> bool: ...
    async def read(self, member_id: uuid.UUID, chats: list[str], known: dict[str, list[str]] | None = None) -> Read: ...
    async def qr(self, member_id: uuid.UUID) -> str | None: ...
    async def forget(self, member_id: uuid.UUID) -> None: ...


def profile_dir(member_id: uuid.UUID) -> Path:
    base = Path(settings.whatsapp_profile_dir or "~/.familyos/whatsapp").expanduser()
    return base / str(member_id)


def clean_chats(names: list[str]) -> list[str]:
    """The chats a member named: trimmed, de-duplicated, a handful at most."""
    seen: list[str] = []
    for n in names or []:
        n = " ".join(str(n).split())[:80]
        if n and n.lower() not in {s.lower() for s in seen}:
            seen.append(n)
    if len(seen) > MAX_CHATS:
        raise Invalid(f"name up to {MAX_CHATS} chats; FamilyOS reads only those")
    return seen


def code_of(row_text: str) -> tuple[str, str | None]:
    """A country row's (name, dial code digits). The row of the country already selected shows no code, so it comes back with None."""
    lines = [x.strip() for x in (row_text or "").split("\n") if x.strip()]
    if not lines:
        return "", None
    m = re.fullmatch(r"\+(\d{1,4})", lines[-1])
    return lines[0], (m.group(1) if m else None)


_STAMP = re.compile(r"\[\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*(?:([AaPp])\.?[Mm]\.?)?\s*,\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*\]")


def date_order(stamps: list[str]) -> str | None:
    """Whether this account's stamps are month/day/year or day/month/year, read off the data: a first number above 12 can only be a day, a
    second one only a day the other way round. WhatsApp's order did not follow the browser's language (checked on a live account on
    16 Oct 2026: en-GB still gave 8/29/2026), so it is learned, not assumed. None while every stamp seen is ambiguous."""
    seen = set()
    for st in stamps:
        m = _STAMP.fullmatch((st or "").strip())
        if not m:
            continue
        a, b = int(m[4]), int(m[5])
        if a > 12 and b <= 12:
            seen.add("dmy")
        elif b > 12 and a <= 12:
            seen.add("mdy")
    return seen.pop() if len(seen) == 1 else None


def parse_stamp(stamp: str, tz: str | None = None, order: str | None = None, now=None) -> str | None:
    """WhatsApp's own "[16:59, 9/29/2026]" as an ISO time. The order of day and month is `order` (see date_order); a stamp whose order cannot be
    told, or that is not a date, comes back None rather than guessed, because a wrong month moves every "tomorrow" in the message."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    m = _STAMP.fullmatch((stamp or "").strip())
    if not m:
        return None
    hour, minute, ampm, x, y, year = int(m[1]), int(m[2]), m[3], int(m[4]), int(m[5]), int(m[6])
    if ampm:
        hour = hour % 12 + (12 if ampm.lower() == "p" else 0)
    if x > 12 and y <= 12:
        day, month = x, y
    elif y > 12 and x <= 12:
        day, month = y, x
    elif order == "dmy":
        day, month = x, y
    elif order == "mdy":
        month, day = x, y
    else:
        # Order unknown and the stamp ambiguous: it can still be told if only one reading is a date a recent message could have (not in the
        # future, not more than a year old). Otherwise it stays unknown, and the caller says so.
        if now is None:
            return None
        from datetime import timedelta
        zone = ZoneInfo(tz) if tz else None
        fits = []
        for d_, m_ in ((x, y), (y, x)):
            try:
                cand = datetime(year, m_, d_, hour, minute, tzinfo=zone)
            except ValueError:
                continue
            if now - timedelta(days=366) <= cand <= now + timedelta(days=2):
                fits.append(cand)
        return fits[0].isoformat() if len(fits) == 1 else None
    try:
        when = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz) if tz else None)
    except (ValueError, KeyError):
        return None
    return when.isoformat()


def parse_pre_plain(raw: str) -> tuple[str, str]:
    """'[10:09, 14/10/2026] Emily Carter: ' -> ('[10:09, 14/10/2026]', 'Emily Carter')."""
    m = re.match(r"\s*(\[[^\]]*\])\s*(.*?):\s*$", raw or "", re.S)
    return (m.group(1), m.group(2)) if m else ("", "")


class NoReader:
    async def start_link(self, member_id, phone):
        raise Invalid("reading WhatsApp is not switched on for this deployment")

    async def linked(self, member_id):
        return False

    async def qr(self, member_id):
        return None

    async def read(self, member_id, chats, known=None):
        raise NeedsLink("reading WhatsApp is not switched on for this deployment")

    async def forget(self, member_id):
        shutil.rmtree(profile_dir(member_id), ignore_errors=True)


def runs_here() -> bool:
    """Whether this process may open the WhatsApp profiles: always with one worker; with several, only the one told to (FAMILYOS_WHATSAPP_WORKER)."""
    return (not settings.multi_worker) or settings.whatsapp_worker


class OtherWorkerReader:
    """The reader on a worker that does not hold the profiles: every question is answered with where to ask. It opens nothing and touches no folder."""

    @staticmethod
    def _where() -> Invalid:
        return Invalid("WhatsApp is read by the one worker that holds the linked browser profiles (FAMILYOS_WHATSAPP_WORKER=true); "
                       "this worker does not. Route WhatsApp requests there.")

    async def start_link(self, member_id, phone):
        raise self._where()

    async def linked(self, member_id):
        raise self._where()

    async def qr(self, member_id):
        raise self._where()

    async def read(self, member_id, chats, known=None):
        raise self._where()

    async def forget(self, member_id):
        raise self._where()


@contextlib.asynccontextmanager
async def profile_lock(member_id: uuid.UUID, seconds: float = 20):
    """One process at a time on a member's profile directory, across workers: a Postgres advisory lock held on its own connection for as long as
    the browser is open. The in-process lock still serialises this worker's browsers; this one makes a second worker that is wrongly pointed at the
    same directory wait, and then refuse, instead of opening a second browser on one profile."""
    from familyos import db
    key = f"whatsapp-profile:{member_id}"
    conn = await db.raw_pool().acquire()
    got = False
    try:
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        while True:
            got = bool(await conn.fetchval("SELECT pg_try_advisory_lock(hashtextextended($1, 0))", key))
            if got:
                break
            if loop.time() >= end:
                raise Invalid("another worker is using this WhatsApp profile; try again in a minute")
            await asyncio.sleep(0.25)
        yield
    finally:
        try:
            if got:
                await conn.execute("SELECT pg_advisory_unlock(hashtextextended($1, 0))", key)
        finally:
            await db.raw_pool().release(conn)


class PlaywrightReader:
    """One persistent browser profile per member, opened one at a time (WhatsApp Web allows a page per profile, and a laptop one
    more browser than it needs)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._held: dict[uuid.UUID, tuple[object, float]] = {}      # a linking context kept open until its code is entered
        self._held_locks: dict[uuid.UUID, contextlib.AsyncExitStack] = {}      # the profile lock each of those holds, released with it

    async def _open(self, member_id: uuid.UUID, *, headless: bool = True):
        from playwright.async_api import async_playwright
        path = profile_dir(member_id)
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        pw = await async_playwright().start()
        try:
            ctx = await pw.chromium.launch_persistent_context(str(path), headless=headless, viewport={"width": 1280, "height": 900}, user_agent=USER_AGENT,
                                                              args=["--disable-blink-features=AutomationControlled"])
        except Exception:
            await pw.stop()
            raise
        return pw, ctx

    @staticmethod
    async def _is_linked(page, wait_ms: int = 25000) -> bool:
        try:
            await page.wait_for_selector(SEL_CHAT_LIST, timeout=wait_ms)
            return True
        except Exception:  # noqa: BLE001 - not there in time: the link screen, or a page that did not load
            return False

    async def _release(self, member_id: uuid.UUID) -> None:
        held = self._held.pop(member_id, None)
        if held:
            try:
                await held[0].close()
            except Exception:  # noqa: BLE001
                pass
        lock = self._held_locks.pop(member_id, None)
        if lock is not None:
            await lock.aclose()

    async def _acquire(self) -> None:
        try:
            await asyncio.wait_for(self._lock.acquire(), 5)
        except TimeoutError:
            raise Invalid("another WhatsApp action is still running on this machine; wait a minute, or restart the server if it never ends") from None

    @staticmethod
    async def _close(ctx, pw) -> None:
        for what in (ctx.close(), pw.stop()):
            try:
                await asyncio.wait_for(what, 10)
            except Exception:  # noqa: BLE001 - a browser that will not close is killed with the server
                logger.warning("whatsapp browser did not close cleanly", exc_info=True)

    async def start_link(self, member_id, phone):
        await self._acquire()
        stack = contextlib.AsyncExitStack()
        try:
            await self._release(member_id)           # an earlier attempt's browser, and with it its lock on the profile
            await stack.enter_async_context(profile_lock(member_id))
            pw, ctx = await self._open(member_id, headless=False)   # a visible window: the page shows only a spinner to a headless browser
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            step = ["opened the browser"]
            try:
                out = await asyncio.wait_for(self._link(member_id, phone, pw, ctx, page, step), LINK_SECONDS)
                if member_id in self._held:
                    self._held_locks[member_id] = stack.pop_all()        # the browser stays open for the code: so does the lock
                return out
            except BaseException as exc:
                seen = await self._snapshot(page, member_id)
                await self._close(ctx, pw)
                logger.warning("whatsapp link failed after: %s; page: %s", step[-1], seen)
                if isinstance(exc, Invalid):
                    raise
                raise Invalid(f"WhatsApp Web did not show a link code ({type(exc).__name__}) after: {step[-1]}; what the page showed: {seen[:160]}") from exc
        finally:
            await stack.aclose()
            self._lock.release()

    async def _snapshot(self, page, member_id) -> str:
        """What the sign-in page shows, for whoever is debugging: only when it IS the sign-in page. A signed-in page lists chat names and message
        previews, so it is never read out into a log or an error, and no screenshot is written (an earlier one is removed)."""
        (profile_dir(member_id) / "last_link.png").unlink(missing_ok=True)
        try:
            if await page.locator(SEL_CHAT_LIST).count():
                return "(a signed-in page: not shown)"
            text = await asyncio.wait_for(page.inner_text("body"), 5)
        except Exception:  # noqa: BLE001
            return "(the page could not be read)"
        return re.sub(r"\d{5,}", "…", " | ".join(text.split("\n")))[:300]

    async def _link(self, member_id, phone, pw, ctx, page, step: list[str]) -> dict:
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        step.append("loaded web.whatsapp.com")
        if await self._is_linked(page, 15000):
            await self._close(ctx, pw)
            return {"linked": True, "code": None}
        step.append("the page is not signed in")
        await self._open_phone_login(page)
        step.append("chose to log in with a phone number")
        await self._enter_number(page, phone, step)
        step.append("typed the number")
        await page.keyboard.press("Enter")
        step.append("pressed Next")
        code = None
        try:
            await page.wait_for_function("document.body.innerText.match(/[A-Z0-9]{4}-[A-Z0-9]{4}/)", timeout=25000)
            code = CODE.search(await page.inner_text("body"))
        except Exception:  # noqa: BLE001 - the page showed a spinner and no code: fall back to the QR code on the same page
            step.append("no code appeared, so switching to the QR code")
        qr = None
        if code is None:
            await page.get_by_text(re.compile(r"log in with qr code", re.I)).first.click(timeout=8000)
            qr = await self._qr_png(page)
            if qr is None:
                raise Invalid("WhatsApp Web showed neither a link code nor a QR code")
            step.append("the QR code appeared")
        else:
            step.append("the code appeared")
        self._held[member_id] = (_Held(ctx, pw), time.monotonic() + LINK_MINUTES * 60)
        asyncio.get_running_loop().call_later(LINK_MINUTES * 60 + 5, lambda: asyncio.ensure_future(self._expire(member_id)))
        return {"linked": False, "code": code.group(0) if code else None, "qr": qr, "expires_in": LINK_MINUTES * 60}

    @staticmethod
    async def _qr_png(page) -> str | None:
        """The page's QR code as a base64 PNG, or None. It rotates every half minute, so the page asks again while it waits."""
        import base64
        try:
            canvas = page.locator("canvas").first
            await canvas.wait_for(state="visible", timeout=15000)
            return base64.b64encode(await canvas.screenshot(timeout=8000)).decode()
        except Exception:  # noqa: BLE001
            return None

    async def qr(self, member_id):
        held = self._held.get(member_id)
        if not held:
            return None
        return await self._qr_png(held[0].ctx.pages[0])

    @staticmethod
    async def _open_phone_login(page, seconds: int = 30) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            found = page.get_by_text(LINK_WITH_PHONE)
            for i in range(await found.count()):
                try:
                    await found.nth(i).click(timeout=1500)
                    return
                except Exception:  # noqa: BLE001 - the hidden twin, or not clickable yet: try the next, then look again
                    continue
            await asyncio.sleep(1)
        raise Invalid("WhatsApp Web did not offer to link with a phone number")

    @staticmethod
    async def _enter_number(page, phone: str, step: list[str] | None = None) -> None:
        """Pick the number's country in the page's list, then type the rest. Nothing is submitted here.

        The page wants the country chosen and the national number typed (a whole international number is read as the page's own country).
        The list is virtual and has a search box that matches dial-code digits, so the number's own first digits are searched, longest first."""
        step = step if step is not None else []
        digits = re.sub(r"\D", "", phone)
        shown = re.search(r"\+(\d{1,4})\b", await page.inner_text("body"))          # the code of the country already selected
        current = shown.group(1) if shown else None
        await page.locator("button").first.click(timeout=10000)
        await page.wait_for_selector("button[aria-label^='Selected country']", timeout=10000)
        step.append("opened the country list")
        await asyncio.sleep(1)                                   # the search box takes focus a moment after the list opens
        rows_js = """() => [...document.querySelectorAll("button[aria-label^='Selected country']")].map((b) => (b.innerText || '').trim())"""
        chosen = None
        for size in (4, 3, 2, 1):
            prefix = digits[:size]
            await page.keyboard.press("ControlOrMeta+A")        # Control+A only moves the cursor on a Mac
            await page.keyboard.press("Backspace")
            await page.keyboard.type(prefix, delay=40)
            await asyncio.sleep(0.8)
            rows = [code_of(t) for t in await page.evaluate(rows_js)]
            logger.debug("whatsapp country search %r: current=%r rows=%r", prefix, current, rows[:4])
            exact = sorted((n for n, c in rows if c == prefix), key=lambda n: n != "United States")      # +1 is shared by many: the plain one first
            if exact:
                chosen = (prefix, exact[0], False)
                break
            if current in (None, prefix) and any(c is None for _n, c in rows):
                chosen = (prefix, next(n for n, c in rows if c is None), True)      # the selected country: it shows no code of its own
                break
        if chosen is None:
            raise Invalid("WhatsApp Web's country list has no match for the start of that number")
        prefix, name, already = chosen
        step.append(f"picked the country for +{prefix}")
        if already:
            await page.keyboard.press("Escape")
        else:
            await page.locator(f"button[aria-label^='Selected country: {name}.']").first.click(timeout=10000)
        await page.wait_for_selector("input[data-testid='phone-number-input']", state="visible", timeout=10000)
        box = page.locator("input[data-testid='phone-number-input']").first
        await box.fill("", timeout=10000)
        await page.keyboard.type(digits[len(prefix):], delay=40)
        if f"+{prefix}" not in await page.inner_text("body"):
            raise Invalid(f"WhatsApp Web did not show +{prefix} after the country was picked")      # never press Next on the wrong country

    @contextlib.asynccontextmanager
    async def _locked(self, seconds: float = 20):
        try:
            await asyncio.wait_for(self._lock.acquire(), seconds)
        except TimeoutError:
            raise Invalid("another WhatsApp action is still running; try again in a minute") from None
        try:
            yield
        finally:
            self._lock.release()

    async def _expire(self, member_id: uuid.UUID) -> None:
        async with self._locked():
            held = self._held.get(member_id)
            if held and time.monotonic() >= held[1]:
                await self._release(member_id)

    async def linked(self, member_id):
        async with self._locked():
            held = self._held.get(member_id)
            if held:
                page = held[0].ctx.pages[0]
                if await self._is_linked(page, 1500):
                    # Linked: let the page finish writing its session to the profile before the browser closes.
                    await asyncio.sleep(5)
                    await self._release(member_id)
                    return True
                return False
            if not profile_dir(member_id).exists():
                return False
            async with profile_lock(member_id):
                pw, ctx = await self._open(member_id)
                try:
                    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                    await page.goto(URL, wait_until="domcontentloaded")
                    return await self._is_linked(page)
                finally:
                    await ctx.close()
                    await pw.stop()

    async def read(self, member_id, chats, known=None):
        if not chats:
            return Read()
        async with self._lock:
            if member_id in self._held:
                raise Invalid("a link is in progress; finish it first")
            if not profile_dir(member_id).exists():
                raise NeedsLink("WhatsApp is not linked yet")
            async with profile_lock(member_id):
                pw, ctx = await self._open(member_id)
                try:
                    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                    await page.goto(URL, wait_until="domcontentloaded")
                    if not await self._is_linked(page, 40000):
                        # One more look before calling it lapsed: a slow load or a second browser on the same profile looks the same.
                        await page.reload(wait_until="domcontentloaded")
                        if not await self._is_linked(page, 40000):
                            raise NeedsLink("WhatsApp Web asks to be linked again")
                    out = Read()
                    for name in chats:
                        try:
                            got = await self._chat(page, name, set((known or {}).get(name) or []))
                        except AmbiguousChat:
                            out.ambiguous.append(name)
                            continue
                        if got is None:
                            out.missing.append(name)
                        else:
                            out.messages.extend(got)
                    return out
                finally:
                    await ctx.close()
                    await pw.stop()

    async def _chat(self, page, name: str, known: set[str] | None = None) -> list[Message] | None:
        """Open one named chat by searching for it, and read the messages on screen. Only ever a search box is typed into."""
        search = page.locator(SEL_SEARCH).first
        await search.click(timeout=10000)
        await page.keyboard.press("ControlOrMeta+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(name, delay=20)
        rows = page.locator(f"{SEL_CHAT_LIST} span[title]").filter(has_text=re.compile("^" + re.escape(name) + "$", re.I))
        try:
            await rows.first.wait_for(state="visible", timeout=8000)
        except Exception:  # noqa: BLE001 - no chat of that name on this account
            await page.keyboard.press("Escape")
            return None
        await asyncio.sleep(1.0)            # the rest of the search results land a moment after the first
        if await rows.count() > 1:
            # A group can be started with any name, a lookalike of the class's included: with two answers there is no telling which is
            # the family's, so nothing is read from either.
            await page.keyboard.press("Escape")
            raise AmbiguousChat(name)
        try:
            await rows.first.click(timeout=8000)
        except Exception:  # noqa: BLE001 - it went away between looking and clicking
            await page.keyboard.press("Escape")
            return None
        # A freshly linked device is still downloading history ("Syncing older messages"): give it time, and read what is there once it is.
        end = time.monotonic() + SYNC_SECONDS
        while time.monotonic() < end:
            if await page.locator(SEL_MESSAGE).count() and not await page.get_by_text(re.compile("Syncing older messages", re.I)).count():
                break
            await asyncio.sleep(3)
        await page.wait_for_selector(SEL_MESSAGE, timeout=10000)
        extract = """([sel, textSel]) => {
            const out = [];
            for (const el of document.querySelectorAll(sel)) {
                const row = el.closest('[data-id]');
                const t = el.querySelector(textSel);
                out.push({pre: el.getAttribute('data-pre-plain-text'), id: row ? row.getAttribute('data-id') : null, text: t ? t.innerText : ''});
            }
            return out;
        }"""
        # The list is virtual (only what is near the screen exists) and fills in as it loads: let it settle, then scroll up a few screens,
        # keeping each message by its id, until there are enough or nothing new appears.
        raw: list[dict] = []
        seen: set[str] = set()
        pictures: dict[str, Message] = {}      # opened as they scroll past, because a message that leaves the screen leaves the page
        await asyncio.sleep(2)
        for _ in range(8):
            if len(pictures) < MAX_IMAGES:
                for pic in await self._pictures(page, name, False, (known or set()) | set(pictures), MAX_IMAGES - len(pictures)):
                    pictures[pic.id] = pic
            batch = await page.evaluate(extract, [SEL_MESSAGE, SEL_TEXT])
            fresh = [r for r in batch if r.get("id") and r["id"] not in seen]
            seen.update(r["id"] for r in fresh)
            raw = fresh + raw
            if len(raw) >= MAX_PER_CHAT:
                break
            await page.evaluate("() => { const l = document.querySelector('[data-testid=conversation-panel-messages]'); if (l) l.scrollTop = Math.max(0, l.scrollTop - l.clientHeight * 0.8); }")
            await asyncio.sleep(1.2)
            if not fresh and len(seen) and _ > 1:
                break
        raw = raw[-MAX_PER_CHAT:]
        # A group shows each sender's picture beside their messages, and has more than one author; message ids no longer say "@g.us".
        is_group = (await page.locator("[data-testid='group-chat-profile-picture']").count() > 0
                    or any("@g.us" in (r.get("id") or "") for r in raw)
                    or len({parse_pre_plain(r.get("pre") or "")[1] for r in raw} - {""}) > 1)
        msgs = []
        for r in raw:
            stamp, author = parse_pre_plain(r.get("pre") or "")
            if r.get("id") and r.get("text"):
                msgs.append(Message(chat=name, id=r["id"], stamp=stamp, author=author, text=r["text"].strip(), is_group=is_group))
        by_id = {m.id: m for m in msgs}
        for pic in pictures.values():
            pic.is_group = is_group
            if pic.id in by_id:                      # a captioned picture: one message, the words and the picture together
                by_id[pic.id].media_b64, by_id[pic.id].media_type = pic.media_b64, pic.media_type
            else:
                msgs.append(pic)
        await page.keyboard.press("Escape")
        return msgs

    async def _pictures(self, page, name: str, is_group: bool, known: set[str], limit: int = MAX_IMAGES) -> list[Message]:
        """The newest few pictures not already taken: open each full size (the thumbnails are empty until opened), copy its bytes out of the
        page, close it. Only a viewer is opened and closed; nothing is sent, saved to WhatsApp or downloaded to disk."""
        ids = await page.evaluate("""() => [...document.querySelectorAll('#main [data-testid=image-thumb]')].map((t) => { const r = t.closest('[data-id]'); return r ? r.getAttribute('data-id') : null; }).filter(Boolean)""")
        out: list[Message] = []
        for mid in [i for i in dict.fromkeys(ids) if i not in known][-limit:]:
            try:
                row = page.locator(f'#main [data-id="{mid}"]').first
                meta = await row.evaluate("""(r) => { const pre = r.querySelector('[data-pre-plain-text]'); const a = r.querySelector('[data-testid=author]'); const m = r.querySelector('[data-testid=msg-meta]');
                    const t = r.querySelector("span.selectable-text, [data-testid='selectable-text']");
                    return {pre: pre ? pre.getAttribute('data-pre-plain-text') : '', author: a ? a.innerText : '', meta: m ? m.innerText : '', caption: t ? t.innerText : ''}; }""")
                await row.locator("[data-testid=image-thumb]").first.click(timeout=6000)
                await page.wait_for_function("() => [...document.querySelectorAll('[data-testid=media-image] img, [data-testid=media-url-provider]')].some((i) => i.src && i.src.startsWith('blob:') && i.naturalWidth > 300)", timeout=10000)
                got = await page.evaluate("""async () => { const img = [...document.querySelectorAll('[data-testid=media-image] img, [data-testid=media-url-provider]')].find((i) => i.src && i.src.startsWith('blob:') && i.naturalWidth > 300);
                    const blob = await (await fetch(img.src)).blob(); const b64 = await new Promise((res) => { const f = new FileReader(); f.onload = () => res(String(f.result).split(',')[1]); f.readAsDataURL(blob); });
                    return {b64, type: blob.type || 'image/jpeg'}; }""")
                stamp, author = parse_pre_plain(meta.get("pre") or "")
                out.append(Message(chat=name, id=mid, stamp=stamp or (meta.get("meta") or ""), author=author or meta.get("author") or "", text=(meta.get("caption") or "").strip(),
                                   is_group=is_group, media_b64=got["b64"], media_type=got["type"]))
            except Exception:  # noqa: BLE001 - a picture that will not open is skipped, the rest of the chat is not lost
                logger.info("a picture in %r could not be read", name, exc_info=True)
            finally:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.8)
        return out

    async def forget(self, member_id):
        """Delete the login. If a read is running and the lock is not free in time, the folder goes anyway: removing a credential does not wait."""
        got = True
        try:
            await asyncio.wait_for(self._lock.acquire(), 20)
        except TimeoutError:
            got = False
        try:
            if got:
                await self._release(member_id)
            shutil.rmtree(profile_dir(member_id), ignore_errors=True)
        finally:
            if got:
                self._lock.release()


@dataclass
class _Held:
    ctx: object
    pw: object

    async def close(self) -> None:
        await self.ctx.close()
        await self.pw.stop()


_reader: Reader = NoReader()


def use_reader(reader: Reader) -> None:
    global _reader
    _reader = reader


def current_reader() -> Reader:
    return _reader


def configure() -> bool:
    """Pick the reader from settings, the way the browser is picked: named in configuration, never inferred."""
    if not settings.whatsapp_watch_enabled:
        use_reader(NoReader())
    else:
        use_reader(PlaywrightReader() if runs_here() else OtherWorkerReader())
    return settings.whatsapp_watch_enabled
