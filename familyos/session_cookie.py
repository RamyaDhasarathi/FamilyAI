"""The consoles' session: the same token a bearer header would carry, held in an HttpOnly cookie so no script on the page can read it.

A cookie is sent by the browser on every request to this origin, whoever caused it, so a cookie-authenticated request that changes something
must also prove it came from our own page: a custom header (a cross-site page cannot add one without a CORS preflight, and we send no CORS
headers), Sec-Fetch-Site when the browser says it, and the Origin against the Host when it does not. A request that carries a bearer header
is exempt: nothing makes a browser add that on its own. The iPhone app and every API client stay on bearer and never see any of this.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request, Response

from familyos.settings import settings

COOKIE = "familyos_session"
CSRF_HEADER = "x-familyos-csrf"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _on_localhost(request: Request) -> bool:
    return (request.url.hostname or "") in ("localhost", "127.0.0.1", "::1", "[::1]")


def wants_cookie(request: Request) -> bool:
    """A browser console asks for a session cookie by sending the CSRF header on the sign-in call; a native app or a script does not."""
    return request.headers.get(CSRF_HEADER) == "1"


def set_for(response: Response, request: Request, token: str) -> None:
    # Kept as long as a browser will keep one (400 days is its ceiling): the token slides forward while it is used and the server ends it when it
    # has not been, so a cookie that ended with the first window would sign an active person out. The server's expiry is the only one that counts.
    response.set_cookie(COOKIE, token, max_age=400 * 86400, path="/", httponly=True, samesite="lax",
                        secure=not _on_localhost(request))


def clear(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=not _on_localhost(request))


def token_from(request: Request) -> str | None:
    return request.cookies.get(COOKIE) or None


def csrf_ok(request: Request) -> bool:
    """Whether a cookie-authenticated request that changes state came from our own page."""
    if request.headers.get(CSRF_HEADER) != "1":
        return False
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site in ("same-origin", "none")
    origin = request.headers.get("origin")
    if origin:
        hosts = {request.headers.get("host", "")}
        if settings.trust_proxy_headers and request.headers.get("x-forwarded-host"):
            hosts.add(request.headers["x-forwarded-host"].split(",")[0].strip())
        return urlsplit(origin).netloc in hosts
    return True
