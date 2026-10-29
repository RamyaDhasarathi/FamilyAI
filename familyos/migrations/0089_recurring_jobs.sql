-- One live job per recurring kind, enforced by the database (jobs.ensure_recurring) instead of a check-then-insert in thirteen modules.
-- `recurring` marks the deployment-wide sweeps; the partial unique index lets each kind have at most one that is not finished.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS recurring BOOLEAN NOT NULL DEFAULT FALSE;

-- A table that already holds duplicates (the old check-then-insert could race): keep the oldest live job of each kind, cancel the rest.
WITH live AS (
    SELECT id, row_number() OVER (PARTITION BY kind ORDER BY created_at, id) AS n
    FROM jobs
    WHERE household_id IS NULL
      AND status NOT IN ('succeeded', 'failed', 'cancelled')
      AND kind IN ('digest_weekly', 'morning_sweep', 'whatsapp_watch_sweep', 'exam_sheets', 'nudges_sweep', 'send_reminders',
                   'send_actions', 'text_sealing_sweep', 'sync_calendars', 'routines_sweep', 'handoffs_sweep', 'check_watches',
                   'poll_mailboxes'))
UPDATE jobs SET status = 'cancelled', settled_at = now(), updated_at = now(), lease_id = NULL, lease_until = NULL
WHERE id IN (SELECT id FROM live WHERE n > 1);

UPDATE jobs SET recurring = TRUE
WHERE household_id IS NULL
  AND status NOT IN ('succeeded', 'failed', 'cancelled')
  AND kind IN ('digest_weekly', 'morning_sweep', 'whatsapp_watch_sweep', 'exam_sheets', 'nudges_sweep', 'send_reminders',
               'send_actions', 'text_sealing_sweep', 'sync_calendars', 'routines_sweep', 'handoffs_sweep', 'check_watches',
               'poll_mailboxes');

CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_live_recurring_idx ON jobs (kind)
    WHERE recurring AND status NOT IN ('succeeded', 'failed', 'cancelled');
