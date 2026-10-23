-- Domains a guardian has already vouched for.
--
-- The household address is meant to go on a school admission form, so the
-- sender who matters most is one who will never be a member. Judging by
-- membership alone quarantined every circular; judging by authentication
-- alone would let any spammer with correct DKIM straight in, because DMARC
-- proves who sent a message and not that the family wants it.
--
-- So: the first message from a domain waits for a guardian, and vouching for
-- it trusts that domain afterwards. The school's first circular is held once;
-- every one after it is read.
CREATE TABLE trusted_sender_domains (
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    domain TEXT NOT NULL CHECK (domain = lower(domain) AND length(btrim(domain)) > 0),
    added_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (household_id, domain)
);
