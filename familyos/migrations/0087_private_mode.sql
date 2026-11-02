-- "Make it private" in one tap: the family secret is one recovery phrase (a 1-of-1 SLIP-39 share, threshold 1) kept by the family, and
-- each trusted device holds its own random device secret that also unwraps the household key. The server stores only wrapped copies;
-- neither the phrase nor any device secret is ever stored. Opening the household on a device needs a recent passkey sign-in AND that
-- device's secret, so a copied database or a stolen token alone opens nothing.
ALTER TABLE family_keys DROP CONSTRAINT IF EXISTS family_keys_threshold_check;
ALTER TABLE family_keys DROP CONSTRAINT IF EXISTS family_keys_shares_check;
ALTER TABLE family_keys DROP CONSTRAINT IF EXISTS family_keys_check;
ALTER TABLE family_keys ADD CONSTRAINT family_keys_threshold_check CHECK (threshold BETWEEN 1 AND 9);
ALTER TABLE family_keys ADD CONSTRAINT family_keys_shares_check CHECK (shares BETWEEN 1 AND 9 AND shares >= threshold);
ALTER TABLE family_keys ADD COLUMN simple BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE family_key_devices (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
    wrapped_key BYTEA NOT NULL,
    pending BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX family_key_devices_member_idx ON family_key_devices (member_id) WHERE revoked_at IS NULL;

-- Which sign-ins came from a passkey, so unlocking can ask for a recent one.
ALTER TABLE member_tokens ADD COLUMN passkey_at TIMESTAMPTZ;
