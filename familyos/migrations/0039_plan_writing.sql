-- A plan is asked for in a moment and written over a minute. The row exists
-- from the ask, as "writing", so the page can open on it and watch it fill;
-- a write that fails says why on the row rather than vanishing.
ALTER TABLE plans DROP CONSTRAINT IF EXISTS plans_status_check;
ALTER TABLE plans ADD CONSTRAINT plans_status_check
    CHECK (status IN ('writing', 'draft', 'active', 'done', 'dropped', 'failed'));
ALTER TABLE plans ADD COLUMN error TEXT;
