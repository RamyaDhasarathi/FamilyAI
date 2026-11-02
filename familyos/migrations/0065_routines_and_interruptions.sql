-- Routines: one instruction and the time to run it, set by a member in chat and answered in chat. A routine with nothing
-- to say stays silent. Interruption budget: how much FamilyOS may say unprompted, per member.
CREATE TABLE routines (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    instruction TEXT NOT NULL CHECK (char_length(instruction) BETWEEN 3 AND 400),
    weekday SMALLINT CHECK (weekday BETWEEN 0 AND 6),            -- 0 is Monday; null is every day
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),         -- in the household's own time zone
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX routines_active_idx ON routines (household_id) WHERE active;

-- Each unprompted message sent to a member, so the daily cap can be counted.
CREATE TABLE proactive_log (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX proactive_log_member_idx ON proactive_log (member_id, sent_at DESC);

ALTER TABLE members
    ADD COLUMN quiet_from SMALLINT NOT NULL DEFAULT 22 CHECK (quiet_from BETWEEN 0 AND 23),
    ADD COLUMN quiet_to SMALLINT NOT NULL DEFAULT 7 CHECK (quiet_to BETWEEN 0 AND 23),
    ADD COLUMN proactive_daily_cap SMALLINT NOT NULL DEFAULT 3 CHECK (proactive_daily_cap BETWEEN 0 AND 20);
