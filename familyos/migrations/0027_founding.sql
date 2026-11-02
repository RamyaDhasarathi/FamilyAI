-- Founding a household takes proof of the address.
--
-- POST /households took none: anyone who could reach the API could create
-- households, each with its own guardian token, in anybody's database. On
-- localhost that was a curiosity; the moment the console is reachable from a
-- phone it is the front door standing open.
--
-- The proof is the same one sign-in already relies on: the person holds the
-- mailbox. Google says so at the end of its callback, or a link mailed to the
-- address says so when it comes back. Either way a ticket is issued, bound to
-- that address, spent once, and gone in minutes. There is no member yet to
-- hang it on, so it is not a sign_in_links row; it is its own small table.
CREATE TABLE founding_tickets (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX founding_tickets_email_idx ON founding_tickets (lower(email)) WHERE used_at IS NULL;
