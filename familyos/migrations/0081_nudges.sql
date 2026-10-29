-- What the household graph noticed and told a person about, once each. A heads-up has a stable key; telling is recorded so it is never told twice,
-- and a person who dismissed it (suggestion_dismissals, key insight:<key>) is not told at all.
CREATE TABLE insight_notified (
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    notified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, key)
);
