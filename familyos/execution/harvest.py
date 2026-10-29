"""An assisted harvest: one sitting, a person present, nothing kept afterwards.

Class 1 holds no credential, so it reaches only public pages. Class 2 holds one
service's session between tasks -- powerful, and it leaves a live credential in
custody. Between them is the case a family actually has first: *pull three
years of circulars off the school portal, once.*

The member signs in themselves. Pages collected become candidates they read and
choose from. When the sitting ends, nothing survives but what they picked:
no cookies, no fingerprint, no session row. Weaker than class 2 in reach, and
stronger in custody, because there is nothing left to steal.

The rule this exists to keep: **a harvest never stores a session.** It is
asserted in a test rather than trusted to a comment.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Protocol

from familyos import artifacts, audit, crypto
from familyos.db import pool
from familyos.execution import disposable
from familyos.identity import Invalid, NotFound, Principal

logger = logging.getLogger(__name__)

DEFAULT_MINUTES = 90
MAX_MINUTES = 240
MAX_CANDIDATES = 300


class Busy(Invalid):
    """Another sitting is open and the browser holds one at a time. Said rather
    than quietly evicting whoever got there first."""


class HarvestClosed(Invalid):
    """The sitting is over. Start another rather than reopening this one."""


def _aad(household_id: uuid.UUID, harvest_id: uuid.UUID, digest: str) -> bytes:
    return household_id.bytes + harvest_id.bytes + bytes.fromhex(digest)


class NoCollector(Invalid):
    """Nothing is configured to drive a browser, so a sitting cannot be opened.
    Said plainly rather than opening one that can never collect anything."""


class Collector(Protocol):
    """The seam a browser plugs into.

    `open` returns somewhere the member can watch and drive -- a live view --
    and `close` ends the session. Pages arrive back through `offer`, which is
    the only way anything enters a sitting.

    Steel (Apache-2.0, self-hostable) or Browserbase satisfy this, driven by
    Playwright. Neither changes anything above this line.
    """

    async def open(self, *, allow_hosts: frozenset[str], minutes: int) -> dict:
        ...

    async def close(self, session: dict) -> None:
        ...


class ManualCollector:
    """The default: no browser of ours, and no live view.

    A sitting still works -- pages are handed in by whoever collected them,
    which is how an offline import or a desktop browser would do it. What it
    cannot do is show the member a browser to drive, so the console says so
    rather than rendering an empty frame.
    """

    async def open(self, *, allow_hosts: frozenset[str], minutes: int) -> dict:
        return {}

    async def close(self, session: dict) -> None:
        return None


_collector: Collector = ManualCollector()


def use_collector(collector: Collector) -> None:
    global _collector
    _collector = collector


def current_collector() -> Collector:
    return _collector


async def begin(p: Principal, *, label: str, allow_hosts: list[str],
                minutes: int = DEFAULT_MINUTES) -> dict:
    """Open a sitting. No credential is taken and none is asked for: whoever is
    signing in does it themselves, in front of the browser."""
    name = (label or "").strip()
    hosts = sorted({h.strip().lower() for h in allow_hosts if h.strip()})
    if not name:
        raise Invalid("say what this sitting is for")
    if not hosts:
        raise Invalid("name the site this sitting may reach")
    if not 1 <= minutes <= MAX_MINUTES:
        raise Invalid(f"a sitting lasts between 1 and {MAX_MINUTES} minutes")
    for host in hosts:
        disposable.approved(f"https://{host}/", frozenset(hosts))

    # One sitting at a time, deployment-wide, while the browser behind it holds
    # one session. Steel's single container silently *replaces* a live session
    # when a second is asked for: the first member's view goes dead with no
    # explanation, and whatever their browser was signed into is still loaded.
    # Refusing is the honest behaviour until a container per sitting exists.
    if not isinstance(current_collector(), ManualCollector):
        async with pool().acquire() as conn:
            busy = await conn.fetchrow(
                "SELECT household_id, member_id FROM harvests "
                "WHERE state IN ('collecting', 'review') AND expires_at > NOW() LIMIT 1")
        if busy is not None:
            raise Busy("a sitting is already open; finish it before starting another")

    # Opened before the row is written: a sitting that cannot collect anything
    # should not exist, and the member should be told why rather than shown an
    # empty screen.
    session = await current_collector().open(allow_hosts=frozenset(hosts), minutes=minutes)
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "INSERT INTO harvests (id, household_id, member_id, label, allow_hosts, expires_at, live_url) "
            "VALUES ($1, $2, $3, $4, $5, NOW() + make_interval(mins => $6), $7) RETURNING *",
            uuid.uuid4(), p.household_id, p.member_id, name, hosts, minutes,
            (session or {}).get("live_url"))
        await audit.record(p.household_id, "harvest.began", actor_member_id=p.member_id,
                           target_type="harvest", target_id=row["id"],
                           detail={"hosts": hosts, "minutes": minutes}, conn=conn)
    return dict(row)


async def _open_harvest(conn, p: Principal, harvest_id: uuid.UUID, *, states: tuple[str, ...]) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM harvests WHERE id = $1 AND household_id = $2 AND member_id = $3 FOR UPDATE",
        harvest_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("harvest")
    if row["state"] not in states:
        raise HarvestClosed(f"this sitting is {row['state']}")
    if row["expires_at"] <= dt.datetime.now(dt.UTC):
        raise HarvestClosed("this sitting has ended; start another")
    return dict(row)


async def offer(p: Principal, harvest_id: uuid.UUID, page: disposable.Page) -> dict:
    """A page collected during the sitting. It is a candidate and nothing more
    -- no claim, no obligation, not yet an artifact."""
    async with pool().acquire() as conn, conn.transaction():
        harvest = await _open_harvest(conn, p, harvest_id, states=("collecting",))
        disposable.approved(page.url, frozenset(harvest["allow_hosts"]))
        held = await conn.fetchval(
            "SELECT count(*) FROM harvest_candidates WHERE harvest_id = $1", harvest_id)
        if held >= MAX_CANDIDATES:
            raise Invalid(f"a sitting collects at most {MAX_CANDIDATES} pages")

        key = await artifacts.member_key(conn, p.household_id, p.member_id, create=True)
        row = await conn.fetchrow(
            "INSERT INTO harvest_candidates (id, harvest_id, household_id, member_id, url, title, "
            "sealed_text, sha256, bytes) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
            "ON CONFLICT (harvest_id, sha256) DO NOTHING RETURNING *",
            uuid.uuid4(), harvest_id, p.household_id, p.member_id, page.url, page.title,
            crypto.seal(key, page.text.encode(), _aad(p.household_id, harvest_id, page.sha256)),
            page.sha256, page.bytes)
        if row is None:
            existing = await conn.fetchrow(
                "SELECT * FROM harvest_candidates WHERE harvest_id = $1 AND sha256 = $2",
                harvest_id, page.sha256)
            return dict(existing)
    return dict(row)


async def list_for(p: Principal, *, live_only: bool = True) -> list[dict]:
    """A sitting belongs to the member who opened it, like a notice belongs to
    whoever forwarded it."""
    rows = await pool().fetch(
        "SELECT * FROM harvests WHERE household_id = $1 AND member_id = $2"
        + (" AND state IN ('collecting', 'review')" if live_only else "")
        + " ORDER BY started_at DESC LIMIT 20", p.household_id, p.member_id)
    return [dict(r) for r in rows]


async def candidates(p: Principal, harvest_id: uuid.UUID, *, undecided_only: bool = True) -> list[dict]:
    """What the member is choosing from, with the text, because a review screen
    that cannot show what is being approved is a consent button."""
    async with pool().acquire() as conn:
        harvest = await conn.fetchrow(
            "SELECT * FROM harvests WHERE id = $1 AND household_id = $2 AND member_id = $3",
            harvest_id, p.household_id, p.member_id)
        if harvest is None:
            raise NotFound("harvest")
        rows = await conn.fetch(
            "SELECT * FROM harvest_candidates WHERE harvest_id = $1"
            + (" AND decision IS NULL" if undecided_only else "") + " ORDER BY created_at",
            harvest_id)
        key = await artifacts.member_key(conn, p.household_id, p.member_id)
    out = []
    for row in rows:
        try:
            text = crypto.open_sealed(key, row["sealed_text"],
                                      _aad(p.household_id, harvest_id, row["sha256"])).decode()
        except Exception:  # noqa: BLE001 - an unreadable candidate is shown as such, not hidden
            logger.warning("candidate %s could not be opened", row["id"], exc_info=True)
            text = ""
        out.append({**dict(row), "text": text, "sealed_text": None})
    return out


async def keep(p: Principal, candidate_id: uuid.UUID) -> dict:
    """The member picked this one. Only now does it enter the record, through
    the same door as anything else, and private to them until they share it."""
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT c.*, h.allow_hosts FROM harvest_candidates c JOIN harvests h ON h.id = c.harvest_id "
            "WHERE c.id = $1 AND c.household_id = $2 AND c.member_id = $3 AND c.decision IS NULL FOR UPDATE OF c",
            candidate_id, p.household_id, p.member_id)
        if row is None:
            raise NotFound("candidate")
        key = await artifacts.member_key(conn, p.household_id, p.member_id)
        text = crypto.open_sealed(key, row["sealed_text"],
                                  _aad(p.household_id, row["harvest_id"], row["sha256"])).decode()
        body = f"{row['title']}\n{row['url']}\n\n{text}".encode()
        artifact, _ = await artifacts.create(conn, p.household_id, artifacts.NewArtifact(
            data=body, media_type="text/plain", channel="harvest", visibility="private",
            status="accepted", submitted_by=p.member_id,
            source={"url": row["url"], "title": row["title"], "collected_by": "harvest"},
            dedup_key=f"harvest:{row['harvest_id']}:{row['sha256']}"), actor_kind="member")
        await conn.execute(
            "UPDATE harvest_candidates SET decision = 'kept', decided_at = NOW(), artifact_id = $2 "
            "WHERE id = $1", candidate_id, artifact["id"])
        await audit.record(p.household_id, "harvest.kept", actor_member_id=p.member_id,
                           target_type="artifact", target_id=artifact["id"],
                           detail={"host": row["url"].split("/")[2] if "//" in row["url"] else ""}, conn=conn)
    return dict(artifact)


async def discard(p: Principal, candidate_id: uuid.UUID) -> dict:
    row = await pool().fetchrow(
        "UPDATE harvest_candidates SET decision = 'discarded', decided_at = NOW(), sealed_text = '\\x00'::bytea "
        "WHERE id = $1 AND household_id = $2 AND member_id = $3 AND decision IS NULL RETURNING *",
        candidate_id, p.household_id, p.member_id)
    if row is None:
        raise NotFound("candidate")
    return dict(row)


async def finish(p: Principal, harvest_id: uuid.UUID) -> dict:
    """End the sitting. Anything not picked goes, now rather than at expiry."""
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM harvests WHERE id = $1 AND household_id = $2 AND member_id = $3 FOR UPDATE",
            harvest_id, p.household_id, p.member_id)
        if row is None:
            raise NotFound("harvest")
        dropped = await conn.fetchval(
            "WITH gone AS (DELETE FROM harvest_candidates WHERE harvest_id = $1 AND decision IS NULL "
            "RETURNING 1) SELECT count(*) FROM gone", harvest_id)
        done = await conn.fetchrow(
            "UPDATE harvests SET state = 'done', ended_at = NOW() WHERE id = $1 RETURNING *", harvest_id)
        await audit.record(p.household_id, "harvest.finished", actor_member_id=p.member_id,
                           target_type="harvest", target_id=harvest_id,
                           detail={"discarded": dropped}, conn=conn)
    return dict(done)


async def sweep(now: dt.datetime | None = None) -> dict[str, int]:
    """A sitting nobody finished is abandoned, and what it held goes with it."""
    now = now or dt.datetime.now(dt.UTC)
    async with pool().acquire() as conn, conn.transaction():
        stale = await conn.fetch(
            "UPDATE harvests SET state = 'abandoned', ended_at = NOW() "
            "WHERE state IN ('collecting', 'review') AND expires_at <= $1 RETURNING id, household_id", now)
        dropped = 0
        if stale:
            dropped = await conn.fetchval(
                "WITH gone AS (DELETE FROM harvest_candidates WHERE harvest_id = ANY($1::uuid[]) "
                "RETURNING 1) SELECT count(*) FROM gone", [r["id"] for r in stale])
    return {"abandoned": len(stale), "dropped": dropped}


def describe() -> str:
    driving = type(current_collector()).__name__
    if isinstance(current_collector(), ManualCollector):
        return ("assisted harvest: pages are handed in, with no browser of ours to drive -- "
                "a sitting still keeps only what the member picks")
    return (f"assisted harvest: {driving} drives, the member signs in themselves, and nothing is "
            "stored afterwards but what they picked. ONE SITTING AT A TIME: the browser holds one "
            "session, and its egress is not yet restricted -- it can reach this deployment's own "
            "network. Not for more than one household until that is fixed.")
