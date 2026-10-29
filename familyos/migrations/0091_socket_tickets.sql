-- One-use tickets for the sockets a browser or app cannot put a bearer token on (the live view, an errand taken over, the phone driver),
-- kept for a minute. In a table, not in a process, so the worker that issues one need not be the worker that redeems it. Only a hash of
-- the ticket is stored; what the socket needs (an errand's browser address) is read again when it is redeemed.
CREATE TABLE socket_tickets (
    ticket_sha256 BYTEA PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('live', 'errand_live', 'phone')),
    subject_id UUID NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX socket_tickets_expires_idx ON socket_tickets (expires_at);
