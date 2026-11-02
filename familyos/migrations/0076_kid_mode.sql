-- Child and teen mode, built around growing autonomy and not surveillance. A child never signs in as a member: a guardian
-- gives them a separate, narrow, revocable key that reaches only their own day (kid.py), not the household.
CREATE TABLE kid_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    child_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);
CREATE TABLE kid_routine (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    child_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    slot TEXT NOT NULL CHECK (slot IN ('morning', 'evening')),
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
    icon TEXT NOT NULL DEFAULT '',
    position SMALLINT NOT NULL DEFAULT 0
);
CREATE INDEX kid_routine_child_idx ON kid_routine (child_id, slot, position);
CREATE TABLE kid_checks (
    child_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    key TEXT NOT NULL,
    done_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (child_id, day, key)
);
CREATE TABLE kid_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    child_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at TIMESTAMPTZ,
    answered_by UUID REFERENCES members(id) ON DELETE SET NULL,
    answer TEXT CHECK (answer IN ('yes', 'no', 'later')),
    note TEXT
);
-- A private journal: the child's. A guardian reads an entry only if the child shared it.
CREATE TABLE kid_journal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 2000),
    shared_at TIMESTAMPTZ
);
ALTER TABLE savings_goals ADD COLUMN owner_member_id UUID REFERENCES members(id) ON DELETE CASCADE;
