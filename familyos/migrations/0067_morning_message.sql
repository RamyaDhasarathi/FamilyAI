-- The morning message: what needs a member, as cards, once a day, inside their quiet hours and daily cap.
-- On by default at 8 am for adults; null turns it off. morning_runs records the day it was handled (sent, or silent
-- because nothing needed them) so it runs once.
ALTER TABLE members ADD COLUMN morning_hour SMALLINT DEFAULT 8 CHECK (morning_hour BETWEEN 0 AND 23);
CREATE TABLE morning_runs (
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    run_on DATE NOT NULL,
    sent BOOLEAN NOT NULL,
    PRIMARY KEY (member_id, run_on)
);
