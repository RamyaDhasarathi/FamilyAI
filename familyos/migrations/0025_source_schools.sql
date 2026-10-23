-- Where a notice arrived says which school it is from.
--
-- A circular pasted from the Grade 4 parents' group names no school, no class
-- and no child -- but it came from the Grade 4 parents' group, and that is
-- the whole answer. The message did not have to say it; the channel already
-- did. A household says once which school a source belongs to, and every
-- later notice from that source is attributed on arrival.
--
-- The same shape as trusted_sender_domains: a fact a guardian states once
-- about a source, rather than a decision asked for every time.
--
-- source_key is derived from an artifact's source by familyos.origin:
--   telegram:chat:<chat_id>      a Telegram group the bot was addressed in
--   email:<domain>               the sending domain of a mail
--   whatsapp:group:<name>        a group, where the dev bridge carries one
-- A private chat, a Cloud API forward and a paste carry no origin, and get
-- no key: the parent is the sender there, not the school.
CREATE TABLE source_schools (
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    school TEXT NOT NULL,
    set_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (household_id, source_key)
);
