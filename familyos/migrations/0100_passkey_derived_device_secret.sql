-- A trusted device whose secret is not stored anywhere: it is derived inside the member's passkey (the WebAuthn PRF extension) from a salt kept
-- here. The server keeps only the wrapped household key, which passkey made it and the salt. Opening needs that passkey's own user check.
ALTER TABLE family_key_devices ADD COLUMN prf_salt BYTEA;
ALTER TABLE family_key_devices ADD COLUMN credential_id BYTEA;
