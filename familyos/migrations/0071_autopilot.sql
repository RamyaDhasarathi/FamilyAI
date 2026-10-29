-- Household Autopilot: routines that fire on an event as well as on a clock, with an approval policy, a pause switch and a
-- history of every run. An event routine runs once per event (a bill, a changed date, a trip N days away, a clash); "tell"
-- only says, "prepare" also stages what it would do as buttons a person presses.
ALTER TABLE routines
    ADD COLUMN trigger TEXT NOT NULL DEFAULT 'time' CHECK (trigger IN ('time', 'bill_arrived', 'date_changed', 'trip_soon', 'conflict')),
    ADD COLUMN trigger_days SMALLINT CHECK (trigger_days BETWEEN 0 AND 60),
    ADD COLUMN paused BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN policy TEXT NOT NULL DEFAULT 'tell' CHECK (policy IN ('tell', 'prepare'));
ALTER TABLE routines ALTER COLUMN hour SET DEFAULT 0;
CREATE TABLE routine_runs (
    id BIGSERIAL PRIMARY KEY,
    routine_id UUID NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    trigger TEXT NOT NULL,
    event_ref TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('sent', 'silent', 'waited', 'failed')),
    said TEXT
);
CREATE UNIQUE INDEX routine_runs_once_idx ON routine_runs (routine_id, event_ref) WHERE event_ref IS NOT NULL;
CREATE INDEX routine_runs_routine_idx ON routine_runs (routine_id, ran_at DESC);
