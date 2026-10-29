-- A member's Shamir share, kept sealed to their own passkey: the browser wrapped it under a secret derived inside the passkey (WebAuthn PRF), so
-- the server holds only ciphertext it cannot open. Unlocking a household that uses shares is then a tap on t members' devices instead of typing words.
-- The word shares on paper keep working; this is another way to hold the same share.
CREATE TABLE family_key_share_seals (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    credential_id BYTEA NOT NULL,
    prf_salt BYTEA NOT NULL,
    wrapped_share BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX family_key_share_seals_member_idx ON family_key_share_seals (household_id, member_id) WHERE revoked_at IS NULL;
