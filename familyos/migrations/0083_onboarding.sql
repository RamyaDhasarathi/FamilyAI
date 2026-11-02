-- First-run checklist: what a guardian has confirmed or skipped. The rest of the checklist is read off the household (members added, family key on).
ALTER TABLE households ADD COLUMN onboarding JSONB NOT NULL DEFAULT '{}'::jsonb;
-- Households that already exist are not nagged with a checklist.
UPDATE households SET onboarding = '{"dismissed": true}'::jsonb;
