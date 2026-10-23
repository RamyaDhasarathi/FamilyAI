-- A school's address, typed by a guardian, so the school run from home can
-- be measured when the public map does not know the school by its name;
-- and its timings, so "leave by" can be said and a bad morning's traffic
-- can be told before it is too late to matter.
ALTER TABLE schools
    ADD COLUMN address TEXT,
    ADD COLUMN starts_at TIME,
    ADD COLUMN ends_at TIME;
