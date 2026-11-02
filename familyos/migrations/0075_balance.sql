-- Mental-load balancing, opt-in by the household and private to the person it speaks to: off until a guardian switches it on.
ALTER TABLE households ADD COLUMN balance_enabled BOOLEAN NOT NULL DEFAULT FALSE;
