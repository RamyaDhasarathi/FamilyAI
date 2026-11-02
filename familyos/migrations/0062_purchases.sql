-- A purchase the family asked FamilyOS to make, from the request to the guardian's approval of that one purchase.
-- Card numbers are never stored: the payment provider holds the card and only an id of it is kept here.
ALTER TABLE households ADD COLUMN payment_method_id TEXT;       -- the card a guardian saved with the provider

CREATE TABLE purchases (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    requested_by UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    merchant_name TEXT NOT NULL CHECK (char_length(merchant_name) BETWEEN 1 AND 200),
    merchant_url TEXT CHECK (merchant_url IS NULL OR merchant_url ~ '^https?://'),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested'
        CHECK (status IN ('requested', 'approved', 'ready', 'declined', 'cancelled', 'completed', 'failed', 'expired')),
    note TEXT,                                   -- why it is waiting or failed, in words
    decided_by UUID REFERENCES members(id) ON DELETE SET NULL,
    decided_at TIMESTAMPTZ,
    provider TEXT,
    provider_ref TEXT,                           -- the provider's id for the allowance (never a card number)
    provider_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    obligation_id UUID REFERENCES obligations(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX purchases_household_idx ON purchases (household_id, created_at DESC);
