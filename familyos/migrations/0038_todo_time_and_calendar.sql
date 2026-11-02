-- A to-do can carry a time ("the dentist, Monday 11:00"), and a dated to-do
-- goes to the member's Google Calendar under the same rule as an accepted
-- date; the event's id is kept so it can be taken off again when the to-do
-- is done or removed.
ALTER TABLE todos ADD COLUMN due_time TIME;
ALTER TABLE todos ADD COLUMN calendar_event_id TEXT;
ALTER TABLE todos ADD COLUMN calendar_account_id UUID REFERENCES google_accounts(id) ON DELETE SET NULL;
