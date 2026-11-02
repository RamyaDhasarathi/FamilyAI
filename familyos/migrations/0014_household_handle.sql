-- A family address a person can say out loud.
--
-- The random inbound token is unguessable, which is good, and unrepeatable
-- over a phone line, which is fatal: rung 0 of the intake ladder only works if
-- a parent can write the address on a school admission form. So a household
-- picks a handle, and both route to the same place forever -- an address once
-- given out never stops working.
ALTER TABLE households ADD COLUMN handle TEXT;

-- Lowercase, and distinct from every other household's. Enforced here rather
-- than in code because two guardians can claim a name in the same second.
CREATE UNIQUE INDEX households_handle_idx ON households (lower(handle)) WHERE handle IS NOT NULL;

ALTER TABLE households ADD CONSTRAINT households_handle_shape CHECK (
    handle IS NULL OR (
        handle = lower(handle)
        AND length(handle) BETWEEN 3 AND 32
        AND handle ~ '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$'
        AND handle !~ '[.-]{2}'
        -- Never shaped like the generated token, so the two namespaces cannot
        -- collide when an address is resolved.
        AND handle !~ '^h[0-9a-f]{20}$'
    ));
