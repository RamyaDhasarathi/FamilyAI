"""The decision layer, ported from the collector app (Mobile-UI-Agent backend/src/services/decisionLayer.js,
capabilities.js and appCategories.js; decided 30 Oct 2026): for each phone app switched on for collecting, which
methods may get its data, in a fixed priority -- api, mcp, email, phone_data, mobile_use, browser_use.

Qwen3.5 (the local model server's /methods, `settings.collect_model_url`) proposes methods, data types, a reason and
the senders an app emails from. This file keeps only what the registry backs:
  - every status comes from the registry (what is really configured and collected for this member), never the model
  - unknown methods are dropped, and data types outside the allowed list
  - email is checked against real mail from the senders: the local cache first, then Gmail itself (90 days)
  - the model's reason is shown only where the method is available, as plain one-line text
Three differences from the collector app: with the model server not reachable the decision is made from the registry
alone (`model` None) instead of failing; mobile_use is available for an app switched on (the phone agent); browser_use
is available for a site in Connected services (vault.py). Results go to the local cache (store.app_methods), nowhere else.
"""
from __future__ import annotations

import asyncio
import logging
import re

from familyos.collect import store, vault
from familyos.intake import google
from familyos.settings import settings

logger = logging.getLogger(__name__)

# Default priority: non-agent methods first, UI automation last.
METHODS = ("api", "mcp", "email", "phone_data", "mobile_use", "browser_use")

# Data types each app category can have.
DATA_TYPES: dict[str, list[str]] = {
    "Shopping": ["shopping.order_history", "shopping.cart", "shopping.order_confirmation", "shopping.delivery_status"],
    "Food and Grocery": ["food.order_history", "food.cart", "food.order_confirmation"],
    "Bank": ["bank.transactions", "bank.balance", "bank.statements", "bank.alerts"],
    "Travel and Booking": ["travel.bookings", "travel.tickets", "travel.ride_history"],
    "Health": ["health.records", "health.appointments", "health.activity"],
    "Chat and Communication": ["chat.messages", "chat.contacts"],
    "Social Media": ["social.messages", "social.activity"],
    "Productivity": ["productivity.documents", "productivity.events"],
    "Entertainment": ["entertainment.history", "entertainment.subscriptions"],
    "Maps and Navigation": ["maps.location_history", "maps.saved_places"],
    "Security and Identity": ["identity.documents"],
    "Other": [],
}
NOTIFICATIONS = "app.notifications"     # any app: what its notifications say

# The data types that typically arrive by email, per category.
EMAIL_TYPES: dict[str, list[str]] = {
    "Shopping": ["shopping.order_confirmation", "shopping.delivery_status"],
    "Food and Grocery": ["food.order_confirmation"],
    "Bank": ["bank.statements", "bank.alerts"],
    "Travel and Booking": ["travel.bookings", "travel.tickets"],
    "Health": ["health.appointments"],
    "Entertainment": ["entertainment.subscriptions"],
}

# Email sender domains for known apps (maintained; extend as needed). Checked against real mail before email is ever
# shown as available. Unknown apps: Qwen is asked.
KNOWN_SENDERS: dict[str, list[str]] = {
    "in.amazon.mShop.android.shopping": ["amazon.in"],
    "com.amazon.mShop.android.shopping": ["amazon.com"],
    "com.flipkart.android": ["flipkart.com"],
    "com.myntra.android": ["myntra.com"],
    "com.meesho.supply": ["meesho.com"],
    "in.swiggy.android": ["swiggy.in", "swiggy.com"],
    "com.application.zomato": ["zomato.com"],
    "com.zeptoconsumerapp": ["zeptonow.com", "zepto.co"],
    "com.grofers.customerapp": ["blinkit.com"],
    "com.bigbasket.mobileapp": ["bigbasket.com"],
    "in.redbus.android": ["redbus.in", "redbus.com"],
    "com.whereismytrain.android": ["whereismytrain.in"],
    "cris.org.in.prs.ima": ["irctc.co.in"],
    "com.makemytrip": ["makemytrip.com"],
    "com.goibibo": ["goibibo.com"],
    "com.ubercab": ["uber.com"],
    "com.olacabs.customer": ["olacabs.com"],
    "com.xiaomi.hm.health": ["zepp.com", "huami.com", "amazfit.com"],
    "com.practo.fabric": ["practo.com"],
    "com.bt.bms": ["bookmyshow.com"],
}

# Service APIs / MCP servers configured, by package. None yet -- add entries only when a real, authorised integration
# exists: {"in.swiggy.android": ["food.order_history"]}.
REGISTERED_APIS: dict[str, list[str]] = {}
REGISTERED_MCP: dict[str, list[str]] = {}

# Connected services (vault.CATALOG) by the apps they stand for: the browser agent signs in to the site.
SITE_PACKAGES: dict[str, list[str]] = {
    "amazon": ["in.amazon.mShop.android.shopping", "com.amazon.mShop.android.shopping"],
    "flipkart": ["com.flipkart.android"], "myntra": ["com.myntra.android"], "meesho": ["com.meesho.supply"],
    "bigbasket": ["com.bigbasket.mobileapp"], "blinkit": ["com.grofers.customerapp"], "zepto": ["com.zeptoconsumerapp"],
    "jiomart": ["com.jio.jiomart"], "swiggy": ["in.swiggy.android"], "zomato": ["com.application.zomato"],
    "uber": ["com.ubercab"], "ola": ["com.olacabs.customer"], "irctc": ["cris.org.in.prs.ima"],
    "makemytrip": ["com.makemytrip"], "airtel": ["com.myairtelapp"], "jio": ["com.jio.myjio"],
    "netflix": ["com.netflix.mediaclient"], "hotstar": ["in.startv.hotstar"], "practo": ["com.practo.fabric"],
    "pharmeasy": ["com.phonegap.rxpal"],
}
SITE_FOR = {pkg: site for site, pkgs in SITE_PACKAGES.items() for pkg in pkgs}

# ── Categories (appCategories.js): a known package, else keyword rules on the package and name, else Other ──────

KNOWN: dict[str, list[str]] = {
    "Bank": [
        "com.sbi.lotusintouch", "com.sbi.SBIFreedomPlus", "com.csam.icici.bank.imobile", "com.snapwork.hdfc",
        "com.msf.kbank.mobile", "com.axis.mobile", "com.infrasofttech.indianbank", "com.google.android.apps.nbu.paisa.user",
        "net.one97.paytm", "com.phonepe.app", "in.org.npci.upiapp", "com.dreamplug.androidapp", "com.bankofbaroda.mconnect",
        "com.canarabank.mobility", "com.unionbank.ecommerce.mobile.android", "com.pnb.mbanking",
    ],
    "Shopping": [
        "in.amazon.mShop.android.shopping", "com.amazon.mShop.android.shopping", "com.flipkart.android", "com.myntra.android",
        "com.meesho.supply", "com.ril.ajio", "com.fsn.nykaa", "com.snapdeal.main", "com.tul.tatacliq", "com.jio.jiomart",
    ],
    "Food and Grocery": [
        "com.application.zomato", "in.swiggy.android", "com.grofers.customerapp", "com.bigbasket.mobileapp",
        "com.zeptoconsumerapp", "com.dunzo.user", "com.Dominos", "com.done.faasos",
    ],
    "Travel and Booking": [
        "com.makemytrip", "com.goibibo", "com.ixigo.train.ixitrain", "com.ixigo", "in.redbus.android", "cris.org.in.prs.ima",
        "com.olacabs.customer", "com.ubercab", "com.rapido.passenger", "com.airbnb.android", "com.booking", "com.cleartrip.android",
    ],
    "Maps and Navigation": ["com.google.android.apps.maps", "com.waze", "com.mapmyindia.app.mappls"],
    "Chat and Communication": [
        "com.whatsapp", "com.whatsapp.w4b", "org.telegram.messenger", "com.google.android.apps.messaging", "com.android.mms",
        "com.facebook.orca", "com.discord", "com.google.android.gm", "com.google.android.dialer", "com.android.dialer",
        "com.google.android.contacts", "com.truecaller", "com.skype.raider", "com.Slack", "us.zoom.videomeetings",
        "com.microsoft.teams", "com.google.android.apps.tachyon",
    ],
    "Social Media": [
        "com.instagram.android", "com.facebook.katana", "com.snapchat.android", "com.twitter.android", "com.linkedin.android",
        "com.pinterest", "com.reddit.frontpage", "in.mohalla.sharechat", "com.threads.android", "com.instagram.barcelona",
    ],
    "Entertainment": [
        "com.spotify.music", "com.google.android.youtube", "com.netflix.mediaclient", "in.startv.hotstar", "com.jio.media.jiobeats",
        "com.amazon.avod.thirdpartyclient", "com.gaana", "com.bt.bms", "com.jio.media.ondemand", "com.google.android.apps.youtube.music",
    ],
    "Health": [
        "com.google.android.apps.fitness", "com.practo.fabric", "com.healthifyme.basic", "com.sec.android.app.shealth",
        "com.curefit.android", "com.phonegap.rxpal", "com.netmedsmarketplace.netmeds", "com.aranoah.healthkart.plus",
    ],
    "Productivity": [
        "com.google.android.apps.docs", "com.google.android.calendar", "com.google.android.keep", "notion.id",
        "com.google.android.apps.tasks", "com.dropbox.android", "com.microsoft.office.outlook", "com.microsoft.office.word",
        "com.android.chrome", "com.google.android.apps.photos", "com.google.android.calculator", "com.google.android.deskclock",
    ],
    "Security and Identity": [
        "com.google.android.apps.authenticator2", "com.azure.authenticator", "com.digilocker.android",
        "in.gov.uidai.mAadhaarPlus", "com.lastpass.lpandroid", "com.x8bit.bitwarden", "com.google.android.apps.walletnfcrel",
    ],
}
BY_PACKAGE = {pkg: cat for cat, pkgs in KNOWN.items() for pkg in pkgs}

# Keyword rules on "package label" -- only for packages not in the map above.
RULES = [
    ("Bank", re.compile(r"\bbank|banking|\bsbi\b|yono|hdfc|icici|kotak|\bupi\b|phonepe|paytm|google pay|\bbhim\b|\bcred\b", re.I)),
    ("Food and Grocery", re.compile(r"zomato|swiggy|grocery|blinkit|zepto|bigbasket|\bfood\b|restaurant|pizza", re.I)),
    ("Shopping", re.compile(r"shopping|\bshop\b|\bstore\b|mart\b|amazon|flipkart|myntra|meesho", re.I)),
    ("Travel and Booking", re.compile(r"travel|booking|flight|\btrain|\bbus\b|\bcab\b|hotel|irctc|redbus|\bola\b|uber|rapido", re.I)),
    ("Maps and Navigation", re.compile(r"\bmaps?\b|navigation|\bgps\b", re.I)),
    ("Health", re.compile(r"health|fitness|\bfit\b|medic|pharma|doctor|hospital|clinic", re.I)),
    ("Security and Identity", re.compile(r"authenticator|password|vault|aadhaar|digilocker|\bwallet\b", re.I)),
    ("Chat and Communication", re.compile(r"messag|\bchat\b|\bmail\b|dialer|\bphone\b|contacts|\bsms\b", re.I)),
    ("Social Media", re.compile(r"social|instagram|facebook|twitter|snapchat|linkedin", re.I)),
    ("Entertainment", re.compile(r"music|video|movie|\bgame|player|\bradio\b|podcast|\btv\b", re.I)),
    ("Productivity", re.compile(r"docs|calendar|notes|office|drive|calculator|clock|files|scanner", re.I)),
]


def classify(package: str, label: str | None = None) -> str:
    if package in BY_PACKAGE:
        return BY_PACKAGE[package]
    text = f"{package} {label or ''}"
    return next((cat for cat, rule in RULES if rule.search(text)), "Other")


# ── The registry (capabilities.js): every method's real state for one member's app ───────────────────────────────

def _cap(method: str, status: str, types: list[str], note: str) -> dict:
    return {"method": method, "status": status, "supported_data_types": types, "note": note}


def capabilities(email: str, package: str, category: str, collect: bool) -> list[dict]:
    types = DATA_TYPES.get(category, [])
    caps = []
    api = REGISTERED_APIS.get(package)
    caps.append(_cap("api", "available", api, "A configured service API.") if api
                else _cap("api", "unsupported", [], "No service API is configured for this app."))
    mcp = REGISTERED_MCP.get(package)
    caps.append(_cap("mcp", "available", mcp, "A configured MCP server.") if mcp
                else _cap("mcp", "unsupported", [], "No MCP server is configured for this app."))

    email_types = EMAIL_TYPES.get(category, [])
    account = store.google_account(email)
    if not email_types:
        caps.append(_cap("email", "unsupported", [], "This kind of app doesn't usually send its data by email."))
    elif not settings.google_client_id:
        caps.append(_cap("email", "unsupported", [], "No Google OAuth client is configured."))
    elif account is None or google.GMAIL_SCOPE not in account["scopes"]:
        caps.append(_cap("email", "requires_connection", email_types, "Sign in with Google and allow Gmail to use emails from this app."))
    else:
        caps.append(_cap("email", "unverified", email_types, "Gmail is connected; checked against this app's senders."))

    own, anyn = store.notification_counts(email, package)
    if own:
        caps.append(_cap("phone_data", "available", [NOTIFICATIONS], f"{own} notification{'' if own == 1 else 's'} from this app already collected."))
    elif anyn:
        caps.append(_cap("phone_data", "unverified", [NOTIFICATIONS], "No notifications from this app collected yet."))
    else:
        caps.append(_cap("phone_data", "requires_permission", [NOTIFICATIONS], "Notifications are not collected yet: switch them on in Data sources and allow Notification access."))

    caps.append(_cap("mobile_use", "available", types, "The phone agent can read what the app shows (allow FamilyOS under Accessibility).") if collect
                else _cap("mobile_use", "requires_permission", types, "Collecting is switched off for this app."))

    site = SITE_FOR.get(package)
    if not types:
        caps.append(_cap("browser_use", "unsupported", [], "Nothing for a browser to read for this kind of app."))
    elif site and store.site_account(email, site):
        caps.append(_cap("browser_use", "available", types, "Its sign-in is in Connected services; the browser agent can read it."))
    elif site:
        caps.append(_cap("browser_use", "requires_connection", types, f"Add {vault.BY_ID[site]['name']} under Connected services on the web."))
    else:
        caps.append(_cap("browser_use", "requires_connection", types, "Add its website under Connected services (Another site) on the web."))
    return caps


# ── Validation (decisionLayer.js) ───────────────────────────────────────────────────────────────────────────────

_DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", re.I)
_ADDRESS_DOMAIN = re.compile(r"@([a-z0-9.-]+)", re.I)


def clean_text(s, limit: int = 200) -> str:
    """Plain one-line text only (no code fences, markup or newlines), capped."""
    s = re.sub(r"```[\s\S]*?```", "", str(s or ""))
    s = re.sub(r"[`<>{}]", "", s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def valid_domains(found) -> list[str]:
    domains = [str(d).strip().lower().lstrip("@") for d in (found if isinstance(found, list) else [])]
    return [d for d in domains if _DOMAIN.match(d)][:5]


def _sent_by(sender: str, domains: list[str]) -> bool:
    m = _ADDRESS_DOMAIN.search(sender or "")
    host = m.group(1).lower().rstrip(".") if m else ""
    return any(host == d or host.endswith("." + d) for d in domains)


class NotConnected(Exception):
    pass


async def _gmail_count(email: str, senders: list[str], transport=None) -> int:
    """Mail from these senders in the last 90 days, asked of Gmail itself (read-only, at most one message listed)."""
    from familyos.intake import mailbox
    refresh = store.google_refresh_token(email)
    if refresh is None:
        raise NotConnected
    client_id, client_secret = mailbox._require_client()
    token = await google.refresh(refresh, client_id=client_id, client_secret=client_secret, transport=transport)
    found, _ = await google.list_messages(token.access_token, query=f"from:({' OR '.join(senders)}) newer_than:90d",
                                          limit=1, transport=transport)
    return len(found)


async def _mail_from(email: str, senders: list[str]) -> int:
    cached = sum(1 for s in store.gmail_senders(email) if _sent_by(s, senders))
    return cached or await _gmail_count(email, senders)


async def validate(proposal, caps: list[dict], requested: list[str], *, email: str, package: str,
                   ask_senders=None) -> tuple[list[dict], list[str]]:
    """Validated, prioritised methods from the model's proposal and the registry, and what was rejected (for the log).
    `ask_senders` (optional) asks the model only for the app's sender domains, when nothing else names them."""
    rejected: list[str] = []
    proposed: dict[str, dict] = {}
    for p in proposal if isinstance(proposal, list) else []:
        method = p.get("method", "").strip().lower() if isinstance(p, dict) and isinstance(p.get("method"), str) else ""
        if method not in METHODS:
            rejected.append(f'unknown method "{clean_text(p.get("method") if isinstance(p, dict) else p, 40)}"')
            continue
        proposed.setdefault(method, p)

    methods = []
    for cap in caps:
        p = proposed.get(cap["method"], {})
        allowed = [t for t in cap["supported_data_types"] if t in requested]
        offered = [t for t in p.get("supported_data_types") or [] if isinstance(t, str)] if isinstance(p.get("supported_data_types"), list) else []
        bad = [t for t in offered if t not in allowed]
        if bad:
            rejected.append(f"{cap['method']}: invalid data types {', '.join(bad[:3])}")
        good = [t for t in offered if t in allowed]
        entry = {"method": cap["method"], "status": cap["status"], "supported_data_types": good or allowed, "reason": cap["note"]}

        if cap["method"] == "email" and cap["status"] == "unverified":
            # The maintained list and the model's suggestions together (either alone can miss a sender).
            senders = list(dict.fromkeys([*KNOWN_SENDERS.get(package, []), *valid_domains(p.get("email_senders"))]))[:5]
            if not senders and ask_senders:
                try:
                    senders = valid_domains(await ask_senders())
                except Exception:       # noqa: BLE001 -- no senders is an answer too
                    senders = []
            if not senders:
                entry["reason"] = "Gmail is connected, but no sender for this app was identified."
            else:
                try:
                    found = await _mail_from(email, senders)
                    entry["status"] = "available" if found else "unverified"
                    entry["reason"] = (f"Recent emails from {', '.join(senders)} found in Gmail." if found
                                       else f"No emails from {', '.join(senders)} in the last 90 days.")
                except (NotConnected, google.NeedsReconnect):
                    entry["status"] = "requires_connection"
                    entry["reason"] = "Sign in with Google again and allow Gmail to use emails from this app."
                except Exception as exc:    # noqa: BLE001 -- said, not raised: the other methods still stand
                    entry["status"] = "temporarily_unavailable"
                    entry["reason"] = f"Gmail check failed: {clean_text(exc, 120)}"
        elif p.get("reason") and cap["status"] == "available":
            # The model's short explanation only where the method is actually available; for any other status the
            # registry's factual note is shown (no "can collect…" promises).
            entry["reason"] = clean_text(p["reason"]) or cap["note"]
        methods.append(entry)
    methods.sort(key=lambda m: METHODS.index(m["method"]))
    for i, m in enumerate(methods, 1):
        m["priority"] = i
    return methods, rejected


# ── The model ───────────────────────────────────────────────────────────────────────────────────────────────────

async def _ask_model(body: dict) -> list:
    """Qwen3.5's candidate methods (the model server's /methods); raises when the server is not there or fails."""
    import httpx
    async with httpx.AsyncClient(timeout=settings.collect_model_timeout_s) as client:
        r = await client.post(settings.collect_model_url.rstrip("/") + "/methods", json=body)
    r.raise_for_status()
    found = r.json().get("candidate_methods")
    return found if isinstance(found, list) else []


_lock: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None


def _model_lock() -> asyncio.Lock:
    """One question to the local model at a time (it is one model on this Mac)."""
    global _lock
    loop = asyncio.get_running_loop()
    if _lock is None or _lock[0] is not loop:
        _lock = (loop, asyncio.Lock())
    return _lock[1]


async def _propose(body: dict) -> list:
    async with _model_lock():
        return await _ask_model(body)


async def analyze(email: str, app: dict) -> dict:
    """The decision for one of the member's apps: {category, methods, model}."""
    package, label = app["package"], app.get("label") or app["package"]
    category = classify(package, label)
    requested = [*DATA_TYPES.get(category, []), NOTIFICATIONS]
    caps = capabilities(email, package, category, bool(app.get("collect")))
    ident = {"package_name": package, "display_name": label, "category": category}
    model: str | None = "qwen3.5"
    try:
        proposal = await _propose({"app": ident, "requested_data_types": requested, "available_capabilities": caps})
    except Exception as exc:        # noqa: BLE001 -- the registry alone still decides
        logger.info("decide: the model was not reachable (%s); deciding %s from the registry alone", type(exc).__name__, package)
        proposal, model = [], None

    email_cap = next(c for c in caps if c["method"] == "email")

    async def ask_senders() -> list:
        r = await _propose({"app": ident, "requested_data_types": email_cap["supported_data_types"],
                            "available_capabilities": [{**email_cap, "note": "List the sender domains this app emails from."}]})
        return next((m.get("email_senders") or [] for m in r if isinstance(m, dict) and m.get("method") == "email"), [])

    methods, rejected = await validate(proposal, caps, requested, email=email, package=package,
                                       ask_senders=ask_senders if model else None)
    if rejected:
        logger.info("decide: %s: rejected from model output: %s", package, "; ".join(rejected))
    return {"category": category, "methods": methods, "model": model}


# ── In the background, into the local cache ─────────────────────────────────────────────────────────────────────

_running: dict[tuple[str, str], asyncio.Task] = {}


async def _run(email: str, app: dict) -> None:
    category = classify(app["package"], app.get("label"))
    try:
        found = await analyze(email, app)
        store.set_analysis(email, app["package"], category=found["category"], status="completed",
                           methods=found["methods"], model=found["model"])
    except Exception as exc:        # noqa: BLE001 -- kept as a failed decision, with what went wrong
        logger.warning("decide: %s failed: %s", app["package"], exc)
        store.set_analysis(email, app["package"], category=category, status="failed", error=clean_text(exc, 200))


def start(email: str, package: str) -> bool | None:
    """Decide (again) for one app in the background. None: no such app on the member's phone; False: already deciding."""
    email = (email or "").strip().lower()
    app = next((a for a in store.apps(email) if a["package"] == package), None)
    if app is None:
        return None
    going = _running.get((email, package))
    if going and not going.done():
        return False
    store.set_analysis(email, package, category=classify(package, app.get("label")), status="pending")
    _running[(email, package)] = asyncio.get_running_loop().create_task(_run(email, app))
    return True


def start_new(email: str, *, again: bool = False) -> int:
    """Decide for every app switched on that has no decision yet (or a failed one; with `again`, every one)."""
    done = store.analyses(email)
    started = 0
    for a in store.apps(email):
        prior = done.get(a["package"])
        if a["collect"] and (again or prior is None or prior["status"] == "failed" or _lost(email, prior)):
            started += bool(start(email, a["package"]))
    return started


def _lost(email: str, prior: dict) -> bool:
    """Pending with nothing running: the server stopped before it finished."""
    going = _running.get(((email or "").strip().lower(), prior["package"]))
    return prior["status"] == "pending" and not (going and not going.done())


def results(email: str) -> list[dict]:
    """The decision for each app switched on, in the phone's order."""
    done = store.analyses(email)
    out = []
    for a in store.apps(email):
        if not a["collect"]:
            continue
        d = done.get(a["package"]) or {"status": "none", "methods": [], "error": None, "model": None,
                                       "category": classify(a["package"], a["label"]), "analyzed_at": None}
        if _lost(email, {**d, "package": a["package"]}):
            d = {**d, "status": "failed", "error": "Stopped before it finished. Check again."}
        out.append({"package": a["package"], "label": a["label"], "category": d["category"], "status": d["status"],
                    "methods": d["methods"], "error": d["error"], "model": d["model"], "analyzed_at": d["analyzed_at"]})
    return out
