"""An errand: a booking or a purchase on a site with no API, done in the
member's own signed-in session, after a guardian approved exactly this.

The shape is the purchase-task schema the household wrote down: what, the
requirements, where it may be done, the address by reference, the most it
may cost and how it is paid, and the rules that stop the run. Two things
are different from that schema on purpose. There is no vault reference for
a card, because FamilyOS holds no card: payment is pay-after-service, whose
invoice arrives in the Inbox with its own pay link, or a UPI request the
person approves on their own phone. And the approval is bound to a
fingerprint of the spec, as an action's is, so what runs is what was read.

The run itself is a runbook per site (errands.runbooks), driven in a fresh
browser holding the sealed session for the length of the run. Every step is
written on the errand; a stop rule halts it and says why; "needs you" hands
it back with the browser's live view for the person to finish.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import uuid

from familyos import audit, jobs
from familyos.db import pool
from familyos.execution import sites
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)

KINDS = ("booking", "purchase", "look")
PAYMENT_MODES = ("pay_after_service", "upi_request")
# What stops a run, and what it does then. Fixed, not per errand: a family
# does not get to turn "an unexpected payment prompt" into "carry on".
STOP_RULES = {
    "unexpected_payment_prompt": "stop",
    "new_payment_method_request": "stop",
    "identity_verification_request": "stop",
    "different_delivery_address": "stop",
    "price_above_limit": "stop",
    "unexpected_account_change_request": "stop",
    "alternative_service": "needs_you",
    "slot_unavailable": "needs_you",
}
KIND_LABEL = {"booking": "a booking", "purchase": "a purchase", "look": "a look"}


def fingerprint(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clean_app_spec(raw: dict, *, app: dict) -> dict:
    """The spec of a look at an app on the phone: what to read, and which
    app. Nothing is bought, so there is no limit and no payment."""
    what = " ".join(str(raw.get("what") or "").split())[:200]
    if not what:
        raise Invalid("say what to read in the app")
    # A school's app is often the platform's app in the school's own
    # wrapper, under the school's own bundle id ("Aachi global school" is
    # com.mcb.aachiGlobal, not MyClassBoard's generic id). The family may
    # say which; it has to look like a bundle id.
    bundle = str(raw.get("bundle") or app["bundle"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+", bundle) or len(bundle) > 160:
        raise Invalid("bundle is an app's bundle id, like com.example.app")
    return {
        "what": what,
        "details": " ".join(str(raw.get("details") or "").split())[:600] or None,
        "when": {"date": None, "time": None, "part": "any", "by": None},
        "where": {"service": app["service"], "bundle": bundle, "label": app["label"], "on": "the phone"},
        "limits": {"max_amount": 0, "currency": "INR", "quantity": 0},
        "payment": {"mode": "none", "max_amount": 0, "currency": "INR", "card_held_by_familyos": False},
        "stop_rules": ["read only: a tap or two to reach the notices, nothing typed, nothing bought"],
    }


def clean_spec(raw: dict, *, service: str) -> dict:
    """The spec as kept: every field checked, nothing unknown carried."""
    site = sites.get(service)
    what = " ".join(str(raw.get("what") or "").split())[:200]
    if not what:
        raise Invalid("say what the errand is for")
    limit = raw.get("max_amount")
    try:
        limit = float(limit)
    except (TypeError, ValueError):
        raise Invalid("say the most this may cost") from None
    if not 0 < limit <= 500_000:
        raise Invalid("the most this may cost has to be a number above zero")
    currency = str(raw.get("currency") or "INR").upper()[:3]
    payment = str(raw.get("payment") or "pay_after_service")
    if payment not in PAYMENT_MODES:
        raise Invalid("payment is pay_after_service or upi_request")
    when = raw.get("when") or {}
    if not isinstance(when, dict):
        raise Invalid("when is a date and a part of the day")
    on = when.get("date")
    if on:
        try:
            dt.date.fromisoformat(str(on))
        except ValueError:
            raise Invalid("when.date is an ISO date") from None
    at = when.get("time")
    if at:
        try:
            at = dt.time.fromisoformat(str(at)[:5]).strftime("%H:%M")
        except ValueError:
            raise Invalid("when.time is HH:MM") from None
    part = str(when.get("part") or "any")
    if at and part == "any":
        hour = int(at[:2])
        part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    if part not in ("morning", "afternoon", "evening", "any"):
        raise Invalid("when.part is morning, afternoon, evening or any")
    return {
        "what": what,
        "details": " ".join(str(raw.get("details") or "").split())[:600] or None,
        "when": {"date": str(on) if on else None, "time": at or None, "part": part,
                 "by": str(when.get("by"))[:10] if when.get("by") else None},
        "where": {"service": site["service"], "hosts": site["hosts"], "address": "the saved home address"},
        "limits": {"max_amount": limit, "currency": currency, "quantity": 1},
        "payment": {"mode": payment, "max_amount": limit, "currency": currency,
                    "card_held_by_familyos": False},
        "stop_rules": STOP_RULES,
    }


async def propose(p: Principal, *, service: str, kind: str, title: str, spec: dict) -> dict:
    """Write the errand down in full, and fingerprint it. Nothing runs."""
    if kind not in KINDS:
        raise Invalid("kind is booking or purchase")
    from familyos.execution import apps
    app = apps.get(service)
    if app is None:
        try:
            sites.get(service)
        except KeyError:
            raise Invalid("that site is not one FamilyOS can act on") from None
    title = " ".join((title or "").split())[:160]
    if not title:
        raise Invalid("give the errand a title")
    if app:
        # An app on the phone: a look only, read through the phone's own
        # hands (ios/Driver) on the phone that is signed in to it. No sealed
        # session: the sign-in lives in the app, on the phone, and stays there.
        if kind != "look":
            raise Invalid("an app on the phone can only be looked at, never bought from")
        kept = clean_app_spec(spec, app=app)
    else:
        kept = clean_spec(spec, service=service)
        signed_in = await pool().fetchval(
            "SELECT 1 FROM sealed_sessions WHERE household_id = $1 AND service = $2 AND revoked_at IS NULL AND expires_at > NOW()",
            p.household_id, kept["where"]["service"])
        if not signed_in:
            raise Invalid(f"nobody is signed in to {sites.get(service)['label']}; sign in on the Household page first")
    digest = fingerprint(kept)
    errand_id = uuid.uuid4()
    # A look buys nothing, so it needs no guardian: it runs as soon as it is
    # asked, in the asker's own session, and reports what it saw.
    look = kind == "look"
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "INSERT INTO errands (id, household_id, created_by, service, kind, title, spec, params_sha256, status, approved_by, approved_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CASE WHEN $9 = 'approved' THEN NOW() END) RETURNING *",
            errand_id, p.household_id, p.member_id, kept["where"]["service"], kind, title, kept, digest,
            "approved" if look else "proposed", p.member_id if look else None)
        await audit.record(p.household_id, "errand.proposed", actor_member_id=p.member_id, target_type="errand",
                           target_id=errand_id, detail={"service": kept["where"]["service"], "kind": kind,
                                                        "max_amount": kept["limits"]["max_amount"],
                                                        "currency": kept["limits"]["currency"], "payment": kept["payment"]["mode"]},
                           conn=conn)
        if app:
            # Runs only on the phone that holds the app, when its driver connects.
            row = await conn.fetchrow("UPDATE errands SET outcome = COALESCE(outcome, '{}'::jsonb) || '{\"run_on\": \"phone\"}'::jsonb WHERE id = $1 RETURNING *", errand_id)
        elif look and can_run(kept["where"]["service"], "look"):
            await jobs.create(KIND, {"errand_id": str(errand_id)}, household_id=p.household_id, member_id=p.member_id, conn=conn)
    return dict(row)


async def approve(p: Principal, errand_id: uuid.UUID, params_sha256: str, run_on: str | None = None) -> dict:
    """A guardian approves exactly what was shown. The run is queued, when a
    runbook for the site exists; otherwise it waits, approved, and says so."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can approve an errand")
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("SELECT * FROM errands WHERE id = $1 AND household_id = $2 FOR UPDATE", errand_id, p.household_id)
        if row is None:
            raise NotFound("errand")
        if row["status"] != "proposed":
            raise Invalid(f"this errand is {row['status']}, not waiting to be approved")
        current = fingerprint(row["spec"])
        if current != row["params_sha256"]:
            raise Invalid("this errand has changed since it was proposed, so no approval applies to it. Look at it again.")
        if (params_sha256 or "").lower() != current:
            raise Invalid("this is not what you were shown — look at it again.")
        done = await conn.fetchrow(
            "UPDATE errands SET status = 'approved', approved_by = $2, approved_at = NOW(), updated_at = NOW() "
            "WHERE id = $1 RETURNING *", errand_id, p.member_id)
        if run_on == "phone":
            # Not part of the approved parameters (the fingerprint stands);
            # a note on the row that the job reads and the phone route honours.
            done = await conn.fetchrow("UPDATE errands SET outcome = outcome || '{\"run_on\": \"phone\"}'::jsonb WHERE id = $1 RETURNING *", errand_id)
        await audit.record(p.household_id, "errand.approved", actor_member_id=p.member_id, target_type="errand",
                           target_id=errand_id, detail={"service": row["service"], "kind": row["kind"]}, conn=conn)
        if can_run(row["service"], row["kind"]):
            await jobs.create(KIND, {"errand_id": str(errand_id)}, household_id=p.household_id, member_id=row["created_by"], conn=conn)
    return dict(done)


async def finish(p: Principal, errand_id: uuid.UUID) -> dict:
    """The person finished in the live browser: done, browser released."""
    from familyos.execution import steel
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("SELECT * FROM errands WHERE id = $1 AND household_id = $2 FOR UPDATE", errand_id, p.household_id)
        if row is None:
            raise NotFound("errand")
        if row["status"] != "needs_you":
            raise Invalid(f"this errand is {row['status']}, not waiting on you")
        done = await conn.fetchrow("UPDATE errands SET status = 'done', ended_at = NOW(), updated_at = NOW() WHERE id = $1 RETURNING *", errand_id)
        await audit.record(p.household_id, "errand.done", actor_member_id=p.member_id, target_type="errand",
                           target_id=errand_id, detail={"service": row["service"], "finished_by_person": True}, conn=conn)
    browser = (row["outcome"] or {}).get("browser") or {}
    await steel.current_browser().release(browser.get("session_id"))
    return dict(done)


async def cancel(p: Principal, errand_id: uuid.UUID) -> dict:
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("SELECT * FROM errands WHERE id = $1 AND household_id = $2 FOR UPDATE", errand_id, p.household_id)
        if row is None:
            raise NotFound("errand")
        if row["status"] in ("running", "done"):
            raise Invalid(f"this errand is {row['status']} and cannot be cancelled here")
        done = await conn.fetchrow("UPDATE errands SET status = 'cancelled', ended_at = NOW(), updated_at = NOW() WHERE id = $1 RETURNING *", errand_id)
        await audit.record(p.household_id, "errand.cancelled", actor_member_id=p.member_id, target_type="errand",
                           target_id=errand_id, detail={"service": row["service"]}, conn=conn)
    browser = (row["outcome"] or {}).get("browser") or {}
    if browser.get("session_id"):
        from familyos.execution import steel
        await steel.current_browser().release(browser.get("session_id"))
    return dict(done)


async def list_for(p: Principal, limit: int = 50) -> list[dict]:
    rows = await pool().fetch("SELECT * FROM errands WHERE household_id = $1 ORDER BY created_at DESC LIMIT $2",
                              p.household_id, max(1, min(limit, 200)))
    return [dict(r) for r in rows]


async def get(p: Principal, errand_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT * FROM errands WHERE id = $1 AND household_id = $2", errand_id, p.household_id)
    if row is None:
        raise NotFound("errand")
    return dict(row)


# ----------------------------------------------------------------------------
# running: one runbook per site, the next build
# ----------------------------------------------------------------------------

KIND = "errand_run"
HANDLER_VERSION = "1"
_runbooks: dict = {}


def runbooks() -> dict:
    return _runbooks


def use_runbook(service: str, runbook) -> None:
    _runbooks[service] = runbook


def can_run(service: str, kind: str = "look") -> bool:
    """Whether anything would take this errand: a runbook, or the generalist."""
    from familyos.execution import generalist
    return service in _runbooks or generalist.wants(kind, False)


async def _handle(job: dict, ctx) -> dict:
    from familyos.execution import generalist
    errand_id = uuid.UUID(job["spec"]["errand_id"])
    row = await pool().fetchrow("SELECT * FROM errands WHERE id = $1", errand_id)
    if row is None or row["status"] not in ("approved", "running"):
        return {"skipped": "not approved" if row else "gone"}
    # A job that comes back to a running errand is a restart after a crash or
    # a lost lease. The runbook replays its reads and stops at a step that
    # was interrupted and cannot be repeated (runbooks.interrupted).
    if (row["outcome"] or {}).get("run_on") == "phone":
        # The person asked for this to run in the app's own web view; it
        # runs while they hold it open (run_on_phone), not here.
        return {"skipped": "runs on the phone when it is held open"}
    book = _runbooks.get(row["service"])
    from familyos import chat
    if generalist.wants(row["kind"], book is not None) and not await chat.local_models_on(row["household_id"]):
        return await generalist.run(dict(row))
    if book is None:
        return {"skipped": "no runbook"}
    return await book(dict(row))


async def run_on_phone(p: Principal, errand_id: uuid.UUID, driver) -> dict:
    """The errand, driven through the phone that is holding it open. Only
    the person who asked for it, only while it is approved or already
    running on a phone, and only on a site with a runbook."""
    row = await pool().fetchrow("SELECT * FROM errands WHERE id = $1 AND household_id = $2", errand_id, p.household_id)
    if row is None:
        raise NotFound("errand")
    if row["created_by"] != p.member_id:
        raise NotAllowed("only the person who asked for the errand can run it on their phone")
    if row["status"] not in ("approved", "running", "needs_you"):
        raise Invalid(f"this errand is {row['status']}; it cannot be run now")
    book = _runbooks.get(row["service"])
    if book is None:
        raise Invalid("this site has no runbook yet; it runs from the console")
    if (row["outcome"] or {}).get("run_on") != "phone":
        await pool().execute("UPDATE errands SET outcome = COALESCE(outcome, '{}'::jsonb) || '{\"run_on\": \"phone\"}'::jsonb, updated_at = NOW() WHERE id = $1", errand_id)
    await audit.record(p.household_id, "errand.phone_run", actor_member_id=p.member_id, target_type="errand", target_id=errand_id,
                       detail={"service": row["service"]})
    return await book(dict(row), driver=driver)


def register() -> None:
    from familyos.execution import apps, runbooks
    use_runbook("urbancompany", runbooks.urbancompany)
    for name in apps.APPS:
        use_runbook(name, apps.read_app)
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("steel_url",))


def describe() -> str:
    from familyos.execution import generalist
    have = ", ".join(sorted(_runbooks)) or "none yet"
    return (f"errands: a booking or purchase on a signed-in site, approved by a guardian against its fingerprint; "
            f"pay-after-service or a UPI request on the person's own phone, never a card we hold. Runbooks: {have}. "
            + generalist.describe())
