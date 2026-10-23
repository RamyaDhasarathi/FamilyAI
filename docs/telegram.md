# Telegram intake

The second rail, offered beside WhatsApp rather than instead of it. A family
picks the one they already use, and both land in the same gateway.

## Why have it at all

WhatsApp is where Indian school communication is, which is why it is first and
why that will not change. But everything around Meta's Cloud API is paperwork:
business verification, an approved utility template, and a 24-hour customer
service window outside which free text is simply refused. Telegram has none of
it. A conversation with @BotFather produces a token, and the token works.

| | WhatsApp Cloud API | Telegram Bot API |
|---|---|---|
| to send at all | business verification | a token from @BotFather |
| reminder at 7am | approved utility template, two slots | ordinary text |
| outside 24 hours | refused (error 131047) | no such rule |
| media in | any size we accept | 20MB, Telegram's own ceiling |
| who the sender is | a phone number Meta verified | a numeric account id |
| cost to set up | days to weeks | minutes |

Two practical consequences. **Telegram unblocks development**: the reminder
rail can be exercised end to end today, with no approval pending. And for any
family that does use Telegram it is the better rail, because a reminder about
tomorrow's form arrives as a sentence rather than as a pre-approved form with
two slots in it.

## Identity: the one thing that is harder

WhatsApp hands us a verified phone number, and a guardian has already typed
that number into the member form, so a forwarded message places itself.

Telegram hands us a numeric account id. Nobody knows it, nobody would type it,
and there is no phone number anywhere in the payload. So the member binds it
once, themselves:

1. Signed in to the console, they press **Link my Telegram**.
2. That issues a one-time token and shows `https://t.me/<bot>?start=<token>`.
3. They open it on the phone with Telegram and press **Start**.
4. Telegram delivers `/start <token>`; the token is spent and the account id is
   written to `members.telegram_chat_id`.

The token is a `sign_in_links` row with `purpose = 'telegram'`, which buys the
two properties that table already has: one unused link per member at a time,
and a spend that is the same statement as the check. The purpose is
load-bearing rather than decorative -- **a binding token cannot be redeemed for
a console session, and a sign-in link cannot bind an account**. Either
direction would turn a token that travels through a chat window into a way in.

A `UNIQUE` index makes one Telegram account one member. Re-binding replaces,
so a parent who reinstalls Telegram and comes back with a new id asks for
another link rather than asking for support.

## The group rule, which is the whole design

A Telegram bot **can** read a group. Privacy mode -- on by default -- limits it
to commands aimed at it and replies to its own messages, but Telegram is plain
that it "can be disabled so that the bot receives all messages like an ordinary
user", and a bot added to a group **as an admin receives everything regardless
of the setting**. ([Telegram docs][privacy])

That is a real difference from WhatsApp, where no API reads a group at any
price. It would be easy to treat it as a feature. It is not one: a bot sitting
in the Class 4B parents group reading every message is the product nobody
asked for, and the difference between reading it and not is a checkbox in
somebody else's app.

So the limit lives in our code instead. `telegram.Message.directed` is true for

- **any message in a private chat** -- writing to the bot is the act of
  forwarding, exactly as picking the business number is on WhatsApp; and
- **in a group, only a message that names the bot (`@thebot ...`) or replies to
  one of its messages.**

`gateway.receive_telegram` refuses everything else with `not_addressed`, before
anything is stored and before any model runs. Nothing is said back into the
group, because a group that is not being read should not be told it is being
watched.

The effect: turning privacy mode off, or making the bot an admin, changes what
Telegram sends us and changes nothing about what we keep.

Two further refusals, both inherited rather than new:

- an account bound to no member is **refused and stored nowhere**, as on
  WhatsApp -- there is no household to quarantine it into;
- another bot's messages are never notices.

## What is stored

The same shape as WhatsApp. The message becomes a `telegram` artifact, private
to its sender; each file becomes a `telegram_media` child of it. The words
around a forwarded photo are often where the date is, so the parent is kept
even when it only carried a file.

Dedup is keyed `telegram:{chat_id}:{message_id}`. **A Telegram message_id is
unique within its chat and nowhere else**, so the chat is part of the key --
without it, the same id arriving from a group and from a private chat would
collide and the second would be swallowed. Telegram redelivers anything not
answered 2xx, so duplicates are the ordinary case rather than the strange one.

Edits are ignored rather than ingested: an edit reuses the original
message_id, so reading it again would supersede tasks the family has already
decided on. Channel posts are not handled -- a bot in a channel receives every
post, which for a school's announcement channel would be welcome, but a channel
post has no author to attribute it to and an artifact with no submitter has no
scope.

## Setting it up

```
FAMILYOS_TELEGRAM_BOT_TOKEN=        # @BotFather -> /newbot
FAMILYOS_TELEGRAM_WEBHOOK_SECRET=   # yours to invent, 1-256 of [A-Za-z0-9_-]
FAMILYOS_TELEGRAM_BOT_USERNAME=     # the @name, without the @
```

Register the webhook and the secret together. Locally that means a tunnel,
and `scripts/telegram-webhook.sh` does both -- it reads the token and secret
from `.env`, asks ngrok for its current public URL, and registers them:

```sh
ngrok http 8088 --traffic-policy-file scripts/ngrok-telegram.yml
./scripts/telegram-webhook.sh            # register, then print getWebhookInfo
./scripts/telegram-webhook.sh --show     # what Telegram currently thinks
./scripts/telegram-webhook.sh --delete   # before shutting the tunnel down
```

A free ngrok URL changes every time the tunnel restarts and Telegram holds
exactly one webhook URL per bot, so that first command has to be re-run after
every restart. The traffic policy is not optional: an unrestricted tunnel to
the dev server publishes the whole API, including `POST /v1/households`, which
takes no auth. Telegram only needs the one path, so only the one path is
served and everything else answers 404.

The script registers `allowed_updates=["message"]`, which is a deny-list by
omission: edits, reactions, polls and member changes are never sent at all.
The gateway would refuse them anyway -- this just keeps them off the wire.

In production the same call, without the tunnel:

```
curl -F url=https://<host>/v1/inbound/telegram \
     -F secret_token=<the same secret> \
     https://api.telegram.org/bot<token>/setWebhook
```

The secret is echoed in `X-Telegram-Bot-Api-Secret-Token` on every delivery and
is the whole of the authentication -- unlike Meta's `X-Hub-Signature-256` it is
a shared secret rather than a signature over the body, so it proves the sender
and nothing about what they sent. Unset, **nothing is accepted**: an open
webhook is worse than no rail.

Leave privacy mode on in BotFather and do not make the bot a group admin.
FamilyOS refuses undirected group traffic either way, which is the point --
but there is no reason to be handed what you will not read.

To use it for reminders as well, `FAMILYOS_REMINDER_CHANNEL=telegram`. The boot
log says what that rail will and will not reach, as it does for WhatsApp.

## Download limit

Telegram will not serve a bot a file over **20MB**, whatever `max_upload_bytes`
says. The URL that serves it embeds the bot token, so it is never logged and
never written into `source`: a leaked one is the bot.

[privacy]: https://core.telegram.org/bots/features#privacy-mode
