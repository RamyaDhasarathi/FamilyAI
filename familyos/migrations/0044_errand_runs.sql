-- An errand's run keeps a screenshot at each step, as an artifact on the
-- 'errand' channel, private to the member whose session ran it. And an
-- errand may be a 'look' -- read the slots, buy nothing -- which needs no
-- approval because no money can move.
ALTER TABLE input_artifacts DROP CONSTRAINT input_artifacts_channel_check;
ALTER TABLE input_artifacts ADD CONSTRAINT input_artifacts_channel_check
    CHECK (channel IN ('upload', 'email', 'email_attachment', 'whatsapp', 'whatsapp_media',
                       'gmail', 'gmail_attachment', 'harvest', 'telegram', 'telegram_media', 'share', 'errand'));
ALTER TABLE errands DROP CONSTRAINT errands_kind_check;
ALTER TABLE errands ADD CONSTRAINT errands_kind_check CHECK (kind IN ('booking', 'purchase', 'look'));
