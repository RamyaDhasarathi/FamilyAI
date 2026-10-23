#!/usr/bin/env bash
# Point a running bot at this machine, through ngrok.
#
# The free ngrok URL changes every time the tunnel restarts, and Telegram
# holds exactly one webhook URL per bot, so this has to be re-run after every
# ngrok restart. That is the whole reason it is a script and not a doc.
#
#   ./scripts/telegram-webhook.sh            register, then show what Telegram thinks
#   ./scripts/telegram-webhook.sh --show     only show
#   ./scripts/telegram-webhook.sh --delete   stop delivery (before shutting the tunnel)
#
# Reads the token, the @name and the webhook secret from .env. Nothing is
# echoed: a bot token in a terminal log is the bot.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "no .env here"; exit 1; }
set -a; . ./.env; set +a

TOKEN="${FAMILYOS_TELEGRAM_BOT_TOKEN:-}"
SECRET="${FAMILYOS_TELEGRAM_WEBHOOK_SECRET:-}"
[ -n "$TOKEN" ]  || { echo "FAMILYOS_TELEGRAM_BOT_TOKEN is empty in .env -- get one from @BotFather"; exit 1; }
[ -n "$SECRET" ] || { echo "FAMILYOS_TELEGRAM_WEBHOOK_SECRET is empty in .env -- invent any 1-256 of [A-Za-z0-9_-]"; exit 1; }

API="https://api.telegram.org/bot${TOKEN}"

# Check the @name against the bot the token belongs to, before anything else.
# Getting this wrong fails silently and in two places at once: the deep link
# points at whoever does own that name, and a group mention of the real bot is
# not recognised as addressing it. Ask the API rather than trust the file.
WHO=$(curl -fsS "$API/getMe" | python3 -c '
import json, sys
r = json.load(sys.stdin).get("result", {})
print(r.get("username", ""), r.get("can_read_all_group_messages"))
') || { echo "That bot token was refused by Telegram."; exit 1; }
REAL=${WHO%% *}; READS_GROUPS=${WHO##* }
if [ "$REAL" != "${FAMILYOS_TELEGRAM_BOT_USERNAME:-}" ]; then
  echo "FAMILYOS_TELEGRAM_BOT_USERNAME is '${FAMILYOS_TELEGRAM_BOT_USERNAME:-}',"
  echo "but that token belongs to @$REAL. Fix .env -- it must be the bot's own"
  echo "name, not yours, or the deep link and group mentions both break."
  exit 1
fi
if [ "$READS_GROUPS" = "True" ]; then
  echo "NOTE: privacy mode is OFF, so Telegram will send this bot every message"
  echo "      in any group it is in. FamilyOS refuses all of it, but turn it back"
  echo "      on in @BotFather -> Bot Settings -> Group Privacy."
fi

show() {
  curl -fsS "$API/getWebhookInfo" | python3 -c '
import json, sys
r = json.load(sys.stdin).get("result", {})
print("  url                 ", r.get("url") or "(none)")
print("  custom certificate  ", r.get("has_custom_certificate"))
print("  pending updates     ", r.get("pending_update_count"))
# The two fields worth reading. A last_error_message means Telegram tried and
# we answered badly -- usually a dead tunnel or a 401 from a stale secret.
if r.get("last_error_message"):
    print("  LAST ERROR          ", r.get("last_error_message"))
if r.get("last_synchronization_error_date"):
    print("  last sync error     ", r.get("last_synchronization_error_date"))
'
}

case "${1:-}" in
  --show)
    show; exit 0;;
  --delete)
    curl -fsS -X POST "$API/deleteWebhook" > /dev/null
    echo "Webhook deleted. Telegram will stop delivering."
    show; exit 0;;
esac

# The tunnel's public URL, from ngrok's own local API rather than from a
# scraped log line.
PUBLIC=$(curl -fsS http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c '
import json, sys
tunnels = json.load(sys.stdin).get("tunnels", [])
https = [t["public_url"] for t in tunnels if t["public_url"].startswith("https://")]
print(https[0] if https else "")
' || true)
[ -n "$PUBLIC" ] || { echo "No ngrok tunnel found on :4040. Start one:  ngrok http 8088"; exit 1; }

URL="$PUBLIC/v1/inbound/telegram"
echo "Registering $URL"

# allowed_updates is a deny-list by omission: Telegram is asked for messages
# and nothing else, so edits, reactions, polls and member changes are never
# sent at all. The gateway would refuse them anyway -- this just means they do
# not cross the wire.
curl -fsS -X POST "$API/setWebhook" \
  -F "url=$URL" \
  -F "secret_token=$SECRET" \
  -F 'allowed_updates=["message"]' \
  -F 'drop_pending_updates=true' > /dev/null

echo "Registered. Telegram says:"
show
