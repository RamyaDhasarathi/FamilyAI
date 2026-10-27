"""FastAPI application. Run with: uvicorn familyos.main:app"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from familyos import (
    actions,
    ask,
    calendar,
    chat,
    db,
    digest,
    erasure,
    errands,
    jobs,
    plans,
    publiccontext,
    reminders,
    watches,
)
from familyos.api.routes import router
from familyos.artifacts import HouseholdUnavailable, TooLarge
from familyos.consent import ConsentRequired
from familyos.execution import capability, harvest, research, sessions, steel
from familyos.execution.disposable import Refused as ExecutionRefused
from familyos.extraction import pipeline as extraction_pipeline
from familyos.extraction import sandbox as parse_sandbox
from familyos.extraction import service as extraction
from familyos.identity import Invalid, LinkNotUsable, NotAllowed, NotFound
from familyos.intake import mailbox
from familyos.intake.gateway import Rejected
from familyos.intake.mailbox import NotConfigured
from familyos.settings import settings

logger = logging.getLogger("familyos")

WEB = Path(__file__).parent / "web"


def register_job_handlers() -> None:
    erasure.register()
    extraction.register()
    reminders.register()
    mailbox.register()
    actions.register()
    watches.register()
    calendar.register()
    digest.register()
    plans.register()
    errands.register()
    publiccontext.register()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await db.connect()
    if settings.auto_migrate:
        await db.migrate()
    register_job_handlers()
    steel.configure()
    chat.configure()
    research.configure()
    # Say out loud, every boot, what reads notices and where their text goes.
    # basicConfig is a no-op once the host has configured logging; without it
    # uvicorn leaves the root logger bare and this line goes nowhere.
    logging.basicConfig(level=logging.INFO)
    # httpx logs every request URL at INFO, and Telegram's bot API carries
    # the bot token in the path: a secret would land in the access log on
    # every send. Only its warnings are worth keeping.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for said in (extraction_pipeline.describe(), parse_sandbox.describe(), mailbox.describe(),
                 actions.describe(), watches.describe(), calendar.describe(),
                 sessions.describe(), capability.describe(), harvest.describe(),
                 ask.describe(), chat.describe(), digest.describe(), research.describe(), errands.describe(), reminders.describe_whatsapp(),
                 reminders.describe_telegram()):
        logger.error("%s", said) if "MISCONFIGURED" in said else logger.info("%s", said)
    if settings.jobs_enabled:
        await reminders.ensure_scheduled()
        await mailbox.ensure_scheduled()
        await actions.ensure_scheduled()
        await watches.ensure_scheduled()
        await calendar.ensure_scheduled()
        try:
            from familyos.intake import gateway as _gateway
            named = await _gateway.name_old_shares()
            if named:
                logger.info("named %d older shares from their text", named)
            from familyos import documents as _documents
            masked = await _documents.mask_old_quotes()
            if masked:
                logger.info("masked the numbers in %d document quotes", masked)
        except Exception:  # noqa: BLE001 - a courtesy at startup, never a reason not to start
            logger.warning("could not name older shares", exc_info=True)
        await digest.ensure_scheduled()
        await publiccontext.ensure_scheduled()
    worker = asyncio.create_task(jobs.worker()) if settings.jobs_enabled else None
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        await db.close()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="FamilyOS", version="0.1.0", lifespan=lifespan if with_lifespan else None)
    app.include_router(router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        await db.pool().fetchval("SELECT 1")
        return {"ok": True}

    # The console is served from this app, so it shares the API's origin: the
    # bearer token goes straight on each request and no CORS rule is needed.
    if WEB.is_dir():
        @app.get("/", include_in_schema=False)
        async def root():
            return RedirectResponse("/app/")

        class _Console(StaticFiles):
            """Always revalidate. Without this the browser keeps a console it
            already has, and a shipped change looks like a change that was
            never made. The ETag makes a revalidation a 304, so it costs
            nothing."""

            async def get_response(self, path, scope):
                response = await super().get_response(path, scope)
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
                return response

        app.mount("/app", _Console(directory=WEB, html=True), name="console")

    # The console as it was before the Family Constellation redesign, kept at
    # its own address for a side-by-side comparison. Same API, same sign-in
    # (the token lives in the origin's storage), so nothing is duplicated
    # but the three files. Google sign-in still lands on /app/.
    CLASSIC = WEB.parent / "web_classic"
    if CLASSIC.is_dir():
        app.mount("/classic", _Console(directory=CLASSIC, html=True), name="classic")

    # Orbit: the UI from the Master UI/UX spec (11 Oct 2026): an ambient home
    # with the household at the centre and the spaces in orbit, a swipe-up
    # dashboard sheet, deep layers, one FAB. Same API, same sign-in, its own
    # address, so /app and /classic stay exactly as they are.
    ORBIT = WEB.parent / "web_orbit"
    if ORBIT.is_dir():
        app.mount("/orbit", _Console(directory=ORBIT, html=True), name="orbit")

    # Guide: a pilot of generative UI (OpenUI) for a plan's guide page, 11 Oct
    # 2026. The model composes the page from an allow-listed component
    # library; the server forwards only lines that name those components.
    GUIDE = WEB.parent / "web_guide"
    if GUIDE.is_dir():
        app.mount("/guide", _Console(directory=GUIDE, html=True), name="guide")

    def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": code, "detail": message, **extra})

    @app.exception_handler(RequestValidationError)
    async def malformed(request: Request, exc: RequestValidationError):
        # A request the framework refused before any route ran. Logged, so a
        # phone shortcut that sends the wrong shape can be diagnosed from the
        # server; and answered with a `message` the phone's banner can show.
        said = "; ".join(f"{'.'.join(str(x) for x in e.get('loc', ()))}: {e.get('msg')}" for e in exc.errors()[:3])
        logger.warning("malformed %s %s: %s", request.method, request.url.path, said)
        return JSONResponse(status_code=422, content={"error": "invalid", "detail": exc.errors(), "message": "The request was malformed: " + said})

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return _error(404, "not_found", f"{exc} not found")

    @app.exception_handler(NotAllowed)
    async def not_allowed(_: Request, exc: NotAllowed):
        return _error(403, "not_allowed", str(exc))

    @app.exception_handler(LinkNotUsable)
    async def link_not_usable(_: Request, exc: LinkNotUsable):
        # Registered before Invalid, which it subclasses: a dead link is a
        # failed sign-in, not a malformed request.
        return _error(401, "link_not_usable", str(exc))

    @app.exception_handler(chat.ModelUnavailable)
    async def model_unavailable(_: Request, exc: chat.ModelUnavailable):
        return _error(503, "model_unavailable", str(exc))

    @app.exception_handler(NotConfigured)
    async def not_configured(_: Request, exc: NotConfigured):
        # Something this deployment cannot do yet. The message says what to set,
        # so it has to reach the console rather than become a 500.
        return _error(503, "not_configured", str(exc))

    @app.exception_handler(ExecutionRefused)
    async def execution_refused(_: Request, exc: ExecutionRefused):
        # A page we will not read. Says which rule stopped it.
        return _error(422, "refused", str(exc))

    @app.exception_handler(Invalid)
    async def invalid(_: Request, exc: Invalid):
        return _error(422, "invalid", str(exc))

    @app.exception_handler(ConsentRequired)
    async def consent_required(_: Request, exc: ConsentRequired):
        return _error(409, "consent_required", "a guardian must give consent before recording anything about this child",
                      member_ids=[str(m) for m in exc.member_ids])

    @app.exception_handler(Rejected)
    async def rejected(_: Request, exc: Rejected):
        return _error(exc.status, "rejected", exc.reason)

    @app.exception_handler(TooLarge)
    async def too_large(_: Request, exc: TooLarge):
        return _error(413, "too_large", str(exc))

    @app.exception_handler(HouseholdUnavailable)
    async def unavailable(_: Request, exc: HouseholdUnavailable):
        return _error(409, "household_unavailable", "this household is being erased")

    return app


app = create_app()
