-- Health from the phone's Health app (which holds the Apple Watch's data): one summary row per day, the
-- member's own, only while they sync. Switching sync off deletes every row. No raw samples are ever sent.
ALTER TABLE members ADD COLUMN health_sync boolean NOT NULL DEFAULT false;
CREATE TABLE health_daily (
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    steps INTEGER CHECK (steps BETWEEN 0 AND 500000),
    sleep_minutes INTEGER CHECK (sleep_minutes BETWEEN 0 AND 1440),
    resting_hr SMALLINT CHECK (resting_hr BETWEEN 20 AND 250),
    workouts SMALLINT NOT NULL DEFAULT 0 CHECK (workouts BETWEEN 0 AND 50),
    workout_minutes INTEGER NOT NULL DEFAULT 0 CHECK (workout_minutes BETWEEN 0 AND 1440),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, day)
);
CREATE INDEX health_daily_household_idx ON health_daily (household_id);
