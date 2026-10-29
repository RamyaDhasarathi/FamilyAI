-- Things FamilyOS was taught by being shown: a short list of steps on a phone app or a public web page, by the words on the screen.
-- A skill only opens, taps by label, swipes and reads; it has no step that types, pays or submits. What it reads is handed in as a
-- private notice, like a shared screenshot.
CREATE TABLE taught_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
    kind TEXT NOT NULL CHECK (kind IN ('phone', 'web')),
    target TEXT NOT NULL,
    steps JSONB NOT NULL,
    runs INTEGER NOT NULL DEFAULT 0,
    last_run_at TIMESTAMPTZ,
    last_outcome TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ
);
CREATE INDEX taught_skills_member_idx ON taught_skills (member_id, created_at DESC);
