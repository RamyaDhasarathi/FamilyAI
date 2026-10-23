-- The share sheet and Shortcuts as a rail, with a token a phone can hold.
--
-- "Send to FamilyOS" in any app's share sheet, or an automation that fires
-- on a bank SMS, needs somewhere to send and something to send it as. The
-- somewhere is POST /inbound/share. The something is a device token: a
-- member token that does not slide or expire, carries a label ("Arun's
-- iPhone shortcut"), and is revoked from the Household page like any other
-- sign-in. It is a member token so every visibility rule and every audit
-- line already applies to what the phone sends.
ALTER TABLE member_tokens
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'session' CHECK (kind IN ('session', 'device')),
    ADD COLUMN label TEXT CHECK (label IS NULL OR length(label) <= 80);

-- What arrived through the share sheet is its own channel: it carries no
-- sender, no group and no app -- the phone does not say -- so what it is
-- about comes from its words, or from the one word the person sends after it.
ALTER TABLE input_artifacts DROP CONSTRAINT input_artifacts_channel_check;
ALTER TABLE input_artifacts ADD CONSTRAINT input_artifacts_channel_check
    CHECK (channel IN ('upload', 'email', 'email_attachment', 'whatsapp', 'whatsapp_media',
                       'gmail', 'gmail_attachment', 'harvest', 'telegram', 'telegram_media', 'share'));
