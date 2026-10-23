-- A document the family holds -- a passport, a visa, a policy, a vehicle's
-- RC, its PUC, a driving licence -- read from a notice, kept with its dates.
-- Of its number only the last four characters: the original is on the notice.
ALTER TABLE claims ADD COLUMN document_kind TEXT, ADD COLUMN issuer TEXT, ADD COLUMN identifier_tail TEXT;
ALTER TABLE claims DROP CONSTRAINT claims_kind_check;
ALTER TABLE claims ADD CONSTRAINT claims_kind_check
    CHECK (kind IN ('event', 'deadline', 'payment', 'form', 'amendment', 'instruction', 'info', 'document'));
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES input_artifacts(id) ON DELETE CASCADE,
    claim_id UUID REFERENCES claims(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('passport', 'visa', 'insurance', 'vehicle_rc', 'puc', 'driving_licence', 'id_card', 'other')),
    title TEXT NOT NULL,
    holder_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    holder_text TEXT,
    issuer TEXT,
    identifier_tail TEXT CHECK (identifier_tail IS NULL OR length(identifier_tail) <= 4),
    valid_from DATE,
    expires_on DATE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    superseded_by UUID
);
CREATE INDEX documents_live_idx ON documents (household_id, expires_on) WHERE superseded_at IS NULL;
