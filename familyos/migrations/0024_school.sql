-- Which school and class a child is in: the key a circular is actually
-- addressed by.
--
-- Extraction attaches a claim to a child by name, and circulars almost never
-- name one. They say "Dear Parents of Grade 4" or "Class IX students will",
-- or nothing at all and come from a school both children attend. The name was
-- not missing; the key was different. A child with a class and a school can
-- be found by either.
ALTER TABLE members ADD COLUMN school TEXT, ADD COLUMN class_label TEXT;
-- Children only, as with every other fact about who a person is at school.
ALTER TABLE members ADD CONSTRAINT members_school_child_check
    CHECK (role = 'child' OR (school IS NULL AND class_label IS NULL));

-- A subject the system worked out, as opposed to one a person set. Kept apart
-- so a re-read of the notice can replace what it inferred and never touch a
-- parent's own tagging -- and so the console can say which is which.
ALTER TABLE artifact_subjects ADD COLUMN inferred BOOLEAN NOT NULL DEFAULT FALSE;
