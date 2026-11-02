-- The family key's short-lived state, for a deployment with more than one worker (FAMILYOS_MULTI_WORKER=true). With one worker nothing is
-- written here: the unlocked key stays in that process's memory and a restart locks the household, as before.
-- family_key_unlocks: the unlocked data key, wrapped under the server's master key (the table alone is useless without it), gone at expiry,
--   on lock, on disable, and with the household.
-- family_key_attempts: one row per failed unlock or confirm try, counted over the last hour; a success clears the member's rows.
CREATE TABLE family_key_unlocks (
    household_id UUID PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
    wrapped_key BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE family_key_attempts (
    id BIGSERIAL PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX family_key_attempts_member_idx ON family_key_attempts (household_id, member_id, at);
