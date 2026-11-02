-- A Gmail message that would not store, counted per poll. After gmail_skip_after tries it is stepped past (skipped_at)
-- so one message that can never be stored does not stall the whole mailbox for good. Holds an id, never mail content.
CREATE TABLE mailbox_failures (
    account_id  UUID NOT NULL REFERENCES google_accounts(id) ON DELETE CASCADE,
    gmail_id    TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 1,
    last_error  TEXT,
    skipped_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_id, gmail_id)
);
