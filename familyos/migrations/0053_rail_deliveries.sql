-- Which rail delivered each school notice, and whether it was first or an
-- echo. A notice reaches the household by several rails (the school app read
-- by the phone's own hands, a WhatsApp forward, a photographed circular,
-- mail), and the same notice often arrives twice. One row per notice says
-- the rail it came by and whether an earlier notice from another rail
-- already carried the same date. The score per rail is computed from these
-- rows, never stored: a projection, like everything else.
CREATE TABLE rail_deliveries (
    artifact_id UUID PRIMARY KEY REFERENCES input_artifacts(id) ON DELETE CASCADE,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    school_id UUID REFERENCES schools(id) ON DELETE SET NULL,
    rail TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('first', 'echo', 'empty')),
    echo_of UUID REFERENCES input_artifacts(id) ON DELETE SET NULL,
    delivered_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX rail_deliveries_by_school ON rail_deliveries (household_id, school_id, rail, delivered_at DESC);
