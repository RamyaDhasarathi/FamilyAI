"""The sites a member can sign in to for FamilyOS to act on, by name.

A short, checked list rather than a free-text host: each entry says where
the sign-in page is and which origins a sealed session may ever reach. A
site not on the list cannot be signed in to, which is the point -- a session
is a credential, and FamilyOS takes custody of one only for a site whose
flow has been looked at.
"""
from __future__ import annotations

SITES: dict[str, dict] = {
    "urbancompany": {
        "label": "Urban Company",
        "login_url": "https://www.urbancompany.com/",
        "hosts": ["www.urbancompany.com", "urbancompany.com"],
        "how": "Tap the profile icon, enter your phone number, then the OTP from your SMS.",
        # The cookie the site sets only once a person is signed in. A sitting
        # sealed without it would sign nobody in, so it is refused.
        "signed_in_cookie": r"^_uc_user_(access_)?token$",
    },
}


def get(service: str) -> dict:
    name = (service or "").strip().lower()
    if name not in SITES:
        raise KeyError(name)
    return {"service": name, **SITES[name]}


def listing() -> list[dict]:
    return [{"service": k, "label": v["label"], "hosts": v["hosts"], "how": v["how"]} for k, v in SITES.items()]


def signed_in(service: str, cookies: list[dict]) -> bool:
    """Whether these cookies carry the site's own sign-in."""
    import re
    pattern = SITES.get(service, {}).get("signed_in_cookie")
    if not pattern:
        return bool(cookies)
    return any(re.search(pattern, c.get("name") or "") for c in cookies)
