-- What each member accepts or waves away, by kind of suggestion ("gift", "ptm", "reorder"), so what is suggested to them
-- can be ordered by what they actually use and a kind they keep dismissing goes quiet. Counts only: the kind and the
-- outcome, never the text of what was suggested. A member can see and clear it; it goes with the member on erasure.
CREATE TABLE suggestion_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 40),
    outcome TEXT NOT NULL CHECK (outcome IN ('accepted', 'dismissed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX suggestion_feedback_member_idx ON suggestion_feedback (member_id, kind, created_at DESC);
