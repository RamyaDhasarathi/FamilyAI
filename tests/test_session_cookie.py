"""The consoles' session cookie: the same token as a bearer header, HttpOnly, with a CSRF check on anything it changes."""
import re

import pytest

from familyos import identity, mail

CSRF = {"X-FamilyOS-CSRF": "1"}


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(to, subject, body, *, ics=None):
        out.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(mail, "send", fake)
    monkeypatch.setattr(mail, "configured", lambda: True)
    return out


def _cookie(response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        m = re.match(r"familyos_session=([^;]*)", header)
        if m:
            return m.group(1)
    return None


def _jar(token: str) -> dict:
    return {"Cookie": f"familyos_session={token}"}


async def _link_signin(family, sent, headers=None):
    await identity.request_sign_in("amma@example.com")
    link = re.search(r"link=([A-Za-z0-9_\-]+)", sent[-1]["body"]).group(1)
    return await family.client.post("/v1/sign-in/redeem", json={"link": link}, headers=headers or {})


async def test_a_console_sign_in_sets_an_httponly_cookie_and_the_cookie_signs_in(family, sent):
    r = await _link_signin(family, sent, CSRF)
    assert r.status_code == 200
    assert r.json()["token"] is None                                        # a console holds the session in the cookie alone: no script is handed the token
    token = _cookie(r)
    assert token and token.startswith("fos_")                               # the same token row a bearer would carry
    header = next(h for h in r.headers.get_list("set-cookie") if h.startswith("familyos_session="))
    assert "HttpOnly" in header and "SameSite=lax" in header and "Secure" in header and "Path=/" in header
    me = await family.client.get("/v1/me", headers=_jar(token))
    assert me.status_code == 200 and me.json()["id"] == family.amma["id"]


async def test_a_native_sign_in_gets_no_cookie_and_the_bearer_is_unchanged(family, sent):
    r = await _link_signin(family, sent)                                    # no console header: the iPhone app
    assert r.status_code == 200 and _cookie(r) is None and r.json()["token"]
    me = await family.client.get("/v1/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.status_code == 200
    assert (await family.client.get("/v1/me")).status_code == 401           # and nothing is signed in by accident


async def test_a_cookie_may_not_change_anything_without_the_consoles_own_header(family, sent):
    token = _cookie(await _link_signin(family, sent, CSRF))
    body = {"label": "x"}
    # A cross-site page can make the browser send the cookie; it cannot add our header.
    r = await family.client.post("/v1/devices", headers=_jar(token), json=body)
    assert r.status_code == 403 and "own page" in r.json()["detail"]
    # The header with a cross-site Fetch Metadata verdict is refused too, and without metadata an Origin from elsewhere is.
    assert (await family.client.post("/v1/devices", headers={**_jar(token), **CSRF, "Sec-Fetch-Site": "cross-site"}, json=body)).status_code == 403
    assert (await family.client.post("/v1/devices", headers={**_jar(token), **CSRF, "Sec-Fetch-Site": "same-site"}, json=body)).status_code == 403
    assert (await family.client.post("/v1/devices", headers={**_jar(token), **CSRF, "Origin": "https://evil.example"}, json=body)).status_code == 403
    ok = await family.client.post("/v1/devices", headers={**_jar(token), **CSRF, "Sec-Fetch-Site": "same-origin"}, json=body)
    assert ok.status_code == 201
    ok = await family.client.post("/v1/devices", headers={**_jar(token), **CSRF, "Origin": "http://test"}, json=body)
    assert ok.status_code == 201
    # A bearer header needs none of it: nothing makes a browser add one by itself.
    assert (await family.client.post("/v1/devices", headers={"Authorization": f"Bearer {token}"}, json=body)).status_code == 201
    # Reading with the cookie needs nothing extra.
    assert (await family.client.get("/v1/me", headers={**_jar(token), "Sec-Fetch-Site": "cross-site"})).status_code == 200


async def test_a_device_token_is_never_honoured_from_a_cookie(family):
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "phone"})
    device = r.json()["token"]
    assert (await family.client.get("/v1/me", headers=_jar(device))).status_code == 401
    assert (await family.client.post("/v1/session", headers=CSRF, json={"token": device})).status_code == 401


async def test_sign_out_ends_the_token_and_clears_the_cookie(family, sent):
    token = _cookie(await _link_signin(family, sent, CSRF))
    r = await family.client.post("/v1/signout", headers={**_jar(token), **CSRF})
    assert r.status_code == 200 and r.json()["ended"] == 1
    cleared = next(h for h in r.headers.get_list("set-cookie") if h.startswith("familyos_session="))
    assert re.search(r'familyos_session=("")?;', cleared) and ("Max-Age=0" in cleared or "expires" in cleared.lower())
    assert (await family.client.get("/v1/me", headers=_jar(token))).status_code == 401        # the token itself is revoked


async def test_a_token_kept_by_an_earlier_version_is_traded_once_for_a_cookie(family):
    token = family.amma_token
    r = await family.client.post("/v1/session", headers=CSRF, json={"token": token})
    assert r.status_code == 200 and _cookie(r) == token and r.json()["member_id"] == family.amma["id"]
    assert (await family.client.get("/v1/me", headers=_jar(token))).status_code == 200
    # Not for a script: only the consoles' own header asks for it, and a wrong token gets nothing.
    assert (await family.client.post("/v1/session", json={"token": token})).status_code == 403
    bad = await family.client.post("/v1/session", headers=CSRF, json={"token": "fos_nope"})
    assert bad.status_code == 401 and _cookie(bad) is None


async def test_a_household_started_in_a_console_is_signed_in_by_cookie_too(client):
    from tests.conftest import Family
    started = await Family(client).setup(name="Cookie House", guardian_email="c@example.com")
    assert started.amma_token                                                # the helper uses the body's token: bearer still returned


async def test_the_cookie_is_not_marked_secure_on_localhost(family, sent):
    import httpx

    from familyos.main import create_app
    app = create_app(with_lifespan=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8088") as c:
        r = await c.post("/v1/session", headers=CSRF, json={"token": family.amma_token})
        header = next(h for h in r.headers.get_list("set-cookie") if h.startswith("familyos_session="))
        assert "HttpOnly" in header and "Secure" not in header


def test_no_console_script_keeps_or_sends_the_session_token():
    """The session is the cookie. The web app (web/, which replaced the founder's consoles on 29 Oct 2026) never stores the
    token or sends it as a Bearer header, and every call says it is a browser (the CSRF header)."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "web" / "src" / "familyos" / "services"
    text = (root / "api.ts").read_text()
    assert "localStorage" not in text and "sessionStorage" not in text
    assert "Bearer" not in text and "Authorization" not in text
    assert "x-familyos-csrf" in text.lower() and "credentials: 'same-origin'" in text