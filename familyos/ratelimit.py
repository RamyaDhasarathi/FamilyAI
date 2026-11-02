"""A small in-process sliding-window limiter.

Per process: with several workers or hosts each keeps its own count, so the
real ceiling is limit x processes. Good enough to stop a script mailing a
stranger a hundred sign-in links; put a proxy limit in front for more.
"""
from __future__ import annotations

import math
import time
from collections import deque

from fastapi import HTTPException, Request

from familyos.settings import settings

HOUR = 3600.0


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def reset(self) -> None:
        self._hits.clear()

    def _live(self, key: str, window: float, now: float) -> deque[float]:
        q = self._hits.get(key)
        if q is None:
            return deque()
        while q and q[0] <= now - window:
            q.popleft()
        if not q:
            del self._hits[key]
            return deque()
        return q

    def wait_if_full(self, key: str, limit: int, window: float) -> float:
        """Seconds until `key` has room again, or 0; counts nothing. For a limit on failures: ask first, count only when something fails."""
        now = time.monotonic()
        q = self._live(key, window, now)
        return max(q[0] + window - now, 0.001) if limit > 0 and len(q) >= limit else 0.0

    def take(self, rules: list[tuple[str, int, float]]) -> float:
        """Count one request against every (key, limit, window_seconds) rule,
        all or none. Returns 0 when allowed, else the seconds until the
        earliest blocking rule frees a slot (and nothing is counted)."""
        now = time.monotonic()
        wait = 0.0
        for key, limit, window in rules:
            q = self._live(key, window, now)
            if len(q) >= limit:
                wait = max(wait, q[0] + window - now)
        if wait:
            return max(wait, 0.001)
        for key, _, _window in rules:
            self._hits.setdefault(key, deque()).append(now)
        return 0.0


limiter = SlidingWindow()


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is only believed when the
    deployment says a proxy it controls sets it (`trust_proxy_headers`); then
    the last entry is used, the one that proxy appended, not what the client
    claimed first."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [x.strip() for x in forwarded.split(",") if x.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def enforce(rules: list[tuple[str, int]], *, window: float = HOUR) -> None:
    """Raise 429 with Retry-After when any (key, limit) is exhausted. A limit
    of 0 or less turns that rule off."""
    wait = limiter.take([(k, n, window) for k, n in rules if n > 0])
    if wait:
        seconds = math.ceil(wait)
        raise HTTPException(429, f"too many requests; try again in {seconds} seconds",
                            headers={"Retry-After": str(seconds)})
