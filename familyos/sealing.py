"""Sealing what FamilyOS has read out of a household's notices, under the household's own data key.

The originals are already sealed (artifacts.py). The text read out of them sat in Postgres in the clear, so a database copy or a backup would
still tell a story. With settings.seal_extracted_text on (the default since 23 Oct 2026), these columns are stored as
`enc:v1:<household>:<column>:<base64>`, AES-GCM under the household data key (the same key the family may hold as Shamir shares, familykey.py),
bound to its household and column so a value cannot be moved elsewhere and opened:

    claims.quote (column "quote"), claims.title, claims.subject_name, claims.issuer, obligations.title (columns named "claims.title" etc.)

Reads stay transparent: the pool every module uses (db.pool()) is wrapped, and any text value it returns that carries the prefix (alone, or inside
an array a query built from these columns) is opened on the way out, using that household's key, so no query had to change except the ones that
searched or sorted these columns in SQL, which now do it in Python. A household whose key the family holds and has not unlocked answers with
HouseholdLocked (HTTP 423). Writes are explicit: seal() at the place the text is stored. A value without the prefix is left alone, so old rows
keep working until the backfill (backfill()) seals them, and turning the setting off stops sealing new text without breaking old.

Not sealed: dates, amounts, kinds, statuses and ids, which queries need in the clear; the other text columns of claims (place, applies_to, change,
amends, date_text, time_text, dose_text); extractions.notes (machine tags such as "no_text", no family words); and every other table. Several of
those hold a copy of a sealed title (a to-do made from an obligation, a document, a medication, a calendar entry): the copy is as readable as it
was. docs/family-key.md lists each column and what was done about it. Erasing a household destroys its key and with it every sealed value.
"""
from __future__ import annotations

import base64
import logging
import uuid

from familyos import crypto
from familyos.settings import settings

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"

# The name a column is bound to when sealed. claims.quote kept its short name so rows sealed before the others still open.
QUOTE = "quote"
CLAIM_TITLE = "claims.title"
CLAIM_SUBJECT = "claims.subject_name"
CLAIM_ISSUER = "claims.issuer"
OBLIGATION_TITLE = "obligations.title"

# (table, column, the name it is sealed under): what the sweep seals in rows stored before the setting was on.
BACKFILL_COLUMNS = (
    ("claims", "quote", QUOTE),
    ("claims", "title", CLAIM_TITLE),
    ("claims", "subject_name", CLAIM_SUBJECT),
    ("claims", "issuer", CLAIM_ISSUER),
    ("obligations", "title", OBLIGATION_TITLE),
)


def enabled() -> bool:
    return bool(settings.seal_extracted_text)


async def write_key(conn, household_id: uuid.UUID) -> bytes:
    """The key to seal this household's text with, or b"" when sealing is off (seal() then returns the text unchanged)."""
    from familyos import artifacts
    return await artifacts.household_key(conn, household_id) if enabled() else b""


def _aad(household_id: uuid.UUID, column: str) -> bytes:
    return b"sealed-text|" + column.encode() + b"|" + household_id.bytes


def seal(key: bytes, household_id: uuid.UUID, column: str, text: str | None) -> str | None:
    """The text sealed for storage, or unchanged when sealing is off, there is nothing to seal, or it is already sealed."""
    if not enabled() or not text or text.startswith(PREFIX):
        return text
    sealed = crypto.seal(key, text.encode(), _aad(household_id, column))
    return f"{PREFIX}{household_id.hex}:{column}:{base64.urlsafe_b64encode(sealed).decode()}"


def parse(value: str) -> tuple[uuid.UUID, str, bytes]:
    body = value[len(PREFIX):]
    hid, column, blob = body.split(":", 2)
    return uuid.UUID(hid), column, base64.urlsafe_b64decode(blob.encode())


async def _open_one(value: str, conn, keys: dict[uuid.UUID, bytes]) -> str:
    from familyos import artifacts
    hid, column, blob = parse(value)
    if hid not in keys:
        keys[hid] = await artifacts.household_key(conn, hid)
    return crypto.open_sealed(keys[hid], blob, _aad(hid, column)).decode()


class OpenedRecord:
    """A row whose sealed text has been opened. Behaves like asyncpg's Record: by name or position, keys/values/items, dict(row), **row,
    and iteration over the values."""
    __slots__ = ("_k", "_v")

    def __init__(self, keys: list[str], values: list) -> None:
        self._k, self._v = keys, values

    def __getitem__(self, i):
        return self._v[i] if isinstance(i, int) else self._v[self._k.index(i)]

    def get(self, name, default=None):
        return self._v[self._k.index(name)] if name in self._k else default

    def keys(self):
        return list(self._k)

    def values(self):
        return list(self._v)

    def items(self):
        return list(zip(self._k, self._v, strict=True))

    def __iter__(self):
        return iter(self._v)

    def __len__(self) -> int:
        return len(self._v)

    def __contains__(self, name) -> bool:
        return name in self._k

    def __repr__(self) -> str:
        return f"<OpenedRecord {dict(self.items())!r}>"


def _sealed(v) -> bool:
    """A sealed string, or a list holding one (array_agg over a sealed column)."""
    if isinstance(v, list):
        return any(_sealed(x) for x in v)
    return isinstance(v, str) and v.startswith(PREFIX)


async def _open_value(v, conn, keys):
    if isinstance(v, list):
        return [await _open_value(x, conn, keys) for x in v]
    return await _open_one(v, conn, keys) if _sealed(v) else v


async def open_row(row, conn, keys):
    if row is None or not any(_sealed(v) for v in row.values()):
        return row
    return OpenedRecord(list(row.keys()), [await _open_value(v, conn, keys) for v in row.values()])


async def open_rows(rows, conn):
    if not rows or not any(_sealed(v) for r in rows for v in r.values()):
        return rows
    keys: dict[uuid.UUID, bytes] = {}
    return [await open_row(r, conn, keys) for r in rows]


class SealingConn:
    """A connection whose reads open sealed text. Everything else is the real connection's."""

    def __init__(self, conn) -> None:
        self._c = conn

    def __getattr__(self, name):
        return getattr(self._c, name)

    async def fetch(self, *a, **k):
        return await open_rows(await self._c.fetch(*a, **k), self._c)

    async def fetchrow(self, *a, **k):
        return await open_row(await self._c.fetchrow(*a, **k), self._c, {})

    async def fetchval(self, *a, **k):
        return await _open_value(await self._c.fetchval(*a, **k), self._c, {})


class _Acquire:
    def __init__(self, ctx) -> None:
        self._ctx = ctx

    async def __aenter__(self):
        return SealingConn(await self._ctx.__aenter__())

    async def __aexit__(self, *exc):
        return await self._ctx.__aexit__(*exc)

    def __await__(self):
        async def go():
            return SealingConn(await self._ctx)
        return go().__await__()


class SealingPool:
    """The pool every module uses: the real pool, with reads that open sealed text."""

    def __init__(self, raw) -> None:
        self.raw = raw

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def acquire(self, *a, **k):
        return _Acquire(self.raw.acquire(*a, **k))

    async def fetch(self, *a, **k):
        async with self.raw.acquire() as c:
            return await open_rows(await c.fetch(*a, **k), c)

    async def fetchrow(self, *a, **k):
        async with self.raw.acquire() as c:
            return await open_row(await c.fetchrow(*a, **k), c, {})

    async def fetchval(self, *a, **k):
        async with self.raw.acquire() as c:
            return await _open_value(await c.fetchval(*a, **k), c, {})


async def backfill(limit: int = 500) -> dict[str, int]:
    """Seal text stored before the setting was on. A household whose family-held key is locked is skipped, to be done when it is open."""
    from familyos import artifacts, db, familykey
    from familyos.familykey import HouseholdLocked
    out = {"sealed": 0, "skipped_locked": 0}
    if not enabled():
        return out
    raw = db.raw_pool()
    for table, column, name in BACKFILL_COLUMNS:
        async with raw.acquire() as conn:
            # Locked households are filtered here, not after the LIMIT: 500 rows of a locked household must not starve the rest.
            family_held = [r["id"] for r in await conn.fetch("SELECT id FROM households WHERE key_mode = 'family'")]
            locked = []
            for hid in family_held:
                try:
                    await familykey.unlocked_key(hid)
                except HouseholdLocked:
                    locked.append(hid)
            if locked:
                out["skipped_locked"] += await conn.fetchval(
                    f"SELECT count(*) FROM {table} WHERE household_id = ANY($1::uuid[]) AND {column} IS NOT NULL AND {column} NOT LIKE '{PREFIX}%'", locked)
            rows = await conn.fetch(
                f"SELECT id, household_id, {column} AS text FROM {table} WHERE {column} IS NOT NULL AND {column} NOT LIKE '{PREFIX}%' "
                f"AND household_id <> ALL($2::uuid[]) LIMIT $1", limit, locked)
            keys: dict[uuid.UUID, bytes | None] = {}
            for r in rows:
                hid = r["household_id"]
                if hid not in keys:
                    try:
                        keys[hid] = await artifacts.household_key(conn, hid)
                    except Exception:  # noqa: BLE001 - locked meanwhile, or a household being erased
                        keys[hid] = None
                if keys[hid] is None:
                    out["skipped_locked"] += 1
                    continue
                # Only if the value is still the one we read: a write that landed since wins, and the next pass seals it.
                done = await conn.execute(f"UPDATE {table} SET {column} = $2 WHERE id = $1 AND {column} = $3",
                                          r["id"], seal(keys[hid], hid, name, r["text"]), r["text"])
                if done.endswith(" 1"):
                    out["sealed"] += 1
    return out


KIND = "text_sealing_sweep"
SWEEP_SECONDS = 600


async def _handle(job: dict, ctx) -> dict:
    import datetime as dt
    now = dt.datetime.now(dt.UTC)
    try:
        result = await backfill()
    except Exception:  # noqa: BLE001 - the sweep must come back
        import logging
        logging.getLogger(__name__).warning("the sealing sweep failed; it will run again", exc_info=True)
        result = {"failed_pass": 1}
    return {**result, "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled():
    from familyos import jobs
    return await jobs.ensure_recurring(KIND)


def register() -> None:
    from familyos import jobs
    jobs.register(KIND, _handle, version="1", settings_keys=("seal_extracted_text",))
