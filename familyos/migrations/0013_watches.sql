-- A generic task: watch a public page and say when what it says changes.
--
-- Deliberately not an obligation. An obligation is something an institution
-- asked a family to do, read out of a notice with a quote behind it. A watch
-- is something a member asked for themselves, and its result is a message to
-- that member -- so it needs no new action kind, and the deny-list on
-- `actions` stays exactly as narrow as it was.
CREATE TABLE watches (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,

    url TEXT NOT NULL,
    -- The host grant for this watch. A redirect anywhere else is refused
    -- rather than followed.
    allow_hosts TEXT[] NOT NULL CHECK (cardinality(allow_hosts) > 0),
    -- What the member is looking for, in their own words. Matched literally
    -- and case-insensitively against the page text; no model reads this.
    look_for TEXT NOT NULL CHECK (length(btrim(look_for)) > 0),
    label TEXT NOT NULL CHECK (length(btrim(label)) > 0),

    every_hours INT NOT NULL DEFAULT 24 CHECK (every_hours BETWEEN 1 AND 720),
    -- Watches end by themselves. A task nobody renews is a task nobody wanted.
    expires_at TIMESTAMPTZ NOT NULL,

    -- The last reading, so a change can be noticed without storing a history.
    last_sha256 TEXT,
    last_found BOOLEAN,
    last_excerpt TEXT,
    last_checked_at TIMESTAMPTZ,
    last_error TEXT,

    notified_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX watches_due_idx ON watches (last_checked_at) WHERE paused_at IS NULL;
CREATE INDEX watches_household_idx ON watches (household_id);
