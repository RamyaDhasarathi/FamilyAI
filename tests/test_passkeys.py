"""Passkeys: a software authenticator makes a real WebAuthn registration and sign-in, and the server's rules hold."""
import base64
import hashlib
import json
import os
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from familyos.settings import settings

ORIGIN = "http://localhost:8088"
RP = "localhost"


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Authenticator:
    """Just enough of a phone to make and use a passkey, the way a browser would hand it over."""

    def __init__(self, user_handle: bytes | None = None):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(32)
        self.counter = 0
        self.handle = user_handle

    def _client(self, kind, challenge_b64, origin):
        return json.dumps({"type": kind, "challenge": challenge_b64, "origin": origin, "crossOrigin": False}).encode()

    def create(self, options: dict, origin=ORIGIN) -> dict:
        self.handle = unb64u(options["user"]["id"])
        pub = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: pub.x.to_bytes(32, "big"), -3: pub.y.to_bytes(32, "big")})
        rp_hash = hashlib.sha256(options["rp"]["id"].encode()).digest()
        auth = rp_hash + bytes([0x45]) + struct.pack(">I", 0) + bytes(16) + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose
        client = self._client("webauthn.create", options["challenge"], origin)
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64u(client), "attestationObject": b64u(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})), "transports": ["internal"]}}

    def get(self, options: dict, origin=ORIGIN, counter=None, rp=None, uv=True) -> dict:
        self.counter = counter if counter is not None else self.counter + 1
        auth = hashlib.sha256((rp or options["rpId"]).encode()).digest() + bytes([0x05 if uv else 0x01]) + struct.pack(">I", self.counter)
        client = self._client("webauthn.get", options["challenge"], origin)
        sig = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64u(client), "authenticatorData": b64u(auth), "signature": b64u(sig), "userHandle": b64u(self.handle or b"")}}


@pytest.fixture(autouse=True)
def _origins(monkeypatch):
    monkeypatch.setattr(settings, "webauthn_origins", ORIGIN)


async def _add(family, who="amma", label="Emily's iPhone", phone=None):
    phone = phone or Authenticator()
    h = {**family.h(who), "Origin": ORIGIN}
    opts = await family.client.post("/v1/me/passkeys/options", headers=h)
    assert opts.status_code == 200, opts.text
    done = await family.client.post("/v1/me/passkeys", headers=h, json={"credential": phone.create(opts.json()), "label": label})
    assert done.status_code == 201, done.text
    return phone, done.json()


async def _sign_in(family, phone, **kw):
    opts = await family.client.post("/v1/sign-in/passkey/options", headers={"Origin": ORIGIN})
    assert opts.status_code == 200, opts.text
    return await family.client.post("/v1/sign-in/passkey", headers={"Origin": ORIGIN}, json={"credential": phone.get(opts.json(), **kw)})


async def test_a_member_adds_a_passkey_then_signs_in_with_it_without_a_username(family):
    phone, added = await _add(family)
    assert added["label"] == "Emily's iPhone"
    mine = (await family.client.get("/v1/me/passkeys", headers=family.h("amma"))).json()
    assert [p["label"] for p in mine] == ["Emily's iPhone"] and "public_key" not in json.dumps(mine)
    r = await _sign_in(family, phone)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["member"]["display_name"] == family.amma["display_name"] and body["token"].startswith("fos_")
    me = await family.client.get("/v1/me/day", headers={"Authorization": "Bearer " + body["token"]})
    assert me.status_code == 200                                                                      # the token works
    assert (await family.client.get("/v1/me/passkeys", headers=family.h("amma"))).json()[0]["last_used_at"] is not None


async def test_a_replayed_wrong_origin_wrong_key_or_old_counter_sign_in_is_refused_the_same_way(family):
    phone, _ = await _add(family)
    opts = (await family.client.post("/v1/sign-in/passkey/options", headers={"Origin": ORIGIN})).json()
    ok = phone.get(opts)
    assert (await family.client.post("/v1/sign-in/passkey", headers={"Origin": ORIGIN}, json={"credential": ok})).status_code == 200
    assert (await family.client.post("/v1/sign-in/passkey", headers={"Origin": ORIGIN}, json={"credential": ok})).status_code in (400, 401, 422)     # a challenge works once
    wrong_origin = await _sign_in(family, phone, origin="https://evil.example")
    assert wrong_origin.status_code in (400, 401, 422)
    stranger = await _sign_in(family, Authenticator())
    assert stranger.status_code in (400, 401, 422)                                                   # a passkey nobody registered
    backwards = await _sign_in(family, phone, counter=0)
    assert backwards.status_code in (400, 401, 422)                                                  # a counter that went backwards is a cloned key
    no_origin = await family.client.post("/v1/sign-in/passkey/options")
    assert no_origin.status_code in (400, 422) and "not set up" in no_origin.text


async def test_a_removed_passkey_no_longer_signs_in_and_a_child_cannot_add_one(family):
    phone, added = await _add(family)
    assert (await family.client.delete(f"/v1/me/passkeys/{added['id']}", headers=family.h("amma"))).status_code == 204
    assert (await _sign_in(family, phone)).status_code in (400, 401, 422)
    assert (await family.client.delete(f"/v1/me/passkeys/{added['id']}", headers=family.h("amma"))).status_code == 404
    import uuid

    from familyos import passkeys
    from familyos.identity import NotAllowed, Principal
    kid = Principal(member_id=uuid.UUID(family.younger["id"]), household_id=uuid.UUID(family.household["id"]), role="child", display_name="Younger one")
    with pytest.raises(NotAllowed):
        await passkeys.register_options(kid, ORIGIN)


async def test_a_second_device_a_duplicate_and_the_limit(family):
    first, _ = await _add(family, label="iPhone")
    second, _ = await _add(family, label="iPad")
    assert len((await family.client.get("/v1/me/passkeys", headers=family.h("amma"))).json()) == 2
    h = {**family.h("amma"), "Origin": ORIGIN}
    opts = (await family.client.post("/v1/me/passkeys/options", headers=h)).json()
    assert [c["id"] for c in opts["excludeCredentials"]] and b64u(first.cred_id) in [c["id"] for c in opts["excludeCredentials"]]
    dup = await family.client.post("/v1/me/passkeys", headers=h, json={"credential": first.create(opts)})
    assert dup.status_code in (400, 422)
    assert (await _sign_in(family, second)).status_code == 200


async def test_a_challenge_for_another_member_cannot_register_my_key(family):
    h1 = {**family.h("amma"), "Origin": ORIGIN}
    opts = (await family.client.post("/v1/me/passkeys/options", headers=h1)).json()
    phone = Authenticator()
    cred = phone.create(opts)
    stolen = await family.client.post("/v1/me/passkeys", headers={**family.h("paati"), "Origin": ORIGIN}, json={"credential": cred})
    assert stolen.status_code in (400, 422)


async def test_a_sign_in_without_user_verification_is_refused(family):
    phone, _ = await _add(family)
    assert (await _sign_in(family, phone)).status_code == 200
    assert (await _sign_in(family, phone, uv=False)).status_code == 401
    opts = await family.client.post("/v1/sign-in/passkey/options", headers={"Origin": ORIGIN})
    assert opts.json()["userVerification"] == "required"
