-- An assisted harvest: one sitting, a person present, nothing kept afterwards.
--
-- Class 1 holds no credential and so reaches only public pages. Class 2 holds
-- one service's session between tasks, which is powerful and leaves a live
-- credential in custody. Between them sits the case a family actually has
-- first: "pull three years of circulars off the school portal, once."
--
-- The member signs in themselves, the pages collected become candidates they
-- read and choose from, and when the sitting ends nothing survives but what
-- they picked. No cookies, no fingerprint, no session row -- which makes this
-- weaker than class 2 in reach and stronger in custody, because there is
-- nothing left to steal.
CREATE TABLE harvests (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,

    label TEXT NOT NULL CHECK (length(btrim(label)) > 0),
    allow_hosts TEXT[] NOT NULL CHECK (cardinality(allow_hosts) > 0),

    state TEXT NOT NULL DEFAULT 'collecting'
        CHECK (state IN ('collecting', 'review', 'done', 'abandoned')),
    -- A sitting nobody finishes does not sit forever: the candidates in it are
    -- a family's documents, held outside the record.
    expires_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);
CREATE INDEX harvests_open_idx ON harvests (expires_at) WHERE state IN ('collecting', 'review');

CREATE TABLE harvest_candidates (
    id UUID PRIMARY KEY,
    harvest_id UUID NOT NULL REFERENCES harvests(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,

    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    -- Sealed with the member's own sub-key: a candidate is a page from their
    -- account, and it has not been admitted to anything yet.
    sealed_text BYTEA NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INT NOT NULL,

    decision TEXT CHECK (decision IN ('kept', 'discarded')),
    decided_at TIMESTAMPTZ,
    artifact_id UUID REFERENCES input_artifacts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (harvest_id, sha256)
);
CREATE INDEX harvest_candidates_open_idx ON harvest_candidates (harvest_id) WHERE decision IS NULL;

-- Kept pages enter the record as ordinary artifacts, by their own channel.
ALTER TABLE input_artifacts DROP CONSTRAINT input_artifacts_channel_check;
ALTER TABLE input_artifacts ADD CONSTRAINT input_artifacts_channel_check
    CHECK (channel IN ('upload', 'email', 'email_attachment', 'whatsapp', 'whatsapp_media',
                       'gmail', 'gmail_attachment', 'harvest'));
