-- Hand-offs that close the loop: the person handed a notice says yes or no, a backup can take it if nobody answers, and the
-- household sets how long to wait. A hand-off is "pending" until the assignee answers; one made to oneself is accepted at once.
ALTER TABLE input_artifacts
    ADD COLUMN assigned_ack TEXT CHECK (assigned_ack IN ('pending', 'accepted', 'declined')),
    ADD COLUMN assigned_ack_at TIMESTAMPTZ,
    ADD COLUMN assigned_backup UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN assigned_escalated_at TIMESTAMPTZ;
ALTER TABLE households ADD COLUMN handoff_escalate_hours SMALLINT NOT NULL DEFAULT 24 CHECK (handoff_escalate_hours BETWEEN 1 AND 168);
CREATE INDEX input_artifacts_ack_idx ON input_artifacts (household_id) WHERE assigned_ack = 'pending' AND assigned_escalated_at IS NULL;
