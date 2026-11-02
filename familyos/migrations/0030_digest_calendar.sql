-- The Sunday digest, and the family's calendar written to.
--
-- A digest is sent once per member per week, and "once" has to survive a
-- restart in the middle of sending: the row is claimed before the message
-- goes, so a second sweep finds it taken.
CREATE TABLE digests (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    channel TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (member_id, period_start)
);

-- An accepted date can be put on the member's own Google Calendar, when they
-- have granted that (calendar.events.owned -- a sensitive scope, ordinary
-- verification, no CASA). The event id is kept so a change here -- dismissed,
-- handled, superseded, re-read -- updates or removes the one event rather
-- than making another. Which account wrote it is kept too: the event belongs
-- to that calendar, and only that account's token can take it back.
ALTER TABLE obligations
    ADD COLUMN calendar_event_id TEXT,
    ADD COLUMN calendar_account_id UUID REFERENCES google_accounts(id) ON DELETE SET NULL;
