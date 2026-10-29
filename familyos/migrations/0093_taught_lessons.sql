-- A lesson in progress, as a row, for a deployment with more than one worker (FAMILYOS_MULTI_WORKER=true): which member has how many, and which
-- worker holds each. The lesson's browser or phone socket cannot move between workers, so only the owner can step it; another worker finds the
-- row and says so (the request needs sticky routing, docs/deploy.md). With one worker nothing is written here.
CREATE TABLE taught_lessons (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX taught_lessons_member_idx ON taught_lessons (member_id);
