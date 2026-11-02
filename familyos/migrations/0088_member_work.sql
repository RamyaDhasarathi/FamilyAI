-- A person's own work place and usual start, for their commute on Today. Until now there was one office for the whole household.
-- Personal: shown to that person and to guardians, covered by erasure (the columns go with the member row) and by export.
ALTER TABLE members
    ADD COLUMN work_place TEXT,
    ADD COLUMN work_lat DOUBLE PRECISION,
    ADD COLUMN work_lon DOUBLE PRECISION,
    ADD COLUMN work_starts TIME,
    ADD CONSTRAINT members_work_point_chk CHECK ((work_lat IS NULL) = (work_lon IS NULL));
