-- A household may have its notices read and its questions answered by a
-- model running on the deployment's own machine, so the family's text
-- never leaves it. A switch on the household, off until a guardian says.
ALTER TABLE households ADD COLUMN local_models boolean NOT NULL DEFAULT false;
