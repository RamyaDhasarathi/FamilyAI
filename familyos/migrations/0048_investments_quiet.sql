-- Investment mail -- e-votes, ballots, AGMs, contract notes -- is filed and
-- asks nothing of the family unless a guardian says otherwise.
ALTER TABLE households ADD COLUMN investments_quiet BOOLEAN NOT NULL DEFAULT true;
