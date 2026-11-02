"""Apps on the phone that FamilyOS can read through the phone's own hands.

A school app has no API; its notices live on a screen. With the XCTest
driver running on a parent's phone (ios/Driver), an errand can open the
app, read what the screen says through the accessibility tree, and hand
the words in as a notice, the way a shared screenshot comes in but with
the text already there. The same questions a web runbook asks; a bundle
id instead of a URL.

What it never does: type into the app, pay, or go anywhere the runbook
did not say. A tap on the child's name if the app opens on its list of
children, a tap to reach the notices page, by the words the family gave,
and every tap a commit mark.
"""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
from collections.abc import Mapping

from familyos.db import pool
from familyos.execution import screens

logger = logging.getLogger(__name__)

# What ships in the code is generic and public: MyClassBoard's common parent app and a trial entry. Everything specific to a family (which school uses
# which app, a school's own bundle id, a school's own app) is local configuration: a JSON file, by default ~/.familyos/school_apps.json
# (settings.school_apps_file / FAMILYOS_SCHOOL_APPS_FILE), merged over this at call time. Shape:
#   { "myclassboard": {"schools": ["oakridge"], "bundle": "com.example.oakridgeApp"},          # extend a built-in app: school names and/or its own bundle id
#     "brightstart":  {"label": "Bright Start school app", "bundle": "com.example.brightstart", "how": "...", "notices": ["Classwork"],
#                      "schools": ["bright start"], "more": "Read more"} }                                           # or add an app (needs a restart to be registered)
BASE: dict[str, dict] = {
    # MyClassBoard ships one app per school under the school's own name and bundle id; the generic parent app is the default, and a school's own
    # bundle id comes from the local file (or from spec.bundle on the errand).
    "myclassboard": {"label": "MyClassBoard school app", "bundle": "com.myclassboard.commonParentPortal",
                     # Schools known to use this app, matched against a child's school by name. Another school has another app.
                     "schools": [],
                     "how": "The school's parent app. Sign in on the phone itself; FamilyOS reads the announcements page.",
                     "notices": ["Announcements", "Circulars", "Notices"],
                     # The list shows each announcement cut short and ends it with this; opening the card gives the whole text.
                     "more": "View More"},
    # A built-in app, for trying the phone's hands on a simulator or a phone
    # before pointing them at the school's app.
    "iossettings": {"label": "iOS Settings (a trial run)", "bundle": "com.apple.Preferences", "how": "Nothing to sign in to.", "notices": []},
}

_cache: dict = {"key": None, "merged": BASE}


def _config_path() -> pathlib.Path:
    from familyos.settings import settings
    return pathlib.Path(settings.school_apps_file or "~/.familyos/school_apps.json").expanduser()


def _merged() -> dict[str, dict]:
    """BASE with the local file laid over it; re-read when the file's modification time changes, and a bad file or entry is skipped, said once."""
    path = _config_path()
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
    except OSError:
        stamp = (str(path), None)
    if _cache["key"] == stamp:
        return _cache["merged"]
    merged = {k: {**v, "schools": list(v.get("schools", []))} for k, v in BASE.items()}
    if stamp[1] is not None:
        try:
            extra = json.loads(path.read_text())
            if not isinstance(extra, dict):
                raise ValueError("the file is not a JSON object")
        except (OSError, ValueError) as exc:
            logger.warning("school apps file %s ignored: %s", path, exc)
            extra = {}
        for key, e in extra.items():
            try:
                key = str(key).strip().lower()
                schools = [str(x).strip().lower() for x in (e.get("schools") or []) if str(x).strip()]
                if key in merged:
                    merged[key]["schools"] += [x for x in schools if x not in merged[key]["schools"]]
                    if e.get("bundle"):
                        merged[key]["bundle"] = str(e["bundle"])
                    if e.get("more"):
                        merged[key]["more"] = str(e["more"])
                elif e.get("label") and e.get("bundle"):
                    merged[key] = {"label": str(e["label"]), "bundle": str(e["bundle"]), "schools": schools,
                                   "how": str(e.get("how") or "The school's parent app. Sign in on the phone itself; FamilyOS reads what the screen says."),
                                   "notices": [str(x) for x in (e.get("notices") or [])],
                                   # the words that open an announcement cut short on the list (see MyClassBoard above); none, and the list is what is read
                                   **({"more": str(e["more"])} if e.get("more") else {})}
                else:
                    logger.warning("school apps file: %r is not a built-in app and has no label and bundle; ignored", key)
            except (AttributeError, TypeError):
                logger.warning("school apps file: entry %r is not an object; ignored", key)
    _cache.update(key=stamp, merged=merged)
    return merged


class _Registry(Mapping):
    """The apps FamilyOS can read on a phone: the built-in ones and what the local file adds. A read-only mapping, so every caller sees the current file."""
    def __getitem__(self, key):
        return _merged()[key]

    def __iter__(self):
        return iter(_merged())

    def __len__(self):
        return len(_merged())


APPS = _Registry()


def app_for_school(school: str | None) -> str | None:
    """The key of the registered app a school uses, by the school's name, or None. The one place this is decided."""
    low = (school or "").lower()
    if not low:
        return None
    return next((k for k, app in APPS.items() if any(x in low for x in app.get("schools", []))), None)


async def _children(household_id) -> list[str]:
    """The household's children, each by the first word of their name: what
    a school app prints on its list of children."""
    rows = await pool().fetch("SELECT display_name FROM members WHERE household_id = $1 AND role = 'child'", household_id)
    names = []
    for r in rows:
        for w in (r["display_name"] or "").split():
            if len(w) >= 3:
                names.append(w)
                break
    return names


def get(service: str) -> dict | None:
    name = (service or "").strip().lower()
    return {"service": name, **APPS[name]} if name in APPS else None


def listing() -> list[dict]:
    return [{"service": k, "label": v["label"], "bundle": v["bundle"], "how": v["how"]} for k, v in APPS.items()]


MAX_DETAILS = 8                    # cards opened in one read: the newest ones on the first screen
_STAMP = re.compile(r"\d{1,2} [A-Z][a-z]{2} \d{4} \d{1,2}:\d{2} [AP]M")


async def _open_each(run, p, driver, words: str, app: dict) -> int:
    """A list whose items are cut short ("View More"): open each such card, read the whole text, hand it in as its own notice, go back.
    The card is found by its own date and time, which no other card shares, as whole words inside its label. Stops quietly at the first
    card that cannot be found or the first Back that does not work: a half-read list is better than a lost place."""
    from familyos.execution import screens
    from familyos.execution.phone import TapRefused
    marker = (app.get("more") or "").lower()
    cards = []
    for segment in words.split(" · "):
        stamp = _STAMP.search(segment)
        if stamp and segment.rstrip(". ").lower().endswith(marker) and stamp.group(0) not in cards:
            cards.append(stamp.group(0))
    done = 0
    for stamp in cards[:MAX_DETAILS]:
        try:
            async with run.commit(f"open the card of {stamp}"):
                tapped = await driver.click_text(stamp, contains=True)
            if not tapped:
                break
            detail = (await screens.settle(driver)).strip()
            if len(detail) > 40:
                await screens.hand_in_text(p, detail, f"the whole announcement of {stamp}, read from {app['label']} by the phone")
                done += 1
            if not await driver.click_text("Back"):
                await run.note("Could not get back to the list; stopped after the cards read so far.", picture=False)
                break
        except TapRefused:
            break
    if done:
        await run.note(f"Opened {done} announcement(s) for the whole text.")
    return done


SCROLLS_TO_FIND = 6    # swipes down a child's page looking for the notices tile before reading what is there


async def read_app(row: dict, driver=None) -> dict:
    """Open the app on the phone, reach the notices page, read it, and hand
    the words in as a notice for the reader. Needs the phone's driver; no
    rented browser can run an app."""
    from familyos.execution.runbooks import Run, _principal, interrupted
    p = await _principal(row)
    app = get(row["service"])
    if driver is None or app is None:
        await pool().execute("UPDATE errands SET status = 'needs_you', error = $2, updated_at = NOW() WHERE id = $1", row["id"],
                             "an app on the phone can only be read through the phone's own hands: run it from the app")
        return {"status": "needs_you", "error": "no phone driver"}
    await pool().execute("UPDATE errands SET status = 'running', started_at = NOW(), updated_at = NOW() WHERE id = $1", row["id"])
    run = Run(row, p, driver, browser_session=None)
    if step := interrupted(row):
        await run.note(f"A previous attempt was interrupted while it was about to {step}; it may have happened.", picture=False)
        return await run.end("needs_you", error=f"interrupted during: {step}")
    try:
        bundle = ((row.get("spec") or {}).get("where") or {}).get("bundle") or app["bundle"]
        await driver.open(bundle, fresh=True)
        await run.note(f"Opened {app['label']}.")
        want = (row.get("spec") or {}).get("what") or ""
        # What may be tapped is the app's own list of notices pages and nothing else. `what` is free text, from a person or from a model that
        # read a stranger's notice, and a look is approved the moment it is asked: "Pay fees" there is not a button to press. It chooses
        # among the notices pages (the family says "Circulars"), it never adds a word to tap.
        notices = list(app.get("notices") or [])
        known = {screens.stem(n).lower() for n in notices}
        targets = list(dict.fromkeys(t for t in ([want] if want else []) + notices if screens.stem(t).lower() in known))
        words = await screens.settle(driver, targets)
        in_child = False
        if targets and not screens.names_any(words, targets):
            # The app opened before the notices: MyClassBoard's first screen
            # is the list of children (seen 9 Oct 2026). One tap on a child
            # of this household opens that child's pages.
            for name in await _children(p.household_id):
                if name.lower() in words.lower():
                    async with run.commit(f"tap {name}"):
                        tapped = await driver.click_text(name, contains=True)
                    if tapped:
                        await run.note(f"Opened {name}'s pages.")
                        words = await screens.settle(driver, targets)
                        in_child = True
                        # The tile for the notices can sit below the first screen (MyClassBoard, 20 Oct 2026: 66
                        # characters read, no announcements). Scroll the child's page until it is named.
                        for _ in range(SCROLLS_TO_FIND):
                            if screens.names_any(words, targets) or not await driver.swipe("up"):
                                break
                            words = await driver.text()
                    break
        for target in targets:
            if screens.stem(target).lower() in words.lower():
                async with run.commit(f"tap {target}"):
                    tapped = await driver.click_text(screens.stem(target), contains=True)
                if tapped:
                    await run.note(f"Opened “{target}”.")
                    words = await driver.text()
                    break
        if len(words.strip()) < 20 or (in_child and not screens.names_any(words, targets) and len(words.strip()) < 200):
            # An app that draws its own screen (Flutter, a canvas) gives the
            # accessibility tree nothing: the MyClassBoard app does, seen 9
            # Oct 2026 with a full page of announcements behind an empty
            # tree. Then the pictures are the notice: one per screen, read by
            # the picture reader like a shared screenshot, never kept as text
            # here. A few screens, swiped, so a list longer than one is read.
            pictures = await screens.hand_in_pictures(p, driver, app['service'], f"{app['label']}, taken by the phone")
            if not pictures:
                await run.note("The screen had nothing to read; it may need a sign-in.", picture=True)
                return await run.end("needs_you", error="nothing readable on the screen")
            await run.note(f"The screen names nothing it shows; handed in {len(pictures)} picture(s) of it for the reader.", picture=False)
            return await run.end("done", pictures=pictures)
        artifact_id = await screens.hand_in_text(p, words, f"read from {app['label']} by the phone")
        await run.note(f"Handed in what the screen said ({len(words)} characters).")
        opened = await _open_each(run, p, driver, words, app) if app.get("more") else 0
        return await run.end("done", shared=artifact_id, characters=len(words), details=opened)
    except asyncio.CancelledError:
        # The socket's task was cancelled with the phone: the row must not
        # stay "running" with nothing to say.
        await pool().execute("UPDATE errands SET status = 'needs_you', error = 'the phone went away', updated_at = NOW() WHERE id = $1", row["id"])
        raise
    except Exception as exc:  # noqa: BLE001 - the phone went away, or the app did something new
        logger.warning("app errand %s stopped", row["id"], exc_info=True)
        return await run.end("needs_you", error=f"{type(exc).__name__}: {str(exc)[:200]}")
