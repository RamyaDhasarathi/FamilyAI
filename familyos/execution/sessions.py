"""Class 2 custody: one service's session, sealed, lent for one task.

The pattern every comparable product uses is a **persistent browser profile**
on disk inside the agent's container. A live cookie jar is a credential, so
that leaves a credential sitting in the execution environment for its whole
life: anything that reads the container's filesystem has the family's school
portal login.

Here the session is sealed under the household key and unsealed into a task
for the length of that task only. Three consequences follow:

  * Destroying the household key makes every stored session unreadable at
    once, so erasure reaches a logged-in service.
  * A session sealed for one household or one service will not open for
    another, because both are bound into the AAD rather than checked in code.
  * Nothing re-authenticates by itself. When a session lapses the member signs
    in again by takeover -- an agent that can re-acquire a credential on its
    own is a class-2 container pretending to be class 1.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import uuid
from dataclasses import dataclass, field

from familyos import audit, crypto
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 30
MAX_DAYS = 90


class SessionLapsed(Invalid):
    """The stored session is gone, revoked or past its date. The member signs
    in again by takeover; nothing here will do it for them."""


def _aad(household_id: uuid.UUID, member_id: uuid.UUID, service: str) -> bytes:
    """Bound to the household, the member and the service. A sealed session
    moved to any other row simply will not open -- the check is the cipher's,
    not a line of code someone can forget."""
    return household_id.bytes + member_id.bytes + b"session:" + service.encode()


@dataclass(frozen=True)
class SessionState:
    """What a browser needs to look like the same browser it was last time.
    `storage` is the page's localStorage and sessionStorage by origin: a
    single-page app keeps its sign-in there as often as in a cookie."""
    cookies: list[dict] = field(default_factory=list)
    fingerprint: dict = field(default_factory=dict)
    egress_id: str = ""
    storage: dict = field(default_factory=dict)

    def as_bytes(self) -> bytes:
        return json.dumps({"cookies": self.cookies, "fingerprint": self.fingerprint,
                           "egress_id": self.egress_id, "storage": self.storage}, sort_keys=True).encode()

    @staticmethod
    def from_bytes(raw: bytes) -> SessionState:
        body = json.loads(raw.decode())
        return SessionState(cookies=body.get("cookies") or [],
                            fingerprint=body.get("fingerprint") or {},
                            egress_id=body.get("egress_id") or "",
                            storage=body.get("storage") or {})

    def as_browser_context(self) -> dict:
        """The shape a browser session is opened with to hold this again."""
        out = {"cookies": self.cookies}
        for key in ("localStorage", "sessionStorage"):
            if self.storage.get(key):
                out[key] = self.storage[key]
        return out


def _clean_service(raw: str) -> str:
    service = (raw or "").strip().lower()
    if not service:
        raise Invalid("name the service this session is for")
    return service


async def store(p: Principal, *, service: str, state: SessionState, allow_hosts: list[str],
                days: int = DEFAULT_DAYS) -> dict:
    """Keep what a human sign-in produced. Only ever called after a takeover:
    there is no path here that types a password."""
    name = _clean_service(service)
    hosts = sorted({h.strip().lower() for h in allow_hosts if h.strip()})
    if not hosts:
        raise Invalid("say which origins this session may reach")
    if not 1 <= days <= MAX_DAYS:
        raise Invalid(f"a session lasts between 1 and {MAX_DAYS} days")

    async with pool().acquire() as conn, conn.transaction():
        key = await conn.fetchval("SELECT wrapped_key FROM households WHERE id = $1", p.household_id)
        sealed = crypto.seal(crypto.unwrap(p.household_id, key), state.as_bytes(),
                             _aad(p.household_id, p.member_id, name))
        # Replacing a sign-in revokes the one it replaces, so a stale cookie
        # jar cannot be restored afterwards.
        await conn.execute(
            "UPDATE sealed_sessions SET revoked_at = NOW() WHERE household_id = $1 AND member_id = $2 "
            "AND service = $3 AND revoked_at IS NULL", p.household_id, p.member_id, name)
        row = await conn.fetchrow(
            "INSERT INTO sealed_sessions (id, household_id, member_id, service, allow_hosts, sealed_state, "
            "expires_at) VALUES ($1, $2, $3, $4, $5, $6, NOW() + make_interval(days => $7)) RETURNING *",
            uuid.uuid4(), p.household_id, p.member_id, name, hosts, sealed, days)
        await audit.record(p.household_id, "session.stored", actor_member_id=p.member_id,
                           target_type="session", target_id=row["id"],
                           detail={"service": name, "hosts": hosts, "days": days}, conn=conn)
    return dict(row)


async def revoke(p: Principal, session_id: uuid.UUID) -> dict:
    row = await pool().fetchrow(
        "UPDATE sealed_sessions SET revoked_at = NOW() WHERE id = $1 AND household_id = $2 "
        "AND member_id = $3 AND revoked_at IS NULL RETURNING *", session_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("session")
    await audit.record(p.household_id, "session.revoked", actor_member_id=p.member_id,
                       target_type="session", target_id=session_id, detail={"service": row["service"]})
    return dict(row)


async def list_for(p: Principal) -> list[dict]:
    """What is signed in, and nothing of what it holds."""
    rows = await pool().fetch(
        "SELECT id, service, allow_hosts, expires_at, last_used_at, uses, created_at "
        "FROM sealed_sessions WHERE household_id = $1 AND member_id = $2 AND revoked_at IS NULL "
        "ORDER BY created_at DESC", p.household_id, p.member_id)
    return [dict(r) for r in rows]


@contextlib.asynccontextmanager
async def lease(p: Principal, service: str, *, reason: str):
    """Unseal a session for the length of one task, and no longer.

    Yields a `Lease` carrying the state and the origins it may reach. The
    caller is the driver; nothing above it -- and no model -- is handed this.
    """
    name = _clean_service(service)
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM sealed_sessions WHERE household_id = $1 AND member_id = $2 AND service = $3 "
            "AND revoked_at IS NULL", p.household_id, p.member_id, name)
        if row is None:
            raise SessionLapsed(f"nobody has signed in to {name}; a member has to do that themselves")
        if row["expires_at"] <= dt.datetime.now(dt.UTC):
            raise SessionLapsed(f"the {name} session has lapsed; sign in again to continue")
        key = await conn.fetchval("SELECT wrapped_key FROM households WHERE id = $1", p.household_id)

    try:
        state = SessionState.from_bytes(crypto.open_sealed(
            crypto.unwrap(p.household_id, key), row["sealed_state"],
            _aad(p.household_id, p.member_id, name)))
    except Exception as exc:  # noqa: BLE001 - an unreadable session is a lapsed one
        logger.warning("session %s could not be opened", row["id"], exc_info=True)
        raise SessionLapsed(f"the stored {name} session could not be read; sign in again") from exc

    await audit.record(p.household_id, "session.opened", actor_member_id=p.member_id,
                       target_type="session", target_id=row["id"],
                       detail={"service": name, "reason": reason[:200]})
    held = Lease(session_id=row["id"], service=name, state=state,
                 allow_hosts=frozenset(row["allow_hosts"]))
    try:
        yield held
    finally:
        # Said whether the task worked or not: the useful question later is
        # when a credential was in play, not whether it helped.
        await pool().execute(
            "UPDATE sealed_sessions SET last_used_at = NOW(), uses = uses + 1 WHERE id = $1", row["id"])
        await audit.record(p.household_id, "session.closed", actor_member_id=p.member_id,
                           target_type="session", target_id=row["id"], detail={"service": name})
        held.forget()


@dataclass
class Lease:
    """A session, in the open, for one task. `forget()` is called for you when
    the lease ends."""
    session_id: uuid.UUID
    service: str
    state: SessionState
    allow_hosts: frozenset[str]
    _spent: bool = False

    def forget(self) -> None:
        self.state = SessionState()
        self._spent = True

    @property
    def live(self) -> bool:
        return not self._spent

    def __repr__(self) -> str:  # pragma: no cover - a safety net for logs
        return f"<Lease {self.service} session={self.session_id} live={self.live}>"


def describe() -> str:
    return ("execution class 2 (session-persistent): one service, sealed under the household key, "
            "unsealed for one task; nothing re-authenticates on its own")


# ----------------------------------------------------------------------------
# the sign-in sitting: how a sealed session comes to exist
# ----------------------------------------------------------------------------

SITTING_MINUTES = 20


class SittingBusy(Invalid):
    """One browser, one sitting, deployment-wide (see harvest.begin)."""


def _hosts_match(cookie_domain: str, hosts: list[str]) -> bool:
    d = (cookie_domain or "").lstrip(".").lower()
    return any(d == h or d.endswith("." + h) or h.endswith("." + d) for h in hosts)


async def begin_sign_in(p: Principal, service: str) -> dict:
    """Open a browser on the site's sign-in page for the member to use.

    Nothing is typed for them and nothing is asked of them here but to sign
    in as they would on their own phone. The sitting is short, because a
    browser signed in to a family's account should not sit idle.
    """
    from familyos.execution import sites, steel
    try:
        site = sites.get(service)
    except KeyError:
        raise Invalid("that site is not one FamilyOS can sign in to") from None
    async with pool().acquire() as conn:
        busy = await conn.fetchrow(
            "SELECT 1 FROM sign_in_sittings WHERE state = 'open' AND expires_at > NOW() "
            "UNION ALL SELECT 1 FROM harvests WHERE state IN ('collecting', 'review') AND expires_at > NOW() LIMIT 1")
    if busy is not None:
        raise SittingBusy("a sitting is already open; finish it before starting another")
    session = await steel.current_browser().open_at(site["login_url"], minutes=SITTING_MINUTES)
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "INSERT INTO sign_in_sittings (id, household_id, member_id, service, browser_session_id, live_url, ws_url, expires_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, NOW() + make_interval(mins => $8)) RETURNING *",
            uuid.uuid4(), p.household_id, p.member_id, site["service"], session.get("session_id"),
            session.get("live_url"), session.get("websocket_url"), SITTING_MINUTES)
        await audit.record(p.household_id, "sign_in.began", actor_member_id=p.member_id, target_type="sign_in",
                           target_id=row["id"], detail={"service": site["service"]}, conn=conn)
    return {**dict(row), "label": site["label"], "how": site["how"], "hosts": site["hosts"],
            "user_agent": session.get("user_agent"), "dimensions": session.get("dimensions") or {}}


async def open_sign_in(p: Principal) -> dict | None:
    """The member's own open sitting, if any."""
    from familyos.execution import sites
    row = await pool().fetchrow(
        "SELECT * FROM sign_in_sittings WHERE household_id = $1 AND member_id = $2 AND state = 'open' "
        "AND expires_at > NOW() ORDER BY created_at DESC LIMIT 1", p.household_id, p.member_id)
    if row is None:
        return None
    site = sites.get(row["service"])
    return {**dict(row), "label": site["label"], "how": site["how"], "hosts": site["hosts"]}


async def seal_sign_in(p: Principal, sitting_id: uuid.UUID, *, days: int = DEFAULT_DAYS) -> dict:
    """The member says they are in. What the browser holds for the site's own
    origins is sealed as a session; everything else the browser holds is
    dropped with the browser. No cookie for the site means they are not in
    yet, and nothing is stored."""
    from familyos.execution import sites, steel
    row = await pool().fetchrow(
        "SELECT * FROM sign_in_sittings WHERE id = $1 AND household_id = $2 AND member_id = $3 AND state = 'open'",
        sitting_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("sitting")
    if row["expires_at"] <= dt.datetime.now(dt.UTC):
        raise Invalid("that sitting has ended; open another")
    site = sites.get(row["service"])
    held = await steel.current_browser().context(row["browser_session_id"])
    cookies = [c for c in (held.get("cookies") or []) if _hosts_match(c.get("domain", ""), site["hosts"])]
    storage = {}
    for key in ("localStorage", "sessionStorage"):
        kept = {origin: values for origin, values in (held.get(key) or {}).items()
                if _hosts_match(origin.split("//")[-1].split(":")[0], site["hosts"])}
        if kept:
            storage[key] = kept
    if not sites.signed_in(site["service"], cookies):
        raise Invalid(f"the browser is not signed in to {site['label']} yet \u2014 finish the OTP step, then press the button again")
    state = SessionState(cookies=cookies, fingerprint={"user_agent": held.get("userAgent") or ""}, storage=storage)
    stored = await store(p, service=site["service"], state=state, allow_hosts=site["hosts"], days=days)
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("UPDATE sign_in_sittings SET state = 'sealed', ended_at = NOW() WHERE id = $1", sitting_id)
        await audit.record(p.household_id, "sign_in.sealed", actor_member_id=p.member_id, target_type="sign_in",
                           target_id=sitting_id, detail={"service": site["service"], "cookies": len(cookies),
                                                         "storage_origins": sum(len(v) for v in storage.values())}, conn=conn)
    await steel.current_browser().release(row["browser_session_id"])
    return {**stored, "label": site["label"]}


async def abandon_sign_in(p: Principal, sitting_id: uuid.UUID) -> None:
    from familyos.execution import steel
    row = await pool().fetchrow(
        "UPDATE sign_in_sittings SET state = 'abandoned', ended_at = NOW() WHERE id = $1 AND household_id = $2 "
        "AND member_id = $3 AND state = 'open' RETURNING *", sitting_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("sitting")
    await audit.record(p.household_id, "sign_in.abandoned", actor_member_id=p.member_id, target_type="sign_in",
                       target_id=sitting_id, detail={"service": row["service"]})
    await steel.current_browser().release(row["browser_session_id"])


async def sweep_sittings() -> int:
    """A sitting nobody sealed or abandoned ends with its clock: the browser
    is released, so a signed-in page does not sit open."""
    from familyos.execution import steel
    rows = await pool().fetch(
        "UPDATE sign_in_sittings SET state = 'abandoned', ended_at = NOW() WHERE state = 'open' AND expires_at <= NOW() "
        "RETURNING id, browser_session_id")
    for r in rows:
        await steel.current_browser().release(r["browser_session_id"])
    return len(rows)


# ----------------------------------------------------------------------------
# the live view's ticket: one socket, one sitting, one minute to use it
# ----------------------------------------------------------------------------

import secrets  # noqa: E402 - after the module's own names it needs
import time  # noqa: E402 - after the module's own names it needs

_live_tickets: dict[str, tuple[uuid.UUID, float]] = {}
LIVE_TICKET_SECONDS = 60


async def issue_live_ticket(p: Principal, sitting_id: uuid.UUID) -> str:
    """A one-time ticket for the member's own open sitting. A browser cannot
    put a bearer token on a websocket, and a token in a query string would
    end up in logs; a ticket that dies in a minute, or on first use, does
    not."""
    row = await pool().fetchrow(
        "SELECT id, ws_url FROM sign_in_sittings WHERE id = $1 AND household_id = $2 AND member_id = $3 "
        "AND state = 'open' AND expires_at > NOW()", sitting_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("sitting")
    if not row["ws_url"]:
        raise Invalid("this sitting has no browser socket to show")
    now = time.monotonic()
    for t, (_, until) in list(_live_tickets.items()):
        if until < now:
            del _live_tickets[t]
    ticket = secrets.token_urlsafe(24)
    _live_tickets[ticket] = (sitting_id, now + LIVE_TICKET_SECONDS)
    return ticket


async def redeem_live_ticket(ticket: str, sitting_id: uuid.UUID) -> dict | None:
    held = _live_tickets.pop(ticket or "", None)
    if held is None or held[0] != sitting_id or held[1] < time.monotonic():
        return None
    row = await pool().fetchrow("SELECT * FROM sign_in_sittings WHERE id = $1 AND state = 'open' AND expires_at > NOW()", sitting_id)
    return dict(row) if row else None


# The same ticket, for an errand that stopped and handed the person its browser.
_errand_tickets: dict[str, tuple[uuid.UUID, str, float]] = {}


async def issue_errand_live_ticket(p: Principal, errand_id: uuid.UUID) -> str:
    row = await pool().fetchrow("SELECT outcome, status, created_by FROM errands WHERE id = $1 AND household_id = $2", errand_id, p.household_id)
    if row is None:
        raise NotFound("errand")
    ws_url = ((row["outcome"] or {}).get("browser") or {}).get("ws_url")
    if row["status"] != "needs_you" or not ws_url:
        raise Invalid("this errand is not waiting on you in a browser")
    if row["created_by"] != p.member_id:
        raise NotAllowed("the browser holds the session of whoever asked; only they may take it over")
    now = time.monotonic()
    for t, (_, _, until) in list(_errand_tickets.items()):
        if until < now:
            del _errand_tickets[t]
    ticket = secrets.token_urlsafe(24)
    _errand_tickets[ticket] = (errand_id, ws_url, now + LIVE_TICKET_SECONDS)
    return ticket


def redeem_errand_live_ticket(ticket: str, errand_id: uuid.UUID) -> str | None:
    held = _errand_tickets.pop(ticket or "", None)
    if held is None or held[0] != errand_id or held[2] < time.monotonic():
        return None
    return held[1]
