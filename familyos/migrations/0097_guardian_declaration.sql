-- A guardian's own declaration, when giving consent for a child, that they are the child's parent or lawful guardian (India's DPDP Rule 10 asks the
-- fiduciary to check; docs/children-data-compliance.md). NULL on every consent given before this, and wherever it was not asked.
ALTER TABLE consent_records ADD COLUMN guardian_declared_at TIMESTAMPTZ;
