-- Accounts a family pays, so a bill that does not arrive can be noticed.
--
-- PayTM and GPay show bill reminders by *pulling*: you register a consumer
-- number and they fetch the bill over BBPS. That needs a licence or an
-- aggregator, and every aggregator earns on the payment -- which this system
-- structurally cannot do.
--
-- The push side needs none of that. The electricity board emails, the insurer
-- emails, the gas company texts; those already come down the intake ladder
-- with full provenance. What a biller row adds is the thing pulling cannot do
-- well: knowing that a bill which normally arrives on the 5th has not.
CREATE TABLE billers (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    -- Who added it. Household bills are shared; a life insurance premium is
    -- usually not, so this follows the same rule as a notice.
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    visibility TEXT NOT NULL DEFAULT 'shared' CHECK (visibility IN ('private', 'shared')),

    label TEXT NOT NULL CHECK (length(btrim(label)) > 0),
    provider TEXT NOT NULL CHECK (length(btrim(provider)) > 0),

    -- The consumer number is never stored. A ten-digit number is trivially
    -- brute-forced from a plain hash, so what is kept is an HMAC under the
    -- household key: stable enough to match an incoming bill within this
    -- family, meaningless outside it. The hint is the last four digits, which
    -- is all a person needs to recognise their own account.
    identifier_mac BYTEA,
    identifier_hint TEXT,

    -- How often a bill is expected, and how late is late. A monthly bill that
    -- is three days overdue is not news; one that is ten days overdue is.
    every_days INT NOT NULL DEFAULT 30 CHECK (every_days BETWEEN 1 AND 400),
    grace_days INT NOT NULL DEFAULT 7 CHECK (grace_days BETWEEN 0 AND 60),

    last_seen_at TIMESTAMPTZ,
    last_obligation_id UUID REFERENCES obligations(id) ON DELETE SET NULL,
    muted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX billers_household_idx ON billers (household_id) WHERE muted_at IS NULL;
CREATE UNIQUE INDEX billers_identifier_idx ON billers (household_id, identifier_mac)
    WHERE identifier_mac IS NOT NULL;
