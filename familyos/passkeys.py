"""Passkeys: signing in with Face ID or the device's unlock instead of an emailed link.

A passkey is a key pair made on the member's device (or in their password manager). FamilyOS keeps only the public half, bound to the address
it was made at, and proves each sign-in with a fresh one-use challenge the device signs. There is no secret on the server to steal, nothing to
phish into a look-alike page, and no email to wait for. The verification is the `webauthn` library's; this module is the storage, the challenges
and the session. Passkeys are discoverable, so the sign-in needs no username: the device offers the family's accounts it holds.

What a passkey is not, here: it does not encrypt anything or hold the household key (docs/family-key.md). It proves who is at the door. The emailed
link and Google stay as ways in, and as the way to add the first passkey.
"""
from __future__ import annotations

import json
import logging
import uuid
from urllib.parse import urlsplit

from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidCBORData, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from familyos import audit, crypto
from familyos.db import pool
from familyos.identity import Invalid, LinkNotUsable, NotAllowed, NotFound, Principal, _issue_token
from familyos.settings import settings

logger = logging.getLogger(__name__)

CHALLENGE_MINUTES = 5
MAX_PER_MEMBER = 10
MAX_OPEN_CHALLENGES = 2000


def _origin(header: str | None) -> tuple[str, str]:
    """(origin, rp_id) for a request, only if the address is one the deployment has named."""
    allowed = [o.strip().rstrip("/") for o in settings.webauthn_origins.split(",") if o.strip()]
    origin = (header or "").strip().rstrip("/")
    if origin not in allowed:
        raise Invalid("passkeys are not set up for this address")
    return origin, urlsplit(origin).hostname or ""


async def _store_challenge(challenge: bytes, purpose: str, rp_id: str, member_id=None) -> None:
    await pool().execute("DELETE FROM webauthn_challenges WHERE expires_at < NOW()")
    if await pool().fetchval("SELECT count(*) FROM webauthn_challenges") >= MAX_OPEN_CHALLENGES:
        raise Invalid("too many sign-ins in progress; try again in a few minutes")
    await pool().execute("INSERT INTO webauthn_challenges (challenge, purpose, member_id, rp_id, expires_at) VALUES ($1, $2, $3, $4, NOW() + make_interval(mins => $5))",
                         challenge, purpose, member_id, rp_id, CHALLENGE_MINUTES)


def _challenge_of(credential: dict) -> bytes:
    try:
        client = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
        return base64url_to_bytes(client["challenge"])
    except Exception:  # noqa: BLE001 - anything malformed is just not a valid response
        raise Invalid("that passkey response was not understood") from None


async def _spend_challenge(challenge: bytes, purpose: str, rp_id: str, member_id=None) -> None:
    row = await pool().fetchrow(
        "DELETE FROM webauthn_challenges WHERE challenge = $1 AND purpose = $2 AND rp_id = $3 AND expires_at > NOW() AND member_id IS NOT DISTINCT FROM $4 RETURNING challenge",
        challenge, purpose, rp_id, member_id)
    if row is None:
        raise Invalid("that passkey request has expired; try again")


async def register_options(p: Principal, origin_header: str | None) -> dict:
    if p.role == "child":
        raise NotAllowed("children do not sign in")
    _, rp_id = _origin(origin_header)
    member = await pool().fetchrow("SELECT id, display_name, email FROM members WHERE id = $1", p.member_id)
    if await pool().fetchval("SELECT count(*) FROM member_passkeys WHERE member_id = $1 AND revoked_at IS NULL", p.member_id) >= MAX_PER_MEMBER:
        raise Invalid(f"up to {MAX_PER_MEMBER} passkeys each; remove one first")
    have = [PublicKeyCredentialDescriptor(id=bytes(r["credential_id"])) for r in await pool().fetch(
        "SELECT credential_id FROM member_passkeys WHERE member_id = $1 AND rp_id = $2 AND revoked_at IS NULL", p.member_id, rp_id)]
    options = generate_registration_options(
        rp_id=rp_id, rp_name=settings.webauthn_rp_name, user_name=member["email"] or member["display_name"], user_id=member["id"].bytes,
        user_display_name=member["display_name"], exclude_credentials=have,
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED))
    await _store_challenge(options.challenge, "register", rp_id, p.member_id)
    return json.loads(options_to_json(options))


async def register_finish(p: Principal, origin_header: str | None, credential: dict, label: str) -> dict:
    origin, rp_id = _origin(origin_header)
    label = " ".join((label or "").split())[:60] or "This device"
    await _spend_challenge(_challenge_of(credential), "register", rp_id, p.member_id)
    try:
        verified = verify_registration_response(credential=credential, expected_challenge=_challenge_of(credential), expected_rp_id=rp_id, expected_origin=origin, require_user_verification=True)
    except (InvalidRegistrationResponse, InvalidCBORData, ValueError, KeyError):
        raise Invalid("that passkey could not be verified") from None
    transports = [t for t in ((credential.get("response") or {}).get("transports") or []) if isinstance(t, str)][:6]
    pid = uuid.uuid4()
    try:
        await pool().execute(
            "INSERT INTO member_passkeys (id, member_id, rp_id, credential_id, public_key, sign_count, transports, label, backed_up) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            pid, p.member_id, rp_id, verified.credential_id, verified.credential_public_key, verified.sign_count, transports, label, bool(verified.credential_backed_up))
    except Exception as exc:  # noqa: BLE001 - the same credential twice
        if "unique" in str(exc).lower():
            raise Invalid("this passkey is already added") from None
        raise
    await audit.record(p.household_id, "passkey.added", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"label": label})
    return {"id": pid, "label": label, "backed_up": bool(verified.credential_backed_up)}


async def list_for(p: Principal) -> list[dict]:
    rows = await pool().fetch("SELECT id, label, rp_id, backed_up, created_at, last_used_at FROM member_passkeys WHERE member_id = $1 AND revoked_at IS NULL ORDER BY created_at", p.member_id)
    return [dict(r) for r in rows]


async def revoke(p: Principal, passkey_id: uuid.UUID) -> None:
    done = await pool().execute("UPDATE member_passkeys SET revoked_at = NOW() WHERE id = $1 AND member_id = $2 AND revoked_at IS NULL", passkey_id, p.member_id)
    if done.endswith(" 0"):
        raise NotFound("passkey")
    await audit.record(p.household_id, "passkey.removed", actor_member_id=p.member_id, target_type="member", target_id=p.member_id)


async def login_options(origin_header: str | None) -> dict:
    _, rp_id = _origin(origin_header)
    options = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED)
    await _store_challenge(options.challenge, "login", rp_id)
    return json.loads(options_to_json(options))


async def login_finish(origin_header: str | None, credential: dict) -> tuple[dict, str]:
    """Verify a sign-in and return (member, session token). Every failure reads the same, so a stranger learns nothing about which passkeys exist."""
    origin, rp_id = _origin(origin_header)
    challenge = _challenge_of(credential)
    await _spend_challenge(challenge, "login", rp_id)
    bad = LinkNotUsable("that passkey could not be verified")
    try:
        cred_id = base64url_to_bytes(credential["id"])
    except Exception:  # noqa: BLE001
        raise bad from None
    row = await pool().fetchrow("SELECT id, member_id, public_key, sign_count FROM member_passkeys WHERE credential_id = $1 AND rp_id = $2 AND revoked_at IS NULL", cred_id, rp_id)
    if row is None:
        raise bad
    try:
        verified = verify_authentication_response(credential=credential, expected_challenge=challenge, expected_rp_id=rp_id, expected_origin=origin,
                                                  credential_public_key=bytes(row["public_key"]), credential_current_sign_count=row["sign_count"], require_user_verification=True)
    except (InvalidAuthenticationResponse, InvalidCBORData, ValueError, KeyError):
        raise bad from None
    async with pool().acquire() as conn, conn.transaction():
        member = await conn.fetchrow(
            "SELECT m.id, m.household_id, m.display_name, m.role, m.email, m.phone, m.date_of_birth, m.created_at FROM members m JOIN households h ON h.id = m.household_id "
            "WHERE m.id = $1 AND m.role <> 'child' AND h.status = 'active'", row["member_id"])
        if member is None:
            raise bad
        await conn.execute("UPDATE member_passkeys SET sign_count = $2, last_used_at = NOW() WHERE id = $1", row["id"], verified.new_sign_count)
        token = await _issue_token(conn, member["id"], via_passkey=True)
        await audit.record(member["household_id"], "member.signed_in", actor_member_id=member["id"], target_type="member", target_id=member["id"], detail={"via": "passkey"}, conn=conn)
    return dict(member), token


b64u = crypto.b64u
