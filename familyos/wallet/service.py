"""The optional family wallet: linking a wallet to a member, signing in with it, the family wallet's limits, and transfers a guardian approves.

FamilyOS never holds a key and never sends anything. A transfer is proposed here, a guardian approves exactly what was shown by signing a fixed message with
their own linked wallet (the signer is recovered, never trusted), the guardian sends it from the family wallet, and the chain is read afterwards to see that it
happened as approved. Test networks only (settings.py refuses anything else).

Two switches stand in front of everything: settings.wallet_enabled (the deployment) and households.wallet_enabled (a guardian, on the rules page). Off, every
call but `delete_data` answers NotFound and nothing is read or written.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlsplit

import asyncpg
from eth_account import Account
from eth_account.messages import encode_defunct

from familyos import audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal, _hash, _issue_token
from familyos.settings import settings
from familyos.wallet import chain, siwe

MAX_LINKS_PER_MEMBER = 5
DELETE_PHRASE = "delete wallet data"
_PRECISION = 120                                     # digits for amount arithmetic: far more than an amount under 10**40 units needs
LIVE = ("approved", "submitted", "settled")           # statuses that count against the limits and make a payee known


# --- the two switches -----------------------------------------------------------------------------------------------------------------

def deployed() -> bool:
    return bool(settings.wallet_enabled)


async def gate(p: Principal) -> None:
    """NotFound unless the deployment offers the wallet and this household has chosen it. A child never sees it."""
    if not deployed() or p.role == "child" or not await pool().fetchval("SELECT wallet_enabled FROM households WHERE id = $1", p.household_id):
        raise NotFound("wallet")


def _guardian(p: Principal) -> None:
    if not p.is_guardian:
        raise NotAllowed("only a guardian can do that")


# --- amounts --------------------------------------------------------------------------------------------------------------------------

def to_units(text) -> int:
    """'2.5' whole tokens to the token's smallest unit. More decimals than the token has, zero, or a negative are refused, not rounded."""
    try:
        d = Decimal(str(text).strip())
    except InvalidOperation:
        raise Invalid("that is not an amount") from None
    with localcontext() as ctx:
        ctx.prec = _PRECISION               # the default 28 digits would round a long fraction away, and the check below would then call it exact
        scaled = d * (Decimal(10) ** settings.wallet_token_decimals)
        if not d.is_finite() or scaled != scaled.to_integral_value() or scaled <= 0 or scaled >= Decimal(10) ** 40:
            raise Invalid(f"an amount above zero with at most {settings.wallet_token_decimals} decimals")
        return int(scaled)


def from_units(units) -> str:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        d = Decimal(int(units)) / (Decimal(10) ** settings.wallet_token_decimals)
        return format(d.quantize(Decimal(1)) if d == d.to_integral_value() else d.normalize(), "f")


# --- Sign-In with Ethereum nonces and messages ----------------------------------------------------------------------------------------

def _site(origin_header: str | None) -> tuple[str, str]:
    """(domain, uri) the message must name: an address the deployment has named for passkeys, which are bound to the same sites."""
    allowed = [o.strip().rstrip("/") for o in settings.webauthn_origins.split(",") if o.strip()]
    origin = (origin_header or "").strip().rstrip("/")
    if origin not in allowed:
        raise Invalid("the wallet is not set up for this address")
    return urlsplit(origin).netloc, origin


async def _message(origin: str | None, address: str, purpose: str, household_id=None, member_id=None) -> dict:
    domain, uri = _site(origin)
    nonce = siwe.new_nonce()
    message = siwe.build(domain=domain, uri=uri, address=address, chain_id=settings.wallet_chain_id, nonce=nonce, purpose=purpose)
    await pool().execute("DELETE FROM wallet_nonces WHERE expires_at < NOW() - interval '1 day'")
    await pool().execute("INSERT INTO wallet_nonces (nonce_hash, purpose, household_id, member_id, expires_at) VALUES ($1, $2, $3, $4, NOW() + make_interval(mins => $5))",
                         _hash(nonce), purpose, household_id, member_id, siwe.LIFETIME_MINUTES)
    return {"message": message, "chain_id": settings.wallet_chain_id, "chain": settings.wallet_chain_name}


async def _spend(conn, nonce: str, purpose: str, member_id=None) -> None:
    if await conn.fetchval("UPDATE wallet_nonces SET used_at = NOW() WHERE nonce_hash = $1 AND purpose = $2 AND used_at IS NULL AND expires_at > NOW() "
                           "AND member_id IS NOT DISTINCT FROM $3 RETURNING nonce_hash", _hash(nonce), purpose, member_id) is None:
        raise Invalid("that sign-in did not check out")


def _verified(origin: str | None, message: str, signature: str, purpose: str) -> siwe.Parsed:
    domain, uri = _site(origin)
    return siwe.verify(message, signature, domain=domain, uri=uri, chain_id=settings.wallet_chain_id, purpose=purpose)


# --- linking a wallet to a member -----------------------------------------------------------------------------------------------------

async def link_message(p: Principal, origin: str | None, address: str) -> dict:
    await gate(p)
    return await _message(origin, siwe.checksum(address), "link", p.household_id, p.member_id)


async def link(p: Principal, origin: str | None, message: str, signature: str) -> dict:
    await gate(p)
    parsed = _verified(origin, message, signature, "link")
    address = parsed.address.lower()
    async with pool().acquire() as conn, conn.transaction():
        await _spend(conn, parsed.nonce, "link", p.member_id)
        if await conn.fetchval("SELECT count(*) FROM wallet_links WHERE member_id = $1 AND revoked_at IS NULL", p.member_id) >= MAX_LINKS_PER_MEMBER:
            raise Invalid(f"at most {MAX_LINKS_PER_MEMBER} wallets per person; remove one first")
        if await conn.fetchval("SELECT 1 FROM wallet_links WHERE address = $1 AND revoked_at IS NULL", address):
            raise Invalid("that wallet is already linked to someone")
        link_id = uuid.uuid4()
        await conn.execute("INSERT INTO wallet_links (id, household_id, member_id, address, chain_id) VALUES ($1, $2, $3, $4, $5)",
                           link_id, p.household_id, p.member_id, address, settings.wallet_chain_id)
        await audit.record(p.household_id, "wallet.linked", actor_member_id=p.member_id, target_type="member", target_id=p.member_id, detail={"link_id": str(link_id)}, conn=conn)
    return {"id": str(link_id), "address": parsed.address}


async def links(p: Principal) -> list[dict]:
    await gate(p)
    rows = await pool().fetch("SELECT id, address, chain_id, linked_at FROM wallet_links WHERE member_id = $1 AND revoked_at IS NULL ORDER BY linked_at", p.member_id)
    return [{"id": str(r["id"]), "address": siwe.checksum(r["address"]), "chain_id": r["chain_id"], "linked_at": r["linked_at"].isoformat()} for r in rows]


async def unlink(p: Principal, link_id: uuid.UUID) -> None:
    """Your own link, or any in the household if you are a guardian."""
    await gate(p)
    row = await pool().fetchrow("SELECT member_id FROM wallet_links WHERE id = $1 AND household_id = $2 AND revoked_at IS NULL", link_id, p.household_id)
    if row is None or (row["member_id"] != p.member_id and not p.is_guardian):
        raise NotFound("wallet link")
    await pool().execute("UPDATE wallet_links SET revoked_at = NOW() WHERE id = $1", link_id)
    await audit.record(p.household_id, "wallet.unlinked", actor_member_id=p.member_id, target_type="member", target_id=row["member_id"], detail={"link_id": str(link_id)})


# --- signing in with a wallet ---------------------------------------------------------------------------------------------------------

async def signin_message(origin: str | None, address: str) -> dict:
    """Anyone may ask; the answer never says whether the address is linked."""
    if not deployed():
        raise NotFound("wallet")
    return await _message(origin, siwe.checksum(address), "signin")


async def signin(origin: str | None, message: str, signature: str) -> tuple[dict, str]:
    """(member, session token). Every failure reads the same. A wallet sign-in is not a passkey sign-in: it does not open the family key."""
    if not deployed():
        raise NotFound("wallet")
    bad = Invalid("that sign-in did not check out")
    parsed = _verified(origin, message, signature, "signin")
    async with pool().acquire() as conn, conn.transaction():
        await _spend(conn, parsed.nonce, "signin")
        member = await conn.fetchrow(
            "SELECT m.id, m.household_id, m.display_name, m.role, m.email, m.phone, m.date_of_birth, m.created_at FROM wallet_links w "
            "JOIN members m ON m.id = w.member_id JOIN households h ON h.id = m.household_id "
            "WHERE w.address = $1 AND w.revoked_at IS NULL AND m.role <> 'child' AND h.status = 'active' AND h.wallet_enabled", parsed.address.lower())
        if member is None:
            raise bad
        token = await _issue_token(conn, member["id"], via_passkey=False)
        await audit.record(member["household_id"], "member.signed_in", actor_member_id=member["id"], target_type="member", target_id=member["id"], detail={"via": "wallet"}, conn=conn)
    return dict(member), token


# --- the family wallet and its limits -------------------------------------------------------------------------------------------------

def _limits_default() -> tuple[int, int, int]:
    unit = 10 ** settings.wallet_token_decimals
    return settings.wallet_default_per_transfer * unit, settings.wallet_default_per_day * unit, settings.wallet_default_per_month * unit


async def _family_row(household_id) -> dict:
    row = await pool().fetchrow("SELECT * FROM household_wallet WHERE household_id = $1", household_id)
    if row is None:
        a, b, c = _limits_default()
        return {"address": None, "label": None, "per_transfer_limit": a, "daily_limit": b, "monthly_limit": c}
    return dict(row)


def _limits_view(r: dict) -> dict:
    return {"per_transfer": from_units(r["per_transfer_limit"]), "per_day": from_units(r["daily_limit"]), "per_month": from_units(r["monthly_limit"])}


async def _expire(household_id) -> None:
    await pool().execute("UPDATE wallet_transfers SET status = 'expired' WHERE household_id = $1 AND status IN ('proposed', 'approved') AND expires_at < NOW()", household_id)


async def set_family_wallet(p: Principal, address: str | None, label: str | None, per_transfer, per_day, per_month) -> dict:
    await gate(p)
    _guardian(p)
    current = await _family_row(p.household_id)
    new_address = siwe.checksum(address).lower() if address else current["address"]
    limits = [to_units(v) if v is not None else current[k] for v, k in ((per_transfer, "per_transfer_limit"), (per_day, "daily_limit"), (per_month, "monthly_limit"))]
    if not limits[0] <= limits[1] <= limits[2]:
        raise Invalid("the limits must grow: one transfer, then a day, then a month")
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO household_wallet (household_id, address, label, set_by, set_at, per_transfer_limit, daily_limit, monthly_limit) VALUES ($1, $2, $3, $4, NOW(), $5, $6, $7) "
            "ON CONFLICT (household_id) DO UPDATE SET address = $2, label = $3, set_by = $4, set_at = NOW(), per_transfer_limit = $5, daily_limit = $6, monthly_limit = $7",
            p.household_id, new_address, (label or current["label"] or None), p.member_id, *limits)
        if new_address != current["address"]:
            # A transfer approved to leave the old wallet no longer says what will happen.
            await conn.execute("UPDATE wallet_transfers SET status = 'expired' WHERE household_id = $1 AND status IN ('proposed', 'approved')", p.household_id)
        await audit.record(p.household_id, "wallet.family_wallet_set", actor_member_id=p.member_id, target_type="household", target_id=p.household_id,
                           detail={"address_changed": new_address != current["address"], "per_transfer": str(limits[0]), "per_day": str(limits[1]), "per_month": str(limits[2])}, conn=conn)
    return await overview(p)


async def overview(p: Principal) -> dict:
    await gate(p)
    await _expire(p.household_id)
    fam = await _family_row(p.household_id)
    balance, unavailable = None, False
    if fam["address"]:
        try:
            b = await chain.balances(fam["address"])
            balance = {"token": from_units(b["token"]), "native": str(b["native"])}
        except chain.ChainUnavailable:
            unavailable = True
    return {"network": {"name": settings.wallet_chain_name, "chain_id": settings.wallet_chain_id, "test_network": True, "token": settings.wallet_token_symbol},
            "family_wallet": {"address": siwe.checksum(fam["address"]) if fam["address"] else None, "label": fam["label"], "limits": _limits_view(fam),
                              "balance": balance, "chain_unavailable": unavailable},
            "my_links": await links(p), "transfers": await transfers(p, limit=20)}


# --- transfers ------------------------------------------------------------------------------------------------------------------------

def _fingerprint(t: dict) -> str:
    body = {k: (str(int(t[k])) if k == "amount" else str(t[k]) if k in ("id", "expires_at") else t[k]) for k in
            ("id", "household_id", "chain_id", "from_address", "payee_address", "token_address", "amount", "memo", "expires_at")}
    body["household_id"] = str(body["household_id"])
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def approval_text(t: dict) -> str:
    """Exactly what the guardian signs. Everything that matters is in it, so a signature cannot be reused for another transfer."""
    return (f"FamilyOS approval\nTransfer {t['id']}\nFingerprint {t['fingerprint']}\nSend {from_units(t['amount'])} {t['token_symbol']} to {siwe.checksum(t['payee_address'])}\n"
            f"From {siwe.checksum(t['from_address'])} on {settings.wallet_chain_name} (chain {t['chain_id']})")


def _view(t: dict) -> dict:
    out = {"id": str(t["id"]), "status": t["status"], "payee_address": siwe.checksum(t["payee_address"]), "payee_label": t["payee_label"], "payee_new": t["payee_new"],
           "from_address": siwe.checksum(t["from_address"]), "amount": from_units(t["amount"]), "token": t["token_symbol"], "memo": t["memo"],
           "chain": settings.wallet_chain_name, "chain_id": t["chain_id"], "fingerprint": t["fingerprint"], "proposed_by": str(t["proposed_by"]) if t["proposed_by"] else None,
           "approved_by": str(t["approved_by"]) if t["approved_by"] else None, "created_at": t["created_at"].isoformat(), "expires_at": t["expires_at"].isoformat(),
           "tx_hash": t["tx_hash"], "failure_reason": t["failure_reason"]}
    if t["status"] == "proposed":
        out["approval_text"] = approval_text(t)
    if t["status"] == "approved":
        out["send"] = {"to": t["token_address"], "data": chain.transfer_calldata(t["payee_address"], int(t["amount"])), "value": "0x0", "chain_id": t["chain_id"]}
    return out


async def transfers(p: Principal, limit: int = 50) -> list[dict]:
    await gate(p)
    await _expire(p.household_id)
    rows = await pool().fetch("SELECT * FROM wallet_transfers WHERE household_id = $1 ORDER BY created_at DESC LIMIT $2", p.household_id, limit)
    return [_view(dict(r)) for r in rows]


async def _spent(conn, household_id, since: dt.timedelta, exclude=None) -> int:
    return int(await conn.fetchval("SELECT COALESCE(sum(amount), 0) FROM wallet_transfers WHERE household_id = $1 AND status = ANY($2::text[]) AND id IS DISTINCT FROM $3 "
                                   "AND COALESCE(approved_at, created_at) > NOW() - $4::interval", household_id, list(LIVE), exclude, since))


async def _within_limits(conn, household_id, amount: int, fam: dict, exclude=None) -> None:
    if amount > fam["per_transfer_limit"]:
        raise Invalid(f"above the largest single transfer ({from_units(fam['per_transfer_limit'])} {settings.wallet_token_symbol})")
    if await _spent(conn, household_id, dt.timedelta(days=1), exclude) + amount > fam["daily_limit"]:
        raise Invalid(f"that would pass the day's limit ({from_units(fam['daily_limit'])} {settings.wallet_token_symbol})")
    if await _spent(conn, household_id, dt.timedelta(days=30), exclude) + amount > fam["monthly_limit"]:
        raise Invalid(f"that would pass the month's limit ({from_units(fam['monthly_limit'])} {settings.wallet_token_symbol})")


async def propose(p: Principal, payee_address: str, payee_label: str | None, amount, memo: str | None) -> dict:
    await gate(p)
    fam = await _family_row(p.household_id)
    if not fam["address"]:
        raise Invalid("a guardian has not named the family wallet yet")
    payee = siwe.checksum(payee_address).lower()
    if payee == fam["address"]:
        raise Invalid("the payee is the family wallet itself")
    units = to_units(amount)
    async with pool().acquire() as conn, conn.transaction():
        await _within_limits(conn, p.household_id, units, fam)
        known = await conn.fetchval("SELECT 1 FROM wallet_transfers WHERE household_id = $1 AND payee_address = $2 AND status = ANY($3::text[]) LIMIT 1", p.household_id, payee, list(LIVE))
        t = {"id": uuid.uuid4(), "household_id": p.household_id, "chain_id": settings.wallet_chain_id, "from_address": fam["address"], "payee_address": payee,
             "token_address": settings.wallet_token_address.lower(), "amount": units, "memo": (memo or "").strip() or None,
             "expires_at": dt.datetime.now(dt.UTC) + dt.timedelta(hours=settings.wallet_approval_hours)}
        t["fingerprint"] = _fingerprint(t)
        await conn.execute(
            "INSERT INTO wallet_transfers (id, household_id, proposed_by, chain_id, from_address, payee_address, payee_label, payee_new, token_address, token_symbol, decimals, amount, memo, fingerprint, expires_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
            t["id"], p.household_id, p.member_id, t["chain_id"], t["from_address"], payee, (payee_label or "").strip()[:60] or None, not known, t["token_address"],
            settings.wallet_token_symbol, settings.wallet_token_decimals, units, t["memo"], t["fingerprint"], t["expires_at"])
        await audit.record(p.household_id, "wallet.transfer_proposed", actor_member_id=p.member_id, target_type="wallet_transfer", target_id=t["id"],
                           detail={"amount": str(units), "payee_new": not known, "fingerprint": t["fingerprint"]}, conn=conn)
    return await get(p, t["id"])


async def _load(conn, p: Principal, transfer_id, *, lock: bool = False) -> dict:
    row = await conn.fetchrow("SELECT * FROM wallet_transfers WHERE id = $1 AND household_id = $2" + (" FOR UPDATE" if lock else ""), transfer_id, p.household_id)
    if row is None:
        raise NotFound("transfer")
    return dict(row)


async def get(p: Principal, transfer_id: uuid.UUID) -> dict:
    await gate(p)
    await _expire(p.household_id)
    async with pool().acquire() as conn:
        return _view(await _load(conn, p, transfer_id))


async def approve(p: Principal, transfer_id: uuid.UUID, signature: str) -> dict:
    await gate(p)
    _guardian(p)
    await _expire(p.household_id)
    async with pool().acquire() as conn, conn.transaction():
        # One approval at a time per household: the limits are sums over the other approved transfers, so two approvals that each see room must not both commit.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))", f"wallet-approve:{p.household_id}")
        fam = await _family_row(p.household_id)
        t = await _load(conn, p, transfer_id, lock=True)
        if t["status"] != "proposed":
            raise Invalid(f"this transfer is {t['status']}, not waiting for approval")
        if t["fingerprint"] != _fingerprint(t) or t["from_address"] != fam["address"]:
            raise Invalid("the family wallet changed since this was proposed; propose it again")
        if t["proposed_by"] == p.member_id and await conn.fetchval("SELECT count(*) FROM members WHERE household_id = $1 AND role = 'guardian'", p.household_id) > 1:
            raise NotAllowed("another guardian approves what you proposed")
        try:
            signer = Account.recover_message(encode_defunct(text=approval_text(t)), signature=signature).lower()
        except Exception:  # noqa: BLE001 - a malformed signature is the same refusal as a wrong one
            raise Invalid("that signature does not match this transfer") from None
        if await conn.fetchval("SELECT 1 FROM wallet_links WHERE member_id = $1 AND address = $2 AND revoked_at IS NULL", p.member_id, signer) is None:
            raise Invalid("that signature does not match this transfer, or the wallet is not linked to you")
        await _within_limits(conn, p.household_id, int(t["amount"]), fam, exclude=t["id"])
        await conn.execute("UPDATE wallet_transfers SET status = 'approved', approved_by = $2, approval_signature = $3, approved_at = NOW() WHERE id = $1", t["id"], p.member_id, signature)
        await audit.record(p.household_id, "wallet.transfer_approved", actor_member_id=p.member_id, target_type="wallet_transfer", target_id=t["id"],
                           detail={"amount": str(t["amount"]), "fingerprint": t["fingerprint"]}, conn=conn)
    return await get(p, transfer_id)


async def reject(p: Principal, transfer_id: uuid.UUID) -> dict:
    """A guardian, or the person who proposed it, ends a transfer that has not been sent."""
    await gate(p)
    async with pool().acquire() as conn, conn.transaction():
        t = await _load(conn, p, transfer_id, lock=True)
        if t["proposed_by"] != p.member_id and not p.is_guardian:
            raise NotFound("transfer")
        if t["status"] not in ("proposed", "approved"):
            raise Invalid(f"this transfer is already {t['status']}")
        await conn.execute("UPDATE wallet_transfers SET status = 'rejected' WHERE id = $1", t["id"])
        await audit.record(p.household_id, "wallet.transfer_rejected", actor_member_id=p.member_id, target_type="wallet_transfer", target_id=t["id"], detail={}, conn=conn)
    return await get(p, transfer_id)


async def submitted(p: Principal, transfer_id: uuid.UUID, tx_hash: str) -> dict:
    """The guardian sent it from the family wallet and tells us the transaction hash; the chain, not this claim, decides whether it settled."""
    await gate(p)
    _guardian(p)
    await _expire(p.household_id)
    tx = (tx_hash or "").strip().lower()
    if len(tx) != 66 or not tx.startswith("0x") or any(c not in "0123456789abcdef" for c in tx[2:]):
        raise Invalid("that is not a transaction hash")
    async with pool().acquire() as conn, conn.transaction():
        t = await _load(conn, p, transfer_id, lock=True)
        if t["status"] != "approved":
            raise Invalid(f"this transfer is {t['status']}, not approved")
        try:
            await conn.execute("UPDATE wallet_transfers SET status = 'submitted', tx_hash = $2 WHERE id = $1", t["id"], tx)
        except asyncpg.UniqueViolationError:
            raise Invalid("that transaction is already recorded for another transfer") from None
        await audit.record(p.household_id, "wallet.transfer_submitted", actor_member_id=p.member_id, target_type="wallet_transfer", target_id=t["id"], detail={"tx_hash": tx}, conn=conn)
    return await check(p, transfer_id)


async def check(p: Principal, transfer_id: uuid.UUID) -> dict:
    """Read the chain for a submitted transfer: settled only if the token contract logged exactly the approved transfer. A network that does not answer changes nothing."""
    await gate(p)
    async with pool().acquire() as conn:
        t = await _load(conn, p, transfer_id)
    if t["status"] == "submitted":
        try:
            state, reason = chain.settlement(await chain.receipt(t["tx_hash"]), token=t["token_address"], from_address=t["from_address"], to_address=t["payee_address"], amount=int(t["amount"]))
        except chain.ChainUnavailable:
            return {**_view(t), "chain_unavailable": True}
        if state != "pending":
            await pool().execute("UPDATE wallet_transfers SET status = $2, settled_at = CASE WHEN $2 = 'settled' THEN NOW() END, failure_reason = $3 WHERE id = $1 AND status = 'submitted'",
                                 t["id"], state, reason)
            await audit.record(p.household_id, f"wallet.transfer_{state}", actor_kind="system", target_type="wallet_transfer", target_id=t["id"], detail={"tx_hash": t["tx_hash"]})
    return await get(p, transfer_id)


# --- leaving ----------------------------------------------------------------------------------------------------------------------------

async def delete_data(p: Principal, confirm: str) -> dict:
    """A guardian erases everything the wallet module holds for this household. Works with the household's switch off (that is when you would), not with
    the deployment's. Erasing the whole household removes the same rows by cascade."""
    if not deployed():
        raise NotFound("wallet")
    _guardian(p)
    if (confirm or "").strip().lower() != DELETE_PHRASE:
        raise Invalid(f"type “{DELETE_PHRASE}” to confirm")
    async with pool().acquire() as conn, conn.transaction():
        counts = {}
        for table in ("wallet_transfers", "wallet_links", "wallet_nonces", "household_wallet"):
            counts[table] = int(str(await conn.execute(f"DELETE FROM {table} WHERE household_id = $1", p.household_id)).split()[-1])
        await audit.record(p.household_id, "wallet.data_deleted", actor_member_id=p.member_id, target_type="household", target_id=p.household_id, detail=counts, conn=conn)
    return counts


def say(action: str, who: str, d: dict, names: dict) -> str | None:
    """How the audit page words this module's rows."""
    verb = action.partition(".")[2]
    return {"linked": f"{who} linked a wallet to their account",
            "unlinked": f"{who} removed a linked wallet",
            "family_wallet_set": f"{who} set the family wallet and its limits",
            "transfer_proposed": f"{who} proposed a test-token transfer" + (" to a new payee" if d.get("payee_new") else ""),
            "transfer_approved": f"{who} approved a test-token transfer",
            "transfer_rejected": f"{who} turned down a test-token transfer",
            "transfer_submitted": f"{who} sent an approved transfer from the family wallet",
            "transfer_settled": "The network confirmed a transfer exactly as approved",
            "transfer_failed": "The network did not show a transfer as approved",
            "data_deleted": f"{who} deleted all the family wallet's data"}.get(verb)
