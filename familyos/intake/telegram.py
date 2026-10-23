"""Telegram Bot API adapter: the same four steps, a friendlier wire.

Telegram is the rail WhatsApp would be if Meta sold it differently. There is
no business verification, no template approval and no twenty-four hour window:
a bot token from BotFather works immediately, and a reminder at 7am is an
ordinary message rather than a pre-approved form with two slots. For a family
that uses Telegram this is strictly better. The reason WhatsApp stays first is
not technical -- it is that an Indian school's class group is on WhatsApp.

Two differences from `intake/whatsapp.py` matter, and both are about identity:

**There is no phone number.** Meta hands us a verified number, which a
guardian has already typed into the member form, so a forwarded message places
itself. Telegram hands us a numeric account id that nobody knows and nobody
would type. So the member binds it once, by opening a one-time deep link
(`identity.bind_telegram`), and every later message is matched on the id.

**A bot can read a group, and must not.** Privacy mode -- on by default --
limits a bot in a group to commands aimed at it, replies to its own messages
and service messages. But it "can be disabled so that the bot receives all
messages like an ordinary user", and a bot added to a group *as an admin*
receives everything regardless of the setting. ([Telegram docs][1]) Either
would turn this product into something that reads a parents' group, and the
difference between the two states is a checkbox in someone else's app.

So the rule lives here instead, as `Message.directed`, and the gateway refuses
anything else. A private chat is wholly directed: the parent chose to write to
us, exactly as forwarding to a business number is a choice. In a group only a
message that names the bot or replies to it is, however much Telegram is
willing to send. That makes the group limit a property of our code rather than
of a setting a well-meaning admin can undo.

Channel posts are not handled. A bot in a channel receives every post, which
for a school's announcement channel would be welcome -- but a channel post has
no author to attribute it to, and an artifact with no submitter has no scope.

[1]: https://core.telegram.org/bots/features#privacy-mode
"""
from __future__ import annotations

import hmac
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# What a forwarded school message can reasonably be. `photo` is a list of
# sizes rather than one file; the rest are single objects.
MEDIA_KINDS = ("document", "photo", "video", "audio", "voice", "video_note", "animation")

# Telegram will not serve a bot anything larger, whatever our own upload
# ceiling is: "bots can download files of up to 20MB in size."
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

# A Telegram deep-link payload is at most 64 characters from [A-Za-z0-9_-],
# which is what a binding token has to fit inside.
PAYLOAD_MAX = 64
_PAYLOAD_OK = re.compile(rf"\A[A-Za-z0-9_-]{{1,{PAYLOAD_MAX}}}\Z")

GROUP_CHATS = ("group", "supergroup")


class BadSecret(Exception):
    """The request did not come from Telegram."""


@dataclass
class Media:
    file_id: str
    media_type: str
    filename: str | None = None
    caption: str | None = None


@dataclass
class Message:
    message_id: int
    chat_id: int
    chat_type: str
    sender_id: int
    sender_name: str | None
    sent_at: int | None
    text: str | None = None
    forwarded: bool = False
    media: list[Media] = field(default_factory=list)
    # Whether this was addressed to us, which in a group is the whole question.
    directed: bool = False
    # `/start <token>`, the one thing handled before the sender is known.
    start_payload: str | None = None


def verify_secret(header: str | None, secret: str) -> None:
    """Telegram echoes the `secret_token` given to setWebhook in every
    delivery, as X-Telegram-Bot-Api-Secret-Token.

    It is the whole of the authentication: the webhook URL is otherwise an open
    door to anyone who learns it, and unlike Meta's X-Hub-Signature-256 this
    is a shared secret rather than a signature over the body -- so it proves
    the sender and nothing about what they sent. Without one configured,
    nothing is accepted.
    """
    if not secret:
        raise BadSecret("FAMILYOS_TELEGRAM_WEBHOOK_SECRET is not set, so no delivery can be trusted")
    if not header or not hmac.compare_digest(header.encode(), secret.encode()):
        raise BadSecret("missing or wrong X-Telegram-Bot-Api-Secret-Token")


def valid_payload(raw: str | None) -> bool:
    return bool(raw and _PAYLOAD_OK.match(raw))


def deep_link(bot_username: str, payload: str) -> str:
    return f"https://t.me/{bot_username}?start={payload}"


def parse(update: dict, *, bot_username: str = "") -> Message | None:
    """One Update, which carries at most one message.

    Edited messages are ignored rather than ingested: Telegram reuses the
    original message_id, so an edit would be a duplicate of something already
    read, and re-reading it would supersede the tasks the family has already
    decided on.
    """
    raw = (update or {}).get("message")
    if not isinstance(raw, dict):
        # channel_post, edited_message, callback_query, my_chat_member, polls:
        # nothing a notice arrives as.
        return None
    chat = raw.get("chat") or {}
    sender = raw.get("from") or {}
    message_id, chat_id, sender_id = raw.get("message_id"), chat.get("id"), sender.get("id")
    if message_id is None or chat_id is None or sender_id is None:
        return None
    if sender.get("is_bot"):
        # Another bot in the group, or our own echo. Never a school notice.
        return None

    chat_type = chat.get("type") or "private"
    text = (raw.get("text") or "").strip() or None
    caption = (raw.get("caption") or "").strip() or None
    message = Message(
        message_id=message_id, chat_id=chat_id, chat_type=chat_type, sender_id=sender_id,
        sender_name=_name(sender), sent_at=raw.get("date"),
        text=text or caption,
        # `forward_origin` since Bot API 7.0; `forward_date` is the older
        # marker and still arrives from older clients.
        forwarded=bool(raw.get("forward_origin") or raw.get("forward_date")),
        directed=_directed(raw, chat_type, text, caption, bot_username),
    )
    message.start_payload = _start_payload(text, bot_username)
    for media in _media(raw, caption):
        message.media.append(media)
    if not message.text and not message.media and not message.start_payload:
        # A location, a poll, a sticker, a left_chat_member service message.
        logger.debug("ignoring telegram message %s with nothing in it", message_id)
        return None
    return message


def _name(sender: dict) -> str | None:
    parts = [sender.get("first_name"), sender.get("last_name")]
    full = " ".join(p for p in parts if p).strip()
    return full or sender.get("username") or None


def _directed(raw: dict, chat_type: str, text: str | None, caption: str | None,
              bot_username: str) -> bool:
    """Was this aimed at us?

    In a private chat, always: writing to the bot is the act of forwarding.

    In a group, only when the bot is named or replied to. Telegram may hand us
    a great deal more -- with privacy mode off, or with the bot made an admin,
    it hands us the entire group -- and this is where that is thrown away.
    """
    if chat_type not in GROUP_CHATS:
        return True
    handle = ("@" + bot_username.lstrip("@")).lower() if bot_username else None
    if handle and handle in ((text or "") + " " + (caption or "")).lower():
        return True
    replied_to = (raw.get("reply_to_message") or {}).get("from") or {}
    if not replied_to.get("is_bot"):
        return False
    # Replying to a different bot in the same group is not talking to us.
    if bot_username:
        return (replied_to.get("username") or "").lower() == bot_username.lstrip("@").lower()
    return True


def _start_payload(text: str | None, bot_username: str) -> str | None:
    """The token out of `/start <token>`.

    In a group Telegram writes the command as `/start@our_bot <token>`, so the
    suffix is stripped before the argument is read.
    """
    if not text or not text.startswith("/start"):
        return None
    head, _, rest = text.partition(" ")
    if head != "/start" and not head.startswith("/start@"):
        return None  # /started, /startgroup: not this command
    payload = rest.strip()
    return payload if valid_payload(payload) else None


def _media(raw: dict, caption: str | None) -> list[Media]:
    for kind in MEDIA_KINDS:
        part = raw.get(kind)
        if not part:
            continue
        if kind == "photo":
            # Telegram sends every size it holds, smallest first. A circular
            # photographed on a noticeboard is only legible at the largest.
            sizes = [p for p in part if isinstance(p, dict) and p.get("file_id")]
            if not sizes:
                continue
            part = max(sizes, key=lambda p: (p.get("file_size") or 0,
                                             (p.get("width") or 0) * (p.get("height") or 0)))
        if not isinstance(part, dict) or not part.get("file_id"):
            continue
        return [Media(
            file_id=part["file_id"],
            # getFile "may not preserve the original file name and MIME type",
            # so both are taken here, where Telegram still reports them.
            media_type=part.get("mime_type") or _DEFAULT_TYPE.get(kind, "application/octet-stream"),
            filename=part.get("file_name"),
            caption=caption)]
    return []


_DEFAULT_TYPE = {"photo": "image/jpeg", "voice": "audio/ogg", "video_note": "video/mp4"}


# ----------------------------------------------------------------------------
# talking to the API
# ----------------------------------------------------------------------------

def _method_url(api_base: str, bot_token: str, method: str) -> str:
    return f"{api_base}/bot{bot_token}/{method}"


async def download(file_id: str, *, bot_token: str, api_base: str, fetch=None) -> bytes:
    """Media arrives as a file_id; the bytes are two more calls -- getFile for
    a path, then the file itself.

    Bytes alone, unlike the WhatsApp adapter: getFile "may not preserve the
    original file name and MIME type", so the type worth having is the one
    already on the Media, and the gateway sniffs it regardless.

    The download URL embeds the bot token, so it is never logged and never put
    in `source`. A leaked one is the bot.

    `fetch` is injected by the tests so none of this needs the network.
    """
    if fetch is not None:
        return await fetch(file_id)
    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        described = await client.get(_method_url(api_base, bot_token, "getFile"),
                                     params={"file_id": file_id})
        described.raise_for_status()
        result = (described.json() or {}).get("result") or {}
        path = result.get("file_path")
        if not path:
            raise RuntimeError("telegram getFile returned no file_path")
        if (result.get("file_size") or 0) > MAX_DOWNLOAD_BYTES:
            raise RuntimeError("telegram will not serve a bot a file over 20MB")
        got = await client.get(f"{api_base}/file/bot{bot_token}/{path}")
        got.raise_for_status()
        return got.content


async def send_message(chat_id: int, text: str, *, bot_token: str, api_base: str, post=None) -> None:
    """One plain message. No template, no window, no approval -- which is the
    whole reason this rail exists."""
    if post is not None:
        await post(chat_id, text)
        return
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_method_url(api_base, bot_token, "sendMessage"),
                              json={"chat_id": chat_id, "text": text,
                                    "disable_web_page_preview": True})
        r.raise_for_status()
