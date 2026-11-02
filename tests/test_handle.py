"""A family address a person can say out loud."""
import uuid

import pytest

from familyos import identity
from familyos.identity import Invalid, NotAllowed, Principal


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def test_a_household_starts_with_a_generated_address(family):
    r = await family.client.get("/v1/household", headers=family.h("amma"))
    assert r.json()["inbound_address"].startswith("h")


async def test_a_guardian_names_the_family_and_both_addresses_keep_working(family, database):
    generated = (await family.client.get("/v1/household", headers=family.h("amma"))).json()["inbound_address"]
    token = generated.split("@")[0]

    r = await family.client.put("/v1/household/handle", headers=family.h("amma"), json={"handle": "the.sharmas"})
    assert r.status_code == 200, r.text
    assert r.json()["inbound_address"].startswith("the.sharmas@")

    # The one a school may already have been given still resolves.
    assert (await identity.household_by_inbound_token(token))["id"] == uuid.UUID(family.household["id"])
    assert (await identity.household_by_inbound_token("the.sharmas"))["id"] == uuid.UUID(family.household["id"])
    # And it is matched however it was typed.
    assert (await identity.household_by_inbound_token("The.Sharmas")) is not None


async def test_only_a_guardian_names_the_family(family):
    with pytest.raises(NotAllowed):
        await identity.set_handle(_principal(family, "paati"), "the.sharmas")


async def test_a_name_has_to_be_sayable_and_not_already_meant_for_someone(family):
    me = _principal(family)
    for bad in ("ab", "x" * 33, "The.Sharmas!", "-sharmas", "sharmas-", "the..sharmas",
                "postmaster", "admin", "h0123456789abcdef0123"):
        with pytest.raises(Invalid):
            await identity.set_handle(me, bad)


async def test_two_households_cannot_hold_the_same_name(family, client):
    await identity.set_handle(_principal(family), "the.sharmas")
    from tests.conftest import found
    other = await found(client, "Other", "B", "b@example.com")
    token = other.json()["credentials"]["token"]
    r = await client.put("/v1/household/handle", headers={"Authorization": f"Bearer {token}"},
                         json={"handle": "The.Sharmas"})
    assert r.status_code == 422
    assert "taken" in r.json()["detail"]


async def test_availability_can_be_checked_before_claiming(family):
    free = await family.client.get("/v1/household/handle/available?handle=the.sharmas",
                                   headers=family.h("amma"))
    assert free.json()["available"] is True
    await identity.set_handle(_principal(family), "the.sharmas")
    taken = await family.client.get("/v1/household/handle/available?handle=the.sharmas",
                                    headers=family.h("amma"))
    assert taken.json()["available"] is False


async def test_a_notice_sent_to_the_chosen_address_reaches_the_household(family, database):
    """The whole point: a school writes to the name on the form, and it lands."""
    from tests.test_email import message, post

    await identity.set_handle(_principal(family), "the.sharmas")
    chosen = (await family.client.get("/v1/household", headers=family.h("amma"))).json()["inbound_address"]
    assert chosen.startswith("the.sharmas@")

    r = await post(family.client, message("appa@example.com", chosen))
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "accepted"
