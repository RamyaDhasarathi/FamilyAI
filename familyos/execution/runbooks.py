"""Runbooks: how an errand is driven through a site, step by step.

A runbook is a plain sequence over a small browser driver -- go to a page,
read its words, find the buttons near some words, press one, keep a
picture -- with the errand's stop rules applied at every step. It does not
read the page with a model and it does not improvise: when it cannot find
what the next step needs, it stops where it is and hands the person the
browser, live, to finish. That is a normal outcome, not a failure. The
first run of any site is mostly hand-overs; each one shows what the next
step should look for.

The browser is whichever steel.current_browser() gives -- a rented Steel
session or the local Chromium on the machine FamilyOS runs on -- or, for a
run approved "on this phone", the app's own web view (execution/phone.py).
It holds the member's sealed session for the length of the run
(sessions.lease). Every page it reaches is checked against the site's own
hosts. Nothing here types a password, enters a card,
or answers an OTP; those stop the run by rule.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid
from collections.abc import Callable
from typing import Protocol

from familyos import artifacts, audit, notify
from familyos.db import pool
from familyos.execution import choose, disposable, sessions, sites, steel
from familyos.identity import Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

RUN_MINUTES = 15
MAX_STEPS = 24


class Driver(Protocol):
    """What a runbook may do to a page. Implemented over Playwright for a
    real browser, and by a script in tests."""

    async def goto(self, url: str) -> None: ...
    async def url(self) -> str: ...
    async def text(self) -> str: ...
    async def screenshot(self) -> bytes: ...
    async def buttons(self, label: str) -> list[dict]: ...      # [{index, near, price}]
    async def links(self) -> list[dict]: ...                     # [{text, href}] on the page
    async def press(self, label: str, index: int) -> bool: ...
    async def click_text(self, text: str) -> bool: ...
    async def close(self) -> None: ...


class PlaywrightDriver:
    """A page in the run's browser, over its DevTools socket."""

    # The card an Add belongs to: the nearest ancestor whose words carry a
    # price, else the nearest with enough words. Up to ten levels, because a
    # site's markup nests a button deep inside its card.
    _NEAR = ("b => { let box = b, fallback = null; for (let i = 0; i < 10 && box.parentElement; i++) { box = box.parentElement; "
             "const t = (box.innerText||'').replace(/\\s+/g,' ').trim(); if (!fallback && t.length > 40) fallback = box; "
             "if (/\u20b9\\s?[\\d,]+/.test(t) && t.length < 400) return t.slice(0,160); } "
             "return ((fallback||b).innerText||'').replace(/\\s+/g,' ').trim().slice(0,160); }")

    def __init__(self, ws_url: str, storage: dict | None = None) -> None:
        self._ws = ws_url
        self._pw = self._browser = self._page = None
        # The sealed session's localStorage, put into the page on first arrival
        # at its origin: a single-page app keeps its sign-in there as often as
        # in a cookie.
        self._storage = storage or {}
        self._storage_done: set[str] = set()

    async def _open(self):
        if self._page is not None:
            return self._page
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(self._ws, timeout=20_000)
        context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        self._page = context.pages[0] if context.pages else await context.new_page()
        return self._page

    async def goto(self, url: str) -> None:
        page = await self._open()
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
        origin = page.url.split("/", 3)[0] + "//" + page.url.split("/", 3)[2] if "//" in page.url else ""
        local = (self._storage.get("localStorage") or {}).get(origin) or {}
        if local and origin not in self._storage_done:
            self._storage_done.add(origin)
            await page.evaluate("items => { for (const [k, v] of Object.entries(items)) localStorage.setItem(k, v); }", local)
            await page.reload(wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(2500)

    async def url(self) -> str:
        return (await self._open()).url

    async def text(self) -> str:
        return await (await self._open()).evaluate("() => (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 6000)")

    async def screenshot(self) -> bytes:
        return await (await self._open()).screenshot(type="jpeg", quality=55)

    async def buttons(self, label: str) -> list[dict]:
        page = await self._open()
        found = page.locator("button", has_text=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
        out = []
        for i in range(min(await found.count(), 30)):
            near = await found.nth(i).evaluate(self._NEAR)
            out.append({"index": i, "near": near, "price": parse_price(near)})
        return out

    async def links(self) -> list[dict]:
        page = await self._open()
        return await page.evaluate("""() => { const seen = new Set(); const out = [];
          for (const a of document.querySelectorAll('a[href]')) { const t = (a.innerText||'').replace(/\\s+/g,' ').trim(); const h = a.href;
            if (!t || t.length > 80 || !h.startsWith('https://') || seen.has(h)) continue; seen.add(h); out.push({text: t, href: h}); if (out.length >= 60) break; }
          return out; }""")

    async def press(self, label: str, index: int) -> bool:
        page = await self._open()
        found = page.locator("button", has_text=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
        if index >= await found.count():
            return False
        await found.nth(index).scroll_into_view_if_needed()
        await found.nth(index).click()
        await page.wait_for_timeout(2500)
        return True

    async def click_text(self, text: str) -> bool:
        page = await self._open()
        try:
            await page.get_by_text(text, exact=False).first.click(timeout=4000)
            await page.wait_for_timeout(3000)
            return True
        except Exception:  # noqa: BLE001 - not there, then
            return False

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


def parse_price(text: str) -> float | None:
    m = re.search(r"₹\s?([\d,]+)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


# The site's category pages, by the words of the errand. A short table: a
# page the runbook has been walked through, not a guess.
_CATEGORIES = (
    (re.compile(r"\bac\b|air ?con", re.I), "ac-service-repair"),
    (re.compile(r"kitchen|bathroom|sofa|carpet|home clean|deep clean|full home", re.I), "professional-home-cleaning"),
    (re.compile(r"pest|cockroach|termite|bed ?bug", re.I), "pest-control"),
    (re.compile(r"electric|fan|switch|wiring", re.I), "electrician-density"),
    (re.compile(r"plumb|tap|leak|pipe", re.I), "plumbers-density"),
)


def category_for(what: str) -> str | None:
    for pattern, slug in _CATEGORIES:
        if pattern.search(what or ""):
            return slug
    return None


# What a site calls the thing a family asks for. Urban Company's AC deep
# clean is its "foam-jet" service; a word a person says maps to the words
# the card says.
_SYNONYMS = {
    "deep": ("foam", "deep", "intense"),
    "clean": ("clean", "foam", "jet", "service"),
    "cleaning": ("clean", "foam", "jet", "service"),
    "ac": ("ac", "air"),
    "repair": ("repair", "fix"),
    "gas": ("gas", "refill"),
    "install": ("install",),
}


def pick_service(buttons: list[dict], what: str) -> dict | None:
    """The Add button whose card reads most like the errand's words; among
    equals, the one with a price on its card. Nothing matching, nothing."""
    words = [w for w in re.findall(r"[a-z]+", (what or "").lower()) if w not in ("service", "the", "and", "for", "a", "an")]
    best, score = None, 0
    for b in buttons:
        near = (b.get("near") or "").lower()
        if not near or near.strip() == "add":
            continue
        hit = 0.0
        for w in words:
            # The person's own word on the card outranks a word the site uses for it.
            if w in near:
                hit += 1
            elif any(alt in near for alt in _SYNONYMS.get(w, ())):
                hit += 0.75
        if "option" in near:
            hit -= 0.5          # "Add 9 options" needs a choice the runbook cannot make
        if b.get("price"):
            hit += 0.25
        if hit > score:
            best, score = b, hit
    return best if score >= 1 else None


_SLOT = re.compile(r"\b(\d{1,2}[:.]\d{2}\s*(?:am|pm))\b", re.I)


def slots_in(text: str) -> list[str]:
    """Times said on the page, as written, in order, once each."""
    out = []
    for m in _SLOT.finditer(text or ""):
        t = m.group(1).replace(".", ":").upper().replace(" ", "")
        if t not in out:
            out.append(t)
    return out


def _wanted_slot(spec: dict) -> str | None:
    at = (spec.get("when") or {}).get("time")
    if not at:
        return None
    h, m = int(at[:2]), int(at[3:5])
    return f"{(h % 12) or 12}:{m:02d}{'AM' if h < 12 else 'PM'}"


async def _principal(row: dict) -> Principal:
    m = await pool().fetchrow("SELECT id, household_id, role, display_name FROM members WHERE id = $1", row["created_by"])
    return Principal(member_id=m["id"], household_id=m["household_id"], role=m["role"], display_name=m["display_name"])


class Run:
    """One errand's run: its steps, its pictures, its outcome on the row."""

    def __init__(self, row: dict, p: Principal, driver: Driver, *, browser_session: dict | None):
        self.row, self.p, self.driver, self.browser_session = row, p, driver, browser_session
        self.steps: list[dict] = []

    async def note(self, said: str, *, picture: bool = True) -> None:
        step = {"at": dt.datetime.now(dt.UTC).isoformat(), "said": said[:300]}
        if picture:
            try:
                shot = await self.driver.screenshot()
                async with pool().acquire() as conn, conn.transaction():
                    art, _ = await artifacts.create(conn, self.p.household_id, artifacts.NewArtifact(
                        data=shot, media_type="image/jpeg", channel="errand", visibility="private", status="accepted",
                        submitted_by=self.p.member_id, filename=f"errand-step-{len(self.steps) + 1}.jpg",
                        source={"errand_id": str(self.row["id"]), "step": len(self.steps) + 1, "said": said[:120]},
                        dedup_key=f"errand:{self.row['id']}:{len(self.steps) + 1}:{uuid.uuid4().hex[:6]}"), actor_kind="system")
                step["artifact_id"] = str(art["id"])
            except Exception:  # noqa: BLE001 - a missing picture does not stop the run
                logger.warning("errand %s: no screenshot for step", self.row["id"], exc_info=True)
        self.steps.append(step)
        await pool().execute("UPDATE errands SET outcome = outcome || $2::jsonb, updated_at = NOW() WHERE id = $1",
                             self.row["id"], {"steps": self.steps})
        if len(self.steps) > MAX_STEPS:
            raise RuntimeError("too many steps; stopped")

    def commit(self, step: str):
        """A step that changes something on the site -- an Add, a View cart, a
        slot picked -- is written on the row before it happens and struck
        through after. A run that restarts and finds one still written
        does not repeat it: the click may have landed, and only a person can
        tell. Reads and navigation are not wrapped; they replay freely."""
        run = self

        class _Commit:
            async def __aenter__(self):
                await pool().execute("UPDATE errands SET outcome = outcome || $2::jsonb, updated_at = NOW() WHERE id = $1",
                                     run.row["id"], {"commit": {"step": step, "at": dt.datetime.now(dt.UTC).isoformat()}})

            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is None:
                    await pool().execute(
                        "UPDATE errands SET outcome = (outcome - 'commit') || jsonb_build_object('committed', "
                        "COALESCE(outcome->'committed', '[]'::jsonb) || to_jsonb($2::text)), updated_at = NOW() WHERE id = $1",
                        run.row["id"], step)
                # On an error the mark stays: the click may or may not have landed.
        return _Commit()

    async def end(self, status: str, *, error: str | None = None, **outcome) -> dict:
        keep_browser = status == "needs_you" and self.browser_session
        extra = {"steps": self.steps, **outcome}
        if keep_browser:
            extra["browser"] = {"session_id": self.browser_session.get("session_id"), "ws_url": self.browser_session.get("websocket_url")}
        await pool().execute(
            "UPDATE errands SET status = $2, error = $3, ended_at = CASE WHEN $2 IN ('done','stopped','failed') THEN NOW() ELSE ended_at END, "
            "outcome = outcome || $4::jsonb, updated_at = NOW() WHERE id = $1", self.row["id"], status, error, extra)
        await audit.record(self.p.household_id, f"errand.{status}", actor_kind="system", target_type="errand", target_id=self.row["id"],
                           detail={"service": self.row["service"], "steps": len(self.steps), "error": (error or "")[:200]})
        if not keep_browser:
            await self.driver.close()
            if self.browser_session:
                await steel.current_browser().release(self.browser_session.get("session_id"))
        if status == "needs_you" or (status == "stopped" and (error or "").startswith("session_lapsed")):
            await self._tell(error)
        return {"status": status, "steps": len(self.steps), **({"error": error} if error else {})}

    async def _tell(self, error: str | None) -> None:
        """The asker hears at once, on Telegram when it is linked: a run that
        waits on a person is worth nothing until they know, and an OTP lasts
        minutes. Until there is push, this is the fastest rail the phone has.
        A run in the phone's own web view needs no telling: the person is
        looking at it."""
        if (self.row.get("outcome") or {}).get("run_on") == "phone":
            return
        last = self.steps[-1]["said"] if self.steps else ""
        if (error or "").startswith("session_lapsed"):
            why = "The sign-in has lapsed. Sign in again on the Household page, then run it once more."
        elif re.search(r"\botp\b|card", last, re.I):
            why = "The page asks for an OTP or a card. Only you can answer that; the browser is held open for you."
        elif (error or "").startswith("interrupted"):
            why = "A step may already have happened; look before doing it again."
        else:
            why = (last + " " if last else "") + "The run stopped where it is; finish it in the live view."
        link = f"{settings.console_url}#/errands/{self.row['id']}"
        try:
            await notify.member(self.row["created_by"], f"Needs you now: {self.row['title']}", f"{why}\n\nOpen: {link}")
        except Exception:  # noqa: BLE001 - a courtesy; the row already says needs_you
            logger.warning("could not tell the asker of errand %s", self.row["id"], exc_info=True)


def interrupted(row: dict) -> str | None:
    """The step a previous attempt was in the middle of, if it was one that
    cannot be repeated."""
    mark = (row.get("outcome") or {}).get("commit")
    return mark.get("step") if isinstance(mark, dict) and mark.get("step") else None


DriverFactory = Callable[[str, dict | None], Driver]
_driver_factory: DriverFactory = PlaywrightDriver


def use_driver_factory(make: DriverFactory) -> None:
    global _driver_factory
    _driver_factory = make


async def urbancompany(row: dict, driver: Driver | None = None) -> dict:
    """Urban Company: the category page, the service's Add, the cart, the
    checkout's slot and payment. Stops, by rule, at anything unexpected.
    With a `driver` handed in (the phone's web view), no browser is rented
    and no sealed session is needed: the phone is signed in already."""
    p = await _principal(row)
    spec = row["spec"]
    site = sites.get("urbancompany")
    hosts = frozenset(site["hosts"])
    await pool().execute("UPDATE errands SET status = 'running', started_at = NOW(), updated_at = NOW() WHERE id = $1", row["id"])
    if driver is not None:
        run = Run(row, p, driver, browser_session=None)
        if step := interrupted(row):
            await run.note(f"A previous attempt was interrupted while it was about to {step}; it may have happened. "
                           "Check the page and finish from here.", picture=False)
            return await run.end("needs_you", error=f"interrupted during: {step}")
        try:
            return await _drive(run, spec, site, hosts)
        except Exception as exc:  # noqa: BLE001 - the phone went away, or the page did something new
            logger.warning("errand %s on the phone stopped", row["id"], exc_info=True)
            return await run.end("needs_you", error=f"{type(exc).__name__}: {str(exc)[:200]}")
    try:
        async with sessions.lease(p, "urbancompany", reason=f"errand {row['id']}") as held:
            browser = await steel.current_browser().open_with(
                held.state.as_browser_context(), user_agent=(held.state.fingerprint or {}).get("user_agent"), minutes=RUN_MINUTES)
            driver = _driver_factory(browser.get("websocket_url") or "", browser.get("storage"))
            run = Run(row, p, driver, browser_session=browser)
            if step := interrupted(row):
                await run.note(f"A previous attempt was interrupted while it was about to {step}; it may have happened. "
                               "Check the site and finish from here.", picture=False)
                return await run.end("needs_you", error=f"interrupted during: {step}")
            try:
                return await _drive(run, spec, site, hosts)
            except Exception as exc:  # noqa: BLE001 - said on the row, browser released
                logger.warning("errand %s failed", row["id"], exc_info=True)
                return await run.end("failed", error=f"{type(exc).__name__}: {str(exc)[:200]}")
    except sessions.SessionLapsed as exc:
        await pool().execute("UPDATE errands SET status = 'stopped', error = $2, ended_at = NOW(), updated_at = NOW() WHERE id = $1", row["id"], str(exc))
        return {"status": "stopped", "error": str(exc)}


async def _drive(run: Run, spec: dict, site: dict, hosts: frozenset[str]) -> dict:
    d = run.driver
    await d.goto(site["login_url"])
    url = await d.url()
    disposable.approved(url, hosts)
    words = await d.text()
    if re.search(r"\blogin\b|sign ?up|log in", words, re.I) and not re.search(r"logout|log out|my bookings|hi,? [a-z]", words, re.I):
        # The sign-in did not carry: the session has lapsed on the site's side.
        await run.note("The site does not show you signed in; the saved session has lapsed.")
        return await run.end("stopped", error="session_lapsed: sign in to Urban Company again on the Household page")
    await run.note("Opened Urban Company, signed in.")
    city = url.split("urbancompany.com/", 1)[-1].split("?")[0].split("/")[0] or "delhi-ncr"
    slug = category_for(spec["what"])
    if slug:
        await d.goto(f"https://www.urbancompany.com/{city}-{slug}")
    else:
        # One closed question: which of the page's own links is the category?
        links = [line for line in await d.links() if hosts & {line["href"].split("/")[2].lower()}]
        index, why = await choose.pick(f"Which link is the category page for: {spec['what']}?", [line["text"] for line in links], run.p.household_id)
        if index is None:
            await run.note(f"No page is known for “{spec['what']}” ({why}); finish from here.")
            return await run.end("needs_you")
        await d.goto(links[index]["href"])
        await run.note(f"Went to “{links[index]['text']}” — the model picked it from {len(links)} links: {why}", picture=False)
    disposable.approved(await d.url(), hosts)
    await run.note(f"On the {(slug or 'category').replace('-', ' ')} page for {city}.")
    buttons = await d.buttons("Add")
    chosen = pick_service(buttons, spec["what"])
    if not chosen:
        # The words did not settle it; one closed question over the cards' own words.
        cards = [b for b in buttons if (b.get("near") or "").strip().lower() != "add"]
        index, why = await choose.pick(f"Which card is the service for: {spec['what']}?", [b["near"] for b in cards], run.p.household_id)
        if index is not None:
            chosen = cards[index]
            await run.note(f"The model picked “{chosen['near'][:60]}” from {len(cards)} cards: {why}", picture=False)
    if not chosen:
        await run.note("Could not tell which service matches; pick it yourself and go on.")
        return await run.end("needs_you")
    # A look buys nothing, so no price stops it; it reports the price instead.
    limit = float("inf") if run.row["kind"] == "look" else float(spec["limits"]["max_amount"])
    if chosen.get("price") and chosen["price"] > limit:
        await run.note(f"The service reads {chosen['near'][:80]} — above the limit of {limit:.0f}.")
        return await run.end("stopped", error=f"price_above_limit: the page says ₹{chosen['price']:.0f}, the errand allows ₹{limit:.0f}")
    async with run.commit("press Add on the service"):
        await d.press("Add", chosen["index"])
    after = await d.text()
    if re.search(r"\boptions?\b", chosen["near"], re.I) and re.search(r"select|choose", after[:2000], re.I):
        await run.note(f"“{chosen['near'][:60]}” has options to choose; choose them yourself.")
        return await run.end("needs_you")
    await run.note(f"Added “{chosen['near'][:70]}”.")
    async with run.commit("open the cart"):
        opened = await d.click_text("View cart")
    if not opened:
        await run.note("No cart to open; finish from here.")
        return await run.end("needs_you")
    disposable.approved(await d.url(), hosts)
    checkout = await d.text()
    if re.search(r"please login|login or sign up", checkout, re.I):
        await run.note("The checkout asks for a login; the saved session has lapsed.")
        return await run.end("stopped", error="session_lapsed: sign in to Urban Company again on the Household page")
    total = parse_price(checkout.split("Amount to pay", 1)[-1]) if "Amount to pay" in checkout else None
    slots = slots_in(checkout)
    await run.note(f"At the checkout. Total reads ₹{total:.0f}." if total else "At the checkout.")
    if total and total > limit:
        return await run.end("stopped", error=f"price_above_limit: the checkout says ₹{total:.0f}, the errand allows ₹{limit:.0f}", total=total, slots=slots)
    if run.row["kind"] == "look":
        await run.note(f"Slots on the page: {', '.join(slots) if slots else 'none shown yet'}.", picture=False)
        return await run.end("done", total=total, slots=slots)
    wanted = _wanted_slot(spec)
    norm = lambda t: (t or "").replace(" ", "").upper().lstrip("0")  # noqa: E731 - "03:30 PM", "3:30PM", "03:30PM" are one slot
    match = next((t for t in slots if norm(t) == norm(wanted)), None) if wanted else None
    if wanted and not match and slots:
        index, why = await choose.pick(f"Which slot is {wanted}, or the nearest after it?", slots, run.p.household_id)
        if index is not None:
            match = slots[index]
            await run.note(f"No exact {wanted}; the model picked {match} from {len(slots)} slots: {why}", picture=False)
    picked = False
    if match:
        async with run.commit(f"pick the slot {match}"):
            picked = await d.click_text(match) or await d.click_text(match[:-2] + " " + match[-2:])
    if picked:
        await run.note(f"Chose the {match} slot.")
    else:
        await run.note(f"Pick the slot yourself ({wanted or 'any'}), the address and “Pay after service”, then press Finished here.")
        return await run.end("needs_you", total=total, slots=slots)
    if re.search(r"card number|cvv|enter otp|verify your identity", await d.text(), re.I):
        await run.note("The page asked for a card or an OTP; stopped by rule.")
        return await run.end("stopped", error="unexpected_payment_prompt")
    await run.note("Everything but the last tap is done; confirm the booking and payment yourself, then press Finished here.")
    return await run.end("needs_you", total=total, slots=slots)
