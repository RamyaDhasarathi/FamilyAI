-- A member cannot paste a hashed token, so sign-in needs something a person can
-- use. One table serves both sign-in and invitation: the only difference is who
-- asked for the link, and whether the member has signed in before.
CREATE TABLE sign_in_links (
    id UUID PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    -- 'sign_in' was asked for by the member; 'invite' was sent by a guardian.
    purpose TEXT NOT NULL CHECK (purpose IN ('sign_in', 'invite')),
    -- Null for a sign-in the member asked for themselves.
    issued_by UUID REFERENCES members(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    -- Single use. Set the moment it is redeemed, inside the same statement that
    -- checks it, so two tabs cannot both spend one link.
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX sign_in_links_member_idx ON sign_in_links (member_id) WHERE used_at IS NULL;
