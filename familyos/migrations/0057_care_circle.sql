-- Caring for a parent from far away: who is who in the circle (a label, not
-- a permission: what a member may see is still visibility and grants), a
-- scam assessment kept on the notice it was made about, and the household's
-- own numbers for the constitution: how much earlier a document is warned
-- about, how far above its usual a bill is said, and the scam guard switch.
ALTER TABLE members
    ADD COLUMN circle_role TEXT CHECK (circle_role IN ('parent', 'sibling', 'spouse', 'caregiver', 'other')),
    ADD CONSTRAINT members_child_has_no_circle_role CHECK (role <> 'child' OR circle_role IS NULL);
ALTER TABLE input_artifacts ADD COLUMN suspicion JSONB;
CREATE INDEX input_artifacts_suspicion ON input_artifacts (household_id, received_at DESC) WHERE suspicion IS NOT NULL;
ALTER TABLE households
    ADD COLUMN scam_guard BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN doc_warn_days INTEGER NOT NULL DEFAULT 0 CHECK (doc_warn_days BETWEEN 0 AND 365),
    ADD COLUMN bill_flag_percent INTEGER NOT NULL DEFAULT 25 CHECK (bill_flag_percent BETWEEN 5 AND 300);
