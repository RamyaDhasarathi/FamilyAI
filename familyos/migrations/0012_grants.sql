-- Delegation without a role taxonomy.
--
-- A nanny needs Thursday's pickup and nothing else; a grandparent needs the
-- schedule but not the medical form. Adding a 'carer' role answers neither and
-- leads to 'tutor', 'driver' and 'grandparent_but_only_schedules'. A grant
-- bounds the objects instead of the person.
--
-- Grants reach obligations and never artifacts. The carer is told "collect
-- Kabir at 15:30 on Thursday"; they never see the notice it was read from,
-- which may also name a fee, a medical appointment and another child. So
-- artifacts.VISIBLE_TO_MEMBER is untouched by all of this.
CREATE TABLE grants (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    grantee_member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    granted_by UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,

    -- The selector. NULL subject means "about anyone", which is still bounded
    -- by the actions below.
    subject_member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    actions TEXT[] NOT NULL CHECK (
        cardinality(actions) > 0
        AND actions <@ ARRAY['sign', 'pay', 'attend', 'submit', 'prepare', 'note']::TEXT[]),

    -- A sentence the family reads on their own visibility page. A permission
    -- nobody can explain is a permission nobody reviews.
    reason TEXT NOT NULL CHECK (length(btrim(reason)) > 0),

    -- Never nullable: a grant without an expiry is a role wearing a hat.
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoked_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Delegating to yourself is not delegation.
    CHECK (grantee_member_id <> granted_by)
);
CREATE INDEX grants_grantee_idx ON grants (grantee_member_id) WHERE revoked_at IS NULL;
CREATE INDEX grants_household_idx ON grants (household_id);
