"""Sign-In with Ethereum (EIP-4361), built and verified here on top of eth_account's signature recovery.

Read from eips.ethereum.org/EIPS/eip-4361 (23 Oct 2026). We write the message ourselves in one fixed shape and accept only that shape back, so
there is no optional-field grammar to get wrong: the domain line, the address, a statement, URI, Version 1, Chain ID, Nonce, Issued At and
Expiration Time. The signature is EIP-191 personal_sign (eips.ethereum.org/EIPS/eip-191), so the signer is recovered with `recover_message`
and must equal the address the message names. Nothing here signs anything: only recovery.
"""
from __future__ import annotations

import datetime as dt
import re
import secrets
from dataclasses import dataclass

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import is_address, to_checksum_address

from familyos.identity import Invalid

STATEMENTS = {"link": "Link this wallet to your FamilyOS account. No funds move and nothing is sent.",
              "signin": "Sign in to FamilyOS with this wallet. No funds move and nothing is sent."}
LIFETIME_MINUTES = 10
SKEW = dt.timedelta(minutes=1)
_NONCE = re.compile(r"^[A-Za-z0-9]{8,64}$")
_TIME = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
_MESSAGE = re.compile(
    r"^(?P<domain>[^\s/?#]+) wants you to sign in with your Ethereum account:\n(?P<address>0x[0-9a-fA-F]{40})\n\n(?P<statement>[^\n]+)\n\n"
    r"URI: (?P<uri>https?://[^\s]+)\nVersion: 1\nChain ID: (?P<chain>\d+)\nNonce: (?P<nonce>[A-Za-z0-9]+)\n"
    rf"Issued At: (?P<issued>{_TIME})\nExpiration Time: (?P<expires>{_TIME})$")


@dataclass(frozen=True)
class Parsed:
    domain: str
    address: str            # EIP-55 checksummed
    statement: str
    uri: str
    chain_id: int
    nonce: str
    issued_at: dt.datetime
    expires_at: dt.datetime


def new_nonce() -> str:
    return secrets.token_hex(16)


def checksum(address: str) -> str:
    """The EIP-55 form of an address, or Invalid. A mixed-case address whose capitals are wrong is refused, not corrected."""
    text = (address or "").strip()
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", text) or not is_address(text):
        raise Invalid("that is not an Ethereum address")
    good = to_checksum_address(text)
    if text != text.lower() and text != text.upper().replace("0X", "0x") and text != good:
        raise Invalid("that address has a mistyped capital letter")
    return good


def build(*, domain: str, uri: str, address: str, chain_id: int, nonce: str, purpose: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.UTC)
    stamp = lambda t: t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731 - one-line formatter
    return (f"{domain} wants you to sign in with your Ethereum account:\n{checksum(address)}\n\n{STATEMENTS[purpose]}\n\n"
            f"URI: {uri}\nVersion: 1\nChain ID: {chain_id}\nNonce: {nonce}\n"
            f"Issued At: {stamp(now)}\nExpiration Time: {stamp(now + dt.timedelta(minutes=LIFETIME_MINUTES))}")


def _when(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(dt.UTC)


def parse(message: str) -> Parsed:
    m = _MESSAGE.match(message or "")
    if m is None or not _NONCE.match(m["nonce"]):
        raise Invalid("that is not a sign-in message from FamilyOS")
    return Parsed(m["domain"], checksum(m["address"]), m["statement"], m["uri"], int(m["chain"]), m["nonce"], _when(m["issued"]), _when(m["expires"]))


def verify(message: str, signature: str, *, domain: str, uri: str, chain_id: int, purpose: str, now: dt.datetime | None = None) -> Parsed:
    """The message's fields checked against what this deployment expects, then the signer recovered and compared with the address it names.
    The nonce is checked separately (and spent) against the database by the caller."""
    now = now or dt.datetime.now(dt.UTC)
    p = parse(message)
    bad = Invalid("that sign-in did not check out")
    if p.domain != domain or p.uri != uri or p.chain_id != chain_id or p.statement != STATEMENTS[purpose]:
        raise bad
    if p.issued_at > now + SKEW or p.expires_at <= now or p.expires_at - p.issued_at > dt.timedelta(minutes=LIFETIME_MINUTES, seconds=1) or now - p.issued_at > dt.timedelta(minutes=LIFETIME_MINUTES + 1):
        raise bad
    try:
        signer = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:  # noqa: BLE001 - a malformed signature is the same refusal as a wrong one
        raise bad from None
    if signer != p.address:
        raise bad
    return p
