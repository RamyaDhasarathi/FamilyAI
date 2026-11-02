"""Reading a test network over JSON-RPC, and building (never signing) the calls a guardian's wallet will send.

Only reads: eth_getBalance, eth_call (ERC-20 balanceOf), eth_getTransactionReceipt. ERC-20 per eips.ethereum.org/EIPS/eip-20 (read 23 Oct 2026):
`transfer(address,uint256)`, `balanceOf(address)`, and the event `Transfer(address indexed from, address indexed to, uint256 value)`. The network, the chain id
and the USDC test token come from settings; the chain-id check at config load is what keeps this on test networks.
"""
from __future__ import annotations

import time

import httpx
from eth_utils import keccak

from familyos.settings import settings

TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
SELECTOR_TRANSFER = "a9059cbb"        # keccak("transfer(address,uint256)")[:4]
SELECTOR_BALANCE_OF = "70a08231"      # keccak("balanceOf(address)")[:4]
TIMEOUT = 5.0
CACHE_SECONDS = 20.0
_cache: dict[tuple, tuple[float, object]] = {}


class ChainUnavailable(Exception):
    """The test network did not answer (or answered nonsense). Never a reason to call a transfer failed: the caller says so and tries later."""


def _pad(address: str) -> str:
    return address.lower().removeprefix("0x").rjust(64, "0")


def transfer_calldata(to: str, amount: int) -> str:
    """What the guardian's wallet sends to the token contract: transfer(to, amount). Built here so the console shows exactly the approved numbers."""
    return "0x" + SELECTOR_TRANSFER + _pad(to) + format(amount, "064x")


async def rpc(method: str, params: list, *, transport: httpx.AsyncBaseTransport | None = None) -> object:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport, follow_redirects=False) as http:
            r = await http.post(settings.wallet_rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        body = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ChainUnavailable(str(exc) or exc.__class__.__name__) from None
    if r.status_code != 200 or "error" in body:
        raise ChainUnavailable(str((body.get("error") or {}).get("message") or r.status_code))
    return body.get("result")


async def balances(address: str, *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Native balance and the test token's balance of one address, as integers in their smallest units, cached for a few seconds."""
    key = (settings.wallet_rpc_url, address.lower())
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    native = await rpc("eth_getBalance", [address, "latest"], transport=transport)
    token = await rpc("eth_call", [{"to": settings.wallet_token_address, "data": "0x" + SELECTOR_BALANCE_OF + _pad(address)}, "latest"], transport=transport)
    try:
        out = {"native": int(native, 16), "token": int(token, 16)}
    except (TypeError, ValueError):
        raise ChainUnavailable("the network's answer was not a number") from None
    _cache[key] = (time.monotonic(), out)
    return out


def settlement(receipt: dict | None, *, token: str, from_address: str, to_address: str, amount: int) -> tuple[str, str | None]:
    """What a receipt says about an approved transfer: ('pending', None) when it is not mined yet, ('settled', None) when the token contract logged a Transfer
    from the family wallet to exactly this payee for exactly the approved amount, else ('failed', plain reason). More is not "as approved" either."""
    if receipt is None:
        return "pending", None
    if receipt.get("status") != "0x1":
        return "failed", "the transaction did not succeed on the network"
    want_from, want_to = "0x" + _pad(from_address), "0x" + _pad(to_address)
    for log in receipt.get("logs") or []:
        topics = [t.lower() for t in log.get("topics") or []]
        if (log.get("address") or "").lower() == token.lower() and len(topics) == 3 and topics[0] == TRANSFER_TOPIC and topics[1] == want_from and topics[2] == want_to:
            try:
                if int(log.get("data") or "0x0", 16) == amount:
                    return "settled", None
            except ValueError:
                continue
    return "failed", "the network shows no transfer of that token, from the family wallet, to that payee, for the approved amount"


async def receipt(tx_hash: str, *, transport: httpx.AsyncBaseTransport | None = None) -> dict | None:
    out = await rpc("eth_getTransactionReceipt", [tx_hash], transport=transport)
    if out is not None and not isinstance(out, dict):
        raise ChainUnavailable("the network's answer was not a receipt")
    return out
