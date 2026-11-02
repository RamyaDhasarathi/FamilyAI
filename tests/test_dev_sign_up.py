"""Development sign-up (FAMILYOS_DEV_SIGN_IN): an address alone gets the
founding ticket the founding mail would carry, so the phone can start a
household through the real POST /v1/households. Off, the route does not exist.
Until mail is connected (decided 29 Oct 2026); then the mailed ticket returns."""
import pytest

from familyos import crypto, db
from familyos.settings import settings


@pytest.fixture
def dev_on(monkeypatch):
    monkeypatch.setattr(settings, "dev_sign_in", True)


async def test_the_route_does_not_exist_when_development_sign_in_is_off(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_sign_in", False)
    r = await client.post("/v1/sign-up/dev", json={"email": "new@example.com"})
    assert r.status_code == 404


async def test_a_new_address_founds_a_household_with_the_ticket(client, dev_on):
    r = await client.post("/v1/sign-up/dev", json={"email": "New@Example.com "})
    assert r.status_code == 200, r.text
    ticket = r.json()["founding"]
    r = await client.post("/v1/households", json={"name": "The New family", "founding": ticket,
                                                  "guardian": {"display_name": "New Guardian", "email": "new@example.com"}})
    assert r.status_code == 201, r.text
    token = r.json()["credentials"]["token"]
    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["role"] == "guardian"
    # The household's key is wrapped by this server's master key.
    row = await db.pool().fetchrow("SELECT id, wrapped_key FROM households WHERE id = $1", me.json()["household_id"])
    assert len(crypto.unwrap(row["id"], row["wrapped_key"])) == 32


async def test_the_ticket_is_spent_once(client, dev_on):
    ticket = (await client.post("/v1/sign-up/dev", json={"email": "once@example.com"})).json()["founding"]
    body = {"name": "Once", "founding": ticket, "guardian": {"display_name": "Once", "email": "once@example.com"}}
    assert (await client.post("/v1/households", json=body)).status_code == 201
    assert (await client.post("/v1/households", json=body)).status_code == 403


async def test_the_ticket_is_only_for_its_own_address(client, dev_on):
    ticket = (await client.post("/v1/sign-up/dev", json={"email": "mine@example.com"})).json()["founding"]
    r = await client.post("/v1/households", json={"name": "Not mine", "founding": ticket,
                                                  "guardian": {"display_name": "Other", "email": "other@example.com"}})
    assert r.status_code == 403


async def test_an_address_already_in_a_household_is_told_to_log_in(family, dev_on):
    r = await family.client.post("/v1/sign-up/dev", json={"email": "Amma@Example.com"})
    assert r.status_code == 422 and "log in" in r.json()["detail"]
    assert "founding" not in r.json()


async def test_a_bad_address_is_refused(client, dev_on):
    assert (await client.post("/v1/sign-up/dev", json={"email": "not-an-address"})).status_code == 422
