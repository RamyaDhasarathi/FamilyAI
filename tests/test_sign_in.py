"""Magic-link sign-in: the only thing standing between the build and a family."""
import re

import pytest

from familyos import identity, mail
from familyos.settings import settings


@pytest.fixture
def sent(monkeypatch):
    """Nothing leaves the test suite. Records what would have."""
    out = []

    async def fake(to, subject, body, *, ics=None):
        out.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(mail, "send", fake)
    monkeypatch.setattr(mail, "configured", lambda: True)
    return out


def _link(message: str) -> str:
    found = re.search(r"link=([A-Za-z0-9_\-]+)", message)
    assert found, message
    return found.group(1)


async def test_a_member_signs_in_with_a_link_sent_to_their_mailbox(family, sent):
    assert await identity.request_sign_in("amma@example.com") == 1
    assert sent[0]["to"] == "amma@example.com"

    r = await family.client.post("/v1/sign-in/redeem", json={"link": _link(sent[0]["body"])})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    me = await family.client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == family.amma["id"]


async def test_a_link_works_once(family, sent):
    await identity.request_sign_in("amma@example.com")
    link = _link(sent[0]["body"])
    assert (await family.client.post("/v1/sign-in/redeem", json={"link": link})).status_code == 200
    second = await family.client.post("/v1/sign-in/redeem", json={"link": link})
    assert second.status_code == 401
    assert second.json()["error"] == "link_not_usable"


async def test_asking_again_kills_the_previous_link(family, sent):
    await identity.request_sign_in("amma@example.com")
    first = _link(sent[0]["body"])
    await identity.request_sign_in("amma@example.com")
    second = _link(sent[1]["body"])
    # A link left in a mailbox or a screenshot stops working once a new one is asked for.
    assert (await family.client.post("/v1/sign-in/redeem", json={"link": first})).status_code == 401
    assert (await family.client.post("/v1/sign-in/redeem", json={"link": second})).status_code == 200


async def test_an_expired_link_is_refused(family, database, sent):
    await identity.request_sign_in("amma@example.com")
    link = _link(sent[0]["body"])
    await database.execute("UPDATE sign_in_links SET expires_at = NOW() - interval '1 minute'")
    assert (await family.client.post("/v1/sign-in/redeem", json={"link": link})).status_code == 401


async def test_an_unknown_address_is_answered_the_same_way_and_only_its_mailbox_learns_more(family, sent):
    """The form says the same thing to everyone. What differs arrives only in
    the mailbox: a member gets a sign-in link; an address no family uses gets
    an offer to start one, which is not a way into anything that exists."""
    r = await family.client.post("/v1/sign-in/request", json={"email": "stranger@example.com"})
    assert r.status_code == 202
    known = await family.client.post("/v1/sign-in/request", json={"email": "amma@example.com"})
    assert known.status_code == 202 and known.json() == r.json()
    assert [m["to"] for m in sent] == ["stranger@example.com", "amma@example.com"]
    assert "Start a household" in sent[0]["subject"] and "link=" not in sent[0]["body"]
    assert "link=" in sent[1]["body"]


async def test_a_child_can_never_receive_a_link(family, database, sent):
    """Two independent guards, and the outer one is the database's."""
    import asyncpg

    # The schema will not even let a child hold an address to send a link to.
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await database.execute("UPDATE members SET email = 'kid@example.com' WHERE role = 'child'")

    # And were one to exist anyway, the lookup excludes children by role, and
    # an address on any member row -- even one that cannot sign in -- is never
    # offered a household either. Only a sign-in link counts as a way in.
    assert await identity.request_sign_in("kid@example.com") == 1   # an unknown address: offered a household
    assert all("link=" not in m["body"] for m in sent)


async def test_a_guardian_invites_a_member_and_an_adult_cannot(family, sent):
    r = await family.client.post(f"/v1/members/{family.paati['id']}/invite", headers=family.h("paati"))
    assert r.status_code == 403

    r = await family.client.post(f"/v1/members/{family.paati['id']}/invite", headers=family.h("amma"))
    assert r.status_code == 202, r.text
    assert sent[0]["to"] == family.paati["email"]
    assert (await family.client.post("/v1/sign-in/redeem", json={"link": _link(sent[0]["body"])})).status_code == 200


async def test_inviting_a_child_is_refused(family, sent):
    child = next(m for m in (await family.client.get("/v1/household", headers=family.h("amma"))).json()["members"]
                 if m["role"] == "child")
    r = await family.client.post(f"/v1/members/{child['id']}/invite", headers=family.h("amma"))
    assert r.status_code == 422
    assert sent == []


async def test_the_link_points_at_the_console(family, sent, monkeypatch):
    monkeypatch.setattr(settings, "console_url", "https://app.example.com/app/")
    await identity.request_sign_in("amma@example.com")
    assert "https://app.example.com/app/?link=lnk_" in sent[0]["body"]


async def test_a_mail_failure_does_not_reveal_that_the_address_exists(family, monkeypatch):
    """Found live: with SMTP down, an unknown address answered 202 and a known
    one answered 500 — which is precisely the thing this route hides."""
    async def refuse(*a, **kw):
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(mail, "send", refuse)
    monkeypatch.setattr(mail, "configured", lambda: True)

    unknown = await family.client.post("/v1/sign-in/request", json={"email": "stranger@example.com"})
    known = await family.client.post("/v1/sign-in/request", json={"email": "amma@example.com"})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
