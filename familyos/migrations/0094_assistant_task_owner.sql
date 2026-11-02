-- Which worker runs an assistant task, and when it last said it was alive. A task whose heartbeat has stopped belongs to a worker that died, whatever
-- that worker was; one whose heartbeat is fresh is running on another worker and is left alone.
ALTER TABLE assistant_tasks ADD COLUMN owner TEXT;
ALTER TABLE assistant_tasks ADD COLUMN heartbeat_at TIMESTAMPTZ;
