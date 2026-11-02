"""Teaching FamilyOS by showing it: do a task once, step by step, and it keeps the steps to do again.

A person starts a lesson on a phone app (the phone driver, ios/Driver, connects to the lesson) or on a public web page. FamilyOS
shows what the screen says and which words on it could be tapped; the person picks one, and it is tapped for real and kept as a
step, by its words rather than where it sits, so a redesign that keeps the words keeps the skill. "Read this screen" is a step
too. Saving keeps the list.

What a skill can be: open, tap by label, swipe, read. There is no step that types, pays, sends or submits, and a label that
looks like one (Pay, Submit, Send, Delete, Confirm, Sign out ...) is refused when taught and again when replayed. What a
skill reads is handed in as a private notice, the way a shared screenshot is, and the ordinary pipeline takes it from there.

A replay that cannot find the next label stops where it is and says so; it never guesses a tap.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from familyos import audit
from familyos.db import pool
from familyos.execution import phone, screens
from familyos.identity import Invalid, NotAllowed, NotFound, Principal
from familyos.settings import settings
from familyos.worker import WORKER_ID

logger = logging.getLogger(__name__)

MAX_STEPS = 20
LESSON_MINUTES = 30
MAX_LESSONS = 3
WORDS_SHOWN = 2500
LABELS_SHOWN = 40
# Things a skill must never tap, by what the label says. Whole words or phrases, any case.
RISKY = re.compile(r"\b(pay|payment|buy|purchase|order|place order|checkout|check out|submit|send|post|publish|confirm|approve|delete|remove|erase|"
                   r"cancel|sign out|log out|logout|unsubscribe|donate|transfer|withdraw|book now|reserve|subscribe|upgrade|install|allow|agree|accept)\b", re.I)

_lessons: dict[uuid.UUID, Lesson] = {}


class HeldElsewhere(Exception):
    """The lesson is real but its browser or phone socket is held by another worker. Only that worker can step it: route the member's
    requests for a lesson to the worker that started it (docs/deploy.md, "More than one worker")."""


def _shared() -> bool:
    return bool(settings.multi_worker)


class Lesson:
    def __init__(self, member_id, household_id, kind: str, target: str, driver=None, release=None) -> None:
        self.id = uuid.uuid4()
        self.member_id, self.household_id, self.kind, self.target = member_id, household_id, kind, target
        self._driver, self._release = driver, release
        self.steps: list[dict] = []
        self.opened = driver is not None      # a web lesson starts on its page; a phone lesson when the app is opened
        self.started = time.monotonic()

    @property
    def driver(self):
        if self._driver is not None:
            return self._driver
        return phone.connected(self.id)

    async def end(self) -> None:
        """Leave the registry and give the browser back. Safe to call twice: the browser is released once."""
        _lessons.pop(self.id, None)
        phone.detach(self.id)
        if _shared():
            try:
                await pool().execute("DELETE FROM taught_lessons WHERE id = $1", self.id)
            except Exception:  # noqa: BLE001 - the row expires on its own
                logger.warning("could not drop the lesson's row", exc_info=True)
        release, self._release = self._release, None
        if release is not None:
            try:
                await release()
            except Exception:  # noqa: BLE001 - the browser's own timeout ends it anyway
                logger.warning("could not release the lesson's browser", exc_info=True)

    def expired(self) -> bool:
        return time.monotonic() - self.started > LESSON_MINUTES * 60


# --- what a step may be ------------------------------------------------------------------------------------------------------

def check_label(text: str) -> str:
    t = " ".join((text or "").split())
    if not 1 <= len(t) <= 80:
        raise Invalid("a tap needs the words on the thing to tap, up to 80 characters")
    if RISKY.search(t):
        raise Invalid(f"“{t}” looks like it would do something (pay, send, submit, delete ...). A skill only opens and reads.")
    return t


def clean_target(kind: str, target: str) -> str:
    t = (target or "").strip()
    if kind == "phone":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]{2,120}", t):
            raise Invalid("the phone app is named by its bundle id, like com.example.schoolapp")
        return t
    if kind == "web":
        if not t.startswith("https://") or len(t) > 500:
            raise Invalid("a web page must be an https address")
        return t
    raise Invalid("teach on a phone app or a web page")


def clean_step(step: dict) -> dict:
    op = (step or {}).get("op")
    if op in ("read",):
        return {"op": "read"}
    if op == "tap":
        return {"op": "tap", "text": check_label(step.get("text"))}
    if op == "swipe":
        return {"op": "swipe", "direction": "down" if step.get("direction") == "down" else "up"}
    raise Invalid("a step is tap, swipe or read")


def clean_steps(kind: str, target: str, steps: list[dict]) -> list[dict]:
    if not steps or len(steps) > MAX_STEPS:
        raise Invalid(f"a skill has 1 to {MAX_STEPS} steps")
    kept = [clean_step(s) for s in steps]
    if not any(s["op"] == "read" for s in kept):
        raise Invalid("a skill must read a screen, or it brings nothing back")
    clean_target(kind, target)
    return kept


# --- screens ----------------------------------------------------------------------------------------------------------------

def _labels(words: str) -> list[str]:
    """What on a screen could be tapped: its short lines, once each. The accessibility tree and a page's text both read as lines."""
    seen, out = set(), []
    for line in (words or "").splitlines():
        t = " ".join(line.split())
        if 1 <= len(t) <= 60 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:LABELS_SHOWN]


async def _read(driver) -> str:
    return (await driver.text() or "")[:WORDS_SHOWN * 2]


async def _settle(driver, want: str | None = None) -> str:
    return await screens.settle(driver, [want] if want else None)


def _screen(lesson: Lesson, words: str | None) -> dict:
    risky = [t for t in _labels(words or "") if RISKY.search(t)]
    return {"id": lesson.id, "kind": lesson.kind, "target": lesson.target, "connected": lesson.driver is not None,
            "words": (words or "")[:WORDS_SHOWN], "labels": [t for t in _labels(words or "") if t not in risky], "steps": lesson.steps, "not_offered": risky}


# --- teaching ---------------------------------------------------------------------------------------------------------------

async def _mine(p: Principal, lesson_id: uuid.UUID) -> Lesson:
    lesson = _lessons.get(lesson_id)
    if lesson is None and _shared():
        # Not in this process. A live row says another worker holds it; no row (or an expired or someone else's one) says there is none.
        if await pool().fetchval("SELECT 1 FROM taught_lessons WHERE id = $1 AND member_id = $2 AND expires_at > NOW()", lesson_id, p.member_id):
            raise HeldElsewhere(str(lesson_id))
    if lesson is None or lesson.member_id != p.member_id or lesson.expired():
        raise NotFound("lesson")          # an expired one is still in the registry until the next expire_stale() releases its browser
    return lesson


async def expire_stale() -> int:
    """End every lesson past its time, releasing its browser. Run by a recurring sweep and before a new lesson starts, so an
    aborted run (the person closed the tab, the request died) cannot hold a browser or a slot forever. With several workers it also
    drops the rows a dead worker left (its browser ended on its own timeout), a few minutes after they expired."""
    stale = [v for v in list(_lessons.values()) if v.expired()]
    for lesson in stale:
        await lesson.end()
    if _shared():
        await pool().execute("DELETE FROM taught_lessons WHERE expires_at < NOW() - INTERVAL '5 minutes'")
    return len(stale)


async def start(p: Principal, kind: str, target: str, *, driver=None, release=None) -> dict:
    """Begin a lesson. A phone lesson waits for the phone driver to connect to /v1/teach/{id}/phone; a web lesson is given its driver.

    Takes over `release` the moment it is called: whatever happens here, including a refusal before anything is registered, the
    browser is given back exactly once. The lesson is registered before the first navigation, so a run that dies in goto is
    still found, ended and released."""
    lesson = None
    try:
        if p.role == "child":
            raise NotAllowed("children do not teach FamilyOS")
        target = clean_target(kind, target)
        await expire_stale()
        if _shared():
            held = await pool().fetchval("SELECT count(*) FROM taught_lessons WHERE member_id = $1 AND expires_at > NOW()", p.member_id)
        else:
            held = sum(1 for v in _lessons.values() if v.member_id == p.member_id)
        if held >= MAX_LESSONS:
            raise Invalid("finish or cancel a lesson before starting another")
        if kind == "web" and driver is None:
            raise Invalid("no browser is available to teach on")
        lesson = Lesson(p.member_id, p.household_id, kind, target, driver, release)
        _lessons[lesson.id] = lesson                       # registered before the first navigation
        if _shared():
            await pool().execute(
                "INSERT INTO taught_lessons (id, household_id, member_id, owner, kind, target, expires_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, NOW() + make_interval(mins => $7))",
                lesson.id, p.household_id, p.member_id, WORKER_ID, kind, target, LESSON_MINUTES)
        if driver is not None:
            await driver.goto(target)
            return _screen(lesson, await _settle(driver))
        return _screen(lesson, None)
    except BaseException:
        if lesson is not None:
            await lesson.end()
        elif release is not None:
            try:
                await release()
            except Exception:  # noqa: BLE001
                logger.warning("could not release the lesson's browser", exc_info=True)
        raise


async def show(p: Principal, lesson_id: uuid.UUID) -> dict:
    lesson = await _mine(p, lesson_id)
    d = lesson.driver
    if d is None:
        return _screen(lesson, None)
    if lesson.opened:
        return _screen(lesson, await _read(d))
    return _screen(lesson, None)


async def step(p: Principal, lesson_id: uuid.UUID, body: dict) -> dict:
    lesson = await _mine(p, lesson_id)
    d = lesson.driver
    if d is None:
        raise Invalid("the phone has not connected to this lesson yet")
    if not lesson.opened and body.get("op") != "open":
        raise Invalid("open the app first")
    if len(lesson.steps) >= MAX_STEPS:
        raise Invalid(f"a skill has at most {MAX_STEPS} steps; save it")
    if body.get("op") == "open":
        if lesson.opened:
            raise Invalid("the app is already open")
        await d.open(lesson.target)
        lesson.opened = True
        return _screen(lesson, await _settle(d))
    s = clean_step(body)
    if s["op"] == "tap":
        try:
            tapped = await d.click_text(s["text"])
        except phone.TapRefused as exc:
            raise Invalid(str(exc)) from None
        if not tapped:
            raise Invalid(f"could not find “{s['text']}” on the screen to tap")
        words = await _settle(d)
    elif s["op"] == "swipe":
        if not await d.swipe(s["direction"]):
            raise Invalid("the screen did not move")
        words = await _settle(d)
    else:
        words = await _read(d)
    lesson.steps.append(s)
    out = _screen(lesson, words)
    if s["op"] == "read":
        out["captured"] = words[:300]
    return out


async def undo(p: Principal, lesson_id: uuid.UUID) -> dict:
    lesson = await _mine(p, lesson_id)
    if lesson.steps:
        lesson.steps.pop()          # the screen is not rewound; the person does that and carries on from where it is
    return _screen(lesson, await _read(lesson.driver) if lesson.driver else None)


async def cancel(p: Principal, lesson_id: uuid.UUID) -> None:
    lesson = await _mine(p, lesson_id)
    await lesson.end()


async def save(p: Principal, lesson_id: uuid.UUID, title: str) -> dict:
    lesson = await _mine(p, lesson_id)
    title = " ".join((title or "").split())[:80]
    if not title:
        raise Invalid("name the skill")
    steps = clean_steps(lesson.kind, lesson.target, lesson.steps)
    row = await pool().fetchrow(
        "INSERT INTO taught_skills (household_id, member_id, title, kind, target, steps) VALUES ($1, $2, $3, $4, $5, $6::jsonb) RETURNING id, title, kind, target, steps, runs, created_at",
        p.household_id, p.member_id, title, lesson.kind, lesson.target, json.dumps(steps))
    await lesson.end()
    await audit.record(p.household_id, "skill.taught", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"kind": lesson.kind, "steps": len(steps)})
    return _skill(row)


async def web_browser(url: str):
    """A browser on a public page: (driver, release). Raises when this deployment has none."""
    from familyos import mcp_client
    from familyos.execution import runbooks, steel
    await mcp_client.check_url(url)                      # https, and nothing on a private network
    browser = steel.current_browser()
    try:
        session = await browser.open_at(url, minutes=LESSON_MINUTES)
    except steel.NoCollector as exc:
        raise Invalid(str(exc)) from None
    return runbooks.PlaywrightDriver(session["websocket_url"]), (lambda: browser.release(session.get("session_id")))


def _skill(r) -> dict:
    steps = r["steps"] if isinstance(r["steps"], list) else json.loads(r["steps"])
    return {"id": r["id"], "title": r["title"], "kind": r["kind"], "target": r["target"], "steps": steps, "runs": r["runs"],
            "last_run_at": r.get("last_run_at"), "last_outcome": r.get("last_outcome")}


async def list_skills(p: Principal) -> list[dict]:
    rows = await pool().fetch("SELECT * FROM taught_skills WHERE member_id = $1 AND archived_at IS NULL ORDER BY created_at DESC", p.member_id)
    return [_skill(r) for r in rows]


async def get_skill(p: Principal, skill_id: uuid.UUID) -> dict:
    r = await pool().fetchrow("SELECT * FROM taught_skills WHERE id = $1 AND member_id = $2 AND archived_at IS NULL", skill_id, p.member_id)
    if r is None:
        raise NotFound("skill")
    return _skill(r)


async def forget(p: Principal, skill_id: uuid.UUID) -> None:
    done = await pool().execute("UPDATE taught_skills SET archived_at = NOW() WHERE id = $1 AND member_id = $2 AND archived_at IS NULL", skill_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("skill")
    await audit.record(p.household_id, "skill.forgotten", actor_member_id=p.member_id, target_type="member", target_id=p.member_id)


# --- doing it again ---------------------------------------------------------------------------------------------------------

async def replay(p: Principal, skill: dict, driver) -> dict:
    """Do the steps on a driver. Stops, saying where, when the next label is not on the screen. Hands in each read as a private notice."""
    handed, outcome, stopped, i = 0, "done", None, 0
    try:
        if skill["kind"] == "phone":
            await driver.open(skill["target"])
        else:
            await driver.goto(skill["target"])
        words = await _settle(driver)
        for i, s in enumerate(skill["steps"], 1):
            if s["op"] == "tap":
                label = check_label(s["text"])                       # re-checked: a stored skill is not trusted to be clean
                words = await _settle(driver, label)
                if label.lower() not in words.lower() or not await driver.click_text(label):
                    outcome, stopped = "needs_you", f"step {i}: “{label}” is not on the screen"
                    break
                words = await _settle(driver)
            elif s["op"] == "swipe":
                if not await driver.swipe(s.get("direction", "up")):
                    outcome, stopped = "needs_you", f"step {i}: the screen did not move"
                    break
                words = await _settle(driver)
            elif s["op"] == "read":
                words = await _read(driver)
                note = f"read by the skill “{skill['title']}”"
                if len(words.strip()) < 20:
                    handed += len(await screens.hand_in_pictures(p, driver, "skill", note))
                else:
                    await screens.hand_in_text(p, words, note)
                    handed += 1
            else:
                outcome, stopped = "needs_you", f"step {i}: not a step this version knows"
                break
        if outcome == "done" and not handed:
            outcome, stopped = "needs_you", "the screen had nothing to read"
    except phone.TapRefused as exc:
        outcome, stopped = "needs_you", f"step {i}: {exc}"
    except phone.PhoneGone:
        outcome, stopped = "needs_you", "the phone went away"
    except Exception:  # noqa: BLE001 - one plain line; the cause is in the log
        logger.warning("skill replay failed", exc_info=True)
        outcome, stopped = "needs_you", "it stopped on something unexpected"
    await pool().execute("UPDATE taught_skills SET runs = runs + 1, last_run_at = NOW(), last_outcome = $2 WHERE id = $1", skill["id"], outcome if not stopped else stopped[:200])
    await audit.record(p.household_id, f"skill.{'ran' if outcome == 'done' else 'stopped'}", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"kind": skill["kind"]})
    return {"status": outcome, "handed_in": handed, "stopped": stopped}
