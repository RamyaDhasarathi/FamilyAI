-- Where the household lives. The country picks a profile in code (school
-- year, payment rails, document kinds); the time zone and the home currency
-- replace what was one server-wide setting and an assumption of rupees.
-- Every household so far is in India.
ALTER TABLE households ADD COLUMN country TEXT NOT NULL DEFAULT 'IN';
ALTER TABLE households ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata';
ALTER TABLE households ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR';
