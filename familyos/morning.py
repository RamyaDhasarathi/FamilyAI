"""The morning message: what needs a member today, once, as the same cards the chat opens with.

At the member's chosen hour in their household's time zone (8 am unless they say otherwise), over Telegram with the
buttons live, or by mail as plain text. It says nothing at all on a morning when nothing needs them. It counts against
that member's interruption budget (quiet hours and a daily cap) and waits, rather than drops, when over it. The
buttons stay good until evening, so a message read at lunch still works.

It only offers. Every button is a staged action a person presses; nothing runs on its own.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from familyos import cards, clock, interruptions, jobs, notify
from familyos.db import pool
from familyos.identity import Principal
from familyos.intake import telegram
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "morning_sweep"
HANDLER_VERSION = "1"
SWEEP_SECONDS = 600
TTL_MINUTES = 18 * 60            # the buttons last until the evening


async def compose(p: Principal, today: dt.date) -> dict | None:
    """The opening, or None on a morning when nothing needs this member."""
    opening = await cards.opening(p, today, ttl_minutes=TTL_MINUTES)
    return opening if any(c["type"] in ("action", "text") for c in opening["cards"]) else None


async def _deliver(p: Principal, opening: dict) -> str | None:
    row = await pool().fetchrow("SELECT telegram_chat_id, email FROM members WHERE id = $1", p.member_id)
    texts = [c["text"] for c in opening["cards"] if c["type"] == "text"]
    actions = [c for c in opening["cards"] if c["type"] == "action"]
    head = "\n".join([f"Good morning, {p.display_name.split()[0]}.", opening["say"], *texts])
    if row["telegram_chat_id"] and settings.telegram_bot_token:
        try:
            kw = {"bot_token": settings.telegram_bot_token, "api_base": settings.telegram_api_base}
            await telegram.send_message(row["telegram_chat_id"], head, **kw)
            for c in actions:
                await telegram.send_message(row["telegram_chat_id"], c["title"] + (f"\n{c['sub']}" if c.get("sub") else ""), buttons=[cards.telegram_buttons(c)], **kw)
            return "telegram"
        except Exception:  # noqa: BLE001 - fall through to mail
            logger.warning("morning message to %s over telegram failed", p.member_id, exc_info=True)
    # Mail carries the words, not the buttons: a staged action is only good where it can be pressed.
    lines = [head, *[f"- {c['title']}" + (f" ({c['sub']})" if c.get("sub") else "") for c in actions]]
    return await notify.member(p.member_id, "Your morning", "\n".join(lines) + "\n\nOpen FamilyOS to answer these.")


async def sweep(now: dt.datetime | None = None) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    out = {"sent": 0, "silent": 0, "waited": 0, "failed": 0}
    rows = await pool().fetch(
        "SELECT m.id, m.household_id, m.role, m.display_name, m.morning_hour, COALESCE(m.timezone, h.timezone) AS timezone FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE h.status = 'active' AND m.role <> 'child' AND m.morning_hour IS NOT NULL")
    for r in rows:
        try:
            local = now.astimezone(ZoneInfo(r["timezone"] or settings.timezone))
        except Exception:  # noqa: BLE001 - a zone the system does not know: the server's own
            local = now.astimezone(ZoneInfo(settings.timezone))
        if local.hour < r["morning_hour"]:
            continue
        if await pool().fetchval("SELECT 1 FROM morning_runs WHERE member_id = $1 AND run_on = $2", r["id"], local.date()):
            continue
        ok, _why = await interruptions.allow(r["id"], local)
        if not ok:
            out["waited"] += 1
            continue
        claimed = await pool().fetchval("INSERT INTO morning_runs (member_id, run_on, sent) VALUES ($1, $2, FALSE) ON CONFLICT DO NOTHING RETURNING member_id", r["id"], local.date())
        if claimed is None:
            continue
        p = Principal(member_id=r["id"], household_id=r["household_id"], role=r["role"], display_name=r["display_name"])
        try:
            async with clock.household(p.household_id, p.member_id):
                opening = await compose(p, local.date())
                if opening is None:
                    out["silent"] += 1
                    continue
                if await _deliver(p, opening) is None:
                    out["failed"] += 1
                    continue
        except Exception:  # noqa: BLE001 - one member must not stop the rest; tomorrow is another day
            logger.warning("morning message for %s failed", r["id"], exc_info=True)
            out["failed"] += 1
            continue
        await pool().execute("UPDATE morning_runs SET sent = TRUE WHERE member_id = $1 AND run_on = $2", r["id"], local.date())
        await interruptions.record(r["household_id"], r["id"], "morning")
        out["sent"] += 1
    return out


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    return {**await sweep(now), "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled() -> dict | None:
    return await jobs.ensure_recurring(KIND)


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("timezone",))


def describe() -> str:
    return "The morning message goes at each adult's chosen hour (8 am by default), once a day, only when something needs them."
