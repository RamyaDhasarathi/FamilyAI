"""Continue with Google: the cheapest scopes there are, and the checks that
signing in needs but labelling does not."""
import base64
import json
import uuid

import pytest

from familyos import identity
from familyos.identity import LinkNotUsable
from familyos.intake import google
from familyos.settings import settings

CLIENT = "client-id.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def oauth(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", CLIENT)
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_sign_in_redirect_uri",
                        "http://localhost:8000/v1/sign-in/google/callback")


def _id_token(email="amma@example.com", *, verified=True, aud=CLIENT):
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'RS256'})}.{seg({'email': email, 'email_verified': verified, 'aud': aud, 'sub': 'g-1'})}.sig"


class FakeGoogle:
    def __init__(self, **claims):
        self.claims = claims

    async def __call__(self, method, url, *, headers, params, data):
        assert url == google.TOKEN_URL
        return 200, json.dumps({"access_token": "a", "expires_in": 3599, "scope": " ".join(google.SIGN_IN_SCOPES),
                                "id_token": _id_token(**self.claims)}).encode()


async def _url_and_state(database):
    begun = await identity.google_sign_in_url()
    return begun["url"], begun["state"]


async def test_sign_in_asks_google_for_nothing_that_needs_review(database):
    url, _ = await _url_and_state(database)
    assert "openid" in url and "userinfo.email" in url
    # Not the restricted scope, and not the sensitive one: signing in is free.
    assert "gmail.readonly" not in url and "calendar.readonly" not in url
    assert "code_challenge_method=S256" in url


async def test_a_member_signs_in_with_their_google_address(family, database):
    _, state = await _url_and_state(database)
    member, token = await identity.complete_google_sign_in(state, "auth-code",
                                                           transport=FakeGoogle(email="amma@example.com"))
    assert member["id"] == uuid.UUID(family.amma["id"])
    me = await family.client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["id"] == family.amma["id"]


async def test_the_state_works_once(family, database):
    _, state = await _url_and_state(database)
    await identity.complete_google_sign_in(state, "auth-code", transport=FakeGoogle())
    with pytest.raises(LinkNotUsable):
        await identity.complete_google_sign_in(state, "auth-code", transport=FakeGoogle())


async def test_an_address_google_has_not_verified_cannot_sign_in(family, database):
    """A Workspace administrator can put any address on an account. Verified
    means somebody proved they hold the mailbox."""
    _, state = await _url_and_state(database)
    with pytest.raises(LinkNotUsable):
        await identity.complete_google_sign_in(
            state, "auth-code", transport=FakeGoogle(email="amma@example.com", verified=False))


async def test_a_token_minted_for_another_client_is_refused(family, database):
    _, state = await _url_and_state(database)
    with pytest.raises(LinkNotUsable):
        await identity.complete_google_sign_in(
            state, "auth-code", transport=FakeGoogle(email="amma@example.com", aud="someone-else.apps.googleusercontent.com"))


async def test_an_address_nobody_here_uses_is_offered_a_household(family, database):
    """Not refused: Google has verified this person holds this mailbox, so the
    only address they can learn about is their own. The magic-link form must
    stay silent because anyone can type anything into it; this path need not.

    Found by a real new user doing the obvious thing -- tapping Google first on
    an empty deployment -- and hitting "cannot sign in here" with no way on."""
    _, state = await _url_and_state(database)
    with pytest.raises(identity.NoHouseholdYet) as caught:
        await identity.complete_google_sign_in(state, "auth-code",
                                               transport=FakeGoogle(email="New.Parent@example.com"))
    assert caught.value.email == "new.parent@example.com"


async def test_the_callback_sends_a_new_parent_to_start_a_household(family, database):
    _, state = await _url_and_state(database)
    import familyos.intake.google as g
    original = g.exchange_code

    async def fake(code, verifier, **kw):
        return g.token_from({"access_token": "a", "expires_in": 3599,
                             "scope": " ".join(g.SIGN_IN_SCOPES),
                             "id_token": _id_token("new.parent@example.com")})

    g.exchange_code = fake
    try:
        r = await family.client.get(f"/v1/sign-in/google/callback?state={state}&code=x",
                                    follow_redirects=False)
    finally:
        g.exchange_code = original
    assert r.status_code in (302, 307)
    # The address rides in the fragment like the token does: never sent to a
    # server, taken out of the address bar at once.
    location = r.headers["location"]
    assert location.startswith("/app/?signin=new#found=fnd_") and location.endswith("&email=new.parent%40example.com")
    # And that ticket founds a household for that address, once.
    ticket = location.split("#found=")[1].split("&")[0]
    from urllib.parse import unquote
    body = {"name": "New", "guardian": {"display_name": "N", "email": "new.parent@example.com"}, "founding": unquote(ticket)}
    assert (await family.client.post("/v1/households", json=body)).status_code == 201
    assert (await family.client.post("/v1/households", json=body)).status_code == 403


async def test_a_child_cannot_have_an_address_so_google_never_matches_one(family, database):
    """The invariant sign-in leans on. An unmatched address is offered a
    household because no member row has it -- and that is only safe while a
    child cannot carry an email, which the schema enforces (members_check).

    The old version of this test signed in as kid@example.com and was refused.
    It passed because the fixture's children have no email: it was testing a
    stranger, not a child. When age transition lets a child's address arrive
    before their role changes, this fails, and complete_google_sign_in needs a
    "known but not a way in" branch before NoHouseholdYet."""
    import asyncpg

    from familyos.db import pool
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await pool().execute("UPDATE members SET email = 'kid@example.com' WHERE id = $1",
                             uuid.UUID(family.older["id"]))


async def test_the_callback_sends_a_browser_back_to_the_console(family, database):
    _, state = await _url_and_state(database)
    import familyos.intake.google as g
    original = g.exchange_code

    async def fake(code, verifier, **kw):
        return g.token_from({"access_token": "a", "expires_in": 3599,
                             "scope": " ".join(g.SIGN_IN_SCOPES),
                             "id_token": _id_token("amma@example.com")})

    g.exchange_code = fake
    try:
        r = await family.client.get(f"/v1/sign-in/google/callback?state={state}&code=x",
                                    follow_redirects=False)
    finally:
        g.exchange_code = original
    assert r.status_code in (302, 307)
    # The session goes in the fragment, which never reaches a server.
    assert r.headers["location"].startswith("/app/#token=")


async def test_a_cancelled_sign_in_lands_somewhere_a_person_recognises(family):
    r = await family.client.get("/v1/sign-in/google/callback?error=access_denied", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/app/?signin=cancelled"


async def test_a_sign_in_begun_in_the_phone_app_returns_to_the_app(family, database):
    """The app opens Google in a web session and waits on its own URL
    scheme; the callback must come back there, token in the fragment, and
    never to the console."""
    r = await family.client.get("/v1/sign-in/google?native=true")
    assert r.status_code == 200
    state = r.json()["url"].split("state=")[1].split("&")[0]
    assert state.startswith("app-")
    import familyos.intake.google as g
    original = g.exchange_code

    async def fake(code, verifier, **kw):
        return g.token_from({"access_token": "a", "expires_in": 3599, "scope": " ".join(g.SIGN_IN_SCOPES),
                             "id_token": _id_token("amma@example.com")})

    g.exchange_code = fake
    try:
        r = await family.client.get(f"/v1/sign-in/google/callback?state={state}&code=x", follow_redirects=False)
    finally:
        g.exchange_code = original
    assert r.status_code in (302, 307)
    location = r.headers["location"]
    assert location.startswith("familyos://signed-in#token=")
    token = location.split("#token=")[1]
    from urllib.parse import unquote
    me = await family.client.get("/v1/me", headers={"Authorization": f"Bearer {unquote(token)}"})
    assert me.status_code == 200 and me.json()["id"] == family.amma["id"]
    # Cancelled or failed, the app hears it too, on its own scheme.
    r = await family.client.get("/v1/sign-in/google/callback?state=app-nothing&error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "familyos://signin?signin=cancelled"
    # The console's own flow is untouched.
    r = await family.client.get("/v1/sign-in/google/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/app/?signin=cancelled"
