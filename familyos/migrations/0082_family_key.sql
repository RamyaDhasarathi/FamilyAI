-- A family-held key. By default the household's data key is wrapped by the server's master key (key_mode 'server'). A household may instead
-- have it wrapped by a secret that only exists as Shamir shares held by the family (key_mode 'family'): the server then holds nothing it can
-- unwrap with, and the key is in memory only while the family has unlocked it. The shares are never stored.
ALTER TABLE households ADD COLUMN key_mode TEXT NOT NULL DEFAULT 'server' CHECK (key_mode IN ('server', 'family'));
CREATE TABLE family_keys (
    household_id UUID PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
    threshold SMALLINT NOT NULL CHECK (threshold BETWEEN 2 AND 9),
    shares SMALLINT NOT NULL CHECK (shares BETWEEN 2 AND 9 AND shares >= threshold),
    wrapped_key BYTEA NOT NULL,
    pending BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    rotated_at TIMESTAMPTZ
);
