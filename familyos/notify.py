"""One message to one member, on whatever they have.

Reminders have their own rail with a schedule, retries and an audit trail.
This is the other kind of message: somebody did something that concerns you
and you should hear now -- a notice was handed to you with a note. It goes
by Telegram when the member has linked it, because that is plain text with
no template and no window; otherwise by email. It never goes by WhatsApp,
where an unprompted message is refused outside the 24-hour window and the
failure would be silent.

Best effort, by design. The assignment is already recorded; the message is
a courtesy, and a courtesy that fails must not undo the thing it describes.
"""
from __future__ import annotations

import logging
import uuid

from familyos import mail
from familyos.db import pool
from familyos.intake import telegram
from familyos.settings import settings

logger = logging.getLogger(__name__)


async def member(member_id: uuid.UUID, subject: str, body: str) -> str | None:
    """Returns the channel used, or None when nothing could carry it."""
    row = await pool().fetchrow(
        "SELECT display_name, email, telegram_chat_id FROM members WHERE id = $1 AND role <> 'child'", member_id)
    if row is None:
        return None
    if row["telegram_chat_id"] and settings.telegram_bot_token:
        try:
            await telegram.send_message(row["telegram_chat_id"], subject + "\n\n" + body,
                                        bot_token=settings.telegram_bot_token, api_base=settings.telegram_api_base)
            return "telegram"
        except Exception:  # noqa: BLE001 - a courtesy, logged and let go
            logger.warning("could not reach member %s on telegram", member_id, exc_info=True)
    if row["email"] and mail.configured():
        try:
            await mail.send(row["email"], subject, body)
            return "email"
        except Exception:  # noqa: BLE001
            logger.warning("could not reach member %s by email", member_id, exc_info=True)
    return None
