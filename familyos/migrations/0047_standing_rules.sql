-- Standing decisions, as the household's rules: a holiday is accepted the
-- moment it is read; a receipt that matches a bill closes it; a bill is
-- handed to a named adult. Each a sentence with a switch, audited when flipped.
ALTER TABLE households
    ADD COLUMN holidays_accepted BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN receipts_close_bills BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN bills_handed_to UUID REFERENCES members(id) ON DELETE SET NULL;
