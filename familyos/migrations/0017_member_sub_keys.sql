-- Level 2 of the key hierarchy: a private notice sealed with its member's key.
--
-- Until now one household key sealed everything, and privacy was the
-- visibility column alone. So a bug in a read path leaked the document, and
-- erasing one member left yesterday's backup readable.
--
-- The shape that works with per-household blob dedup is ordinary envelope
-- encryption one level down: every blob gets its own random key, and that key
-- is wrapped by whichever scope owns the blob -- the household for shared
-- bytes, the member for private ones. Changing who can see a notice re-wraps
-- 32 bytes instead of re-encrypting the document.

-- One key per member, wrapped by the household key -- never by the master key,
-- so destroying the household key still takes every member's with it.
ALTER TABLE members ADD COLUMN wrapped_sub_key BYTEA;

-- The blob's own key, and whose scope holds it.
ALTER TABLE blobs ADD COLUMN wrapped_key BYTEA;
ALTER TABLE blobs ADD COLUMN sealed_for UUID REFERENCES members(id) ON DELETE CASCADE;

-- Dedup has to follow the scope: two members forwarding the same circular
-- privately each keep their own copy, because neither can open the other's.
-- It is also the better privacy answer -- household-wide dedup lets one member
-- learn, from a write that suddenly costs nothing, that another already has
-- these bytes.
DROP INDEX IF EXISTS blobs_household_sha_idx;
ALTER TABLE blobs DROP CONSTRAINT IF EXISTS blobs_household_id_sha256_key;
CREATE UNIQUE INDEX blobs_scope_sha_idx
    ON blobs (household_id, COALESCE(sealed_for, '00000000-0000-0000-0000-000000000000'::uuid), sha256);
