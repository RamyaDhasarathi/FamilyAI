"""Development sign-in (FAMILYOS_DEV_SIGN_IN): an address alone signs a member
in, through the same link-and-redeem path the mailed link takes, so the rows
it writes are a real sign-in's. Off, the route does not exist."""
import pytest

from familyos import db
from familyos.settings import settings


@pytest.fixture
def dev_on(monkeypatch):
    monkeypatch.setattr(settings, "dev_sign_in", True)


async def test_the_route_does_not_exist_when_development_sign_in_is_off(family, monkeypatch):
    monkeypatch.setattr(settings, "dev_sign_in", False)
    r = await family.client.post("/v1/sign-in/dev", json={"email": "amma@example.com"})
    assert r.status_code == 404


async def test_an_address_signs_in_and_the_session_is_a_real_one(family, dev_on):
    r = await family.client.post("/v1/sign-in/dev", json={"email": "Amma@Example.com "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["member"]["id"] == family.amma["id"] and body["token"]
    me = await family.client.get("/v1/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["id"] == family.amma["id"]
    # The rows a mailed link leaves: the link (spent), the session, and the audit row.
    pool = db.pool()
    assert await pool.fetchval("SELECT count(*) FROM sign_in_links WHERE member_id = $1 AND purpose = 'sign_in' "
                               "AND used_at IS NOT NULL", family.amma["id"]) == 1
    audit = await pool.fetchrow("SELECT detail FROM audit_events WHERE action = 'member.signed_in' AND target_id = $1 "
                                "ORDER BY id DESC LIMIT 1", family.amma["id"])
    assert audit is not None and audit["detail"]["via"] == "sign_in"


async def test_an_unknown_address_is_refused(family, dev_on):
    r = await family.client.post("/v1/sign-in/dev", json={"email": "nobody@example.com"})
    assert 400 <= r.status_code < 500 and "token" not in r.json()


async def test_no_address_can_lead_to_a_child(family, dev_on):
    """The schema refuses an address on a child, so an address never signs one in."""
    import asyncpg
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool().execute("UPDATE members SET email = 'kid@example.com' WHERE id = $1", family.older["id"])


async def test_a_browser_asking_for_the_cookie_gets_the_cookie_not_the_token(family, dev_on):
    r = await family.client.post("/v1/sign-in/dev", json={"email": "appa@example.com"}, headers={"x-familyos-csrf": "1"})
    assert r.status_code == 200, r.text
    assert r.json()["token"] is None and "familyos_session" in r.cookies


async def test_the_phone_gets_the_token_in_the_body(family, dev_on):
    r = await family.client.post("/v1/sign-in/dev", json={"email": "appa@example.com"})
    assert r.status_code == 200 and r.json()["token"] and "familyos_session" not in r.cookies
