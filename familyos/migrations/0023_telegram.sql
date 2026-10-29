-- Telegram as a second intake rail, chosen per family rather than per product.
--
-- Telegram gives no phone number, so WhatsApp's identity trick does not carry
-- over: there a parent's number is already in `members.phone` because a
-- guardian typed it. Here the only durable handle is a numeric account id,
-- which nobody knows and nobody can type. So the member binds it themselves,
-- once, by following a one-time deep link -- and the id is what every later
-- message is matched against.
ALTER TABLE members ADD COLUMN telegram_chat_id BIGINT;

-- One Telegram account is one member, enforced rather than detected.
-- `member_by_phone` has to cope with the same number appearing in two
-- households, because a guardian can type anything into a form; nobody types
-- this, so the ambiguity can be made impossible instead of handled.
CREATE UNIQUE INDEX members_telegram_chat_idx ON members (telegram_chat_id)
    WHERE telegram_chat_id IS NOT NULL;

-- The binding link is a sign-in link with a third purpose. Reusing the table
-- buys its two properties for nothing: one unused link per member at a time,
-- and a spend that is the same statement as the check.
--
-- The purpose is load-bearing, not a label. A telegram link must not be
-- redeemable for a console session, and a sign-in link must not bind an
-- account: a token that could do either would let whoever intercepts one do
-- the other. `identity.redeem` and `identity.bind_telegram` each filter on it.
ALTER TABLE sign_in_links DROP CONSTRAINT sign_in_links_purpose_check;
ALTER TABLE sign_in_links ADD CONSTRAINT sign_in_links_purpose_check
    CHECK (purpose IN ('sign_in', 'invite', 'telegram'));

-- A new channel is a schema change, not a string somebody passes in. This is
-- the constraint that refused the first run of the Telegram tests, which is
-- exactly what it is for: an adapter cannot invent a channel the record does
-- not know about.
ALTER TABLE input_artifacts DROP CONSTRAINT input_artifacts_channel_check;
ALTER TABLE input_artifacts ADD CONSTRAINT input_artifacts_channel_check
    CHECK (channel IN ('upload', 'email', 'email_attachment', 'whatsapp', 'whatsapp_media',
                       'gmail', 'gmail_attachment', 'harvest', 'telegram', 'telegram_media'));
