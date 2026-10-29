"""Mental-load balance: off by default, private, gentle, and quiet once waved away."""
import uuid

from tests.conftest import pdf


async def _handle_n(family, who, n, school=True):
    for _ in range(n):
        a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared", subjects=[family.younger] if school else ())).json()["artifact"]["id"]
        r = await family.client.post(f"/v1/artifacts/{a}/handled", headers=family.h(who), json={"note": "done"})
        assert r.status_code == 200, r.text


async def test_it_is_off_until_a_guardian_switches_it_on_and_says_nothing_then(family):
    await family.consent(family.younger)
    await _handle_n(family, "amma", 8)
    assert (await family.client.get("/v1/me/balance", headers=family.h("amma"))).json() == {"enabled": False, "nudges": []}
    assert (await family.client.put("/v1/household/balance", headers=family.h("paati"), json={"enabled": True})).status_code == 403


async def test_the_one_carrying_most_gets_one_gentle_private_sentence(family):
    await family.consent(family.younger)
    await family.client.put("/v1/household/balance", headers=family.h("amma"), json={"enabled": True})
    await _handle_n(family, "amma", 7)
    await _handle_n(family, "appa", 1)
    mine = (await family.client.get("/v1/me/balance", headers=family.h("amma"))).json()
    assert mine["enabled"] and len(mine["nudges"]) == 1
    n = mine["nudges"][0]
    assert n["domain"] == "school" and "7 of the last 8" in n["text"] and "offer the next one to" in n["text"]
    assert n["offer_to"]["name"] != family.amma["display_name"]
    theirs = (await family.client.get("/v1/me/balance", headers=family.h("appa"))).json()
    assert theirs["nudges"] == []                                       # not shown to the one carrying less, nor anyone else


async def test_a_small_or_even_split_says_nothing(family):
    await family.consent(family.younger)
    await family.client.put("/v1/household/balance", headers=family.h("amma"), json={"enabled": True})
    await _handle_n(family, "amma", 3)
    await _handle_n(family, "appa", 3)
    assert (await family.client.get("/v1/me/balance", headers=family.h("amma"))).json()["nudges"] == []


async def test_waving_it_away_keeps_it_quiet(family):
    await family.consent(family.younger)
    await family.client.put("/v1/household/balance", headers=family.h("amma"), json={"enabled": True})
    await _handle_n(family, "amma", 8)
    assert len((await family.client.get("/v1/me/balance", headers=family.h("amma"))).json()["nudges"]) == 1
    await family.client.post("/v1/me/balance/dismiss", headers=family.h("amma"), json={"domain": "school"})
    assert (await family.client.get("/v1/me/balance", headers=family.h("amma"))).json()["nudges"] == []
