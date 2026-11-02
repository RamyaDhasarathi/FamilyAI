"""One idea of "today": the household's own.

The server's clock is UTC at heart and its local zone is whatever the machine is set to; neither is the family's. A household has a timezone
(`households.timezone`), and what is "today", "tomorrow", "overdue" and "at 15:30" are questions about the household's day. Everything stored is UTC
(`timestamptz`); the day is worked out here, and shown in the household's zone.

`today()` and `now()` read the zone bound to the request (`bind`, done once per authenticated request in api/deps.py) or to a job
(`use`, around a household's turn in a sweep), and fall back to the deployment's own zone (`settings.timezone`), never the machine's.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from familyos.settings import settings

_zone: contextvars.ContextVar[str | None] = contextvars.ContextVar("household_timezone", default=None)
_cache: dict[tuple[uuid.UUID, uuid.UUID | None], tuple[str, float]] = {}
CACHE_SECONDS = 60


def _named(name: str | None) -> ZoneInfo:
    for candidate in (name, settings.timezone, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            continue
    return ZoneInfo("UTC")


def zone(name: str | None = None) -> ZoneInfo:
    """The household's zone: the one asked for, else the one bound here, else the deployment's."""
    return _named(name or _zone.get())


_frozen: dt.datetime | None = None


def utcnow() -> dt.datetime:
    """The current instant in UTC: the real one, or the one a test froze (`freeze`)."""
    return _frozen or dt.datetime.now(dt.UTC)


@contextlib.contextmanager
def freeze(at: dt.datetime):
    """For tests: make `now`, `today` and `utcnow` answer as if it were this instant (naive means UTC). SQL's NOW() is not affected."""
    global _frozen
    before = _frozen
    _frozen = at if at.tzinfo else at.replace(tzinfo=dt.UTC)
    try:
        yield
    finally:
        _frozen = before


def now(name: str | None = None) -> dt.datetime:
    return utcnow().astimezone(zone(name))


def today(name: str | None = None) -> dt.date:
    return now(name).date()


@contextlib.contextmanager
def use(name: str | None):
    """Work as one household's day, for a job's turn."""
    token = _zone.set(name)
    try:
        yield
    finally:
        _zone.reset(token)


async def timezone_of(household_id: uuid.UUID, member_id: uuid.UUID | None = None) -> str | None:
    """The person's own zone if they set one, else the household's (both in the database, never in configuration)."""
    from familyos.db import pool
    key = (household_id, member_id)
    held = _cache.get(key)
    if held and held[1] > time.monotonic():
        return held[0]
    name = await pool().fetchval(
        "SELECT COALESCE(m.timezone, h.timezone) FROM households h LEFT JOIN members m ON m.id = $2 AND m.household_id = h.id WHERE h.id = $1",
        household_id, member_id)
    _cache[key] = (name or settings.timezone, time.monotonic() + CACHE_SECONDS)
    return _cache[key][0]


async def bind(household_id: uuid.UUID, member_id: uuid.UUID | None = None) -> None:
    """Make this request's day the person's (else the household's). Set in the request's own context, so it ends with it."""
    _zone.set(await timezone_of(household_id, member_id))


@contextlib.asynccontextmanager
async def household(household_id: uuid.UUID | str | None, member_id: uuid.UUID | str | None = None):
    """Work as one household's (or one person's) day for a turn of a sweep or a job: a loop over households must not carry one family's zone
    into the next. No household (a job with none) leaves the deployment's zone."""
    if household_id is None:
        yield
        return
    hid = uuid.UUID(str(household_id))
    mid = uuid.UUID(str(member_id)) if member_id else None
    token = _zone.set(await timezone_of(hid, mid))
    try:
        yield
    finally:
        _zone.reset(token)


def forget(household_id: uuid.UUID) -> None:
    for key in [k for k in _cache if k[0] == household_id]:
        _cache.pop(key, None)


def sql_date(name: str | None = None) -> str:
    """Today as a SQL date literal, for the few queries that said CURRENT_DATE (the database session's zone, not the household's).
    Built from our own clock, never from input."""
    return f"'{today(name).isoformat()}'::date"
