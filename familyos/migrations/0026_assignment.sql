-- Who is handling a notice, which is a different question from whom it is
-- about. A circular about Kabir is Priya's to deal with this week, and the
-- note that says why ("can you let them know who's on pickup?") is the whole
-- point of saying so.
--
-- One assignee, on the artifact. An obligation already records who decided
-- it; this records who was asked to. Visibility is not changed by assigning:
-- a member can only be handed a notice they can already see, and the API
-- refuses the rest rather than widening a private notice on the quiet.
ALTER TABLE input_artifacts
    ADD COLUMN assigned_to UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN assigned_note TEXT,
    ADD COLUMN assigned_by UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN assigned_at TIMESTAMPTZ;
CREATE INDEX input_artifacts_assigned_idx ON input_artifacts (assigned_to) WHERE assigned_to IS NOT NULL;
