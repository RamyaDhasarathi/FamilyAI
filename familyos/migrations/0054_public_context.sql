-- Public context, read without any credential, each behind a switch that
-- is off until a guardian turns it on: the weather for tomorrow's dated
-- things, travel time from home to a dated place, the country's public
-- holidays, and a board's exam date sheet read once as a notice. Home is a
-- place name a guardian types, geocoded once.
ALTER TABLE households
    ADD COLUMN weather_lines BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN travel_time BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN public_holidays BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN exam_dates BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN home_place TEXT,
    ADD COLUMN home_lat DOUBLE PRECISION,
    ADD COLUMN home_lon DOUBLE PRECISION;
ALTER TABLE schools
    ADD COLUMN exam_sheet_url TEXT,
    ADD COLUMN exam_sheet_sha256 TEXT,
    ADD COLUMN exam_sheet_read_at TIMESTAMPTZ;
