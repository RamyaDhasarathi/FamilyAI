-- What Ask proposed and a person has not yet confirmed, held by id so any chat surface can confirm it with one tap.
CREATE TABLE pending_actions (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    params JSONB NOT NULL,
    summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    done_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ
);
CREATE INDEX pending_actions_member_idx ON pending_actions (member_id, created_at DESC);
