"""Founding a household takes proof of the address. POST /households used
to take none; the moment the console is reachable from a phone that is the
front door standing open."""


from familyos import identity
from familyos.db import pool


async def test_without_a_ticket_nobody_founds_anything(client, database):
    r = await client.post("/v1/households", json={
        "name": "Home", "guardian": {"display_name": "A", "email": "a@example.com"}})
    assert r.status_code == 422          # the field is required
    r = await client.post("/v1/households", json={
        "name": "Home", "guardian": {"display_name": "A", "email": "a@example.com"}, "founding": "fnd_made_up"})
    assert r.status_code == 403
    assert await database.fetchval("SELECT count(*) FROM households") == 0


async def test_a_ticket_is_for_one_address_and_one_use(client, database):
    async with pool().acquire() as conn, conn.transaction():
        ticket = await identity.issue_founding(conn, "Amma@Example.com")
    other = {"name": "Home", "guardian": {"display_name": "B", "email": "b@example.com"}, "founding": ticket}
    assert (await client.post("/v1/households", json=other)).status_code == 403
    mine = {"name": "Home", "guardian": {"display_name": "A", "email": "amma@example.com"}, "founding": ticket}
    assert (await client.post("/v1/households", json=mine)).status_code == 201
    assert (await client.post("/v1/households", json=mine)).status_code == 403


async def test_asking_again_replaces_the_last_ticket(client, database):
    async with pool().acquire() as conn, conn.transaction():
        first = await identity.issue_founding(conn, "a@example.com")
        second = await identity.issue_founding(conn, "a@example.com")
    body = {"name": "Home", "guardian": {"display_name": "A", "email": "a@example.com"}}
    assert (await client.post("/v1/households", json={**body, "founding": first})).status_code == 403
    assert (await client.post("/v1/households", json={**body, "founding": second})).status_code == 201


async def test_an_unknown_address_asking_to_sign_in_is_mailed_a_way_to_start(client, database, monkeypatch):
    """The form answers the same for every address. Only the mailbox learns
    which it got: a sign-in link, or an offer to start a household."""
    from familyos import mail
    out = []

    async def fake(to, subject, body, *, ics=None):
        out.append((to, subject, body))

    monkeypatch.setattr(mail, "send", fake)
    monkeypatch.setattr(mail, "configured", lambda: True)
    r = await client.post("/v1/sign-in/request", json={"email": "nobody@example.com"})
    assert r.status_code == 202 and "on its way" in r.json()["sent"]
    assert len(out) == 1 and out[0][0] == "nobody@example.com" and "Start a household" in out[0][1]
    link = out[0][2].split("#found=")[1].split("&")[0]
    from urllib.parse import unquote
    r = await client.post("/v1/households", json={
        "name": "Home", "guardian": {"display_name": "N", "email": "nobody@example.com"}, "founding": unquote(link)})
    assert r.status_code == 201, r.text
