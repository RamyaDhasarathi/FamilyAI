-- Implied to-dos: what an event on the calendar quietly asks for.
--
-- A birthday party on Saturday asks for a gift by Wednesday. A PTM asks for
-- the questions you meant to raise. A trip asks for the passports to be
-- found. Nobody writes these down, which is why they are the mental load.
--
-- They are *suggested*, never added on their own: a card with Add and a
-- cross. Adding makes an ordinary to-do that remembers where it came from,
-- so the same event never suggests it twice; the cross is remembered for
-- the same reason. Both are per household, derived from the calendar, and
-- go when the household goes.
ALTER TABLE todos ADD COLUMN source_key TEXT;
CREATE INDEX todos_source_idx ON todos (household_id, source_key) WHERE source_key IS NOT NULL;

CREATE TABLE suggestion_dismissals (
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    dismissed_by UUID REFERENCES members(id) ON DELETE SET NULL,
    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (household_id, source_key)
);
