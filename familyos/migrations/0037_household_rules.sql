-- The household's rules, each a sentence with a switch, all on by default.
-- A guardian turns one off for the household. Deployment settings
-- (FAMILYOS_DIGEST_ENABLED, FAMILYOS_CALENDAR_WRITE_ENABLED) still gate the
-- feature itself; these say what this family wants of it.
ALTER TABLE households ADD COLUMN weekly_digest BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE households ADD COLUMN calendar_follows_decisions BOOLEAN NOT NULL DEFAULT TRUE;
