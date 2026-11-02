"""The agent says what it is.

Every browser FamilyOS drives -- the rented Steel session, the local
Chromium, the phone's own web view -- carries one token in its user agent,
so a site can tell a household's agent from a person and from a scraper
without guessing from the address it came from. On the family's own
devices the address is already the truth; the token makes the rest of it
true as well. The token rides on the browser's real user agent, never
replaces it: a browser that tells two stories (one Chrome in the string,
another in the client hints) is what a bot check looks for, and Urban
Company's Turnstile spun on exactly that (execution/steel.py).

The token is the same at the sign-in sitting and at the run, so a sealed
session is used by the browser that made it. Web Bot Auth (HTTP message
signatures, RFC 9421, with a key directory at a well-known URI) is the
next step; it needs a stable HTTPS origin to serve the key directory from
(a domain in front of a static host, or Tailscale Funnel), not a hosted
deployment. See docs/todo.md, "The agent says what it is".
"""
from __future__ import annotations

VERSION = "0.2"
PRODUCT = f"FamilyOS/{VERSION}"
TOKEN = f"{PRODUCT} (+household agent; each run approved by a guardian; never pays)"


def announce(user_agent: str | None) -> str | None:
    """The browser's own user agent with the token appended, once. A headless
    Chromium says so in its string; that word is the second story, so it goes."""
    if not user_agent:
        return None
    ua = " ".join(user_agent.replace("HeadlessChrome", "Chrome").split())
    return ua if PRODUCT in ua else f"{ua} {TOKEN}"


def is_announced(user_agent: str | None) -> bool:
    return bool(user_agent) and PRODUCT in user_agent
