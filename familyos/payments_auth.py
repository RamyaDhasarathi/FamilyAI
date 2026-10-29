"""The login tokens the payment provider checks, signed here and verified by the provider from a public key address.

The provider (Crossmint) lets an app say who a cardholder is with a JWT it signs itself (RS256, claims iss = the
provider's project id, sub = a user id, aud = "crossmint.com", exp at least ten minutes ahead) and a public JWKS
address the provider reads to check the signature. The private key never leaves this machine. The user id is
the member's own, so a card saved by one guardian is that guardian's and no one else's.

The key is a file, made once on first use, kept out of git (`.keys/`). Setting `payments_jwt_key_file` moves it.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from familyos.crypto import b64u
from familyos.settings import settings

AUDIENCE = "crossmint.com"
LIFETIME_SECONDS = 15 * 60

_key: rsa.RSAPrivateKey | None = None


_b64 = b64u


def _int_b64(n: int) -> str:
    return _b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def private_key() -> rsa.RSAPrivateKey:
    global _key
    if _key is not None:
        return _key
    path = Path(settings.payments_jwt_key_file)
    if path.exists():
        _key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    else:
        _key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        path.chmod(0o600)
    return _key


def forget_key() -> None:
    global _key
    _key = None


def key_id() -> str:
    numbers = private_key().public_key().public_numbers()
    return hashlib.sha256(_int_b64(numbers.n).encode() + b"." + _int_b64(numbers.e).encode()).hexdigest()[:16]


def jwks() -> dict:
    numbers = private_key().public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": key_id(), "n": _int_b64(numbers.n), "e": _int_b64(numbers.e)}]}


def user_id(member_id: uuid.UUID) -> str:
    return f"familyos-{member_id}"


def mint(member_id: uuid.UUID, *, now: float | None = None) -> str:
    """A token that says this member is this provider user, good for fifteen minutes."""
    if not settings.payments_project_id:
        raise RuntimeError("FAMILYOS_PAYMENTS_PROJECT_ID is not set")
    now = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": key_id()}
    claims = {"iss": settings.payments_project_id, "sub": user_id(member_id), "aud": AUDIENCE, "iat": now, "nbf": now - 5, "exp": now + LIFETIME_SECONDS}
    signing_input = _b64(json.dumps(header, separators=(",", ":")).encode()) + "." + _b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = private_key().sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return signing_input + "." + _b64(signature)
