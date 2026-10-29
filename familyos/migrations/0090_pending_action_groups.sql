-- Buttons offered together ("Accept" / "Not this") are one decision: answering one closes the others. They share a group id.
ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS group_id UUID;
CREATE INDEX IF NOT EXISTS pending_actions_group_idx ON pending_actions (group_id) WHERE group_id IS NOT NULL;
-- The sweep that purges answered and expired rows finds them by expiry.
CREATE INDEX IF NOT EXISTS pending_actions_expires_idx ON pending_actions (expires_at);
