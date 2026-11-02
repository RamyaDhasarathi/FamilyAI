-- Class 2: one service's session, sealed, restored per task.
--
-- Every agent product we looked at keeps a *persistent browser profile* on
-- disk inside the container. A live cookie jar is a credential, so that design
-- leaves a credential sitting in the execution environment for its whole life.
--
-- Here the session lives sealed under the household key, is unsealed into a
-- container for the length of one task, and is gone when the task ends.
-- Destroying the household key kills every stored session at once, which is
-- what makes erasure mean something for a logged-in service.
CREATE TABLE sealed_sessions (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    -- Whose sign-in this is. A session is never shared between members: two
    -- parents with portal logins have two sessions.
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,

    -- The one service this session may ever be used against, and the only
    -- origins a task carrying it may reach.
    service TEXT NOT NULL CHECK (length(btrim(service)) > 0),
    allow_hosts TEXT[] NOT NULL CHECK (cardinality(allow_hosts) > 0),

    -- Cookies, the browser fingerprint and the pinned egress identity, sealed
    -- together. Restoring cookies alone on a different fingerprint or address
    -- gets you logged out and asked for an OTP, so all three travel as one.
    sealed_state BYTEA NOT NULL,

    -- A session is not forever. When it lapses the member signs in again by
    -- takeover; the system never re-authenticates on its own.
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    uses INT NOT NULL DEFAULT 0,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- One live session per member per service.
CREATE UNIQUE INDEX sealed_sessions_live_idx
    ON sealed_sessions (household_id, member_id, service) WHERE revoked_at IS NULL;
