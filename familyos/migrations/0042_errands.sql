-- An errand: a booking or a purchase on a site the member is signed in to,
-- written down in full before anything is done -- what, where, by when,
-- the most it may cost, how it is paid -- fingerprinted, and approved by a
-- guardian against that exact fingerprint. The run keeps its steps and its
-- screenshots; a stop rule halts it and says why. Nothing here pays: the
-- payment is pay-after-service, or a UPI request the person approves on
-- their own phone.
CREATE TABLE errands (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('booking', 'purchase')),
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    spec JSONB NOT NULL,
    params_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'running', 'needs_you', 'done', 'stopped', 'failed', 'cancelled')),
    approved_by UUID REFERENCES members(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX errands_household_idx ON errands (household_id, status, created_at DESC);
