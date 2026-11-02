-- WhatsApp, read from the member's own linked web session, for the chats they name and no others. Off until they say yes.
CREATE TABLE whatsapp_watches (
    member_id UUID PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    chats TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'off' CHECK (status IN ('off', 'needs_link', 'linked', 'lapsed', 'error')),
    consented_at TIMESTAMPTZ,
    consent JSONB NOT NULL DEFAULT '{}',
    cursors JSONB NOT NULL DEFAULT '{}',
    last_run_at TIMESTAMPTZ,
    last_ok_at TIMESTAMPTZ,
    last_error TEXT,
    last_found INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX whatsapp_watches_on_idx ON whatsapp_watches (household_id) WHERE enabled;
