-- The optional family wallet's own tables (familyos/wallet/). Every table hangs off the household with ON DELETE CASCADE, so erasing a household
-- removes them with it. They are inert when the package is not loaded or the household's switch is off: nothing reads or writes them then.
-- Nothing here is a key: addresses are public, signatures are proofs, and the server never holds anything that can move funds.

-- A member's wallet address, proved by a signed message. One live link per address across the deployment.
CREATE TABLE wallet_links (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    address TEXT NOT NULL CHECK (address ~ '^0x[0-9a-f]{40}$'),
    chain_id BIGINT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX wallet_links_address_idx ON wallet_links (address) WHERE revoked_at IS NULL;
CREATE INDEX wallet_links_member_idx ON wallet_links (member_id) WHERE revoked_at IS NULL;

-- One-use nonces for Sign-In with Ethereum messages. A link nonce belongs to the member who asked; a sign-in nonce belongs to nobody yet.
CREATE TABLE wallet_nonces (
    nonce_hash TEXT PRIMARY KEY,
    purpose TEXT NOT NULL CHECK (purpose IN ('link', 'signin')),
    household_id UUID REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);
CREATE INDEX wallet_nonces_expiry_idx ON wallet_nonces (expires_at);

-- The family's own wallet: an address a guardian names, and the limits FamilyOS holds every proposal to. Amounts are in the token's smallest unit.
CREATE TABLE household_wallet (
    household_id UUID PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
    address TEXT CHECK (address IS NULL OR address ~ '^0x[0-9a-f]{40}$'),
    label TEXT CHECK (label IS NULL OR length(label) BETWEEN 1 AND 60),
    set_by UUID REFERENCES members(id) ON DELETE SET NULL,
    set_at TIMESTAMPTZ,
    per_transfer_limit NUMERIC(78, 0) NOT NULL CHECK (per_transfer_limit >= 0),
    daily_limit NUMERIC(78, 0) NOT NULL CHECK (daily_limit >= 0),
    monthly_limit NUMERIC(78, 0) NOT NULL CHECK (monthly_limit >= 0)
);

-- A transfer someone proposed and a guardian approved, exactly as shown (the fingerprint). FamilyOS never sends it: the guardian does, from the family wallet,
-- and the chain is read afterwards to see that it happened as approved.
CREATE TABLE wallet_transfers (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    proposed_by UUID REFERENCES members(id) ON DELETE SET NULL,
    chain_id BIGINT NOT NULL,
    from_address TEXT NOT NULL CHECK (from_address ~ '^0x[0-9a-f]{40}$'),
    payee_address TEXT NOT NULL CHECK (payee_address ~ '^0x[0-9a-f]{40}$'),
    payee_label TEXT CHECK (payee_label IS NULL OR length(payee_label) <= 60),
    payee_new BOOLEAN NOT NULL,
    token_address TEXT NOT NULL CHECK (token_address ~ '^0x[0-9a-f]{40}$'),
    token_symbol TEXT NOT NULL,
    decimals SMALLINT NOT NULL,
    amount NUMERIC(78, 0) NOT NULL CHECK (amount > 0),
    memo TEXT CHECK (memo IS NULL OR length(memo) <= 140),
    fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved', 'submitted', 'settled', 'rejected', 'expired', 'failed')),
    approved_by UUID REFERENCES members(id) ON DELETE SET NULL,
    approval_signature TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    tx_hash TEXT CHECK (tx_hash IS NULL OR tx_hash ~ '^0x[0-9a-f]{64}$'),
    settled_at TIMESTAMPTZ,
    failure_reason TEXT
);
CREATE INDEX wallet_transfers_household_idx ON wallet_transfers (household_id, created_at DESC);
