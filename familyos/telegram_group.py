"""A family's own Telegram group: two read-only answers, from what the household shared with everyone.

A bot does not read a group (docs/telegram.md): only a message that names it or replies to it gets past the door. A guardian can make one group
the family's own by saying `family` to the bot in it. After that, anyone bound to a member who names the bot with `today` or `week` is answered
in the group. Everyone in the group sees the answer, so it is built as if asked by nobody: a principal that is no member, which sees only what the
household shared with everyone (`artifacts.VISIBLE_TO_MEMBER` with an id that submitted nothing), never a person's private notices, and only the
dates the family has accepted: no payment at all (a title says the amount), no links, no mailbox, no health, nothing a model wrote.
"""
from __future__ import annotations

import datetime as dt
import uuid

from familyos import brief, clock
from familyos.db import pool
from familyos.identity import Principal

GROUP_CHATS = ("group", "supergroup")
_NAMESPACE = uuid.UUID("6c1f7a0e-3f55-4c31-9d0a-0d3a5b9a7e11")
MAX_LINES = 10

JOINED = ("This group is now the family's. Anyone in it can name me and say `today` or `week`, and everyone here sees the answer. "
          "It comes only from dates your household has shared with everyone and accepted, never from anyone's private notices. "
          "Keep it to family: I cannot see who is in a group. A guardian can say `leave` to end this.")
LEFT = "Done: this is an ordinary group again, and I read nothing in it unless named."
ONLY_GUARDIAN = "Only a guardian can say that."
HELP = "In this group I answer `today` and `week`, from what the household shared with everyone."


def silent_principal(household_id: uuid.UUID, chat_id: int) -> Principal:
    """Asks as nobody: a member id no row has, so only what is shared with the whole household is seen."""
    return Principal(member_id=uuid.uuid5(_NAMESPACE, f"{household_id}:{chat_id}"), household_id=household_id, role="adult",
                     display_name="the family group")


async def household_of(chat_id: int) -> uuid.UUID | None:
    return await pool().fetchval("SELECT household_id FROM telegram_family_groups WHERE chat_id = $1", chat_id)


async def register(chat_id: int, member: dict) -> str:
    """Make this chat the member's household's family group. A guardian only; one household per chat."""
    if member["role"] != "guardian":
        return ONLY_GUARDIAN
    other = await household_of(chat_id)
    if other is not None and other != member["household_id"]:
        return "This group already belongs to another household."
    await pool().execute(
        "INSERT INTO telegram_family_groups (chat_id, household_id, registered_by) VALUES ($1, $2, $3) ON CONFLICT (chat_id) DO NOTHING",
        chat_id, member["household_id"], member["id"])
    return JOINED


async def leave(chat_id: int, member: dict) -> str:
    if member["role"] != "guardian":
        return ONLY_GUARDIAN
    await pool().execute("DELETE FROM telegram_family_groups WHERE chat_id = $1 AND household_id = $2", chat_id, member["household_id"])
    return LEFT


def command_of(text: str | None) -> str:
    """The one word after the bot's name: `today`, `week`, `family`, `leave`, or help; '' when there is nothing to answer."""
    words = [w for w in (text or "").lower().replace("/", " ").split() if not w.startswith("@")]
    if not words:
        return ""
    first = words[0].split("@")[0].strip("?!.,:")        # in a group Telegram writes a command as /today@TheBot
    return first if first in ("today", "week", "family", "leave") else "help"


async def answer(chat_id: int, household_id: uuid.UUID, command: str, *, on: dt.date | None = None) -> str:
    p = silent_principal(household_id, chat_id)
    on = on or clock.today()
    end = on if command == "today" else on + dt.timedelta(days=6)
    rows = await pool().fetch(
        brief._OBLIGATIONS, p.household_id, p.member_id, on, end, on)
    # Accepted dates only, and never a payment: a title carries its amount, and the whole group reads the answer.
    items = [r for r in rows if r["status"] == "accepted" and r["action"] != "pay"]
    if not items:
        return "Nothing the family has accepted is due " + ("today." if command == "today" else "this week.")
    lines = []
    for r in items[:MAX_LINES]:
        when = r["due_date"].strftime("%a %d %b") + (f" {str(r['due_time'])[:5]}" if r["due_time"] else "")
        lines.append(f"• {when}: {r['title']}")
    if len(items) > MAX_LINES:
        lines.append(f"…and {len(items) - MAX_LINES} more")
    return ("Today:\n" if command == "today" else "The week ahead:\n") + "\n".join(lines)
