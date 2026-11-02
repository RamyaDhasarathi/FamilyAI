"""The login tokens the payment provider checks: signed here, verifiable from the public key, scoped to one member."""
import base64
import json
import uuid

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from familyos import payments, payments_auth
from familyos.settings import settings


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@pytest.fixture(autouse=True)
def key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "payments_jwt_key_file", str(tmp_path / "k.pem"))
    monkeypatch.setattr(settings, "payments_project_id", "proj-123")
    payments_auth.forget_key()
    yield
    payments_auth.forget_key()


def test_a_token_carries_the_claims_the_provider_requires_and_verifies_from_the_public_key():
    member = uuid.uuid4()
    token = payments_auth.mint(member, now=1_800_000_000)
    head, body, sig = token.split(".")
    header, claims = json.loads(_unb64(head)), json.loads(_unb64(body))
    assert header["alg"] == "RS256" and header["kid"] == payments_auth.key_id()
    assert claims["iss"] == "proj-123" and claims["aud"] == "crossmint.com" and claims["sub"] == f"familyos-{member}"
    assert claims["exp"] - claims["iat"] >= 600
    jwk = payments_auth.jwks()["keys"][0]
    pub = rsa.RSAPublicNumbers(int.from_bytes(_unb64(jwk["e"]), "big"), int.from_bytes(_unb64(jwk["n"]), "big")).public_key()
    pub.verify(_unb64(sig), (head + "." + body).encode(), padding.PKCS1v15(), hashes.SHA256())    # raises if wrong
    assert jwk["kid"] == header["kid"] and "d" not in jwk and "p" not in jwk


def test_the_key_is_made_once_and_reused_and_a_token_needs_a_project_id(monkeypatch):
    first = payments_auth.key_id()
    payments_auth.forget_key()
    assert payments_auth.key_id() == first
    monkeypatch.setattr(settings, "payments_project_id", "")
    with pytest.raises(RuntimeError):
        payments_auth.mint(uuid.uuid4())


async def test_the_public_key_address_needs_no_sign_in_and_has_no_private_part(family):
    r = await family.client.get("/.well-known/payments-jwks.json")
    assert r.status_code == 200 and r.json()["keys"][0]["kty"] == "RSA" and "d" not in r.json()["keys"][0]


async def test_only_a_guardian_gets_a_session_and_only_when_payments_are_connected(family, monkeypatch):
    monkeypatch.setattr(settings, "payments_provider", "crossmint")
    monkeypatch.setattr(settings, "payments_client_key", "ck_staging_test")
    payments.use_provider(None)
    r = await family.client.post("/v1/payments/session", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client_key"] == "ck_staging_test" and body["environment"] == "staging" and body["jwt"].count(".") == 2
    assert "server" not in str(body).lower()
    assert (await family.client.post("/v1/payments/session", headers=family.h("paati"))).status_code == 403
    monkeypatch.setattr(settings, "payments_project_id", "")
    assert (await family.client.post("/v1/payments/session", headers=family.h("amma"))).status_code == 403


async def test_an_approved_purchase_can_be_retried_only_by_a_guardian_and_only_while_it_waits(family, monkeypatch):
    from familyos.db import pool

    class Prov:
        name = "p"
        made = []

        async def create_allowance(self, **kw):
            self.made.append(kw["member_id"])
            return {"ref": "oi_x", "state": {"order_intent": {"orderIntentId": "oi_x"}}}

        async def revoke(self, ref, **kw):
            pass

    prov = Prov()
    payments.use_provider(prov)
    monkeypatch.setattr(settings, "payments_provider", "p")
    await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"payments_enabled": True})
    pid = (await family.client.post("/v1/purchases", headers=family.h("amma"),
                                    json={"title": "Milk", "merchant_name": "Shop", "merchant_url": "https://shop.example", "amount": 100, "currency": "INR"})).json()["id"]
    waiting = await family.client.post(f"/v1/purchases/{pid}/decision", headers=family.h("amma"), json={"approve": True})
    assert waiting.json()["status"] == "approved" and prov.made == []          # no card yet
    await pool().execute("UPDATE members SET payment_method_id = 'pm_1' WHERE id = $1", uuid.UUID(family.amma["id"]))
    assert (await family.client.post(f"/v1/purchases/{pid}/allowance", headers=family.h("paati"))).status_code == 403
    done = await family.client.post(f"/v1/purchases/{pid}/allowance", headers=family.h("amma"))
    assert done.json()["status"] == "ready" and done.json()["provider_state"]["order_intent"]["orderIntentId"] == "oi_x"
    assert (await family.client.post(f"/v1/purchases/{pid}/allowance", headers=family.h("amma"))).status_code == 403
    payments.use_provider(None)
