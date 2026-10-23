-- The family's own calendar, read-only, so a notice can be told it clashes.
--
-- calendar.readonly is a *sensitive* scope, not a restricted one: ordinary
-- OAuth verification, no CASA assessment. That is why it can ship before Gmail
-- does, and why the two are asked for separately.
ALTER TABLE google_accounts ADD COLUMN calendar_synced_at TIMESTAMPTZ;
ALTER TABLE google_accounts ADD COLUMN calendar_error TEXT;

CREATE TABLE calendar_events (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    -- Whose calendar it came from. An event is private to that member unless
    -- they share it, exactly like a forwarded notice.
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES google_accounts(id) ON DELETE CASCADE,

    external_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    all_day BOOLEAN NOT NULL DEFAULT FALSE,

    visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'shared')),
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (ends_at >= starts_at)
);
-- One row per event per account: a re-sync updates rather than duplicates.
CREATE UNIQUE INDEX calendar_events_account_event_idx ON calendar_events (account_id, external_id);
CREATE INDEX calendar_events_window_idx ON calendar_events (household_id, starts_at, ends_at);
