"""A trusted device whose secret is derived inside the member's passkey (WebAuthn PRF): the server wraps the household key under it and stores
neither the secret nor anything that can rebuild it. The browser derives it again, from the passkey and the stored salt, whenever it opens
the household. A device can only be tied to a passkey of the member who enrols it."""
import uuid

import pytest

from familyos import familykey
from familyos.settings import settings
from tests import test_passkeys as pk
from tests.test_private_mode import _passkey_headers, _simple

SECRET = b"\x11" * 32
SALT = b"\x22" * 32


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    familykey._unlocked.clear()
    familykey._attempts.clear()
    monkeypatch.setattr(settings, "webauthn_origins", pk.ORIGIN)
    yield
    familykey._unlocked.clear()


async def _credential(database, family, who="amma") -> str:
    m = getattr(family, who)
    raw = await database.fetchval("SELECT credential_id FROM member_passkeys WHERE member_id = $1 AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1", uuid.UUID(m["id"]))
    return familykey._b64(bytes(raw))


def _prf(cred, secret=SECRET, salt=SALT):
    return {"secret": familykey._b64(secret), "credential_id": cred, "salt": familykey._b64(salt)}


async def test_enrolling_with_prf_returns_no_secret_lists_the_salt_and_unlocks_with_the_rederived_secret(family, database):
    made, _ = await _simple(family)                                     # open (the household was just switched on)
    h = await _passkey_headers(family)
    cred = await _credential(database, family)
    added = await family.client.post("/v1/household/family-key/devices", headers=h, json={"label": "Laptop", "prf": _prf(cred)})
    assert added.status_code == 201, added.text
    out = added.json()
    assert out["prf"] is True and out["secret"] is None
    # nothing that can rebuild the secret is stored: the row holds the wrapped key, the passkey's id and the salt, not the secret
    row = await database.fetchrow("SELECT wrapped_key, prf_salt, credential_id FROM family_key_devices WHERE id = $1", uuid.UUID(out["id"]))
    assert SECRET not in bytes(row["wrapped_key"]) and bytes(row["prf_salt"]) == SALT
    listed = {d["id"]: d for d in (await family.client.get("/v1/household/family-key/devices", headers=h)).json()}
    assert listed[out["id"]]["prf"] is True and listed[out["id"]]["salt"] == familykey._b64(SALT) and listed[out["id"]]["credential_id"] == cred
    assert "secret" not in listed[out["id"]]
    # lock, then open with the secret the browser derives again: it needs a recent passkey sign-in as ever
    await family.client.post("/v1/household/family-key/lock", headers=h)
    wrong = await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h,
                                     json={"device_id": out["id"], "device_secret": familykey._b64(b"\x33" * 32)})
    assert wrong.status_code in (400, 422)
    ok = await family.client.post("/v1/household/family-key/unlock-with-passkey", headers=h, json={"device_id": out["id"], "device_secret": familykey._b64(SECRET)})
    assert ok.status_code == 200 and ok.json()["locked"] is False
    assert made["device"]["secret"]                                      # the first, random-secret device still works the old way


async def test_a_device_cannot_be_tied_to_somebody_elses_passkey_or_a_bad_secret(family, database):
    await _simple(family)
    h = await _passkey_headers(family, "amma")
    await pk._add(family, "paati")                                      # another member's passkey
    theirs = await _credential(database, family, "paati")
    r = await family.client.post("/v1/household/family-key/devices", headers=h, json={"label": "Laptop", "prf": _prf(theirs)})
    assert r.status_code in (400, 422) and "not one of yours" in r.text
    mine = await _credential(database, family, "amma")
    short = await family.client.post("/v1/household/family-key/devices", headers=h, json={"label": "Laptop", "prf": _prf(mine, secret=b"\x01" * 31)})
    assert short.status_code in (400, 422)
    nonsense = await family.client.post("/v1/household/family-key/devices", headers=h, json={"label": "Laptop", "prf": _prf("AAAAAAAAAAAA")})
    assert nonsense.status_code in (400, 422)


async def test_the_first_device_can_be_passkey_derived_when_making_it_private(family, database):
    phone, _ = await pk._add(family, "amma")
    cred = await _credential(database, family)
    r = await family.client.post("/v1/household/family-key/simple", headers=family.h("amma"), json={"label": "This browser", "prf": _prf(cred)})
    assert r.status_code == 200, r.text
    made = r.json()
    assert made["device"]["secret"] is None and made["device"]["prf"] is True and len(made["phrase"].split()) == 33
    done = await family.client.post("/v1/household/family-key/simple/done", headers=family.h("amma"),
                                    json={"device_id": made["device"]["id"], "device_secret": familykey._b64(SECRET)})
    assert done.status_code == 200 and done.json()["mode"] == "family"
    assert phone is not None
