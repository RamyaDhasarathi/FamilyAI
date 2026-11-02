-- Location sharing between the household's adults. Each member opts in for themselves and can stop
-- at any moment, which deletes their stored point. Only the latest point is kept, never a trail.
ALTER TABLE members ADD COLUMN location_sharing boolean NOT NULL DEFAULT false;

CREATE TABLE member_locations (
    member_id UUID PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    lat DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon DOUBLE PRECISION NOT NULL CHECK (lon BETWEEN -180 AND 180),
    accuracy_m INTEGER,
    recorded_at TIMESTAMPTZ NOT NULL,
    at_place TEXT,                      -- 'home', 'work' or null: where the point falls among the household's saved places
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX member_locations_household_idx ON member_locations (household_id);
