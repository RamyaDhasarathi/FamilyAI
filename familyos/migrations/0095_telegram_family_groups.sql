-- A Telegram group a guardian has said is the family's own. In it the bot answers two read-only questions ("today", "week") from what the
-- household shared with everyone, and nothing else. Anywhere else a group is not read (docs/telegram.md, "The group rule").
CREATE TABLE telegram_family_groups (
    chat_id BIGINT PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    registered_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX telegram_family_groups_household_idx ON telegram_family_groups (household_id);
