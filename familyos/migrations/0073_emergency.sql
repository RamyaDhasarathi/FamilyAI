-- Emergency mode: one controlled card (contacts, allergies and current medicines, insurance, school pickup authorisations,
-- travel documents, optionally home access) that a guardian can share by a link that expires and can be revoked, and that
-- records every time it is opened. "I'm safe" check-ins are separate and only the household sees them.
CREATE TABLE emergency_profile (
    household_id UUID PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
    contacts JSONB NOT NULL DEFAULT '[]',
    pickup JSONB NOT NULL DEFAULT '[]',
    home_access TEXT,
    updated_by UUID REFERENCES members(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE members ADD COLUMN allergies TEXT, ADD COLUMN blood_group TEXT;
CREATE TABLE emergency_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 80),
    include_home BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    opened_count INTEGER NOT NULL DEFAULT 0,
    last_opened_at TIMESTAMPTZ
);
CREATE TABLE safe_checkins (
    id BIGSERIAL PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('safe', 'need_help')),
    note TEXT,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX safe_checkins_member_idx ON safe_checkins (member_id, at DESC);
