-- Passkeys (WebAuthn): a public key per device or password manager, bound to the address (rp_id) it was made at. The private key never leaves the member's device.
CREATE TABLE member_passkeys (
    id UUID PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    rp_id TEXT NOT NULL,
    credential_id BYTEA NOT NULL UNIQUE,
    public_key BYTEA NOT NULL,
    sign_count BIGINT NOT NULL DEFAULT 0,
    transports TEXT[] NOT NULL DEFAULT '{}',
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
    backed_up BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX member_passkeys_member_idx ON member_passkeys (member_id) WHERE revoked_at IS NULL;
-- One-use challenges, kept for minutes.
CREATE TABLE webauthn_challenges (
    challenge BYTEA PRIMARY KEY,
    purpose TEXT NOT NULL CHECK (purpose IN ('register', 'login')),
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    rp_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
