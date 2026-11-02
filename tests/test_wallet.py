"""The optional family wallet: two switches, link and sign in, limits, a guardian's signed approval, the chain read afterwards, keep-or-delete."""
import asyncio
import uuid

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from familyos.identity import Invalid
from familyos.settings import settings
from familyos.wallet import chain, service

ORIGIN = "https://app.test"
H = {"origin": ORIGIN}


@pytest.fixture(autouse=True)
def _wallet_deployed(monkeypatch):
    monkeypatch.setattr(settings, "wallet_enabled", True)
    monkeypatch.setattr(settings, "webauthn_origins", ORIGIN)


async def switch(family, who="amma", on=True):
    r = await family.client.put("/v1/household/rules", headers=family.h(who), json={"wallet_enabled": on})
    assert r.status_code == 200, r.text


def sign(acct, text):
    return Account.sign_message(encode_defunct(text=text), acct.key).signature.hex()


async def link(family, who, acct):
    h = {**family.h(who), **H}
    m = await family.client.post("/v1/wallet/links/message", headers=h, json={"address": acct.address})
    assert m.status_code == 200, m.text
    r = await family.client.post("/v1/wallet/links", headers=h, json={"message": m.json()["message"], "signature": sign(acct, m.json()["message"])})
    assert r.status_code == 201, r.text
    return r.json()


async def test_off_by_default_everything_is_not_found(family):
    for method, path in (("get", "/v1/wallet"), ("get", "/v1/wallet/transfers"), ("post", "/v1/wallet/links/message")):
        r = await getattr(family.client, method)(path, headers={**family.h("amma"), **H}, **({"json": {"address": Account.create().address}} if method == "post" else {}))
        assert r.status_code == 404, (path, r.text)
    # The deployment flag alone is not enough, and the household's switch alone is not either.
    await switch(family)
    assert (await family.client.get("/v1/wallet", headers=family.h("amma"))).status_code == 200
    settings.wallet_enabled = False
    assert (await family.client.get("/v1/wallet", headers=family.h("amma"))).status_code == 404


async def test_a_child_and_a_non_guardian_switch(family):
    await switch(family)
    r = await family.client.put("/v1/household/rules", headers=family.h("paati"), json={"wallet_enabled": False})
    assert r.status_code == 403
    assert (await family.client.get("/v1/wallet", headers=family.h("amma"))).status_code == 200


async def test_link_and_sign_in_with_a_wallet(family):
    await switch(family)
    me = Account.create()
    await link(family, "paati", me)
    m = await family.client.post("/v1/sign-in/wallet/message", headers=H, json={"address": me.address})
    msg = m.json()["message"]
    r = await family.client.post("/v1/sign-in/wallet", headers=H, json={"message": msg, "signature": sign(me, msg)})
    assert r.status_code == 200, r.text
    assert r.json()["member"]["display_name"] == "Paati" and r.json()["token"].startswith("fos_")
    # The nonce is spent: the same signed message again is refused.
    again = await family.client.post("/v1/sign-in/wallet", headers=H, json={"message": msg, "signature": sign(me, msg)})
    assert again.status_code == 422
    # An unlinked address fails the same way, and a wrong signer too.
    stranger = Account.create()
    m2 = (await family.client.post("/v1/sign-in/wallet/message", headers=H, json={"address": stranger.address})).json()["message"]
    assert (await family.client.post("/v1/sign-in/wallet", headers=H, json={"message": m2, "signature": sign(stranger, m2)})).status_code == 422
    m3 = (await family.client.post("/v1/sign-in/wallet/message", headers=H, json={"address": me.address})).json()["message"]
    assert (await family.client.post("/v1/sign-in/wallet", headers=H, json={"message": m3, "signature": sign(stranger, m3)})).status_code == 422
    # A wrong site is refused before anything else.
    assert (await family.client.post("/v1/sign-in/wallet/message", headers={"origin": "https://evil.test"}, json={"address": me.address})).status_code == 422


async def test_a_console_wallet_sign_in_is_a_cookie_and_hands_the_script_no_token(family):
    await switch(family)
    me = Account.create()
    await link(family, "paati", me)
    msg = (await family.client.post("/v1/sign-in/wallet/message", headers=H, json={"address": me.address})).json()["message"]
    r = await family.client.post("/v1/sign-in/wallet", headers={**H, "X-FamilyOS-CSRF": "1"}, json={"message": msg, "signature": sign(me, msg)})
    assert r.status_code == 200 and r.json()["token"] is None and "familyos_session=fos_" in r.headers["set-cookie"]


async def test_sign_in_stops_when_the_household_switches_off(family):
    await switch(family)
    me = Account.create()
    await link(family, "paati", me)
    await switch(family, on=False)
    m = (await family.client.post("/v1/sign-in/wallet/message", headers=H, json={"address": me.address})).json()["message"]
    assert (await family.client.post("/v1/sign-in/wallet", headers=H, json={"message": m, "signature": sign(me, m)})).status_code == 422


async def test_one_live_link_per_address(family):
    await switch(family)
    me = Account.create()
    await link(family, "paati", me)
    h = {**family.h("appa"), **H}
    m = (await family.client.post("/v1/wallet/links/message", headers=h, json={"address": me.address})).json()["message"]
    assert (await family.client.post("/v1/wallet/links", headers=h, json={"message": m, "signature": sign(me, m)})).status_code == 422


async def _ready(family):
    await switch(family)
    amma, appa = Account.create(), Account.create()
    await link(family, "amma", amma)
    await link(family, "appa", appa)
    fam, payee = Account.create(), Account.create()
    r = await family.client.put("/v1/wallet/family-wallet", headers=family.h("amma"), json={"address": fam.address, "label": "Family", "per_transfer": "5", "per_day": "8", "per_month": "20"})
    assert r.status_code == 200, r.text
    return amma, appa, fam, payee


async def _propose(family, who, payee, amount="2"):
    r = await family.client.post("/v1/wallet/transfers", headers=family.h(who), json={"payee_address": payee.address, "payee_label": "School", "amount": amount, "memo": "fees"})
    return r


async def test_limits_and_the_family_wallet_are_guardian_only(family):
    await switch(family)
    r = await family.client.put("/v1/wallet/family-wallet", headers=family.h("paati"), json={"address": Account.create().address})
    assert r.status_code == 403
    amma, appa, fam, payee = await _ready(family)
    assert (await _propose(family, "paati", payee, "6")).status_code == 422          # above one transfer
    assert (await _propose(family, "paati", payee, "0")).status_code == 422
    assert (await _propose(family, "paati", payee, "1.0000001")).status_code == 422  # more decimals than the token has
    assert (await _propose(family, "paati", fam)).status_code == 422                 # to the family wallet itself
    r = await family.client.put("/v1/wallet/family-wallet", headers=family.h("amma"), json={"per_transfer": "9", "per_day": "8"})
    assert r.status_code == 422                                                      # limits must grow


async def test_a_signed_approval_then_the_chain_decides(family, monkeypatch):
    amma, appa, fam, payee = await _ready(family)
    r = await _propose(family, "amma", payee)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "proposed" and t["payee_new"] is True and "send" not in t
    tid = t["id"]
    # The proposer cannot approve their own while another guardian exists; the other guardian must sign with a wallet linked to them.
    rr = await family.client.post(f"/v1/wallet/transfers/{tid}/approve", headers=family.h("amma"), json={"signature": sign(amma, t["approval_text"])})
    assert rr.status_code == 403, rr.text
    assert (await family.client.post(f"/v1/wallet/transfers/{tid}/approve", headers=family.h("appa"), json={"signature": sign(amma, t["approval_text"])})).status_code == 422
    assert (await family.client.post(f"/v1/wallet/transfers/{tid}/approve", headers=family.h("appa"), json={"signature": sign(appa, "something else")})).status_code == 422
    assert (await family.client.post(f"/v1/wallet/transfers/{tid}/approve", headers=family.h("paati"), json={"signature": sign(appa, t["approval_text"])})).status_code == 403
    r = await family.client.post(f"/v1/wallet/transfers/{tid}/approve", headers=family.h("appa"), json={"signature": sign(appa, t["approval_text"])})
    assert r.status_code == 200, r.text
    ok = r.json()
    assert ok["status"] == "approved" and ok["send"]["data"] == chain.transfer_calldata(payee.address, 2_000_000) and ok["send"]["to"].lower() == settings.wallet_token_address.lower()
    # The guardian sends it elsewhere and reports the hash; the chain is read, and a receipt that does not match is a failure.
    tx = "0x" + "ab" * 32
    async def wrong(_h):
        return {"status": "0x1", "logs": []}
    monkeypatch.setattr(chain, "receipt", wrong)
    r = await family.client.post(f"/v1/wallet/transfers/{tid}/submitted", headers=family.h("appa"), json={"tx_hash": tx})
    assert r.status_code == 200 and r.json()["status"] == "failed", r.text


async def test_a_matching_receipt_settles_and_an_unreachable_network_changes_nothing(family, monkeypatch):
    amma, appa, fam, payee = await _ready(family)
    t = (await _propose(family, "amma", payee)).json()
    await family.client.post(f"/v1/wallet/transfers/{t['id']}/approve", headers=family.h("appa"), json={"signature": sign(appa, t["approval_text"])})
    async def down(_h):
        raise chain.ChainUnavailable("no")
    monkeypatch.setattr(chain, "receipt", down)
    r = await family.client.post(f"/v1/wallet/transfers/{t['id']}/submitted", headers=family.h("appa"), json={"tx_hash": "0x" + "cd" * 32})
    assert r.status_code == 200 and r.json()["status"] == "submitted" and r.json()["chain_unavailable"] is True, r.text
    good = {"status": "0x1", "logs": [{"address": settings.wallet_token_address, "topics": [chain.TRANSFER_TOPIC, "0x" + chain._pad(fam.address), "0x" + chain._pad(payee.address)], "data": hex(2_000_000)}]}
    async def up(_h):
        return good
    monkeypatch.setattr(chain, "receipt", up)
    r = await family.client.post(f"/v1/wallet/transfers/{t['id']}/check", headers=family.h("appa"))
    assert r.json()["status"] == "settled"
    # A settled transfer counts against the day's limit, and its payee is no longer new.
    assert (await _propose(family, "amma", payee, "7")).status_code == 422
    assert (await _propose(family, "amma", payee, "4")).json()["payee_new"] is False


async def test_an_expired_proposal_cannot_be_approved_and_changing_the_wallet_voids_open_ones(family):
    amma, appa, fam, payee = await _ready(family)
    t = (await _propose(family, "paati", payee)).json()
    from familyos.db import pool
    await pool().execute("UPDATE wallet_transfers SET expires_at = NOW() - interval '1 minute' WHERE id = $1", uuid.UUID(t["id"]))
    r = await family.client.post(f"/v1/wallet/transfers/{t['id']}/approve", headers=family.h("appa"), json={"signature": sign(appa, t["approval_text"])})
    assert r.status_code == 422
    t2 = (await _propose(family, "paati", payee)).json()
    await family.client.put("/v1/wallet/family-wallet", headers=family.h("amma"), json={"address": Account.create().address})
    assert (await family.client.get(f"/v1/wallet/transfers/{t2['id']}", headers=family.h("amma"))).json()["status"] == "expired"


async def test_switching_off_keeps_the_data_and_a_typed_delete_removes_it(family):
    amma, appa, fam, payee = await _ready(family)
    await _propose(family, "paati", payee)
    await switch(family, on=False)
    assert (await family.client.get("/v1/wallet", headers=family.h("amma"))).status_code == 404
    from familyos.db import pool
    hid = uuid.UUID(family.household["id"])
    assert await pool().fetchval("SELECT count(*) FROM wallet_transfers WHERE household_id = $1", hid) == 1
    assert (await family.client.post("/v1/wallet/delete-data", headers=family.h("paati"), json={"confirm": service.DELETE_PHRASE})).status_code == 403
    assert (await family.client.post("/v1/wallet/delete-data", headers=family.h("amma"), json={"confirm": "yes"})).status_code == 422
    r = await family.client.post("/v1/wallet/delete-data", headers=family.h("amma"), json={"confirm": "Delete wallet data"})
    assert r.status_code == 200 and r.json()["wallet_transfers"] == 1 and r.json()["wallet_links"] == 2
    assert await pool().fetchval("SELECT count(*) FROM wallet_links WHERE household_id = $1", hid) == 0
    assert await pool().fetchval("SELECT count(*) FROM audit_events WHERE household_id = $1 AND action = 'wallet.data_deleted'", hid) == 1


async def test_the_audit_page_words_wallet_rows(family):
    amma, appa, fam, payee = await _ready(family)
    await _propose(family, "paati", payee)
    r = await family.client.get("/v1/audit", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    assert any("proposed a test-token transfer" in e["said"] for e in r.json())


def test_a_mainnet_chain_id_is_refused():
    from pydantic import ValidationError

    from familyos.settings import Settings
    with pytest.raises(ValidationError):
        Settings(wallet_chain_id=8453)


def _receipt_for(fam, payee, units, *, token=None, to=None):
    return {"status": "0x1", "logs": [{"address": token or settings.wallet_token_address, "data": hex(units),
                                       "topics": [chain.TRANSFER_TOPIC, "0x" + chain._pad(fam.address), "0x" + chain._pad(to or payee.address)]}]}


def test_a_transfer_settles_only_for_exactly_the_approved_amount_payee_and_token():
    fam, payee, other = Account.create(), Account.create(), Account.create()
    want = {"token": settings.wallet_token_address, "from_address": fam.address, "to_address": payee.address, "amount": 2_000_000}
    assert chain.settlement(_receipt_for(fam, payee, 2_000_000), **want) == ("settled", None)
    assert chain.settlement(_receipt_for(fam, payee, 50_000_000), **want)[0] == "failed"        # more than was approved is not "as approved"
    assert chain.settlement(_receipt_for(fam, payee, 1_999_999), **want)[0] == "failed"
    assert chain.settlement(_receipt_for(fam, payee, 2_000_000, to=other.address), **want)[0] == "failed"
    assert chain.settlement(_receipt_for(fam, payee, 2_000_000, token="0x" + "11" * 20), **want)[0] == "failed"


async def test_one_transaction_cannot_settle_two_transfers(family, monkeypatch):
    amma, appa, fam, payee = await _ready(family)
    ids = []
    for _ in range(2):                                           # two identical approved transfers: the same payee, the same amount
        t = (await _propose(family, "amma", payee)).json()
        r = await family.client.post(f"/v1/wallet/transfers/{t['id']}/approve", headers=family.h("appa"), json={"signature": sign(appa, t["approval_text"])})
        assert r.status_code == 200, r.text
        ids.append(t["id"])

    async def mined(_h):
        return _receipt_for(fam, payee, 2_000_000)
    monkeypatch.setattr(chain, "receipt", mined)
    tx = {"tx_hash": "0x" + "ef" * 32}
    first = await family.client.post(f"/v1/wallet/transfers/{ids[0]}/submitted", headers=family.h("appa"), json=tx)
    assert first.status_code == 200 and first.json()["status"] == "settled", first.text
    second = await family.client.post(f"/v1/wallet/transfers/{ids[1]}/submitted", headers=family.h("appa"), json=tx)
    assert second.status_code == 422, second.text                   # that transaction is already another transfer's
    assert (await family.client.get(f"/v1/wallet/transfers/{ids[1]}", headers=family.h("appa"))).json()["status"] == "approved"


async def test_two_approvals_at_once_cannot_both_fit_under_the_day_limit(family, monkeypatch):
    amma, appa, fam, payee = await _ready(family)                # up to 5 a transfer, 8 a day
    proposals = [(await _propose(family, "amma", payee, "5")).json() for _ in range(2)]
    check = service._within_limits

    async def slow(*args, **kwargs):                             # each approval has passed its check before the other has committed
        await check(*args, **kwargs)
        await asyncio.sleep(0.3)
    monkeypatch.setattr(service, "_within_limits", slow)
    codes = await asyncio.gather(*[family.client.post(f"/v1/wallet/transfers/{t['id']}/approve", headers=family.h("appa"),
                                                      json={"signature": sign(appa, t["approval_text"])}) for t in proposals])
    assert sorted(r.status_code for r in codes) == [200, 422], [r.text for r in codes]


def test_an_amount_is_exact_however_many_digits_it_has():
    with pytest.raises(Invalid):
        service.to_units("1.0000000000000000000000000001")      # more decimals than the token has, past 28 digits: refused, not rounded to 1
    assert service.to_units("1.000000") == 1_000_000
    assert service.from_units(10 ** 36 + 1) == "1000000000000000000000000000000.000001"
