"""FastAPI application. Run with: uvicorn familyos.main:app"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from familyos import (
    actions,
    agents,
    ask,
    assistant_tasks,
    calendar,
    chat,
    crypto,
    db,
    digest,
    emergency,
    erasure,
    errands,
    handoffs,
    jobs,
    logfilter,
    mcp,
    morning,
    nudges,
    plans,
    publiccontext,
    ratelimit,
    reminders,
    routines,
    sealing,
    taught,
    wallet,
    watches,
    whatsapp_watch,
)
from familyos.api.routes import router
from familyos.artifacts import HouseholdUnavailable, TooLarge
from familyos.consent import ConsentRequired
from familyos.execution import capability, harvest, research, sessions, steel, whatsapp_reader
from familyos.execution.disposable import Refused as ExecutionRefused
from familyos.extraction import pipeline as extraction_pipeline
from familyos.extraction import sandbox as parse_sandbox
from familyos.extraction import service as extraction
from familyos.familykey import HouseholdLocked, PasskeyNeeded
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
    routines.register()
    handoffs.register()
    nudges.register()
    whatsapp_watch.register()
    sealing.register()
    morning.register()
    plans.register()
    errands.register()
    publiccontext.register()


IN_MEMORY_STATE = (
    "the family key's unlocked state and its failed-unlock counter (familykey), taught lessons and their browsers (taught), phone-driver sockets "
    "(execution.phone), the WhatsApp reader's browser and its profile directories (execution.whatsapp_reader) and the tasks it is running for assistants"
)


def check_single_worker(raw: str | None) -> int:
    """Refuse to start with more than one worker under one server (WEB_CONCURRENCY). Returns the worker count.

    Part of what this process holds can be shared through Postgres and is, when FAMILYOS_MULTI_WORKER=true: the unlocked family key and its
    failed-try count, the count of a member's lessons, the WebSocket tickets, a per-member lock on the WhatsApp profile, and an assistant
    task's heartbeat. Three things cannot move: a phone-driver socket (the phone is connected to one process), a lesson's browser, and the
    WhatsApp profile directories on one machine's disk. They need a request routed to the process that holds them, by errand or lesson id.
    Workers started by one uvicorn (WEB_CONCURRENCY) share an environment and take connections from one socket: they cannot be routed by id
    and cannot be told apart as "the WhatsApp worker". So this guard stays; running more than one process is done as separate single-worker
    processes behind a proxy that routes, each with FAMILYOS_MULTI_WORKER=true (docs/deploy.md, "More than one process")."""
    try:
        workers = int(raw or 1)
    except ValueError:
        workers = 1
    if workers > 1:
        raise RuntimeError(
            f"FamilyOS runs one worker under one server, not {workers} (WEB_CONCURRENCY). It keeps {IN_MEMORY_STATE} in this process's memory. "
            "FAMILYOS_MULTI_WORKER=true shares the unlocked key, the lesson count, tickets and task heartbeats through Postgres, but phone sockets, "
            "a lesson's browser and the WhatsApp profiles stay in one process, and workers sharing one server cannot be routed to the one that "
            "holds them. To run more than one, start separate single-worker processes behind a proxy that routes by errand or lesson id. "
            "See docs/deploy.md (One worker, and More than one process).")
    return workers


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logfilter.install()
    crypto.check_master_key()
    check_single_worker(os.environ.get("WEB_CONCURRENCY", "1"))
    await db.connect()
    if settings.auto_migrate:
        await db.migrate()
    else:
        logger.warning("FAMILYOS_AUTO_MIGRATE=false: no migrations applied; the schema is assumed to be in place")
    if settings.dev_sign_in:
        logger.warning("FAMILYOS_DEV_SIGN_IN is ON: POST /v1/sign-in/dev signs anyone in by email alone. Development only.")
    register_job_handlers()
    steel.configure()
    if whatsapp_reader.configure() and not whatsapp_reader.runs_here():
        jobs.decline(whatsapp_watch.KIND)          # this worker does not hold the WhatsApp profiles; the one that does takes the sweep
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
    if settings.multi_worker:
        logger.info("More than one process (FAMILYOS_MULTI_WORKER): the unlocked family key, its failed tries, lesson counts, tickets and task heartbeats are "
                    "shared through Postgres (the key wrapped under the master key until it expires). Phone sockets, a lesson's browser and the WhatsApp "
                    "profiles stay in the process that holds them; this process %s the WhatsApp profiles.",
                    "holds" if whatsapp_reader.runs_here() else "does not hold")
    for said in (extraction_pipeline.describe(), parse_sandbox.describe(), mailbox.describe(),
                 actions.describe(), watches.describe(), calendar.describe(),
                 sessions.describe(), capability.describe(), harvest.describe(),
                 ask.describe(), chat.describe(), digest.describe(), routines.describe(), morning.describe(), research.describe(), errands.describe(), reminders.describe_whatsapp(), whatsapp_watch.describe(),
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
        await routines.ensure_scheduled()
        await handoffs.ensure_scheduled()
        await nudges.ensure_scheduled()
        await whatsapp_watch.ensure_scheduled()
        await sealing.ensure_scheduled()
        await morning.ensure_scheduled()
        await publiccontext.ensure_scheduled()
        await assistant_tasks.recover_stale()
    worker = asyncio.create_task(jobs.worker()) if settings.jobs_enabled else None
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        await db.close()


# Consoles whose pages carry no inline script and no inline handler (scripts/externalize_scripts.py,
# tests/test_script_policy.py), with the one outside host each loads code from. /pay is a built bundle
# (familyos/web_pay, committed as public/bundle.js) and /docs is Swagger UI from a pinned CDN copy with its
# start-up script in our own file. /redoc is switched off (its page starts from an inline script); /docs is the reference.
_SCRIPT_HOSTS = {
    "": "", "app": "https://cdnjs.cloudflare.com", "classic": "https://cdnjs.cloudflare.com", "orbit": "", "cockpit": "",
    "family-agent": "", "home": "", "kid": "", "guide": "https://cdn.jsdelivr.net", "pay": "", "docs": "https://cdn.jsdelivr.net",
}

# The API reference. FastAPI's own /docs page starts Swagger UI from an inline script, which the policy forbids, so the page is ours:
# the same bundle from a pinned version with its integrity hash, started by /docs/init.js.
SWAGGER_VERSION = "5.17.14"
SWAGGER_JS = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_VERSION}/swagger-ui-bundle.js"
SWAGGER_JS_SRI = "sha384-wmyclcVGX/WhUkdkATwhaK1X1JtiNrr2EoYJ+diV3vj4v6OC5yCeSu+yW13SYJep"
SWAGGER_CSS = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_VERSION}/swagger-ui.css"
SWAGGER_CSS_SRI = "sha384-wxLW6kwyHktdDGr6Pv1zgm/VGJh99lfUbzSn6HNHBENZlCN7W602k9VkGdxuFvPn"
SWAGGER_PAGE = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">'
    f'<link rel="stylesheet" href="{SWAGGER_CSS}" integrity="{SWAGGER_CSS_SRI}" crossorigin="anonymous">'
    '<title>FamilyOS API</title></head><body><div id="swagger-ui"></div>'
    f'<script src="{SWAGGER_JS}" integrity="{SWAGGER_JS_SRI}" crossorigin="anonymous"></script>'
    '<script src="/docs/init.js"></script></body></html>')
SWAGGER_INIT = (
    "SwaggerUIBundle({ url: '/openapi.json', dom_id: '#swagger-ui', layout: 'BaseLayout', deepLinking: true, showExtensions: true,\n"
    "  showCommonExtensions: true, presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset] });\n")


def _csp_for(path: str) -> str:
    first = path.strip("/").split("/", 1)[0]
    if first not in _SCRIPT_HOSTS or (first == "" and path != "/"):
        return "frame-ancestors 'none'"
    host = _SCRIPT_HOSTS[first]
    scripts = ("'self' " + host).strip()
    return (f"script-src {scripts}; worker-src 'self' blob: {host}".rstrip() +
            "; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")



def create_app(*, with_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="FamilyOS", version="0.1.0", lifespan=lifespan if with_lifespan else None, docs_url=None, redoc_url=None)
    app.include_router(router)
    wallet.register(app)       # the optional family wallet: mounted always, answers 404 unless the deployment and the household chose it

    @app.get("/docs", include_in_schema=False)
    async def api_docs():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(SWAGGER_PAGE)

    @app.get("/docs/init.js", include_in_schema=False)
    async def api_docs_init():
        from fastapi.responses import Response
        return Response(SWAGGER_INIT, media_type="text/javascript")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """The consoles are served from the API origin, so none may be framed
        (clickjacking) or sniffed, and a window opened from one is isolated.
        The consoles also get a script policy (no inline script, no eval, only our own files and
        the one CDN each is known to load from), so a script injected into a page cannot run.
        A route that already set one of these (the original-file endpoint sets nosniff)
        keeps its own value."""
        response = await call_next(request)
        for name, value in (("X-Frame-Options", "DENY"),
                            ("Content-Security-Policy", _csp_for(request.url.path)),
                            ("X-Content-Type-Options", "nosniff"),
                            ("Cross-Origin-Opener-Policy", "same-origin")):
            if name not in response.headers:
                response.headers[name] = value
        if request.url.path.startswith("/v1/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "private, no-store"      # household data, and a device token in the Shortcut: kept by no cache
        return response

    @app.get("/.well-known/payments-jwks.json", include_in_schema=False)
    async def payments_jwks():
        """The public half of the key that signs the payment provider's login tokens. Public by design."""
        from familyos import payments_auth
        return payments_auth.jwks()

    @app.middleware("http")
    async def referrer_policy(request: Request, call_next):
        # Sign-in links travel in ?link=; never let a page they open pass the
        # address on in a Referer header.
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        await db.pool().fetchval("SELECT 1")
        return {"ok": True}

    # The console is served from this app, so it shares the API's origin: the
    # bearer token goes straight on each request and no CORS rule is needed.
    if WEB.is_dir():
        WELCOME = WEB.parent / "web_home" / "index.html"

        @app.get("/e/{token}", include_in_schema=False)
        async def emergency_page(token: str):
            """An emergency card shared by link: no sign-in, read only, and an unknown, expired or revoked link says the same thing."""
            from fastapi.responses import HTMLResponse
            try:
                return HTMLResponse(emergency.page(await emergency.open_shared(token)), headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"})
            except NotFound:
                return HTMLResponse("<!doctype html><meta charset=utf-8><title>Not open</title><p>That link is not open.</p>", status_code=404, headers={"Cache-Control": "no-store"})

        @app.get("/", include_in_schema=False)
        async def root():
            """The signed-out front page. A signed-in visitor is sent on to /app/ by the page itself
            (it reads the console's token); sign-in and start-a-household stay in the console."""
            if WELCOME.is_file():
                return FileResponse(WELCOME, headers={"Cache-Control": "no-cache, must-revalidate"})
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

    # Cockpit: the same console under the web redesign's shell (11 Oct 2026):
    # Today as a decision queue, five jobs in the navigation, source and
    # privacy on every decision row, labelled reversible actions, Ask as a
    # first-class action, a sign-in that sells the trust. It borrows /app's
    # script and stylesheet and brings its own chrome (cockpit.js, cockpit.css).
    COCKPIT = WEB.parent / "web_cockpit"
    if COCKPIT.is_dir():
        app.mount("/cockpit", _Console(directory=COCKPIT, html=True), name="cockpit")

    # Family Agent: a second public product story, intentionally separate from
    # the signed-in console and its landing gate. It presents the same product
    # through a conversation-first, family-friendly surface and sends people
    # into /app only when they choose to start or sign in.
    FAMILY_AGENT = WEB.parent / "web_family_agent"
    if FAMILY_AGENT.is_dir():
        app.mount("/family-agent", _Console(directory=FAMILY_AGENT, html=True), name="family-agent")

    # Home: a quieter, product-led front page (phone screens, one idea per block), mounted beside the others to compare.
    HOME = WEB.parent / "web_home"
    if HOME.is_dir():
        app.mount("/home", _Console(directory=HOME, html=True), name="home")

    # MCP: a person's own assistant connects here with their own key (agents.py, mcp.py). JSON in, JSON out, no session.
    @app.post("/mcp", include_in_schema=False)
    async def mcp_endpoint(request: Request):
        from fastapi.responses import JSONResponse, Response
        auth = request.headers.get("authorization", "")
        fails = f"mcp-fail:{ratelimit.client_ip(request)}"
        if wait := ratelimit.limiter.wait_if_full(fails, settings.rate_mcp_failures_per_ip, ratelimit.HOUR):
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "too many wrong keys from this address; try later"}},
                                status_code=429, headers={"Retry-After": str(math.ceil(wait))})
        agent = await agents.authenticate(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
        if agent is None:
            ratelimit.limiter.take([(fails, max(settings.rate_mcp_failures_per_ip, 1), ratelimit.HOUR)])
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "a connection key is needed"}}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}, status_code=400)
        if isinstance(body, list):
            answers = [x for x in [await mcp.handle(agent, m) for m in body[:20] if isinstance(m, dict)] if x is not None]
            return JSONResponse(answers) if answers else Response(status_code=202)
        if not isinstance(body, dict):
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "not a request"}}, status_code=400)
        answer = await mcp.handle(agent, body)
        return JSONResponse(answer, headers={"Cache-Control": "no-store"}) if answer is not None else Response(status_code=202)

    @app.get("/mcp", include_in_schema=False)
    async def mcp_get():
        from fastapi.responses import Response
        return Response(status_code=405, headers={"Allow": "POST"})

    # Kid: a child's own day, opened with their own key (kid.py). Static; it holds no data, the key does the work.
    KID = WEB.parent / "web_kid"
    if KID.is_dir():
        app.mount("/kid", _Console(directory=KID, html=True), name="kid")

    # Pay: the guardian's card and verification screens for the payment provider, a small page built
    # with the provider's own components (familyos/web_pay, `npm run build`); only public/ is served.
    PAY = WEB.parent / "web_pay" / "public"
    if PAY.is_dir():
        app.mount("/pay", _Console(directory=PAY, html=True), name="pay")

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

    @app.exception_handler(taught.HeldElsewhere)
    async def held_elsewhere(_: Request, exc: taught.HeldElsewhere):
        return _error(409, "held_by_another_worker", "this lesson's browser or phone is held by another worker; route this member's lesson requests to the worker that started it")

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

    @app.exception_handler(HouseholdLocked)
    async def locked(_: Request, exc: HouseholdLocked):
        return _error(423, "household_locked", "this household is locked: an adult unlocks it with the family key (at least the shares it needs)")

    @app.exception_handler(PasskeyNeeded)
    async def passkey_needed(_: Request, exc: PasskeyNeeded):
        return _error(403, "passkey_needed", str(exc))

    @app.exception_handler(HouseholdUnavailable)
    async def unavailable(_: Request, exc: HouseholdUnavailable):
        return _error(409, "household_unavailable", "this household is being erased")

    return app


app = create_app()
