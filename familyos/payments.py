"""Paying for the family, only when the family has said so, one approved purchase at a time.

The order of things, and what stops each step:

1. A member asks for a purchase (merchant, amount, why). Refused unless a guardian has switched
   payments on for the household (rules: payments_enabled) and a provider is connected.
2. Refused above the household's largest single purchase, and when the month's approved purchases
   plus this one would pass the household's monthly limit.
3. A guardian approves or declines that one purchase, seeing the merchant and amount. Nothing else
   approves anything: not the requester (unless they are a guardian), not a rule, not a timer.
4. On approval FamilyOS asks the provider for an allowance of exactly that amount and merchant that
   expires soon. The provider, not FamilyOS, holds the card and asks the cardholder to verify.
FamilyOS never sees or stores a card number; only the provider's ids are kept.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import Protocol

import httpx

from familyos import audit, notify, payments_auth
from familyos.db import pool
from familyos.identity import NotAllowed, NotFound, Principal
from familyos.settings import settings

EXPIRES_HOURS = 24            # a request, and the allowance made for it, lapse after a day


class NeedsCardholder(Exception):
    """The provider creates this only in the cardholder's own browser, so the server cannot."""


class ProviderRefused(Exception):
    """The provider said no, in its own words (a validation message, never a card detail)."""


def _said(r: httpx.Response) -> str:
    try:
        return str(r.json().get("message") or r.text)[:300]
    except Exception:  # noqa: BLE001
        return f"HTTP {r.status_code}"


class Provider(Protocol):
    name: str

    async def create_allowance(self, *, member_id: uuid.UUID, payment_method_id: str, amount: decimal.Decimal, currency: str, description: str,
                               merchant_name: str, merchant_url: str | None, merchant_country: str, expires_at: dt.datetime) -> dict: ...

    async def register_card(self, *, member_id: uuid.UUID, payment_method_id: str, email: str | None, country: str) -> None: ...

    async def revoke(self, ref: str, *, member_id: uuid.UUID | None = None) -> None: ...

    async def get_allowance(self, ref: str, *, member_id: uuid.UUID) -> dict: ...


class Crossmint:
    """Crossmint's agent cards: an "order intent" is a bounded, expiring allowance on a card the cardholder saved
    in Crossmint's hosted form. The API is marked unstable by Crossmint (path /api/unstable/).

    Checked against staging on 12 Oct 2026: the order-intents endpoints refuse a server-side key and want the
    client-side key plus the user's JWT. FamilyOS signs that JWT itself (payments_auth), so the server makes the
    allowance as the approving guardian, with the client key. The cardholder's own verification of the allowance
    still happens in the provider's hosted step, in a browser."""
    name = "crossmint"

    def _base(self) -> str:
        return "https://www.crossmint.com" if settings.payments_environment == "production" else "https://staging.crossmint.com"

    async def create_allowance(self, *, member_id, payment_method_id, amount, currency, description, merchant_name, merchant_url, merchant_country, expires_at) -> dict:
        if not settings.payments_client_key or not settings.payments_project_id:
            raise NeedsCardholder("the provider's client key and project id are not both set")
        merchant = {"name": merchant_name, "countryCode": merchant_country}
        if merchant_url:
            merchant["url"] = merchant_url
        body = {"amount": {"currency": currency, "value": f"{amount:.2f}"}, "description": description[:10000],
                "expiresAt": expires_at.astimezone(dt.UTC).isoformat().replace("+00:00", "Z"),
                "paymentMethodId": payment_method_id, "merchant": merchant}
        headers = {"X-API-KEY": settings.payments_client_key, "Authorization": "Bearer " + payments_auth.mint(member_id), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(self._base() + "/api/unstable/order-intents", json=body, headers=headers)
            if r.status_code >= 400:
                raise ProviderRefused(_said(r))
            out = r.json()
        # Only ids and the public verification settings are kept; no card number is in this response.
        return {"ref": out["orderIntentId"], "state": {"order_intent": out}}

    async def register_card(self, *, member_id, payment_method_id, email, country) -> None:
        """A saved card has to be registered for agent use before an allowance can be made on it. Idempotent."""
        headers = {"X-API-KEY": settings.payments_client_key, "Authorization": "Bearer " + payments_auth.mint(member_id), "Content-Type": "application/json"}
        body = {"countryCode": country, "languageCode": f"en-{country}"}
        if email:
            body["email"] = email
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.put(self._base() + f"/api/unstable/payment-methods/{payment_method_id}/order-intent-registration", json=body, headers=headers)
            if r.status_code >= 400:
                raise ProviderRefused(_said(r))

    async def get_allowance(self, ref: str, *, member_id) -> dict:
        headers = {"X-API-KEY": settings.payments_client_key, "Authorization": "Bearer " + payments_auth.mint(member_id)}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self._base() + f"/api/unstable/order-intents/{ref}", headers=headers)
            if r.status_code >= 400:
                raise ProviderRefused(_said(r))
            return r.json()

    async def revoke(self, ref: str, *, member_id=None) -> None:
        if member_id is None:
            return
        headers = {"X-API-KEY": settings.payments_client_key, "Authorization": "Bearer " + payments_auth.mint(member_id)}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(self._base() + f"/api/unstable/order-intents/{ref}", headers=headers)
            if r.status_code >= 400 and r.status_code != 404:
                raise ProviderRefused(_said(r))


_provider: Provider | None = None


def use_provider(provider: Provider | None) -> None:
    global _provider
    _provider = provider


def provider() -> Provider | None:
    if _provider is not None:
        return _provider
    return Crossmint() if settings.payments_provider == "crossmint" and settings.payments_client_key else None


async def _household(household_id) -> dict:
    return dict(await pool().fetchrow(
        "SELECT payments_enabled, payment_limit, payment_month_limit, currency, country FROM households WHERE id = $1", household_id))


async def month_spent(household_id) -> decimal.Decimal:
    start = dt.datetime.now(dt.UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    v = await pool().fetchval(
        "SELECT COALESCE(SUM(amount), 0) FROM purchases WHERE household_id = $1 AND created_at >= $2 "
        "AND status IN ('approved', 'ready', 'completed')", household_id, start)
    return decimal.Decimal(v)


async def request(p: Principal, *, title: str, merchant_name: str, merchant_url: str | None, amount: decimal.Decimal, currency: str,
                  obligation_id: uuid.UUID | None = None, merchant_country: str | None = None) -> dict:
    if p.role == "child":
        raise NotAllowed("children cannot ask for purchases")
    h = await _household(p.household_id)
    if not h["payments_enabled"] or provider() is None:
        raise NotAllowed("payments are off for this household")
    currency = currency.upper()
    if currency != (h["currency"] or "INR").strip().upper():
        raise NotAllowed(f"purchases are in the household's currency, {h['currency']}")
    if amount > h["payment_limit"]:
        raise NotAllowed(f"that is above the largest single purchase, {h['payment_limit']} {currency}")
    mine = await pool().fetchval("SELECT payment_limit FROM members WHERE id = $1", p.member_id)
    if mine is not None and amount > mine:
        raise NotAllowed(f"that is above the most you may ask to buy at once, {mine} {currency}")
    spent = await month_spent(p.household_id)
    if spent + amount > h["payment_month_limit"]:
        raise NotAllowed(f"that would take this month past {h['payment_month_limit']} {currency}")
    expires = dt.datetime.now(dt.UTC) + dt.timedelta(hours=EXPIRES_HOURS)
    async with pool().acquire() as conn, conn.transaction():
        row = dict(await conn.fetchrow(
            "INSERT INTO purchases (id, household_id, requested_by, title, merchant_name, merchant_url, amount, currency, obligation_id, expires_at, merchant_country) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *",
            uuid.uuid4(), p.household_id, p.member_id, title.strip()[:200], merchant_name.strip()[:200], merchant_url, amount, currency, obligation_id, expires,
            (merchant_country or h.get("country") or "IN").strip().upper()[:2]))
        await audit.record(p.household_id, "purchase.requested", actor_member_id=p.member_id, target_type="purchase", target_id=row["id"],
                           detail={"amount": str(amount), "currency": currency, "merchant": merchant_name[:80]}, conn=conn)
    guardians = await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role = 'guardian'", p.household_id)
    for g in guardians:
        if g["id"] != p.member_id:
            await notify.member(g["id"], f"{p.display_name} asks to buy: {title}",
                                f"{p.display_name} asked for {title} at {merchant_name}, {amount} {currency}. Approve or decline this one purchase.",
                                buttons=[[("Approve", f"buy:{row['id']}:y"), ("Decline", f"buy:{row['id']}:n")]])
    return await _view(row)


async def _view(row: dict) -> dict:
    out = dict(row)
    out["amount"] = float(out["amount"])
    if isinstance(out.get("provider_state"), str):
        out["provider_state"] = json.loads(out["provider_state"])
    return out


async def list_for(p: Principal) -> list[dict]:
    await _lapse(p.household_id)
    rows = await pool().fetch(
        "SELECT * FROM purchases WHERE household_id = $1 AND ($3 OR requested_by = $2) ORDER BY created_at DESC LIMIT 100",
        p.household_id, p.member_id, p.role == "guardian")
    return [await _view(dict(r)) for r in rows]


async def _lapse(household_id) -> None:
    await pool().execute("UPDATE purchases SET status = 'expired' WHERE household_id = $1 AND status IN ('requested', 'approved', 'ready') AND expires_at < NOW()", household_id)


async def decide(p: Principal, purchase_id: uuid.UUID, approve: bool) -> dict:
    """A guardian's yes or no to this one purchase."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can approve a purchase")
    await _lapse(p.household_id)
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("SELECT * FROM purchases WHERE id = $1 AND household_id = $2 FOR UPDATE", purchase_id, p.household_id)
        if row is None:
            raise NotFound("purchase")
        if row["status"] != "requested":
            raise NotAllowed(f"this purchase is already {row['status']}")
        h = await _household(p.household_id)
        if approve and (not h["payments_enabled"] or provider() is None):
            raise NotAllowed("payments are off for this household")
        if not approve:
            await conn.execute("UPDATE purchases SET status = 'declined', decided_by = $2, decided_at = NOW() WHERE id = $1", purchase_id, p.member_id)
            await audit.record(p.household_id, "purchase.declined", actor_member_id=p.member_id, target_type="purchase", target_id=purchase_id, detail={}, conn=conn)
        else:
            others = decimal.Decimal(await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM purchases WHERE household_id = $1 AND id <> $2 AND status IN ('approved', 'ready', 'completed') "
                "AND created_at >= date_trunc('month', NOW())", p.household_id, purchase_id))
            if others + row["amount"] > h["payment_month_limit"] or row["amount"] > h["payment_limit"]:
                raise NotAllowed("the household's limits no longer allow this purchase")
            await conn.execute("UPDATE purchases SET status = 'approved', decided_by = $2, decided_at = NOW() WHERE id = $1", purchase_id, p.member_id)
            await audit.record(p.household_id, "purchase.approved", actor_member_id=p.member_id, target_type="purchase", target_id=purchase_id,
                               detail={"amount": str(row["amount"]), "currency": row["currency"], "merchant": row["merchant_name"][:80]}, conn=conn)
    if approve:
        await _make_allowance(purchase_id, p)
    return await _one(purchase_id)


async def _make_allowance(purchase_id: uuid.UUID, approver: Principal) -> None:
    """On the approving guardian's own saved card: the provider ties a card to the user who saved it."""
    row = dict(await pool().fetchrow("SELECT * FROM purchases WHERE id = $1", purchase_id))
    card = await pool().fetchval("SELECT payment_method_id FROM members WHERE id = $1", approver.member_id)
    prov = provider()
    if not card:
        await pool().execute("UPDATE purchases SET note = $2 WHERE id = $1", purchase_id, "Approved. A guardian still has to save a card with the provider before anything can be bought.")
        return
    try:
        made = await prov.create_allowance(member_id=approver.member_id, payment_method_id=card, amount=row["amount"], currency=row["currency"].strip(),
                                           description=row["title"], merchant_name=row["merchant_name"], merchant_url=row["merchant_url"],
                                           merchant_country=(row.get("merchant_country") or "IN").strip(), expires_at=row["expires_at"])
    except NeedsCardholder:
        await pool().execute("UPDATE purchases SET note = $2 WHERE id = $1", purchase_id,
                             "Approved. The provider makes the allowance in the cardholder's own browser, and that screen is not built yet; nothing has been bought.")
        return
    except Exception as exc:  # noqa: BLE001 - said in words, not a stack trace
        said = str(exc) if isinstance(exc, ProviderRefused) else type(exc).__name__
        await pool().execute("UPDATE purchases SET status = 'failed', note = $2 WHERE id = $1", purchase_id, f"The payment provider refused: {said}"[:400])
        return
    await pool().execute("UPDATE purchases SET status = 'ready', provider = $2, provider_ref = $3, provider_state = $4::jsonb, note = $5 WHERE id = $1",
                         purchase_id, prov.name, made["ref"], json.dumps(made.get("state") or {}),
                         "Ready. The cardholder verifies this allowance with the provider before it can be used.")


async def cancel(p: Principal, purchase_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT * FROM purchases WHERE id = $1 AND household_id = $2", purchase_id, p.household_id)
    if row is None or (row["requested_by"] != p.member_id and not p.is_guardian):
        raise NotFound("purchase")
    if row["status"] not in ("requested", "approved", "ready"):
        raise NotAllowed(f"this purchase is already {row['status']}")
    if row["provider_ref"] and provider() is not None:
        try:
            await provider().revoke(row["provider_ref"], member_id=row["decided_by"])
        except Exception:  # noqa: BLE001 - the allowance expires by itself within a day
            pass
    await pool().execute("UPDATE purchases SET status = 'cancelled' WHERE id = $1", purchase_id)
    await audit.record(p.household_id, "purchase.cancelled", actor_member_id=p.member_id, target_type="purchase", target_id=purchase_id, detail={})
    return await _one(purchase_id)


async def _one(purchase_id) -> dict:
    return await _view(dict(await pool().fetchrow("SELECT * FROM purchases WHERE id = $1", purchase_id)))


async def status(p: Principal) -> dict:
    h = await _household(p.household_id)
    prov = provider()
    return {"enabled": bool(h["payments_enabled"]) and prov is not None, "provider": prov.name if prov else None,
            "environment": settings.payments_environment if prov else None, "has_card": bool(await pool().fetchval("SELECT payment_method_id FROM members WHERE id = $1", p.member_id)),
            "payment_limit": h["payment_limit"], "payment_month_limit": h["payment_month_limit"], "currency": (h["currency"] or "INR").strip(), "month_spent": float(await month_spent(p.household_id))}


async def set_payment_method(p: Principal, payment_method_id: str | None) -> dict:
    """The id of the card this guardian saved in the provider's hosted form. The id is not secret and is not a card number."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can choose the card")
    if payment_method_id and provider() is not None:
        h = await _household(p.household_id)
        email = await pool().fetchval("SELECT email FROM members WHERE id = $1", p.member_id)
        try:
            await provider().register_card(member_id=p.member_id, payment_method_id=payment_method_id, email=email, country=(h["country"] or "IN").strip().upper())
        except ProviderRefused as exc:
            raise NotAllowed(f"the provider would not register that card: {exc}") from exc
    await pool().execute("UPDATE members SET payment_method_id = $2 WHERE id = $1", p.member_id, payment_method_id)
    await audit.record(p.household_id, "household.rules_set", actor_member_id=p.member_id, target_type="household", target_id=p.household_id,
                       detail={"set": {"payment_card": payment_method_id is not None}, "was": {}})
    return await status(p)


async def session(p: Principal) -> dict:
    """What the guardian's browser needs to talk to the provider as themselves: a login token (fifteen minutes), the
    provider's client-side key, and the environment. Never the server key and never a card."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can use the provider's screens")
    if provider() is None or not settings.payments_project_id:
        raise NotAllowed("payments are not connected on this deployment")
    return {"jwt": payments_auth.mint(p.member_id), "client_key": settings.payments_client_key, "environment": settings.payments_environment}


async def make_allowance_now(p: Principal, purchase_id: uuid.UUID) -> dict:
    """An approved purchase that was waiting (no card yet, or the provider needed the guardian's screen): try again,
    as the guardian who is asking, on their card."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can do this")
    await _lapse(p.household_id)
    row = await pool().fetchrow("SELECT status FROM purchases WHERE id = $1 AND household_id = $2", purchase_id, p.household_id)
    if row is None:
        raise NotFound("purchase")
    if row["status"] != "approved":
        raise NotAllowed(f"this purchase is {row['status']}, not waiting for an allowance")
    await _make_allowance(purchase_id, p)
    return await _one(purchase_id)


async def refresh(p: Principal, purchase_id: uuid.UUID) -> dict:
    """Ask the provider how the allowance stands now (for instance after the cardholder verified it) and keep its record."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can do this")
    row = await pool().fetchrow("SELECT provider_ref, status FROM purchases WHERE id = $1 AND household_id = $2", purchase_id, p.household_id)
    if row is None:
        raise NotFound("purchase")
    if row["provider_ref"] and row["status"] == "ready" and provider() is not None:
        try:
            current = await provider().get_allowance(row["provider_ref"], member_id=p.member_id)
        except ProviderRefused as exc:
            await pool().execute("UPDATE purchases SET note = $2 WHERE id = $1", purchase_id, f"Could not check with the provider: {exc}"[:400])
        else:
            await pool().execute("UPDATE purchases SET provider_state = $2::jsonb WHERE id = $1", purchase_id, json.dumps({"order_intent": current}))
    return await _one(purchase_id)
