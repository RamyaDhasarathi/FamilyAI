-- A to-do the family wrote itself.
--
-- Everything else dated in this system came out of a notice and points back
-- at it. A family also has things nobody mailed them about: "book the dentist",
-- "renew the car insurance before Diwali". The chat window is where those get
-- said, and they need somewhere to land that is not a fake notice.
--
-- Shared across the household's adults, like a note on the fridge. One
-- assignee, the same rule as handing over a notice: a child does not sign in,
-- so a to-do is never handed to one.
CREATE TABLE todos (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    assigned_to UUID REFERENCES members(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
    note TEXT CHECK (note IS NULL OR length(note) <= 500),
    due_date DATE,
    done_at TIMESTAMPTZ,
    done_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX todos_open_idx ON todos (household_id, due_date) WHERE done_at IS NULL;
