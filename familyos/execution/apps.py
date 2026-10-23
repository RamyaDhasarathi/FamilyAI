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
import logging

from familyos.db import pool

logger = logging.getLogger(__name__)

APPS: dict[str, dict] = {
    # MyClassBoard ships one app per school under the school's own name and
    # bundle id (seen 9 Oct 2026: "Aachi global school", com.mcb.aachiGlobal);
    # the generic parent app is the default and spec.bundle names the school's.
    "myclassboard": {"label": "MyClassBoard school app", "bundle": "com.myclassboard.commonParentPortal",
                     "how": "The school's parent app. Sign in on the phone itself; FamilyOS reads the announcements page.",
                     "notices": ["Announcements", "Circulars", "Notices"]},
    # A built-in app, for trying the phone's hands on a simulator or a phone
    # before pointing them at the school's app.
    "iossettings": {"label": "iOS Settings (a trial run)", "bundle": "com.apple.Preferences", "how": "Nothing to sign in to.", "notices": []},
}


PAGES = 3   # screens of a list read as pictures, when the app names nothing
SETTLE_READS = 15   # a cold start: a splash, a spinner, then the first screen (15 s at 23:35, 9 Oct 2026)
SETTLE_STEP = 1.0   # seconds between reads of the screen


def _stem(word: str) -> str:
    """The word without its plural: the family says "Announcements", the
    app's tile says "Announcement" over a count (seen 10 Oct 2026, 00:57)."""
    w = word.strip()
    return w[:-1] if len(w) > 4 and w.lower().endswith("s") else w


def _names_any(words: str, targets: list[str]) -> bool:
    low = words.lower()
    return any(_stem(t).lower() in low for t in targets)


async def _settle(driver, targets: list[str]) -> str:
    """Read the screen until it names one of the targets, or until it has
    settled on something else. A cold start shows a splash that names
    nothing for seconds; reading it once, two seconds after open, took the
    splash for a drawn app and handed in pictures of it."""
    last = ""
    for _ in range(SETTLE_READS):
        words = await driver.text()
        if _names_any(words, targets):
            return words
        if words.strip() and words == last:
            return words
        last = words
        await asyncio.sleep(SETTLE_STEP)
    return last


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


async def read_app(row: dict, driver=None) -> dict:
    """Open the app on the phone, reach the notices page, read it, and hand
    the words in as a notice for the reader. Needs the phone's driver; no
    rented browser can run an app."""
    from familyos.execution.runbooks import Run, _principal, interrupted
    from familyos.intake import gateway
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
        await driver.open(bundle)
        await run.note(f"Opened {app['label']}.")
        want = (row.get("spec") or {}).get("what") or ""
        targets = ([want] if want else []) + list(app.get("notices") or [])
        words = await _settle(driver, targets)
        if not _names_any(words, targets):
            # The app opened before the notices: MyClassBoard's first screen
            # is the list of children (seen 9 Oct 2026). One tap on a child
            # of this household opens that child's pages.
            for name in await _children(p.household_id):
                if name.lower() in words.lower():
                    async with run.commit(f"tap {name}"):
                        tapped = await driver.click_text(name)
                    if tapped:
                        await run.note(f"Opened {name}'s pages.")
                        words = await _settle(driver, targets)
                    break
        for target in targets:
            if _stem(target).lower() in words.lower():
                async with run.commit(f"tap {target}"):
                    tapped = await driver.click_text(_stem(target))
                if tapped:
                    await run.note(f"Opened “{target}”.")
                    words = await driver.text()
                    break
        if len(words.strip()) < 20:
            # An app that draws its own screen (Flutter, a canvas) gives the
            # accessibility tree nothing: the MyClassBoard app does, seen 9
            # Oct 2026 with a full page of announcements behind an empty
            # tree. Then the pictures are the notice: one per screen, read by
            # the picture reader like a shared screenshot, never kept as text
            # here. A few screens, swiped, so a list longer than one is read.
            pictures = []
            for page in range(PAGES):
                shot = await driver.screenshot()
                shared = await gateway.receive_share(p, data=shot, declared_type="image/jpeg", filename=f"{app['service']}-screen-{page + 1}.jpg",
                                                     note=f"screen {page + 1} of {app['label']}, taken by the phone", visibility="private")
                artifact_id = str((shared.get("artifact") or {}).get("id") or "")
                if artifact_id and artifact_id not in pictures:
                    pictures.append(artifact_id)
                if page + 1 < PAGES and not await driver.swipe("up"):
                    break
            if not pictures:
                await run.note("The screen had nothing to read; it may need a sign-in.", picture=True)
                return await run.end("needs_you", error="nothing readable on the screen")
            await run.note(f"The screen names nothing it shows; handed in {len(pictures)} picture(s) of it for the reader.", picture=False)
            return await run.end("done", pictures=pictures)
        shared = await gateway.receive_share(p, text=words[:6000], note=f"read from {app['label']} by the phone", visibility="private")
        artifact_id = str((shared.get("artifact") or {}).get("id") or "")
        await run.note(f"Handed in what the screen said ({len(words)} characters).")
        return await run.end("done", shared=artifact_id, characters=len(words))
    except asyncio.CancelledError:
        # The socket's task was cancelled with the phone: the row must not
        # stay "running" with nothing to say.
        await pool().execute("UPDATE errands SET status = 'needs_you', error = 'the phone went away', updated_at = NOW() WHERE id = $1", row["id"])
        raise
    except Exception as exc:  # noqa: BLE001 - the phone went away, or the app did something new
        logger.warning("app errand %s stopped", row["id"], exc_info=True)
        return await run.end("needs_you", error=f"{type(exc).__name__}: {str(exc)[:200]}")


def describe() -> str:
    return "apps on the phone: " + ", ".join(f"{v['label']} ({k})" for k, v in APPS.items()) + "; read through the phone's own hands (ios/Driver), never typed into"
