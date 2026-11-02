-- Medications read from a prescription, and standing obligations a notice
-- never announces (the rent). A medication is a record with its dates, like a
-- document: the original stays on the notice. A standing obligation is a
-- family's own rule ("rent, ₹18,000, on the 5th, to the landlord") that makes
-- the month's obligation by itself; nothing is paid by either.
ALTER TABLE claims ADD COLUMN dose_text TEXT, ADD COLUMN times_per_day INTEGER CHECK (times_per_day IS NULL OR times_per_day BETWEEN 1 AND 12);
ALTER TABLE claims DROP CONSTRAINT claims_kind_check;
ALTER TABLE claims ADD CONSTRAINT claims_kind_check
    CHECK (kind IN ('event', 'deadline', 'payment', 'form', 'amendment', 'instruction', 'info', 'document', 'medication'));

CREATE TABLE medications (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES input_artifacts(id) ON DELETE CASCADE,
    claim_id UUID REFERENCES claims(id) ON DELETE SET NULL,
    drug TEXT NOT NULL,
    dose_text TEXT,
    times_per_day INTEGER CHECK (times_per_day IS NULL OR times_per_day BETWEEN 1 AND 12),
    patient_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    patient_text TEXT,
    prescriber TEXT,
    starts_on DATE,
    ends_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    superseded_by UUID
);
CREATE INDEX medications_live_idx ON medications (household_id, ends_on) WHERE superseded_at IS NULL;

CREATE TABLE standing_obligations (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    payee TEXT NOT NULL CHECK (length(payee) BETWEEN 1 AND 120),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 28),
    subject_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    pay_url TEXT,
    visibility TEXT NOT NULL DEFAULT 'shared' CHECK (visibility IN ('private', 'shared')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_month DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX standing_obligations_idx ON standing_obligations (household_id) WHERE active;
