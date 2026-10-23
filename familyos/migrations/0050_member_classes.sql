-- A child's school and class, with the date each began. The members row
-- keeps the current pair, as before; this table keeps every pair, so a
-- circular is matched to the class the child was in on the notice's date,
-- and "which class was she in last year" has an answer. Backfilled from
-- the current pair, dated to the start of the school year the member was
-- added in (June, as most Indian schools run), so next year's nudge fires.
CREATE TABLE member_classes (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    school TEXT,
    class_label TEXT,
    since DATE NOT NULL,
    set_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX member_classes_member_since ON member_classes (member_id, since DESC);
INSERT INTO member_classes (id, household_id, member_id, school, class_label, since)
SELECT gen_random_uuid(), household_id, id, school, class_label,
       CASE WHEN extract(month FROM created_at) >= 6 THEN make_date(extract(year FROM created_at)::int, 6, 1)
            ELSE make_date(extract(year FROM created_at)::int - 1, 6, 1) END
FROM members WHERE role = 'child' AND (school IS NOT NULL OR class_label IS NOT NULL);
