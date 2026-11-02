"""Connected services (decided 30 Oct 2026: site passwords are allowed, kept on this Mac): a member adds a site
(Amazon, Flipkart …) with a username and password for the browser agent. The password goes to the macOS Keychain only
-- never the database, never the local cache, never back out of the API; the cache keeps which site and which username."""
import pytest

from familyos.collect import vault
from familyos.settings import settings

SECRET = "hunter2-correct-horse"


@pytest.fixture(autouse=True)
def keychain(monkeypatch, tmp_path):
    """A stand-in Keychain: the tests never touch the real one."""
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    held: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(vault, "_keychain_set", lambda svc, acct, pw: held.__setitem__((svc, acct), pw))
    monkeypatch.setattr(vault, "_keychain_get", lambda svc, acct: held.get((svc, acct)))
    monkeypatch.setattr(vault, "_keychain_delete", lambda svc, acct: held.pop((svc, acct), None))
    return held


async def test_a_member_connects_a_site_and_the_password_is_only_in_the_keychain(family, keychain, tmp_path):
    r = await family.client.post("/v1/collect/services", headers=family.h("amma"),
                                 json={"service": "amazon", "username": "amma@example.com", "password": SECRET})
    assert r.status_code == 201, r.text
    assert SECRET not in r.text
    assert list(keychain.values()) == [SECRET]
    listed = (await family.client.get("/v1/collect/services", headers=family.h("amma"))).json()
    assert [(c["service"], c["username"]) for c in listed["connected"]] == [("amazon", "amma@example.com")]
    assert SECRET not in str(listed)
    assert any(s["id"] == "flipkart" for s in listed["catalog"])
    # Not in the local cache file.
    assert SECRET.encode() not in (tmp_path / "collect" / "collect.sqlite3").read_bytes()
    # The browser agent (not the API) can have it back.
    assert vault.credentials("amma@example.com", "amazon") == ("amma@example.com", SECRET)


async def test_each_member_has_their_own(family):
    await family.client.post("/v1/collect/services", headers=family.h("amma"),
                             json={"service": "flipkart", "username": "amma", "password": SECRET})
    assert (await family.client.get("/v1/collect/services", headers=family.h("appa"))).json()["connected"] == []
    assert vault.credentials("appa@example.com", "flipkart") is None


async def test_removing_takes_it_out_of_the_keychain_too(family, keychain):
    await family.client.post("/v1/collect/services", headers=family.h("amma"),
                             json={"service": "swiggy", "username": "amma", "password": SECRET})
    r = await family.client.delete("/v1/collect/services/swiggy", headers=family.h("amma"))
    assert r.status_code == 204
    assert keychain == {} and (await family.client.get("/v1/collect/services", headers=family.h("amma"))).json()["connected"] == []


async def test_another_site_needs_its_address_and_an_unknown_one_is_refused(family):
    ok = await family.client.post("/v1/collect/services", headers=family.h("amma"),
                                  json={"service": "other", "host": "portal.school.example", "username": "amma", "password": SECRET})
    assert ok.status_code == 201, ok.text
    listed = (await family.client.get("/v1/collect/services", headers=family.h("amma"))).json()["connected"]
    assert listed[0]["host"] == "portal.school.example"
    assert (await family.client.post("/v1/collect/services", headers=family.h("amma"),
                                     json={"service": "other", "username": "amma", "password": SECRET})).status_code == 422
    assert (await family.client.post("/v1/collect/services", headers=family.h("amma"),
                                     json={"service": "nope", "username": "amma", "password": SECRET})).status_code == 422
    assert (await family.client.post("/v1/collect/services", json={"service": "amazon", "username": "a", "password": "b"})).status_code == 401
