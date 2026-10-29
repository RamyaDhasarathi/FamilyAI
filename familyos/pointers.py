"""A notification that only points: "You have a new announcement!" with the words inside the app.

A school app's push notification often carries the headline and nothing else, so the Shortcut that forwards it brings in a few
dozen characters with no date or action in them. Nothing is wrong with the notice; it is just not the announcement. Left alone it
sits in the Inbox looking handled, and the announcement is never read.

So FamilyOS says so: a card in Needs you ("an announcement is waiting in the school app, its text was not in the notification") with
the way to read it, which is the phone reading the app (execution/apps.py) as an errand the person asks for, or a screenshot shared
from the app. A pointer is told from its size, its headline and from having no dates in it; nothing is decrypted to decide.
The card goes when the notice is handled, or when a read of the app has been asked for after it arrived.
"""
from __future__ import annotations

import re

from familyos import artifacts
from familyos.db import pool
from familyos.execution import apps
from familyos.identity import Principal

DAYS = 3
MAX_BYTES = 400
_POINTER = re.compile(
    r"\b(new|latest|unread|\d+ new)\b.{0,40}\b(announcements?|messages?|circulars?|notices?|notifications?|updates?|homework|posts?|activity|events?|alerts?)\b"
    r"|\b(tap|click|open) (to|the app) (view|open|read|see)\b|\b(view|check|see) (it )?in (the )?app\b", re.I)


def looks_like_a_pointer(headline: str | None) -> bool:
    return bool(headline and _POINTER.search(headline))


async def apps_for(p: Principal) -> list[str]:
    """The school apps this notification could be from: those the children's schools use. A notification does not say which app sent it,
    so with two apps both are offered rather than one guessed. With none known, the app the household last read."""
    rows = await pool().fetch("SELECT school FROM members WHERE household_id = $1 AND role = 'child' AND school IS NOT NULL ORDER BY created_at", p.household_id)
    found: list[str] = []
    for r in rows:
        k = apps.app_for_school(r["school"])
        if k and k not in found:
            found.append(k)
    if found:
        return found
    last = await pool().fetchval(
        "SELECT service FROM errands WHERE household_id = $1 AND kind = 'look' AND service = ANY($2::text[]) ORDER BY created_at DESC LIMIT 1",
        p.household_id, [k for k in apps.APPS if k != "iossettings"])
    return [last] if last else []


async def waiting(p: Principal) -> list[dict]:
    """Pointer notifications this person can see that nobody has dealt with, newest first."""
    rows = await pool().fetch(
        "SELECT a.id, a.source->>'headline' AS headline, a.received_at FROM input_artifacts a "
        f"WHERE {artifacts.VISIBLE_TO_MEMBER} AND a.channel = 'share' AND a.media_type LIKE 'text/%' AND a.parent_id IS NULL AND a.size_bytes < $3 "
        "AND a.handled_at IS NULL AND a.received_at > NOW() - make_interval(days => $4) "
        "AND NOT EXISTS (SELECT 1 FROM claims c WHERE c.artifact_id = a.id) "
        "ORDER BY a.received_at DESC", p.household_id, p.member_id, MAX_BYTES, DAYS)
    out = [dict(r) for r in rows if looks_like_a_pointer(r["headline"])]
    if not out:
        return []
    candidates = await apps_for(p)
    if candidates:
        asked = await pool().fetchval("SELECT max(created_at) FROM errands WHERE household_id = $1 AND kind = 'look' AND service = ANY($2::text[])", p.household_id, candidates)
        out = [x for x in out if asked is None or asked < x["received_at"]]
    return [{**x, "candidates": [{"service": k, "app": apps.APPS[k]["label"]} for k in candidates]} for x in out]
