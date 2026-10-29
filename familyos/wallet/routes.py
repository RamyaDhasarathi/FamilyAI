"""The wallet's HTTP surface, all under /v1/wallet (and /v1/sign-in/wallet). Each handler goes through service.gate(), so a household that has not chosen the wallet,
or a deployment that does not offer it, gets 404 from every one of them."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from familyos import ratelimit, session_cookie
from familyos.api.deps import current_member
from familyos.identity import Principal
from familyos.models import Member, SignedIn
from familyos.settings import settings
from familyos.wallet import service

router = APIRouter(prefix="/v1", tags=["wallet"])


class AddressIn(BaseModel):
    address: str = Field(max_length=64)


class SignedMessageIn(BaseModel):
    message: str = Field(max_length=2000)
    signature: str = Field(max_length=300)


class FamilyWalletIn(BaseModel):
    address: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=60)
    per_transfer: str | None = Field(default=None, max_length=40)
    per_day: str | None = Field(default=None, max_length=40)
    per_month: str | None = Field(default=None, max_length=40)


class ProposeIn(BaseModel):
    payee_address: str = Field(max_length=64)
    payee_label: str | None = Field(default=None, max_length=60)
    amount: str = Field(max_length=40)
    memo: str | None = Field(default=None, max_length=140)


class ApproveIn(BaseModel):
    signature: str = Field(max_length=300)


class SubmittedIn(BaseModel):
    tx_hash: str = Field(max_length=80)


class DeleteIn(BaseModel):
    confirm: str = Field(max_length=60)


def _ip(request: Request) -> list:
    return [(f"wallet:ip:{ratelimit.client_ip(request)}", settings.rate_passkey_per_ip)]


@router.post("/sign-in/wallet/message", description="Start a wallet sign-in: the message to sign. The answer never says whether the address is linked.")
async def signin_message(body: AddressIn, request: Request):
    ratelimit.enforce(_ip(request))
    return await service.signin_message(request.headers.get("origin"), body.address)


@router.post("/sign-in/wallet", response_model=SignedIn, description="Finish a wallet sign-in with the signed message and receive a session token. A wallet sign-in does not open the family key.")
async def signin(body: SignedMessageIn, request: Request, response: Response):
    ratelimit.enforce(_ip(request))
    member, token = await service.signin(request.headers.get("origin"), body.message, body.signature)
    if session_cookie.wants_cookie(request):
        session_cookie.set_for(response, request, token)
        token = None
    return SignedIn(member=Member(**member), token=token)


@router.get("/wallet", description="The family wallet card: network, the family wallet with its limits and balance, your linked wallets, recent transfers.")
async def overview(p: Principal = Depends(current_member)):
    return await service.overview(p)


@router.post("/wallet/links/message", description="The message to sign to link a wallet to your account.")
async def link_message(body: AddressIn, request: Request, p: Principal = Depends(current_member)):
    return await service.link_message(p, request.headers.get("origin"), body.address)


@router.post("/wallet/links", status_code=201, description="Link a wallet to your account with the signed message.")
async def link(body: SignedMessageIn, request: Request, p: Principal = Depends(current_member)):
    return await service.link(p, request.headers.get("origin"), body.message, body.signature)


@router.delete("/wallet/links/{link_id}", status_code=204, description="Remove a linked wallet: your own, or any as a guardian.")
async def unlink(link_id: uuid.UUID, p: Principal = Depends(current_member)):
    await service.unlink(p, link_id)


@router.put("/wallet/family-wallet", description="A guardian names the family wallet and sets the limits, in whole tokens.")
async def family_wallet(body: FamilyWalletIn, p: Principal = Depends(current_member)):
    return await service.set_family_wallet(p, body.address, body.label, body.per_transfer, body.per_day, body.per_month)


@router.get("/wallet/transfers", description="Transfers, newest first.")
async def transfers(p: Principal = Depends(current_member)):
    return await service.transfers(p)


@router.post("/wallet/transfers", status_code=201, description="Propose a transfer. Nothing moves: a guardian must approve exactly what is shown.")
async def propose(body: ProposeIn, p: Principal = Depends(current_member)):
    return await service.propose(p, body.payee_address, body.payee_label, body.amount, body.memo)


@router.get("/wallet/transfers/{transfer_id}", description="One transfer, with the text to sign when it waits and the call to send once it is approved.")
async def transfer(transfer_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await service.get(p, transfer_id)


@router.post("/wallet/transfers/{transfer_id}/approve", description="A guardian approves by signing the transfer's text with their linked wallet.")
async def approve(transfer_id: uuid.UUID, body: ApproveIn, p: Principal = Depends(current_member)):
    return await service.approve(p, transfer_id, body.signature)


@router.post("/wallet/transfers/{transfer_id}/reject", description="A guardian, or whoever proposed it, ends a transfer that has not been sent.")
async def reject(transfer_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await service.reject(p, transfer_id)


@router.post("/wallet/transfers/{transfer_id}/submitted", description="A guardian reports the transaction hash after sending it from the family wallet; the network decides whether it settled.")
async def submitted(transfer_id: uuid.UUID, body: SubmittedIn, p: Principal = Depends(current_member)):
    return await service.submitted(p, transfer_id, body.tx_hash)


@router.post("/wallet/transfers/{transfer_id}/check", description="Read the network again for a submitted transfer.")
async def check(transfer_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await service.check(p, transfer_id)


@router.post("/wallet/delete-data", description="A guardian deletes everything the wallet holds for this household. Needs the typed confirmation; works with the household's switch off.")
async def delete_data(body: DeleteIn, p: Principal = Depends(current_member)):
    return await service.delete_data(p, body.confirm)
