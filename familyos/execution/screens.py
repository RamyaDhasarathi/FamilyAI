"""Reading a screen through the phone's (or a browser's) hands: the one place that waits for a screen to settle and hands what it
says into the household as a private notice. Used by the built-in school apps (apps.py) and by taught skills (taught.py)."""
from __future__ import annotations

import asyncio

PAGES = 3           # screens of a list read as pictures, when the app names nothing
SETTLE_READS = 15   # a cold start: a splash, a spinner, then the first screen (15 s at 23:35, 9 Oct 2026)
SETTLE_STEP = 1.0   # seconds between reads of the screen
TEXT_LIMIT = 6000


def stem(word: str) -> str:
    """The word without its plural: the family says "Announcements", the app's tile says "Announcement" over a count (seen 10 Oct 2026, 00:57)."""
    w = word.strip()
    return w[:-1] if len(w) > 4 and w.lower().endswith("s") else w


def names_any(words: str, targets: list[str]) -> bool:
    low = words.lower()
    return any(stem(t).lower() in low for t in targets)


async def settle(driver, targets: list[str] | None = None) -> str:
    """Read the screen until it names one of the targets, or until it has settled on something else. A cold start shows a splash that
    names nothing for seconds; reading it once, two seconds after open, took the splash for a drawn app and handed in pictures of it."""
    last = ""
    for _ in range(SETTLE_READS):
        words = await driver.text()
        if targets and names_any(words, targets):
            return words
        if words.strip() and words == last:
            return words
        last = words
        await asyncio.sleep(SETTLE_STEP)
    return last


async def hand_in_text(p, words: str, note: str) -> str:
    """What the screen said, as a private notice. Returns the artifact id."""
    from familyos.intake import gateway
    shared = await gateway.receive_share(p, text=words[:TEXT_LIMIT], note=note, visibility="private")
    return str((shared.get("artifact") or {}).get("id") or "")


async def hand_in_pictures(p, driver, name: str, note: str) -> list[str]:
    """An app that draws its own screen (Flutter, a canvas) gives the accessibility tree nothing (MyClassBoard, 9 Oct 2026, a full page of
    announcements behind an empty tree). Then the pictures are the notice: one per screen, swiped, read by the picture reader like a
    shared screenshot. Returns the artifact ids."""
    from familyos.intake import gateway
    ids: list[str] = []
    for page in range(PAGES):
        shot = await driver.screenshot()
        if shot:
            shared = await gateway.receive_share(p, data=shot, declared_type="image/jpeg", filename=f"{name}-screen-{page + 1}.jpg",
                                                 note=f"{note} (screen {page + 1})", visibility="private")
            artifact_id = str((shared.get("artifact") or {}).get("id") or "")
            if artifact_id and artifact_id not in ids:
                ids.append(artifact_id)
        if page + 1 < PAGES and not await driver.swipe("up"):
            break
    return ids
