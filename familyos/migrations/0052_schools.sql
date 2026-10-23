-- A school as a thing of its own. The name was on each child, again in the
-- source map and again in the class history; the portal, the groups, the
-- term dates and the fees belong to the school, not to a child. One record
-- per school per household, the children attached by id; the name on the
-- member row stays as the display copy and the key attribution matches on.
CREATE TABLE schools (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    portal_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX schools_household_name ON schools (household_id, lower(name));
ALTER TABLE members ADD COLUMN school_id UUID REFERENCES schools(id) ON DELETE SET NULL;
INSERT INTO schools (id, household_id, name)
SELECT gen_random_uuid(), household_id, min(school)
FROM members WHERE role = 'child' AND school IS NOT NULL GROUP BY household_id, lower(school);
UPDATE members m SET school_id = s.id FROM schools s
WHERE m.household_id = s.household_id AND m.school IS NOT NULL AND lower(m.school) = lower(s.name);
