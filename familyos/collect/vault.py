"""Connected services: the sites a member lets the browser agent sign in to (Amazon, Flipkart …), decided 30 Oct 2026
(site passwords allowed; kept on this Mac until the backend team gives them a place). This overrides, for our layer
only, the founder's "FamilyOS never takes a password" (docs/architecture.md) -- the founder's sign-in sittings
(sealed_sessions) are untouched.

The password goes to the **macOS Keychain** (the `keyring` library, extra `collect`), under the service
"FamilyOS collect: <site>" and the account "<member email>|<username>". It is never written to the database or the
local cache, never logged, and never answered by the API: only `credentials()` returns it, for the browser agent. The
local cache keeps which site, which username and when (store.py `site_accounts`).
"""
from __future__ import annotations

from familyos.collect import store

# The sites offered on the Connected services page. "other" is any site, by its address.
CATALOG: list[dict] = [
    {"id": "amazon", "name": "Amazon", "host": "www.amazon.in", "kind": "shopping"},
    {"id": "flipkart", "name": "Flipkart", "host": "www.flipkart.com", "kind": "shopping"},
    {"id": "myntra", "name": "Myntra", "host": "www.myntra.com", "kind": "shopping"},
    {"id": "meesho", "name": "Meesho", "host": "www.meesho.com", "kind": "shopping"},
    {"id": "bigbasket", "name": "BigBasket", "host": "www.bigbasket.com", "kind": "groceries"},
    {"id": "blinkit", "name": "Blinkit", "host": "blinkit.com", "kind": "groceries"},
    {"id": "zepto", "name": "Zepto", "host": "www.zeptonow.com", "kind": "groceries"},
    {"id": "jiomart", "name": "JioMart", "host": "www.jiomart.com", "kind": "groceries"},
    {"id": "swiggy", "name": "Swiggy", "host": "www.swiggy.com", "kind": "food"},
    {"id": "zomato", "name": "Zomato", "host": "www.zomato.com", "kind": "food"},
    {"id": "uber", "name": "Uber", "host": "www.uber.com", "kind": "travel"},
    {"id": "ola", "name": "Ola", "host": "www.olacabs.com", "kind": "travel"},
    {"id": "irctc", "name": "IRCTC", "host": "www.irctc.co.in", "kind": "travel"},
    {"id": "makemytrip", "name": "MakeMyTrip", "host": "www.makemytrip.com", "kind": "travel"},
    {"id": "airtel", "name": "Airtel", "host": "www.airtel.in", "kind": "bills"},
    {"id": "jio", "name": "Jio", "host": "www.jio.com", "kind": "bills"},
    {"id": "netflix", "name": "Netflix", "host": "www.netflix.com", "kind": "subscriptions"},
    {"id": "hotstar", "name": "JioHotstar", "host": "www.hotstar.com", "kind": "subscriptions"},
    {"id": "practo", "name": "Practo", "host": "www.practo.com", "kind": "health"},
    {"id": "pharmeasy", "name": "PharmEasy", "host": "pharmeasy.in", "kind": "health"},
    {"id": "other", "name": "Another site", "host": None, "kind": "other"},
]
BY_ID = {c["id"]: c for c in CATALOG}


class Invalid(ValueError):
    pass


class KeychainUnavailable(RuntimeError):
    pass


def _ring():
    try:
        import keyring
    except ImportError as exc:      # the `collect` extra is not installed (e.g. a server that is not this Mac)
        raise KeychainUnavailable("the Keychain is not available on this server (install the `collect` extra on the Mac)") from exc
    return keyring


# The Keychain, in three calls (the tests stand in for these).
def _keychain_set(service: str, account: str, password: str) -> None:
    _ring().set_password(service, account, password)


def _keychain_get(service: str, account: str) -> str | None:
    return _ring().get_password(service, account)


def _keychain_delete(service: str, account: str) -> None:
    import keyring.errors
    try:
        _ring().delete_password(service, account)
    except keyring.errors.PasswordDeleteError:
        pass


def _names(email: str, service: str, username: str) -> tuple[str, str]:
    return f"FamilyOS collect: {service}", f"{email.strip().lower()}|{username}"


def connect(email: str, service: str, username: str, password: str, host: str | None = None) -> dict:
    site = BY_ID.get(service)
    if site is None:
        raise Invalid("choose a site from the list, or 'other' with its address")
    host = (host or "").strip().lower() or site["host"]
    if not host:
        raise Invalid("another site needs its address, like portal.school.example")
    if not username.strip() or not password:
        raise Invalid("a username and a password are both needed")
    old = store.site_account(email, service)
    if old and old["username"] != username.strip():
        _keychain_delete(*_names(email, service, old["username"]))
    _keychain_set(*_names(email, service, username.strip()), password)
    store.set_site_account(email, service, username.strip(), host)
    return {"service": service, "name": site["name"], "host": host, "username": username.strip()}


def disconnect(email: str, service: str) -> bool:
    old = store.site_account(email, service)
    if not old:
        return False
    _keychain_delete(*_names(email, service, old["username"]))
    store.remove_site_account(email, service)
    return True


def connected(email: str) -> list[dict]:
    return [{**a, "name": BY_ID.get(a["service"], {}).get("name", a["service"])} for a in store.site_accounts(email)]


def credentials(email: str, service: str) -> tuple[str, str] | None:
    """(username, password) for the browser agent signing in -- never for the API."""
    a = store.site_account(email, service)
    if not a:
        return None
    password = _keychain_get(*_names(email, service, a["username"]))
    return (a["username"], password) if password is not None else None
