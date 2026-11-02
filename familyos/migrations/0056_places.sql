-- The family's places, each a point picked from a map search or pasted as
-- a Google Maps link: home (already here), the office, and each school.
-- A point is kept beside the words so the drive is measured to the place
-- the family meant, not to the geocoder's best guess at a name.
ALTER TABLE households
    ADD COLUMN work_place TEXT,
    ADD COLUMN work_lat DOUBLE PRECISION,
    ADD COLUMN work_lon DOUBLE PRECISION;
ALTER TABLE schools
    ADD COLUMN lat DOUBLE PRECISION,
    ADD COLUMN lon DOUBLE PRECISION;
