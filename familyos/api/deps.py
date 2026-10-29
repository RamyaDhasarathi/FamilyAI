from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from familyos import clock, session_cookie
from familyos import kid as kidmod
from familyos.identity import Principal, authenticate

_bearer = HTTPBearer(auto_error=False)

# A device token is what a phone's shortcut or share extension holds: plain text
# in a Shortcuts action, never expiring. It may hand things over to the inbox
# and do nothing else. This is the one place that says so, so a route added
# tomorrow is closed to devices unless it is listed here.
DEVICE_ALLOWED = frozenset({
    ("POST", "/v1/inbound/share"),   # the iOS share extension and the Shortcuts recipe
    ("POST", "/v1/artifacts"),       # the console's older Shortcuts recipe: a file upload
    ("GET", "/v1/inbound/share/tags"),   # the names the shortcut offers as a tag (the children's, or only Nobody for a caregiver); it asks before it shares
})


def device_may(method: str, path: str) -> bool:
    return (method.upper(), "/" + path.strip("/")) in DEVICE_ALLOWED


async def _principal(request: Request, creds: HTTPAuthorizationCredentials | None, *, allow_erasing: bool) -> Principal:
    # The token is the bearer header's, or else the console's session cookie (familyos/session_cookie.py): the same token rows either way.
    token, via_cookie = None, False
    if creds is not None and creds.scheme.lower() == "bearer":
        token = creds.credentials
    elif creds is None and (cookie := session_cookie.token_from(request)):
        token, via_cookie = cookie, True
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required", headers={"WWW-Authenticate": "Bearer"})
    principal = await authenticate(token, allow_erasing=allow_erasing)
    # A device token is a phone shortcut's, never a browser's: it is not honoured from a cookie.
    if principal is None or (via_cookie and principal.kind != "session"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked token", headers={"WWW-Authenticate": "Bearer"})
    if via_cookie and request.method not in session_cookie.SAFE_METHODS and not session_cookie.csrf_ok(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this request did not come from FamilyOS's own page")
    if principal.kind == "device" and not device_may(request.method, request.url.path):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this is a phone shortcut's token: it can only send things to the inbox (POST /v1/inbound/share). "
            "Sign in to use anything else.")
    await clock.bind(principal.household_id, principal.member_id)         # "today" in this request is the household's day (familyos/clock.py)
    return principal


async def current_member(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    return await _principal(request, creds, allow_erasing=False)


async def erasure_reader(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    """Read-only, and the only thing an erasing household still allows: a
    guardian watching the erasure they asked for. It reads `erasure_log`,
    which holds no personal data."""
    return await _principal(request, creds, allow_erasing=True)


async def current_kid(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> kidmod.KidPrincipal:
    """A child's own key: separate from a member's token, and good for nothing but the calls in kid.py."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "your key is needed", headers={"WWW-Authenticate": "Bearer"})
    k = await kidmod.authenticate(creds.credentials)
    if k is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "that key does not work any more", headers={"WWW-Authenticate": "Bearer"})
    await clock.bind(k.household_id)
    return k

