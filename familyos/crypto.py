"""Per-household envelope encryption.

Every household has its own 256-bit data key. Blobs are sealed with it
(AES-GCM) before they reach the object store, and the key itself is stored
only wrapped by the master key. Erasing a household destroys its wrapped
key first: from that moment every copy of its originals, including ones in
backups or a lagging replica of the object store, is unreadable.
"""
from __future__ import annotations

import base64
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from familyos.settings import settings

_NONCE = 12


class KeyUnavailable(RuntimeError):
    """The household's key has been destroyed (erased) or never existed."""


MASTER_KEY_HELP = ("FAMILYOS_MASTER_KEY must be base64 of exactly 32 random bytes; it wraps every household's key. "
                   "Make one with: python3 -c \"import base64,os;print(base64.b64encode(os.urandom(32)).decode())\" "
                   "and keep it somewhere safe -- losing it makes every original unreadable.")


def b64u(data: bytes) -> str:
    """URL-safe base64 without padding: the one encoder for tokens, device secrets and JWT parts."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def check_master_key() -> None:
    """Refuse to start on a missing or malformed master key."""
    try:
        raw = base64.b64decode(settings.master_key or "", validate=True)
    except (ValueError, TypeError):
        raw = b""
    if len(raw) != 32:
        raise RuntimeError(MASTER_KEY_HELP)


def _master() -> AESGCM:
    raw = base64.b64decode(settings.master_key or "")
    if len(raw) != 32:
        raise RuntimeError("FAMILYOS_MASTER_KEY must be 32 bytes, base64-encoded")
    return AESGCM(raw)


def new_wrapped_key(household_id: uuid.UUID) -> bytes:
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE)
    return nonce + _master().encrypt(nonce, data_key, household_id.bytes)


def wrap_key(household_id: uuid.UUID, data_key: bytes) -> bytes:
    """An existing data key wrapped by the master key (going back from a family-held key to the server's)."""
    nonce = os.urandom(_NONCE)
    return nonce + _master().encrypt(nonce, data_key, household_id.bytes)


def unwrap(household_id: uuid.UUID, wrapped: bytes | None) -> bytes:
    if not wrapped:
        raise KeyUnavailable(f"household {household_id} has no key")
    return _master().decrypt(wrapped[:_NONCE], wrapped[_NONCE:], household_id.bytes)


def seal(data_key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(_NONCE)
    return nonce + AESGCM(data_key).encrypt(nonce, plaintext, aad)


def open_sealed(data_key: bytes, sealed: bytes, aad: bytes) -> bytes:
    return AESGCM(data_key).decrypt(sealed[:_NONCE], sealed[_NONCE:], aad)
