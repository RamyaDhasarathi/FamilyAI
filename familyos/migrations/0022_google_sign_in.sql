-- Signing in with Google.
--
-- Separate from google_auth_states, which belongs to a member who is already
-- signed in and is connecting a mailbox. Here there is no member yet: the
-- whole point is to find out who is asking.
CREATE TABLE google_sign_in_states (
    state TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_at TIMESTAMPTZ
);
CREATE INDEX google_sign_in_states_created_idx ON google_sign_in_states (created_at);
