"""A key the family holds: the household's data key wrapped by a secret that exists only as Shamir shares.

By default the server's master key wraps each household's data key, so the operator can unwrap any of them. A household can opt in to
something stronger: a random family secret S is split into n word shares (SLIP-39, any t of them rebuild it); the data key K is wrapped
under a key derived from S; the server keeps that wrapped copy, forgets the master-wrapped one, and never stores a share. Nobody, the
operator included, can unwrap K without t of the family's shares. While an adult has unlocked the household, K sits in this process's
memory for a few hours and the server works as usual; locked, or after a restart, everything sealed under K is unreadable.

What this protects: the original files, mailbox tokens and signed-in sessions (everything sealed with the household key) at rest, in
backups and from the operator. What it does not: the text FamilyOS has already read out of notices sits in the database in the clear until
the extracted text is sealed under K as well (docs/family-key.md, step 2), and while unlocked the server and the model providers it calls see
what is being read. The claim made to a family has to be that exact one.

Simple mode ("Make it private", one tap). The family secret is ONE recovery phrase: a 1-of-1 SLIP-39 share, 33 words, shown once, never stored.
Each trusted device also gets its own random 32-byte device secret that wraps the same household key; the server keeps only the wrapped copies
(family_key_devices). To open the household on a device, the member needs a recent passkey sign-in (member_tokens.passkey_at) and the device
sends its secret; the server unwraps in memory for the usual unlock window. Nothing stored here lets the operator open the household
alone: that needs the phrase, or a device secret that lives only on the member's device (localStorage in the console, the Keychain on the phone).
It is weaker than deriving the device secret inside the authenticator (the WebAuthn PRF extension, docs/family-key.md): a device secret
can be copied off a device by malware or a script injected into the page, where a PRF secret never leaves the authenticator. And while a
device is unlocking, the server sees its secret for that request. The phrase is what you need if every device is lost.

Safety: turning it on is two steps. begin() makes the shares and a pending wrapped copy and shows the shares once; confirm() requires
t of them to be given back and to unwrap the very key in use before the master-wrapped copy is dropped, so a family that lost its shares
cannot lock itself out by switching on. disable() goes back, and reshare() replaces the shares (a member leaves) without touching any data.
"""
from __future__ import annotations

import functools
import hmac
import logging
import secrets
import time
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from shamir_mnemonic import combine_mnemonics, generate_mnemonics
from shamir_mnemonic.shamir import MnemonicError
from shamir_mnemonic.share import Share

from familyos import artifacts, audit, crypto
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

MIN_SHARES, MAX_SHARES = 2, 9
_unlocked: dict[uuid.UUID, tuple[bytes, float]] = {}
_checked: dict[uuid.UUID, float] = {}          # when this process last confirmed its copy against the shared store (multi-worker only)
_attempts: dict[tuple[uuid.UUID, uuid.UUID], list[float]] = {}
# Shares given by members tapping their passkeys, until enough have come to open the household: per household, member -> (share, expires). Memory only.
_contributions: dict[uuid.UUID, dict[uuid.UUID, tuple[str, float]]] = {}
CONTRIBUTION_SECONDS = 600
MAX_ATTEMPTS_PER_HOUR = 10
# With several workers a worker trusts its own copy of an unlocked key for this many seconds, then asks the shared store again: a lock (or
# a disable) on another worker reaches this one within seconds, not hours.
LOCAL_TRUST_SECONDS = 5.0


def _shared() -> bool:
    return bool(settings.multi_worker)


def _persists() -> bool:
    """Whether the unlocked key itself also rests in Postgres (wrapped under the master key). Only when several workers need to share one unlock and
    the operator has said that trade-off is acceptable: it lets a database snapshot plus the master key open a household the family holds the key to."""
    return _shared() and bool(settings.family_key_share_unlock)


class HouseholdLocked(artifacts.HouseholdUnavailable):
    """The household's key is held by the family and nobody has unlocked it."""


def _aad(household_id: uuid.UUID) -> bytes:
    return b"family-key|" + household_id.bytes


def _kek(secret: bytes, household_id: uuid.UUID) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"familyos family key v1|" + household_id.bytes).derive(secret)


def phrase_of(secret: bytes) -> str:
    """The family secret as one recovery phrase: a SLIP-39 share with threshold 1, so a single 33-word phrase rebuilds it."""
    return generate_mnemonics(1, [(1, 1)], secret)[0][0]


def new_device_secret() -> bytes:
    return secrets.token_bytes(32)


async def _prf_device(member_id: uuid.UUID, prf: dict) -> tuple[bytes, bytes, bytes]:
    """(device secret, credential id, salt) from a PRF enrolment, checked: the secret and the salt are 32 bytes, and the credential is a live
    passkey of this member, so a device cannot be tied to somebody else's passkey. The secret was derived inside that passkey; the server
    sees it for this request only, to wrap the key, and never stores it."""
    secret, salt, cred = _unb64(prf["secret"]), _unb64(prf["salt"]), _unb64(prf["credential_id"])
    if len(secret) != 32 or len(salt) != 32:
        raise Invalid("a passkey-derived device secret and its salt are 32 bytes each")
    mine = await pool().fetchval("SELECT 1 FROM member_passkeys WHERE member_id = $1 AND credential_id = $2 AND revoked_at IS NULL", member_id, cred)
    if not mine:
        raise Invalid("that passkey is not one of yours")
    return secret, cred, salt


def _device_aad(household_id: uuid.UUID, device_id: uuid.UUID) -> bytes:
    return b"family-key-device|" + household_id.bytes + device_id.bytes


class PasskeyNeeded(NotAllowed):
    """Opening the household on a device needs a passkey sign-in in the last few minutes."""


def split(secret: bytes, threshold: int, count: int) -> list[str]:
    if not MIN_SHARES <= threshold <= count <= MAX_SHARES:
        raise Invalid(f"a family key needs between {MIN_SHARES} and {MAX_SHARES} shares, and the number needed cannot be more than the number made")
    return generate_mnemonics(1, [(threshold, count)], secret)[0]


def combine(shares: list[str]) -> bytes:
    cleaned = [" ".join((s or "").lower().split()) for s in shares if (s or "").strip()]
    if not cleaned:
        raise Invalid("give the shares, one after another")
    try:
        return combine_mnemonics(cleaned)
    except MnemonicError as exc:
        raise Invalid(f"those shares do not fit together: {str(exc).split('.')[0]}") from None


async def _recent_failures(key: tuple[uuid.UUID, uuid.UUID]) -> int:
    if _shared():
        return int(await pool().fetchval(
            "SELECT count(*) FROM family_key_attempts WHERE household_id = $1 AND member_id = $2 AND at > NOW() - INTERVAL '1 hour'", *key))
    now = time.monotonic()
    tries = [t for t in _attempts.get(key, []) if now - t < 3600]
    _attempts[key] = tries
    return len(tries)


async def _note_failure(key: tuple[uuid.UUID, uuid.UUID]) -> None:
    if _shared():
        await pool().execute("DELETE FROM family_key_attempts WHERE at < NOW() - INTERVAL '1 hour'")
        await pool().execute("INSERT INTO family_key_attempts (household_id, member_id) VALUES ($1, $2)", *key)
    else:
        _attempts[key] = [*_attempts.get(key, []), time.monotonic()]


async def _clear_failures(key: tuple[uuid.UUID, uuid.UUID]) -> None:
    _attempts.pop(key, None)
    if _shared():
        await pool().execute("DELETE FROM family_key_attempts WHERE household_id = $1 AND member_id = $2", *key)


def _guarded(fn):
    """Slow down guessing, per member: only refusals count, a success clears the member's count, and one member's wrong tries do not
    lock the others out. The check runs first, so a member past the limit is told to wait before anything is looked at. The count lives in
    process memory with one worker and in Postgres with several, so a guess cannot be spread across workers."""
    @functools.wraps(fn)
    async def wrapper(p: Principal, *args, **kwargs):
        key = (p.household_id, p.member_id)
        if await _recent_failures(key) >= MAX_ATTEMPTS_PER_HOUR:
            raise Invalid("too many tries in the last hour; wait a while")
        try:
            result = await fn(p, *args, **kwargs)
        except Invalid:
            await _note_failure(key)
            raise
        await _clear_failures(key)
        return result
    return wrapper


def _require_guardian(p: Principal) -> None:
    if not p.is_guardian:
        raise NotAllowed("only a guardian changes how the family key works")


def _require_adult(p: Principal) -> None:
    if p.role == "child":
        raise NotAllowed("children do not unlock the household")


async def unlocked_key(household_id: uuid.UUID) -> bytes:
    """The household's data key while the family has it unlocked, else HouseholdLocked. One worker: this process's memory. Several: this
    process's copy for a few seconds, then the shared store, so a lock on any worker is a lock on all of them."""
    now = time.monotonic()
    held = _unlocked.get(household_id)
    if held is not None and held[1] > now and (not _persists() or now - _checked.get(household_id, 0.0) < LOCAL_TRUST_SECONDS):
        return held[0]
    if _persists():
        row = await pool().fetchrow(
            "SELECT wrapped_key, EXTRACT(EPOCH FROM (expires_at - NOW())) AS left_s FROM family_key_unlocks WHERE household_id = $1 AND expires_at > NOW()",
            household_id)
        if row is not None:
            key = crypto.unwrap(household_id, bytes(row["wrapped_key"]))
            _unlocked[household_id] = (key, now + float(row["left_s"]))
            _checked[household_id] = now
            return key
    _unlocked.pop(household_id, None)
    _checked.pop(household_id, None)
    raise HouseholdLocked(str(household_id))


async def _remember(household_id: uuid.UUID, key: bytes) -> float:
    hours = max(1, settings.family_key_unlock_hours)
    until = time.monotonic() + hours * 3600
    _unlocked[household_id] = (key, until)
    _checked[household_id] = time.monotonic()
    if _persists():
        await pool().execute("DELETE FROM family_key_unlocks WHERE expires_at < NOW()")
        await pool().execute(
            "INSERT INTO family_key_unlocks (household_id, wrapped_key, expires_at) VALUES ($1, $2, NOW() + make_interval(hours => $3)) "
            "ON CONFLICT (household_id) DO UPDATE SET wrapped_key = $2, expires_at = NOW() + make_interval(hours => $3)",
            household_id, crypto.wrap_key(household_id, key), hours)
    return until


async def _forget(household_id: uuid.UUID) -> None:
    _unlocked.pop(household_id, None)
    _checked.pop(household_id, None)
    # Whatever the switch says now: a row left by an earlier run with it on must not outlive the lock the family just asked for, or unlock the
    # household again when the switch comes back. Nothing is ever written here with it off; this only removes.
    await pool().execute("DELETE FROM family_key_unlocks WHERE household_id = $1", household_id)


async def status(p: Principal) -> dict:
    row = await pool().fetchrow("SELECT h.key_mode, f.threshold, f.shares, f.pending, f.simple FROM households h LEFT JOIN family_keys f ON f.household_id = h.id WHERE h.id = $1", p.household_id)
    held = None
    if row["key_mode"] == "family":
        try:
            await unlocked_key(p.household_id)
            held = _unlocked.get(p.household_id)
        except HouseholdLocked:
            pass
    open_ = held is not None and held[1] > time.monotonic()
    return {"mode": row["key_mode"], "threshold": row["threshold"], "shares": row["shares"], "pending": bool(row["pending"]) if row["pending"] is not None else False,
            "simple": bool(row["simple"]) if row["simple"] is not None else False,
            "locked": row["key_mode"] == "family" and not open_,
            "unlocked_for_minutes": max(0, int((held[1] - time.monotonic()) / 60)) if open_ else 0,
            "contributed": len(_live_contributions(p.household_id)) if row["key_mode"] == "family" and not open_ else 0}


async def begin(p: Principal, threshold: int, count: int) -> dict:
    """Make the shares and a pending wrapped copy. The shares are returned this once; nothing is switched yet."""
    _require_guardian(p)
    secret = secrets.token_bytes(32)
    shares = split(secret, threshold, count)
    async with pool().acquire() as conn, conn.transaction():
        # Same discipline as simple_begin: the household row first, one setup at a time, and a new setup of either kind replaces the pending
        # one completely (its devices go, and `simple` is reset) so an older confirmation cannot activate the newer setup.
        if await conn.fetchval("SELECT key_mode FROM households WHERE id = $1 FOR UPDATE", p.household_id) != "server":
            raise Invalid("this household already has a family key")
        data_key = await artifacts.household_key(conn, p.household_id)
        wrapped = crypto.seal(_kek(secret, p.household_id), data_key, _aad(p.household_id))
        await conn.execute("DELETE FROM family_key_devices WHERE household_id = $1", p.household_id)
        await conn.execute(
            "INSERT INTO family_keys (household_id, threshold, shares, wrapped_key, pending, created_by, simple) VALUES ($1, $2, $3, $4, TRUE, $5, FALSE) "
            "ON CONFLICT (household_id) DO UPDATE SET threshold = $2, shares = $3, wrapped_key = $4, pending = TRUE, created_by = $5, simple = FALSE, created_at = NOW(), confirmed_at = NULL",
            p.household_id, threshold, count, wrapped, p.member_id)
    await audit.record(p.household_id, "familykey.begun", actor_member_id=p.member_id, detail={"threshold": threshold, "shares": count})
    return {"shares": shares, "threshold": threshold, "count": count,
            "note": f"Shown once. Write each on paper or keep it in a password manager, and give them to {count} different people. Any {threshold} unlock the household. Nothing has changed yet: confirm with {threshold} of them."}


@_guarded
async def confirm(p: Principal, shares: list[str]) -> dict:
    """Switch to the family key, only after t shares have been given back and unwrap the very key in use."""
    _require_guardian(p)
    row = await pool().fetchrow("SELECT wrapped_key, pending FROM family_keys WHERE household_id = $1", p.household_id)
    if row is None or not row["pending"]:
        raise Invalid("there is no family key waiting to be confirmed")
    secret = combine(shares)
    try:
        recovered = crypto.open_sealed(_kek(secret, p.household_id), bytes(row["wrapped_key"]), _aad(p.household_id))
    except Exception:  # noqa: BLE001 - not this household's secret
        raise Invalid("those shares do not open this household's key") from None
    async with pool().acquire() as conn, conn.transaction():
        current = await artifacts.household_key(conn, p.household_id, lock=True)
        if not hmac.compare_digest(current, recovered):
            raise Invalid("those shares do not open this household's key")
        live = await conn.fetchrow("SELECT wrapped_key, pending, simple FROM family_keys WHERE household_id = $1 FOR UPDATE", p.household_id)
        if live is None or not live["pending"] or live["simple"] or bytes(live["wrapped_key"]) != bytes(row["wrapped_key"]):
            raise Invalid("this setup was replaced by a newer one; start again and keep the new shares")
        await conn.execute("UPDATE family_keys SET pending = FALSE, confirmed_at = NOW() WHERE household_id = $1", p.household_id)
        await conn.execute("UPDATE households SET key_mode = 'family', wrapped_key = NULL WHERE id = $1", p.household_id)
    await _remember(p.household_id, recovered)
    await audit.record(p.household_id, "familykey.enabled", actor_member_id=p.member_id)
    return await status(p)


@_guarded
async def unlock(p: Principal, shares: list[str]) -> dict:
    _require_adult(p)
    mode = await pool().fetchval("SELECT key_mode FROM households WHERE id = $1", p.household_id)
    if mode != "family":
        raise Invalid("this household does not use a family key")
    secret = combine(shares)
    wrapped = await pool().fetchval("SELECT wrapped_key FROM family_keys WHERE household_id = $1 AND NOT pending", p.household_id)
    try:
        key = crypto.open_sealed(_kek(secret, p.household_id), bytes(wrapped), _aad(p.household_id))
    except Exception:  # noqa: BLE001
        await audit.record(p.household_id, "familykey.unlock_failed", actor_member_id=p.member_id)
        raise Invalid("those shares do not open this household's key") from None
    await _remember(p.household_id, key)
    await audit.record(p.household_id, "familykey.unlocked", actor_member_id=p.member_id)
    return await status(p)


async def lock(p: Principal) -> dict:
    _require_adult(p)
    await _forget(p.household_id)
    await audit.record(p.household_id, "familykey.locked", actor_member_id=p.member_id)
    return await status(p)


async def disable(p: Principal, shares: list[str]) -> dict:
    """Back to the server's master key. Needs the family's shares: the family decides, not the operator."""
    _require_guardian(p)
    await unlock(p, shares)
    key = await unlocked_key(p.household_id)
    async with pool().acquire() as conn, conn.transaction():
        nonce_wrapped = crypto.wrap_key(p.household_id, key)
        await conn.execute("UPDATE households SET key_mode = 'server', wrapped_key = $2 WHERE id = $1", p.household_id, nonce_wrapped)
        await conn.execute("DELETE FROM family_keys WHERE household_id = $1", p.household_id)
        await conn.execute("DELETE FROM family_key_devices WHERE household_id = $1", p.household_id)
    await _forget(p.household_id)
    await audit.record(p.household_id, "familykey.disabled", actor_member_id=p.member_id)
    return await status(p)


async def reshare(p: Principal, shares: list[str], threshold: int, count: int) -> dict:
    """New shares, old ones useless, no data touched: for when someone leaves or a share is lost."""
    _require_guardian(p)
    if await pool().fetchval("SELECT simple FROM family_keys WHERE household_id = $1", p.household_id):
        raise Invalid("this household uses one recovery phrase; make a new one instead")
    await unlock(p, shares)
    key = await unlocked_key(p.household_id)
    secret = secrets.token_bytes(32)
    new = split(secret, threshold, count)
    wrapped = crypto.seal(_kek(secret, p.household_id), key, _aad(p.household_id))
    done = await pool().execute("UPDATE family_keys SET threshold = $2, shares = $3, wrapped_key = $4, rotated_at = NOW() WHERE household_id = $1 AND NOT pending",
                                p.household_id, threshold, count, wrapped)
    if done.endswith(" 0"):
        raise Invalid("the family key changed while this was being made; nothing was replaced, try again")
    await audit.record(p.household_id, "familykey.reshared", actor_member_id=p.member_id, detail={"threshold": threshold, "shares": count})
    return {"shares": new, "threshold": threshold, "count": count, "note": "Shown once. The old shares no longer open anything."}


# ---------------------------------------------------------------- "Make it private": one recovery phrase and trusted devices

async def simple_begin(p: Principal, label: str = "This device", prf: dict | None = None) -> dict:
    """Make the recovery phrase and this device's secret, keep only wrapped copies, change nothing yet. Both are returned this once.
    With `prf` the device's secret was derived in the member's passkey and is not returned: nothing is stored on the device."""
    _require_guardian(p)
    label = " ".join((label or "").split())[:60] or "This device"
    async with pool().acquire() as conn:
        mode = await conn.fetchval("SELECT key_mode FROM households WHERE id = $1", p.household_id)
        if mode != "server":
            raise Invalid("this household already has a family key")
        data_key = await artifacts.household_key(conn, p.household_id)
    secret, device_id = secrets.token_bytes(32), uuid.uuid4()
    if prf:
        device_secret, cred, salt = await _prf_device(p.member_id, prf)
    else:
        device_secret, cred, salt = new_device_secret(), None, None
    wrapped = crypto.seal(_kek(secret, p.household_id), data_key, _aad(p.household_id))
    device_wrapped = crypto.seal(_kek(device_secret, p.household_id), data_key, _device_aad(p.household_id, device_id))
    async with pool().acquire() as conn, conn.transaction():
        # The household row is locked first, in begin and in done, so two setups cannot interleave: whichever commits second finds the
        # household already switched, or its own device row already replaced, and stops.
        if await conn.fetchval("SELECT key_mode FROM households WHERE id = $1 FOR UPDATE", p.household_id) != "server":
            raise Invalid("this household already has a family key")
        await conn.execute("DELETE FROM family_key_devices WHERE household_id = $1", p.household_id)
        await conn.execute(
            "INSERT INTO family_keys (household_id, threshold, shares, wrapped_key, pending, created_by, simple) VALUES ($1, 1, 1, $2, TRUE, $3, TRUE) "
            "ON CONFLICT (household_id) DO UPDATE SET threshold = 1, shares = 1, wrapped_key = $2, pending = TRUE, created_by = $3, simple = TRUE, created_at = NOW(), confirmed_at = NULL",
            p.household_id, wrapped, p.member_id)
        await conn.execute("INSERT INTO family_key_devices (id, household_id, member_id, label, wrapped_key, pending, prf_salt, credential_id) VALUES ($1, $2, $3, $4, $5, TRUE, $6, $7)",
                           device_id, p.household_id, p.member_id, label, device_wrapped, salt, cred)
    await audit.record(p.household_id, "familykey.simple_begun", actor_member_id=p.member_id, detail={"prf": bool(prf)})
    return {"phrase": phrase_of(secret), "device": {"id": str(device_id), "secret": None if prf else _b64(device_secret), "label": label, "prf": bool(prf)},
            "note": "Shown once. Save the recovery phrase: it is the only way in if every device is lost. Nothing has changed yet."}


@_guarded
async def simple_done(p: Principal, device_id: uuid.UUID, device_secret: str) -> dict:
    """Switch on, once this device has proved it kept its secret. The master-wrapped copy is dropped only now, so a device that failed to
    store its secret cannot lock the family out (the phrase is the user's to keep; the server cannot check that)."""
    _require_guardian(p)
    key = await _open_device(p.household_id, device_id, device_secret, pending=True, member_id=p.member_id)
    async with pool().acquire() as conn, conn.transaction():
        current = await artifacts.household_key(conn, p.household_id, lock=True)
        if not hmac.compare_digest(current, key):
            raise Invalid("this device's secret does not open this household's key")
        # Still the very setup this device verified? Another begin would have replaced the device row (and the phrase the person saved).
        mine = await conn.fetchval("SELECT 1 FROM family_key_devices WHERE id = $1 AND household_id = $2 AND member_id = $3 AND pending AND revoked_at IS NULL FOR UPDATE",
                                   device_id, p.household_id, p.member_id)
        live = await conn.fetchrow("SELECT pending, simple FROM family_keys WHERE household_id = $1 FOR UPDATE", p.household_id)
        if not mine or live is None or not live["pending"] or not live["simple"]:
            raise Invalid("this setup was replaced by a newer one; start again and save the new recovery phrase")
        await conn.execute("UPDATE family_keys SET pending = FALSE, confirmed_at = NOW() WHERE household_id = $1 AND simple", p.household_id)
        await conn.execute("UPDATE family_key_devices SET pending = FALSE WHERE id = $1", device_id)
        await conn.execute("UPDATE households SET key_mode = 'family', wrapped_key = NULL WHERE id = $1", p.household_id)
    await _remember(p.household_id, key)
    await audit.record(p.household_id, "familykey.enabled", actor_member_id=p.member_id, detail={"mode": "simple"})
    return await status(p)


async def _open_device(household_id: uuid.UUID, device_id: uuid.UUID, device_secret: str, *, pending: bool, member_id: uuid.UUID) -> bytes:
    row = await pool().fetchrow("SELECT wrapped_key, member_id FROM family_key_devices WHERE id = $1 AND household_id = $2 AND revoked_at IS NULL AND pending = $3",
                                device_id, household_id, pending)
    bad = Invalid("this device is not set up to open the household")
    if row is None or row["member_id"] != member_id:
        raise bad
    try:
        return crypto.open_sealed(_kek(_unb64(device_secret), household_id), bytes(row["wrapped_key"]), _device_aad(household_id, device_id))
    except Exception:  # noqa: BLE001 - a wrong secret, or a malformed one
        raise bad from None


async def _recent_passkey(p: Principal) -> bool:
    if p.token_id is None:
        return False
    return bool(await pool().fetchval(
        "SELECT passkey_at > NOW() - make_interval(mins => $2) FROM member_tokens WHERE id = $1", p.token_id, settings.family_key_passkey_minutes))


@_guarded
async def unlock_device(p: Principal, device_id: uuid.UUID, device_secret: str) -> dict:
    """The everyday unlock: a passkey sign-in in the last few minutes, and this device's secret. Either alone opens nothing."""
    _require_adult(p)
    mode = await pool().fetchval("SELECT key_mode FROM households WHERE id = $1", p.household_id)
    if mode != "family":
        raise Invalid("this household does not use a family key")
    if not await _recent_passkey(p):
        raise PasskeyNeeded(f"sign in with your passkey, then unlock (a passkey sign-in in the last {settings.family_key_passkey_minutes} minutes is needed)")
    try:
        key = await _open_device(p.household_id, device_id, device_secret, pending=False, member_id=p.member_id)
    except Invalid:
        await audit.record(p.household_id, "familykey.unlock_failed", actor_member_id=p.member_id, detail={"via": "device"})
        raise
    await pool().execute("UPDATE family_key_devices SET last_used_at = NOW() WHERE id = $1", device_id)
    await _remember(p.household_id, key)
    await audit.record(p.household_id, "familykey.unlocked", actor_member_id=p.member_id, detail={"via": "passkey"})
    return await status(p)


async def recover(p: Principal, phrase: str) -> dict:
    """The recovery phrase opens the household when no device or passkey is to hand. Rate limited like any share."""
    return await unlock(p, [phrase])


async def enroll_device(p: Principal, label: str, prf: dict | None = None) -> dict:
    """Another trusted device for this member (a new phone, a second laptop). Needs the household open, so someone has already proved a
    factor; the new device secret is returned once and kept only on that device. With `prf` the secret is derived inside the member's
    passkey every time it is needed and is returned to nobody and stored nowhere."""
    _require_adult(p)
    row = await pool().fetchrow("SELECT h.key_mode, COALESCE(f.simple, FALSE) AS simple FROM households h LEFT JOIN family_keys f ON f.household_id = h.id WHERE h.id = $1", p.household_id)
    if row["key_mode"] != "family" or not row["simple"]:
        raise Invalid("trusted devices belong to the one-tap private mode")
    key = await unlocked_key(p.household_id)
    label = " ".join((label or "").split())[:60] or "A device"
    n = await pool().fetchval("SELECT count(*) FROM family_key_devices WHERE member_id = $1 AND revoked_at IS NULL AND NOT pending", p.member_id)
    if n >= 6:
        raise Invalid("six trusted devices is the most; remove one first")
    if prf:
        secret, cred, salt = await _prf_device(p.member_id, prf)
    else:
        secret, cred, salt = new_device_secret(), None, None
    did = uuid.uuid4()
    wrapped = crypto.seal(_kek(secret, p.household_id), key, _device_aad(p.household_id, did))
    await pool().execute("INSERT INTO family_key_devices (id, household_id, member_id, label, wrapped_key, pending, prf_salt, credential_id) VALUES ($1, $2, $3, $4, $5, FALSE, $6, $7)",
                         did, p.household_id, p.member_id, label, wrapped, salt, cred)
    await audit.record(p.household_id, "familykey.device_added", actor_member_id=p.member_id, detail={"prf": bool(prf)})
    return {"id": str(did), "secret": None if prf else _b64(secret), "label": label, "prf": bool(prf)}


async def devices(p: Principal) -> list[dict]:
    rows = await pool().fetch("SELECT id, label, created_at, last_used_at, prf_salt, credential_id FROM family_key_devices WHERE member_id = $1 AND revoked_at IS NULL AND NOT pending ORDER BY created_at", p.member_id)
    # The salt and the passkey's id are not secret: the browser needs them to ask the passkey for the secret it derives.
    return [{"id": str(r["id"]), "label": r["label"], "created_at": r["created_at"], "last_used_at": r["last_used_at"], "prf": r["prf_salt"] is not None,
             "credential_id": _b64(bytes(r["credential_id"])) if r["credential_id"] else None, "salt": _b64(bytes(r["prf_salt"])) if r["prf_salt"] else None} for r in rows]


async def revoke_device(p: Principal, device_id: uuid.UUID) -> None:
    done = await pool().execute("UPDATE family_key_devices SET revoked_at = NOW() WHERE id = $1 AND member_id = $2 AND revoked_at IS NULL", device_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("device")
    await audit.record(p.household_id, "familykey.device_removed", actor_member_id=p.member_id)


async def new_phrase(p: Principal) -> dict:
    """A fresh recovery phrase while the household is open: the old phrase stops working, devices keep working. For a lost or exposed phrase."""
    _require_guardian(p)
    simple = await pool().fetchval("SELECT simple FROM family_keys WHERE household_id = $1 AND NOT pending", p.household_id)
    if not simple:
        raise Invalid("this household does not use a recovery phrase")
    key = await unlocked_key(p.household_id)
    secret = secrets.token_bytes(32)
    done = await pool().execute("UPDATE family_keys SET wrapped_key = $2, rotated_at = NOW() WHERE household_id = $1 AND NOT pending",
                                p.household_id, crypto.seal(_kek(secret, p.household_id), key, _aad(p.household_id)))
    if done.endswith(" 0"):
        raise Invalid("the family key changed while this was being made; the old phrase still works, try again")
    await audit.record(p.household_id, "familykey.phrase_replaced", actor_member_id=p.member_id)
    return {"phrase": phrase_of(secret), "note": "Shown once. The old recovery phrase no longer opens anything."}


_b64 = crypto.b64u


def _unb64(text: str) -> bytes:
    import base64
    try:
        return base64.urlsafe_b64decode((text or "") + "=" * (-len(text or "") % 4))
    except Exception:  # noqa: BLE001
        raise Invalid("this device's secret is not readable") from None


# ---------------------------------------------------------------- shares kept in passkeys; unlock by tapping t devices

def _live_contributions(household_id: uuid.UUID) -> dict[uuid.UUID, str]:
    now = time.monotonic()
    live = {m: (sh, exp) for m, (sh, exp) in _contributions.get(household_id, {}).items() if exp > now}
    if live:
        _contributions[household_id] = live
    else:
        _contributions.pop(household_id, None)
    return {m: sh for m, (sh, _) in live.items()}


async def _shares_household(p: Principal) -> dict:
    _require_adult(p)
    row = await pool().fetchrow("SELECT h.key_mode, f.threshold, f.shares, COALESCE(f.simple, FALSE) AS simple, COALESCE(f.pending, FALSE) AS pending "
                                "FROM households h LEFT JOIN family_keys f ON f.household_id = h.id WHERE h.id = $1", p.household_id)
    if row["key_mode"] != "family" or row["simple"] or row["pending"]:
        raise Invalid("sealing a share to a passkey belongs to a household that split its key into shares")
    return dict(row)


async def seal_share(p: Principal, credential_id: str, salt: str, wrapped: str) -> dict:
    """Keep the caller's share sealed to their passkey. The browser did the wrapping under a PRF-derived secret and sent only the ciphertext,
    so the server cannot read the share; a passkey of the caller's own is required. A member holds one at a time: a new one replaces the old."""
    await _shares_household(p)
    cred, prf_salt, blob = _unb64(credential_id), _unb64(salt), _unb64(wrapped)
    if len(prf_salt) != 32 or not 40 <= len(blob) <= 1024:
        raise Invalid("that sealed share is not the shape a passkey makes")
    mine = await pool().fetchval("SELECT 1 FROM member_passkeys WHERE member_id = $1 AND credential_id = $2 AND revoked_at IS NULL", p.member_id, cred)
    if not mine:
        raise Invalid("that passkey is not one of yours")
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("UPDATE family_key_share_seals SET revoked_at = NOW() WHERE household_id = $1 AND member_id = $2 AND revoked_at IS NULL", p.household_id, p.member_id)
        await conn.execute("INSERT INTO family_key_share_seals (id, household_id, member_id, credential_id, prf_salt, wrapped_share) VALUES ($1, $2, $3, $4, $5, $6)",
                           uuid.uuid4(), p.household_id, p.member_id, cred, prf_salt, blob)
    await audit.record(p.household_id, "familykey.share_sealed", actor_member_id=p.member_id)
    return await share_seals(p)


async def share_seals(p: Principal) -> dict:
    """Who holds a share sealed to a passkey (names only), and the caller's own sealed share with what is needed to ask the passkey for the secret."""
    info = await _shares_household(p)
    rows = await pool().fetch(
        "SELECT s.member_id, s.created_at, m.display_name FROM family_key_share_seals s JOIN members m ON m.id = s.member_id "
        "WHERE s.household_id = $1 AND s.revoked_at IS NULL ORDER BY s.created_at", p.household_id)
    mine = await pool().fetchrow("SELECT id, credential_id, prf_salt, wrapped_share FROM family_key_share_seals WHERE household_id = $1 AND member_id = $2 AND revoked_at IS NULL",
                                 p.household_id, p.member_id)
    return {"threshold": info["threshold"], "shares": info["shares"],
            "holders": [{"member_id": str(r["member_id"]), "display_name": r["display_name"], "since": r["created_at"]} for r in rows],
            "mine": None if mine is None else {"id": str(mine["id"]), "credential_id": _b64(bytes(mine["credential_id"])), "salt": _b64(bytes(mine["prf_salt"])),
                                               "wrapped": _b64(bytes(mine["wrapped_share"]))}}


async def revoke_share_seal(p: Principal) -> dict:
    await _shares_household(p)
    done = await pool().execute("UPDATE family_key_share_seals SET revoked_at = NOW() WHERE household_id = $1 AND member_id = $2 AND revoked_at IS NULL", p.household_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("sealed share")
    await audit.record(p.household_id, "familykey.share_unsealed", actor_member_id=p.member_id)
    return await share_seals(p)


@_guarded
async def contribute(p: Principal, share: str) -> dict:
    """One member's share, given by tapping their passkey. It waits in this process's memory for `CONTRIBUTION_SECONDS`; when t different
    members' shares are there, the household opens and they are dropped. A recent passkey sign-in is needed, as for a device. One worker only:
    with several, the shares would have to rest in the database, which this does not do."""
    _require_adult(p)
    if _shared():
        raise Invalid("tapping to unlock needs a single worker for now; type the shares instead")
    info = await _shares_household(p)
    if not await _recent_passkey(p):
        raise PasskeyNeeded(f"sign in with your passkey, then give your share (a passkey sign-in in the last {settings.family_key_passkey_minutes} minutes is needed)")
    try:
        parsed = Share.from_mnemonic(" ".join((share or "").lower().split()))
    except MnemonicError as exc:
        await audit.record(p.household_id, "familykey.unlock_failed", actor_member_id=p.member_id, detail={"via": "share"})
        raise Invalid(f"that share is not readable: {str(exc).split('.')[0]}") from None
    held = _live_contributions(p.household_id)
    held[p.member_id] = " ".join(share.lower().split())
    _contributions[p.household_id] = {m: (sh, time.monotonic() + CONTRIBUTION_SECONDS) for m, sh in held.items()}
    needed = max(parsed.member_threshold, info["threshold"] or 0)
    if len(held) < needed:
        await audit.record(p.household_id, "familykey.share_given", actor_member_id=p.member_id)
        return await status(p)
    wrapped = await pool().fetchval("SELECT wrapped_key FROM family_keys WHERE household_id = $1 AND NOT pending", p.household_id)
    _contributions.pop(p.household_id, None)                                  # whatever the outcome, the shares are not kept
    try:
        key = crypto.open_sealed(_kek(combine(list(held.values())), p.household_id), bytes(wrapped), _aad(p.household_id))
    except Exception:  # noqa: BLE001 - shares from different sets, or not this household's
        await audit.record(p.household_id, "familykey.unlock_failed", actor_member_id=p.member_id, detail={"via": "shares"})
        raise Invalid("those shares do not open this household's key") from None
    await _remember(p.household_id, key)
    await audit.record(p.household_id, "familykey.unlocked", actor_member_id=p.member_id, detail={"via": "passkey-sealed shares", "members": len(held)})
    return await status(p)
