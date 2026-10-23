"""Input artifacts: immutable originals and the envelope that describes them.

Bytes are stored once per household (deduplicated by SHA-256), sealed with
the household key, and never rewritten. The envelope may change status
(quarantined -> accepted), visibility (private <-> shared) and subjects;
the bytes it points to may not.

Visibility is enforced inside every query, never by filtering results
afterwards: a member sees an accepted artifact when it is shared, or when
they submitted it. Quarantined artifacts are visible only to guardians,
through the quarantine endpoints.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

import asyncpg

from familyos import audit, blobstore, consent, crypto
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)

# The visibility rule, as SQL. $1 = household id, $2 = member id.
VISIBLE_TO_MEMBER = "a.household_id = $1 AND a.status = 'accepted' AND (a.visibility = 'shared' OR a.submitted_by = $2)"

_SELECT = ("SELECT a.*, COALESCE((SELECT array_agg(s.member_id) FROM artifact_subjects s WHERE s.artifact_id = a.id), '{}') "
           "AS subject_member_ids, COALESCE((SELECT array_agg(c.id ORDER BY c.received_at, c.id) FROM input_artifacts c "
           "WHERE c.parent_id = a.id), '{}') AS children FROM input_artifacts a")


class HouseholdUnavailable(Exception):
    """The household is being erased: nothing new is accepted."""


class TooLarge(Exception):
    """More than this request is allowed to build."""


@dataclass
class NewArtifact:
    data: bytes
    media_type: str
    channel: str
    visibility: str
    status: str
    submitted_by: uuid.UUID | None = None
    filename: str | None = None
    source: dict | None = None
    note: str | None = None
    dedup_key: str | None = None
    parent_id: uuid.UUID | None = None
    quarantine_reason: str | None = None
    subject_member_ids: tuple[uuid.UUID, ...] = ()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _aad(household_id: uuid.UUID, digest: str) -> bytes:
    return household_id.bytes + bytes.fromhex(digest)


def _sub_aad(household_id: uuid.UUID, member_id: uuid.UUID) -> bytes:
    """A member's sub-key is bound to the member and the household, so one
    member's wrapped key cannot be restored as another's."""
    return household_id.bytes + member_id.bytes + b"member-sub-key"


async def member_key(conn: asyncpg.Connection, household_id: uuid.UUID, member_id: uuid.UUID,
                     *, create: bool = False) -> bytes:
    """A member's own key, wrapped by the household key -- never by the master
    key, so destroying the household key still takes every member's with it.

    Minted on first use rather than at member creation, so existing households
    gain one the moment they need it.
    """
    household = await household_key(conn, household_id, lock=True)
    row = await conn.fetchrow(
        "SELECT wrapped_sub_key FROM members WHERE id = $1 AND household_id = $2 FOR UPDATE",
        member_id, household_id)
    if row is None:
        raise NotFound("member")
    if row["wrapped_sub_key"]:
        return crypto.open_sealed(household, row["wrapped_sub_key"], _sub_aad(household_id, member_id))
    if not create:
        raise crypto.KeyUnavailable(f"member {member_id} has no key")
    sub = crypto.AESGCM.generate_key(bit_length=256)
    await conn.execute("UPDATE members SET wrapped_sub_key = $2 WHERE id = $1", member_id,
                       crypto.seal(household, sub, _sub_aad(household_id, member_id)))
    return sub


async def _scope_key(conn: asyncpg.Connection, household_id: uuid.UUID, sealed_for: uuid.UUID | None,
                     *, create: bool = False) -> bytes:
    """Whose key wraps this blob's key: the member's when it is private to
    them, the household's when it is shared."""
    if sealed_for is None:
        return await household_key(conn, household_id, lock=True)
    return await member_key(conn, household_id, sealed_for, create=create)


async def household_key(conn: asyncpg.Connection, household_id: uuid.UUID, *, lock: bool = False) -> bytes:
    """The household's data key, or nothing if the household is not active.

    Public because blobs are not the only thing that must die with the key:
    a connected mailbox's refresh token is sealed with this too, so erasing
    a household also ends its access to the mailboxes it was reading.
    """
    row = await conn.fetchrow(
        "SELECT status, wrapped_key FROM households WHERE id = $1" + (" FOR SHARE" if lock else ""), household_id)
    if row is None or row["status"] != "active":
        raise HouseholdUnavailable(str(household_id))
    return crypto.unwrap(household_id, row["wrapped_key"])


_NOBODY = uuid.UUID(int=0)


async def _store_blob(conn: asyncpg.Connection, household_id: uuid.UUID, data: bytes, media_type: str,
                      *, sealed_for: uuid.UUID | None = None) -> dict:
    """The blob for these bytes in this scope, uploading them only if new.

    Each blob has its own key, wrapped by whichever scope owns it: the member
    when the bytes are private to them, the household when they are shared.
    Dedup follows the scope, because two members who each privately forward the
    same circular cannot open one another's copy -- and because household-wide
    dedup would let one of them learn, from a write that suddenly costs
    nothing, that the other already has these bytes.
    """
    digest = sha256(data)
    scope = sealed_for or _NOBODY
    # FOR KEY SHARE: an erasure cannot drop this blob before our artifact points to it.
    existing = await conn.fetchrow(
        "SELECT * FROM blobs WHERE household_id = $1 AND COALESCE(sealed_for, $3) = $3 AND sha256 = $2 FOR KEY SHARE",
        household_id, digest, scope)
    if existing is not None:
        return dict(existing)

    wrapping = await _scope_key(conn, household_id, sealed_for, create=True)
    data_key = crypto.AESGCM.generate_key(bit_length=256)
    blob_id = uuid.uuid4()
    storage_key = f"households/{household_id}/blobs/{blob_id}"
    await blobstore.store().put(storage_key, crypto.seal(data_key, data, _aad(household_id, digest)))
    row = await conn.fetchrow(
        "INSERT INTO blobs (id, household_id, sha256, size_bytes, media_type, storage_key, wrapped_key, sealed_for) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
        "ON CONFLICT (household_id, COALESCE(sealed_for, '00000000-0000-0000-0000-000000000000'::uuid), sha256) "
        "DO NOTHING RETURNING *",
        blob_id, household_id, digest, len(data), media_type, storage_key,
        crypto.seal(wrapping, data_key, _aad(household_id, digest)), sealed_for)
    if row is None:
        # Another request stored the same bytes first: keep theirs.
        await blobstore.store().delete(storage_key)
        row = await conn.fetchrow(
            "SELECT * FROM blobs WHERE household_id = $1 AND COALESCE(sealed_for, $3) = $3 AND sha256 = $2",
            household_id, digest, scope)
    return dict(row)


async def blob_key(conn: asyncpg.Connection, household_id: uuid.UUID, blob: dict) -> bytes:
    """Unwrap a blob's own key with whichever scope holds it."""
    if not blob.get("wrapped_key"):
        # Written before blobs had their own keys: sealed with the household
        # key directly. Read it the old way.
        return await household_key(conn, household_id)
    wrapping = await _scope_key(conn, household_id, blob.get("sealed_for"))
    return crypto.open_sealed(wrapping, blob["wrapped_key"], _aad(household_id, blob["sha256"]))


async def create(conn: asyncpg.Connection, household_id: uuid.UUID, new: NewArtifact, *,
                 actor_kind: str = "member") -> tuple[dict, bool]:
    """Store the original and its envelope inside the caller's transaction.
    Returns (artifact, duplicate)."""
    await household_key(conn, household_id, lock=True)
    if new.dedup_key:
        existing = await conn.fetchrow(
            _SELECT + " WHERE a.household_id = $1 AND a.dedup_key = $2", household_id, new.dedup_key)
        if existing is not None:
            await audit.record(household_id, "artifact.duplicate", actor_kind=actor_kind, actor_member_id=new.submitted_by,
                               target_type="artifact", target_id=existing["id"], conn=conn)
            return dict(existing), True
    await consent.require(conn, household_id, list(new.subject_member_ids))
    blob = await _store_blob(conn, household_id, new.data, new.media_type,
                                 # Private bytes are sealed with the submitter's key, so a
                                 # bug in a read path leaks a row and not a document.
                                 sealed_for=new.submitted_by if new.visibility == 'private' else None)
    artifact_id = uuid.uuid4()
    row = await conn.fetchrow(
        "INSERT INTO input_artifacts (id, household_id, blob_id, parent_id, channel, submitted_by, visibility, status, "
        "quarantine_reason, filename, media_type, size_bytes, sha256, source, note, dedup_key, accepted_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, "
        "CASE WHEN $8 = 'accepted' THEN NOW() END) "
        "ON CONFLICT (household_id, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING RETURNING id",
        artifact_id, household_id, blob["id"], new.parent_id, new.channel, new.submitted_by, new.visibility, new.status,
        new.quarantine_reason, new.filename, new.media_type, len(new.data), blob["sha256"], new.source or {}, new.note,
        new.dedup_key)
    if row is None:
        # A concurrent delivery of the same thing won the insert.
        existing = await conn.fetchrow(
            _SELECT + " WHERE a.household_id = $1 AND a.dedup_key = $2", household_id, new.dedup_key)
        return dict(existing), True
    if new.subject_member_ids:
        await conn.executemany("INSERT INTO artifact_subjects (artifact_id, member_id) VALUES ($1, $2)",
                               [(artifact_id, m) for m in set(new.subject_member_ids)])
    await audit.record(household_id, "artifact.quarantined" if new.status == "quarantined" else "artifact.received",
                       actor_kind=actor_kind, actor_member_id=new.submitted_by, target_type="artifact",
                       target_id=artifact_id, conn=conn,
                       detail={"channel": new.channel, "size_bytes": len(new.data), "media_type": new.media_type,
                               "sha256": blob["sha256"], "visibility": new.visibility,
                               "parent_id": str(new.parent_id) if new.parent_id else None,
                               "reason": new.quarantine_reason})
    if new.subject_member_ids:
        await share_for_children(conn, household_id, artifact_id, actor_member_id=new.submitted_by, via="arrival")
    return dict(await conn.fetchrow(_SELECT + " WHERE a.id = $1", artifact_id)), False


# ----------------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------------

async def list_visible(p: Principal, limit: int = 50, top_level_only: bool = True) -> list[dict]:
    rows = await pool().fetch(
        _SELECT + f" WHERE {VISIBLE_TO_MEMBER}" + (" AND a.parent_id IS NULL" if top_level_only else "")
        + " ORDER BY a.received_at DESC LIMIT $3", p.household_id, p.member_id, limit)
    return [dict(r) for r in rows]


async def get_visible(p: Principal, artifact_id: uuid.UUID) -> dict:
    row = await pool().fetchrow(_SELECT + f" WHERE {VISIBLE_TO_MEMBER} AND a.id = $3",
                                p.household_id, p.member_id, artifact_id)
    if row is None:
        raise NotFound("artifact")
    return dict(row)


async def read_original(p: Principal, artifact_id: uuid.UUID) -> tuple[dict, bytes]:
    """The original bytes, decrypted and checked against their hash. Reading
    an original is audited."""
    artifact = await get_visible(p, artifact_id)
    return artifact, await _read_bytes(p, artifact)


async def _read_bytes(p: Principal, artifact: dict) -> bytes:
    return await read_bytes(p.household_id, artifact, actor=p)


async def read_many(household_id: uuid.UUID, artifact_rows: list[dict], *, actor: Principal | None = None,
                    max_bytes: int | None = None) -> dict[uuid.UUID, bytes]:
    """Several originals at once, for an export.

    One connection and one key unwrap rather than one of each per artifact,
    and -- more importantly -- **one** audit event. Reading fifty originals to
    answer a single request for an export is one deliberate act, and fifty
    `artifact.original_read` rows would describe it less truthfully than one
    `artifact.originals_read` saying how many. The integrity check is the same
    one `read_bytes` makes; an original that fails it is not quietly left out.

    `max_bytes` stops before building something too large to send, rather than
    after.
    """
    out: dict[uuid.UUID, bytes] = {}
    if not artifact_rows:
        return out
    total = 0
    async with pool().acquire() as conn:
        store = blobstore.store()
        for artifact in artifact_rows:
            if artifact.get("blob_id") is None:
                continue
            blob = await conn.fetchrow("SELECT * FROM blobs WHERE id = $1", artifact["blob_id"])
            if blob is None:
                continue
            data = crypto.open_sealed(await blob_key(conn, household_id, dict(blob)),
                                      await store.get(blob["storage_key"]),
                                      _aad(household_id, blob["sha256"]))
            if sha256(data) != blob["sha256"]:
                raise RuntimeError(f"blob {blob['id']} failed its integrity check")
            total += len(data)
            if max_bytes is not None and total > max_bytes:
                raise TooLarge(f"this export would be over {max_bytes} bytes of originals")
            out[artifact["id"]] = data
        await audit.record(household_id, "artifact.originals_read",
                           actor_kind="member" if actor else "system",
                           actor_member_id=actor.member_id if actor else None,
                           detail={"artifacts": len(out), "bytes": total}, conn=conn)
    return out


async def read_bytes(household_id: uuid.UUID, artifact: dict, *, actor: Principal | None = None) -> bytes:
    """Decrypt an artifact's original and check it against its hash. Every
    read is audited, by the member who asked or by the system (extraction)."""
    async with pool().acquire() as conn:
        blob = await conn.fetchrow("SELECT * FROM blobs WHERE id = $1", artifact["blob_id"])
        data = crypto.open_sealed(await blob_key(conn, household_id, dict(blob)),
                                  await blobstore.store().get(blob["storage_key"]),
                                  _aad(household_id, blob["sha256"]))
        if sha256(data) != blob["sha256"]:
            raise RuntimeError(f"blob {blob['id']} failed its integrity check")
        await audit.record(household_id, "artifact.original_read", actor_kind="member" if actor else "system",
                           actor_member_id=actor.member_id if actor else None,
                           target_type="artifact", target_id=artifact["id"], conn=conn)
    return data


# ----------------------------------------------------------------------------
# changing the envelope
# ----------------------------------------------------------------------------

async def _rewrap(conn: asyncpg.Connection, household_id: uuid.UUID, artifact_id: uuid.UUID,
                  *, sealed_for: uuid.UUID | None) -> None:
    """Move an artifact's blobs into another scope.

    Only the blob's 32-byte key is re-wrapped -- the document itself is never
    re-encrypted, which is the whole reason the key sits one level down.
    """
    blobs = await conn.fetch(
        "SELECT b.* FROM blobs b JOIN input_artifacts a ON a.blob_id = b.id "
        "WHERE a.household_id = $1 AND (a.id = $2 OR a.parent_id = $2) FOR UPDATE OF b",
        household_id, artifact_id)
    for blob in blobs:
        if blob["sealed_for"] == sealed_for or not blob["wrapped_key"]:
            continue
        data_key = crypto.open_sealed(
            await _scope_key(conn, household_id, blob["sealed_for"]), blob["wrapped_key"],
            _aad(household_id, blob["sha256"]))
        await conn.execute(
            "UPDATE blobs SET wrapped_key = $2, sealed_for = $3 WHERE id = $1", blob["id"],
            crypto.seal(await _scope_key(conn, household_id, sealed_for, create=True), data_key,
                        _aad(household_id, blob["sha256"])),
            sealed_for)


async def share_for_children(conn: asyncpg.Connection, household_id: uuid.UUID, artifact_id: uuid.UUID, *,
                             actor_member_id: uuid.UUID | None = None, via: str) -> bool:
    """The household's rule: a notice about a child is every adult's.

    Applied wherever subjects are written -- on arrival, on a tag from the
    phone, on a parent's tap, on an inferred class -- never on read, so the
    visibility column stays the one truth and the sealing follows it. An
    attachment's subjects share its email. Returns True when it changed
    anything. Off when the household has turned it off; a notice made private
    by hand afterwards is left alone until it is tagged again.
    """
    row = await conn.fetchrow(
        "SELECT a.id, a.visibility, a.submitted_by FROM input_artifacts a JOIN households h ON h.id = a.household_id "
        "WHERE a.household_id = $1 AND a.id = COALESCE((SELECT x.parent_id FROM input_artifacts x WHERE x.id = $2), $2) "
        "AND a.status = 'accepted' AND a.visibility = 'private' AND h.childrens_notices_shared "
        "AND EXISTS (SELECT 1 FROM artifact_subjects s JOIN members m ON m.id = s.member_id "
        "            WHERE m.role = 'child' AND (s.artifact_id = a.id OR s.artifact_id IN "
        "                  (SELECT c.id FROM input_artifacts c WHERE c.parent_id = a.id))) "
        "FOR UPDATE OF a", household_id, artifact_id)
    if row is None:
        return False
    await _rewrap(conn, household_id, row["id"], sealed_for=None)
    await conn.execute("UPDATE input_artifacts SET visibility = 'shared' WHERE id = $1 OR parent_id = $1", row["id"])
    await audit.record(household_id, "artifact.visibility_changed", actor_member_id=actor_member_id,
                       target_type="artifact", target_id=row["id"],
                       detail={"from": "private", "to": "shared", "rule": "childrens_notices_shared", "via": via}, conn=conn)
    return True


async def set_visibility(p: Principal, artifact_id: uuid.UUID, visibility: str) -> dict:
    """Only the member who submitted an artifact decides who sees it.
    Attachments follow their email."""
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM input_artifacts a WHERE a.household_id = $1 AND a.id = $2 AND a.status = 'accepted' "
            "AND (a.visibility = 'shared' OR a.submitted_by = $3) FOR UPDATE", p.household_id, artifact_id, p.member_id)
        if row is None:
            raise NotFound("artifact")
        if row["submitted_by"] != p.member_id:
            raise NotAllowed("only the member who submitted this can change who sees it")
        if row["parent_id"] is not None:
            raise NotAllowed("an attachment follows the visibility of its email")
        if row["visibility"] != visibility:
            await _rewrap(conn, p.household_id, artifact_id,
                          sealed_for=None if visibility == "shared" else row["submitted_by"])
            await conn.execute("UPDATE input_artifacts SET visibility = $2 WHERE id = $1 OR parent_id = $1", artifact_id, visibility)
            await audit.record(p.household_id, "artifact.visibility_changed", actor_member_id=p.member_id,
                               target_type="artifact", target_id=artifact_id,
                               detail={"from": row["visibility"], "to": visibility}, conn=conn)
    return await get_visible(p, artifact_id)


async def set_subjects(p: Principal, artifact_id: uuid.UUID, member_ids: list[uuid.UUID]) -> dict:
    """Say whom an artifact is about. Anyone who can see it may; a child
    needs active consent."""
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(f"SELECT a.id FROM input_artifacts a WHERE {VISIBLE_TO_MEMBER} AND a.id = $3 FOR UPDATE",
                                  p.household_id, p.member_id, artifact_id)
        if row is None:
            raise NotFound("artifact")
        await consent.require(conn, p.household_id, member_ids)
        await conn.execute("DELETE FROM artifact_subjects WHERE artifact_id = $1", artifact_id)
        await conn.executemany("INSERT INTO artifact_subjects (artifact_id, member_id) VALUES ($1, $2)",
                               [(artifact_id, m) for m in set(member_ids)])
        await audit.record(p.household_id, "artifact.subjects_set", actor_member_id=p.member_id, target_type="artifact",
                           target_id=artifact_id, detail={"member_ids": sorted(map(str, set(member_ids)))}, conn=conn)
        await share_for_children(conn, p.household_id, artifact_id, actor_member_id=p.member_id, via="subjects")
    return await get_visible(p, artifact_id)


# ----------------------------------------------------------------------------
# quarantine
# ----------------------------------------------------------------------------

async def list_quarantine(p: Principal) -> list[dict]:
    if not p.is_guardian:
        raise NotAllowed("only a guardian can review quarantined items")
    rows = await pool().fetch(_SELECT + " WHERE a.household_id = $1 AND a.status = 'quarantined' AND a.parent_id IS NULL "
                              "ORDER BY a.received_at DESC", p.household_id)
    return [dict(r) for r in rows]


async def accept_quarantined(p: Principal, artifact_id: uuid.UUID, member_id: uuid.UUID, visibility: str) -> dict:
    """A guardian vouches for a quarantined item and says whose it is."""
    if not p.is_guardian:
        raise NotAllowed("only a guardian can accept quarantined items")
    async with pool().acquire() as conn, conn.transaction():
        owner = await conn.fetchrow("SELECT role FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id)
        if owner is None or owner["role"] == "child":
            raise Invalid("an item belongs to a guardian or adult member")
        row = await conn.fetchrow(
            "UPDATE input_artifacts SET status = 'accepted', accepted_at = NOW(), submitted_by = $3, visibility = $4 "
            "WHERE household_id = $1 AND id = $2 AND status = 'quarantined' AND parent_id IS NULL "
            "RETURNING id, source", p.household_id, artifact_id, member_id, visibility)
        if row is None:
            raise NotFound("quarantined artifact")
        # Vouching for a message vouches for where it came from, so the next
        # circular from this school is read rather than held. Accepting the
        # same sender every week is the chore that teaches people to accept
        # without looking.
        from familyos.intake import gateway  # gateway imports this module
        trusted = await gateway.trust_sender_domain(
            conn, p.household_id, (row["source"] or {}).get("from"), p.member_id)
        children = await conn.fetch("UPDATE input_artifacts SET status = 'accepted', accepted_at = NOW(), submitted_by = $2, "
                                    "visibility = $3 WHERE parent_id = $1 RETURNING id", artifact_id, member_id, visibility)
        from familyos.extraction import service as extraction  # extraction imports this module
        await extraction.enqueue(conn, p.household_id, [artifact_id] + [c["id"] for c in children], member_id=member_id)
        await audit.record(p.household_id, "artifact.quarantine_accepted", actor_member_id=p.member_id,
                           target_type="artifact", target_id=artifact_id,
                           detail={"owner_member_id": str(member_id), "visibility": visibility,
                                   "now_trusted": trusted}, conn=conn)
    return dict(await pool().fetchrow(_SELECT + " WHERE a.id = $1", artifact_id))


async def reject_quarantined(p: Principal, artifact_id: uuid.UUID) -> None:
    if not p.is_guardian:
        raise NotAllowed("only a guardian can reject quarantined items")
    await delete(p.household_id, artifact_id, actor=p, require_status="quarantined", action="artifact.quarantine_rejected")


# ----------------------------------------------------------------------------
# deleting
# ----------------------------------------------------------------------------

async def delete_by_member(p: Principal, artifact_id: uuid.UUID) -> None:
    """The submitter may erase their own artifact; a guardian may erase any
    shared one."""
    row = await get_visible(p, artifact_id)
    if row["parent_id"] is not None:
        raise NotAllowed("delete the email, not one of its attachments")
    if row["submitted_by"] != p.member_id and not (p.is_guardian and row["visibility"] == "shared"):
        raise NotAllowed("only the member who submitted this, or a guardian when it is shared, can delete it")
    await delete(p.household_id, artifact_id, actor=p, action="artifact.deleted")


async def delete(household_id: uuid.UUID, artifact_id: uuid.UUID, *, actor: Principal | None = None,
                 require_status: str | None = None, action: str = "artifact.deleted") -> None:
    async with pool().acquire() as conn, conn.transaction():
        # Attachments go with their email by cascade, so RETURNING will not
        # name their blobs: read them before the delete.
        blob_ids = [r["blob_id"] for r in await conn.fetch(
            "SELECT blob_id FROM input_artifacts WHERE household_id = $1 AND (id = $2 OR parent_id = $2)",
            household_id, artifact_id)]
        row = await conn.fetchrow(
            "DELETE FROM input_artifacts WHERE household_id = $1 AND id = $2 AND ($3::text IS NULL OR status = $3) "
            "RETURNING id", household_id, artifact_id, require_status)
        if row is None:
            raise NotFound("artifact")
        keys = await drop_orphan_blobs(conn, household_id, blob_ids)
        await audit.record(household_id, action, actor_kind="member" if actor else "system",
                           actor_member_id=actor.member_id if actor else None, target_type="artifact",
                           target_id=artifact_id, detail={"blobs_deleted": len(keys)}, conn=conn)
    await delete_objects(keys)


async def drop_orphan_blobs(conn: asyncpg.Connection, household_id: uuid.UUID,
                            blob_ids: list[uuid.UUID] | None = None) -> list[str]:
    """Delete blob rows no artifact points to; returns their storage keys,
    for the caller to delete from the object store after commit.

    `blob_ids` limits the check to the blobs a deletion just released, which
    is all that can have been orphaned by it. Without it every blob of the
    household is swept, which is what an erasure wants and what a single
    deletion should not pay for."""
    rows = await conn.fetch(
        "DELETE FROM blobs b WHERE b.household_id = $1 AND ($2::uuid[] IS NULL OR b.id = ANY($2::uuid[])) "
        "AND NOT EXISTS (SELECT 1 FROM input_artifacts a WHERE a.blob_id = b.id) RETURNING storage_key",
        household_id, blob_ids)
    return [r["storage_key"] for r in rows]


async def delete_objects(keys: list[str]) -> list[str]:
    """Best effort after commit: a leftover object is sealed with the
    household key and unreachable from the database. Returns failures."""
    failed = []
    for key in keys:
        try:
            await blobstore.store().delete(key)
        except Exception:
            logger.warning("could not delete object %s", key, exc_info=True)
            failed.append(key)
    return failed
