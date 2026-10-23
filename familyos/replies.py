"""A reply to the school, drafted and sent on the family's say-so.

Half of what a school sends wants a yes or a no back: attending, not
attending, opting in, the slip is on its way. The notice says who sent it
and how; the record says what the family decided. From those two a short
reply is drafted in the household's model, shown to a parent, and sent
only when they tap Send -- by mail to the address it came from, or into
the Telegram group it was posted in. Nothing goes out unseen, the sent
text is not kept (the audit records that a reply went, where and how
long), and a notice with no way back gets no draft.
"""
from __future__ import annotations

import logging
import uuid

from familyos import artifacts, audit, chat
from familyos.db import pool
from familyos.identity import NotAllowed, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

STANCES = ("yes", "no", "note")
MAX_REPLY = 1200

SYSTEM = """You write short replies from a parent to a school, on the parent's behalf. Plain, warm, two to four sentences, in the language the notice is in, signed with the parent's name. Say only what the facts say: the child's name, the decision (attending or not, consenting or not, done or not), and any note the parent added. Never invent a reason, a date or a detail. Do not use bullet points or a subject line.
Return JSON: {"text": "<the reply>", "subject": "<a subject line for mail, starting with Re: when the notice had one>"}"""

SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}, "subject": {"type": "string"}},
          "required": ["text", "subject"], "additionalProperties": False}


def _address_of(row: dict) -> tuple[str | None, str | None, str | None]:
    """(channel, to, display) for the way back, or (None, None, None)."""
    src = row.get("source") or {}
    if row["channel"] in ("gmail", "gmail_attachment", "email"):
        sender = (src.get("from") or "").strip()
        addr = sender.split("<")[-1].rstrip(">").strip() if "<" in sender else sender
        if "@" in addr and not addr.lower().startswith("noreply") and not addr.lower().startswith("no-reply"):
            return "email", addr, sender
        return None, None, None
    if row["channel"] == "telegram":
        chat_id = src.get("chat_id")
        if chat_id is not None and settings.telegram_bot_token:
            return "telegram", str(chat_id), src.get("chat_title") or "the Telegram group"
    return None, None, None


async def _facts(p: Principal, artifact_id: uuid.UUID) -> tuple[dict, list[str]]:
    row = dict(await artifacts.get_visible(p, artifact_id))
    row["subject_member_ids"] = [r["member_id"] for r in await pool().fetch(
        "SELECT member_id FROM artifact_subjects WHERE artifact_id = $1", artifact_id)]
    lines = []
    src = row.get("source") or {}
    if src.get("subject"):
        lines.append(f"Notice subject: {src['subject']}")
    if src.get("headline"):
        lines.append(f"Notice: {src['headline']}")
    for c in await pool().fetch(
            "SELECT c.title, c.kind, c.date FROM claims c JOIN extractions x ON x.id = c.extraction_id "
            "WHERE c.artifact_id = $1 AND x.superseded_at IS NULL ORDER BY c.ordinal LIMIT 8", artifact_id):
        lines.append(f"The notice says: {c['title']}" + (f" ({c['date'].isoformat()})" if c["date"] else ""))
    for o in await pool().fetch(
            "SELECT title, action, status, due_date FROM obligations WHERE artifact_id = $1 AND superseded_at IS NULL AND status <> 'proposed' ORDER BY due_date",
            artifact_id):
        lines.append(f"The family {o['status']}: {o['title']}" + (f" ({o['due_date'].isoformat()})" if o["due_date"] else ""))
    names = [r["display_name"] for r in await pool().fetch(
        "SELECT display_name FROM members WHERE id = ANY($1::uuid[])", list(row.get("subject_member_ids") or []))]
    if names:
        lines.append("The child: " + ", ".join(names))
    lines.append(f"The parent writing: {p.display_name}")
    return row, lines


async def draft(p: Principal, artifact_id: uuid.UUID, *, stance: str | None, note: str | None) -> dict:
    """A reply, drafted. `stance` is yes, no or note; `note` is the parent's
    own words to carry. Returns channel, to, subject, text."""
    if p.role == "child":
        raise NotAllowed("a child does not reply to the school")
    row, lines = await _facts(p, artifact_id)
    channel, to, display = _address_of(row)
    if channel is None:
        raise ValueError("this notice has no way back: it did not come by mail or from a Telegram group")
    if stance == "yes":
        lines.append("The parent's answer: yes -- attending / consenting / done.")
    elif stance == "no":
        lines.append("The parent's answer: no -- not attending / not consenting.")
    if note:
        lines.append(f"The parent adds: {note.strip()[:300]}")
    model = await chat.model_for(p.household_id)
    out = await model.reply(SYSTEM, [{"role": "user", "content": "FACTS:\n" + "\n".join(lines) + "\n\nWrite the reply."}], SCHEMA)
    text = str(out.get("text") or "").strip()[:MAX_REPLY]
    subject = str(out.get("subject") or "").strip()[:200] or ("Re: " + (row.get("source") or {}).get("subject", "your notice"))
    if not text:
        raise ValueError("the model wrote nothing")
    return {"artifact_id": artifact_id, "channel": channel, "to": display or to, "subject": subject, "text": text}


async def send(p: Principal, artifact_id: uuid.UUID, *, text: str, subject: str | None) -> dict:
    """Send what the parent approved, to where the notice came from."""
    if p.role == "child":
        raise NotAllowed("a child does not reply to the school")
    text = (text or "").strip()
    if not text or len(text) > MAX_REPLY:
        raise ValueError(f"a reply is between one and {MAX_REPLY} characters")
    row, _ = await _facts(p, artifact_id)
    channel, to, display = _address_of(row)
    if channel is None:
        raise ValueError("this notice has no way back")
    if channel == "email":
        from familyos import mail
        await mail.send(to, subject or ("Re: " + (row.get("source") or {}).get("subject", "your notice")), text + f"\n\n— {p.display_name}")
    else:
        from familyos.intake import telegram
        await telegram.send_message(int(to), text, bot_token=settings.telegram_bot_token, api_base=settings.telegram_api_base)
    await audit.record(p.household_id, "reply.sent", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id,
                       detail={"channel": channel, "length": len(text)})
    return {"artifact_id": artifact_id, "channel": channel, "to": display or to, "sent": True}


def describe() -> str:
    return "replies: a short answer to the school drafted from the notice and the family's decision, sent by mail or into the Telegram group only when a parent taps Send; the text is not kept"
