-- What was on the receipt, line by line, so "we're nearly out of eggs" can
-- be said before anyone notices.
--
-- The extractor reads a receipt for what it asks; a receipt asks nothing, so
-- its lines are not claims and never become tasks. They are a pattern: the
-- same item bought every nine days is the one standing fact a grocery
-- receipt carries. Parsed deterministically from the receipt's own text at
-- read time (extraction/items.py), kept beside the artifact, derived like
-- everything else -- a re-read replaces them, erasure takes them.
CREATE TABLE receipt_items (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES input_artifacts(id) ON DELETE CASCADE,
    merchant TEXT NOT NULL,
    item TEXT NOT NULL,
    -- The item as a pattern key: lower-cased, brand and size words kept,
    -- quantities and prices stripped.
    item_key TEXT NOT NULL,
    quantity NUMERIC(8, 2),
    amount NUMERIC(12, 2),
    currency TEXT,
    bought_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX receipt_items_pattern_idx ON receipt_items (household_id, item_key, bought_on DESC);
CREATE INDEX receipt_items_artifact_idx ON receipt_items (artifact_id);
