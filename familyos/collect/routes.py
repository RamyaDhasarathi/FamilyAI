"""/v1/collect: what the collecting layer holds for the signed-in member, from the local cache (store.py).

A member sees only their own: the cache is keyed by the Google address, and the address is the member's own email.
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from familyos.api.deps import current_member
from familyos.collect import browser_agent, decide, device, google_data, phone_agent, store, vault
from familyos.db import pool
from familyos.identity import Principal

router = APIRouter(prefix="/v1/collect", tags=["collect"])


async def _email(p: Principal) -> str | None:
    return await pool().fetchval("SELECT email FROM members WHERE id = $1", p.member_id)


@router.get("/status", description="What is collected for you: Google connected or not, what it may read, how many items, the last run and what went wrong.")
async def collect_status(p: Principal = Depends(current_member)):
    email = await _email(p)
    google = store.status(email) if email else {"connected": False, "email": None, "scopes": [], "counts": {}, "last_errors": {}}
    google["running"] = bool(email) and google_data.is_running(email)
    phone = store.device_counts(email) if email else {}
    return {"google": google, "device": phone, "kept": "on this computer only (local cache)"}


@router.post("/google/run", status_code=202, description="Collect from Google now (Gmail, Calendar, Tasks), in the background.")
async def collect_google_now(p: Principal = Depends(current_member)):
    email = await _email(p)
    if not email or store.google_account(email) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Google is not connected for you: sign in with Google and allow Gmail, Calendar and Tasks.")
    return {"started": google_data.start(email)}


@router.get("/google/attachments", description="Attachments of your collected mail (saved on this computer up to 25 MB each).")
async def gmail_attachments(message_id: str | None = None, p: Principal = Depends(current_member)):
    email = await _email(p)
    return store.attachments(email, message_id) if email else []


@router.get("/google/attachments/{message_id}/{attachment_id}", description="One saved attachment of your mail.")
async def gmail_attachment(message_id: str, attachment_id: str, p: Principal = Depends(current_member)):
    email = await _email(p)
    path = store.attachment_path(email, message_id, attachment_id) if email else None
    if not path or not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such saved attachment of yours")
    return FileResponse(path, filename=os.path.basename(path))


@router.get("/google/{kind}", description="Your collected Gmail messages, calendar events or tasks, newest or soonest first.")
async def collected(kind: str, limit: int = 100, p: Principal = Depends(current_member)):
    if kind not in store.KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "a collected kind is gmail, calendar or tasks")
    email = await _email(p)
    return store.items(kind, email, min(max(limit, 1), 500)) if email else []


# ── What the Android app collects (device.py) ───────────────────────────────

class DeviceItems(BaseModel):
    items: list[dict] = Field(max_length=2000)


class DeviceApp(BaseModel):
    package: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=200)
    collect: bool = False


class DeviceApps(BaseModel):
    apps: list[DeviceApp] = Field(max_length=2000)


async def _own_email(p: Principal) -> str:
    email = await _email(p)
    if not email:
        raise HTTPException(status.HTTP_409_CONFLICT, "collecting needs a member with an email address")
    return email


@router.put("/device/apps", description="The phone's installed apps with your collect switch for each (replaces the last list).")
async def put_device_apps(body: DeviceApps, p: Principal = Depends(current_member)):
    email = await _own_email(p)
    store.set_apps(email, [a.model_dump() for a in body.apps])
    # An app newly switched on gets its decision (decide.py) in the background.
    return {"apps": len(body.apps), "collecting": sum(a.collect for a in body.apps), "deciding": decide.start_new(email)}


@router.get("/device/apps", description="Your phone's apps as last sent, with their collect switch.")
async def get_device_apps(p: Principal = Depends(current_member)):
    email = await _email(p)
    return store.apps(email) if email else []


@router.post("/device/{kind}", description="Keep what your phone collected: sms, calls, notifications, locations or files (names only).")
async def post_device(kind: str, body: DeviceItems, p: Principal = Depends(current_member)):
    if kind not in device.KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "a phone kind is sms, calls, notifications, locations or files")
    return device.keep(kind, await _own_email(p), body.items)


@router.get("/device/{kind}", description="What your phone sent, newest first.")
async def get_device(kind: str, limit: int = 100, p: Principal = Depends(current_member)):
    if kind not in device.KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "a phone kind is sms, calls, notifications, locations or files")
    email = await _email(p)
    return store.items(kind, email, min(max(limit, 1), 500)) if email else []


# ── Connected services (vault.py): sites for the browser agent, passwords in the Keychain ───────────

class ServiceIn(BaseModel):
    service: str = Field(min_length=1, max_length=40)
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256, repr=False)
    host: str | None = Field(default=None, max_length=200)


@router.get("/services", description="The sites you can connect for the browser agent, and the ones you have (never a password).")
async def list_services(p: Principal = Depends(current_member)):
    email = await _email(p)
    connected = [{**c, "running": browser_agent.is_running(email, c["service"]), "items": store.site_item_count(email, c["service"]),
                  "last_run": store.last_run(email, f"site:{c['service']}")} for c in vault.connected(email)] if email else []
    return {"catalog": vault.CATALOG, "connected": connected, "kept": "passwords in this Mac's Keychain",
            "agent": {"model": browser_agent.model_name() or None}}


@router.post("/services", status_code=201, description="Connect a site: its username and password go to this Mac's Keychain.")
async def connect_service(body: ServiceIn, p: Principal = Depends(current_member)):
    email = await _own_email(p)
    try:
        return vault.connect(email, body.service, body.username, body.password, body.host)
    except vault.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except vault.KeychainUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.delete("/services/{service}", status_code=204, description="Remove a site, and its password from the Keychain.")
async def disconnect_service(service: str, p: Principal = Depends(current_member)):
    email = await _own_email(p)
    if not vault.disconnect(email, service):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that site is not connected")


# ── The decision layer (decide.py): which methods may collect from each app switched on ───────────

@router.get("/decide", description="For each app you switched on: the methods that may collect from it, in priority order, each with a status the registry decided.")
async def decisions(p: Principal = Depends(current_member)):
    email = await _email(p)
    return {"apps": decide.results(email) if email else [], "methods": list(decide.METHODS)}


@router.post("/decide", status_code=202, description="Decide again for every app you switched on (after connecting Google or a site).")
async def decide_all(p: Principal = Depends(current_member)):
    return {"started": decide.start_new(await _own_email(p), again=True)}


@router.post("/decide/{package}", status_code=202, description="Decide again for one app.")
async def decide_one(package: str, p: Principal = Depends(current_member)):
    started = decide.start(await _own_email(p), package)
    if started is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that app is not in your phone's list: collect from the phone first")
    return {"started": started}


# ── The browser agent (browser_agent.py): reads your orders, bookings or bills on a connected site ─────────────

def _agent_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, browser_agent.NotConnected):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.post("/services/{service}/run", status_code=202, description="The browser agent signs in to this site and reads your recent orders, bookings or bills, in the background. It never buys, books or changes anything.")
async def run_service(service: str, p: Principal = Depends(current_member)):
    try:
        return {"started": browser_agent.start(await _own_email(p), service)}
    except (browser_agent.NotConnected, browser_agent.NoModel) as exc:
        raise _agent_errors(exc) from exc


@router.post("/services/{service}/sign-in", status_code=202, description="Open the site in a window on this Mac for you to sign in yourself (a one-time code, a captcha); the agent's next run stays signed in.")
async def sign_in_service(service: str, p: Principal = Depends(current_member)):
    try:
        return {"started": browser_agent.start_sign_in(await _own_email(p), service), "minutes": browser_agent.SIGN_IN_MINUTES}
    except browser_agent.NotConnected as exc:
        raise _agent_errors(exc) from exc


@router.get("/services/{service}/items", description="What the browser agent read on this site.")
async def service_items(service: str, limit: int = 100, p: Principal = Depends(current_member)):
    email = await _email(p)
    if not email or store.site_account(email, service) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that site is not in your Connected services")
    return store.site_items(email, service, min(max(limit, 1), 500))


# ── The phone agent (phone_agent.py): reads an app on your phone; the phone does each action it is given ─────────

class PhoneRunIn(BaseModel):
    package: str = Field(min_length=1, max_length=255)
    engine: Literal["claude", "local"] = "claude"          # local: Qwen3.5 + MAI-UI on this Mac


class Observation(BaseModel):
    currentApp: str | None = Field(default=None, max_length=255)
    tree: list[dict] = Field(default_factory=list, max_length=2000)
    screenshot: str | None = Field(default=None, max_length=4_000_000, repr=False)
    width: int = 0
    height: int = 0


@router.post("/phone/runs", status_code=201, description="Start the phone agent on one of your apps switched on for collecting: it reads, never buys, sends or changes anything.")
async def phone_run(body: PhoneRunIn, p: Principal = Depends(current_member)):
    try:
        return phone_agent.start(await _own_email(p), body.package, body.engine).public()
    except phone_agent.NotFound as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/phone/runs/{run_id}/step", description="What the phone shows now; the answer is the one action to do next (or done).")
async def phone_step(run_id: str, body: Observation, p: Principal = Depends(current_member)):
    try:
        return await phone_agent.step(await _own_email(p), run_id, body.model_dump())
    except phone_agent.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/phone/runs/{run_id}/stop", description="Stop a phone agent run.")
async def phone_stop(run_id: str, p: Principal = Depends(current_member)):
    try:
        return phone_agent.stop(await _own_email(p), run_id).public()
    except phone_agent.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/apps/{package}/items", description="What the phone agent read in this app, and its last run.")
async def app_items(package: str, limit: int = 100, p: Principal = Depends(current_member)):
    email = await _email(p)
    if not email or not any(a["package"] == package for a in store.apps(email)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that app is not in your phone's list")
    return {"items": store.site_items(email, f"app:{package}", min(max(limit, 1), 500)),
            "last_run": store.last_run(email, f"app:{package}")}
