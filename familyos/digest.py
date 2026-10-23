"""The Sunday digest: the week ahead, where the family already is.

Home shows it to whoever opens the console. Most of a family never will on a
Sunday evening; they will read Telegram. So once a week, at a quiet hour in
the household's own time, each adult gets the same picture the brief would
have given them -- scoped to what *they* may see, like everything else --
as one plain message:

    This week
    · Thu 9 Oct — Respond to the income-tax demand (undecided)
    · Fri 16 Oct — Pay the Airtel Black bill ₹1,940.98
    Waiting on you
    · Bill for your Airtel Black account — Arunmozhi asked: "can you pay this?"
    To-dos
    · Book the car service — by 20 Oct
    Coming out of the account
    · Apple ₹195 on 9 Oct · Google ₹130 on 14 Oct

No markdown, no links that need a login to make sense, nothing that is not
already true on the console. Sent once per member per week; the row is
claimed before the message goes so a restart cannot send it twice. "Send me
this week's digest now" on the Household page is the same text, on demand.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from zoneinfo import ZoneInfo

from familyos import brief, inbox, jobs, ledger, notify, todos
from familyos.db import pool
from familyos.identity import Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "digest_weekly"
HANDLER_VERSION = "1"
SWEEP_SECONDS = 1800
WEEK = dt.timedelta(days=7)

_DAY = "%a %-d %b"


def _money(amount: float, currency: str) -> str:
    from familyos import country
    return country.money(amount, currency)


async def compose(p: Principal, today: dt.date | None = None) -> tuple[str, str]:
    """The week ahead for this member, as one plain message. Returns
    (subject, body)."""
    today = today or dt.date.today()
    until = today + WEEK
    # The whole week, not the brief's top few: a digest is read once.
    b = await brief.today(p, on=today, limit=-1)
    items = b["items"]
    lines: list[str] = []

    dated = [i for i in items if i.get("due_date") and today <= i["due_date"] <= until
             and i["reason"] in ("today", "soon", "undecided", "overdue")]
    dated.sort(key=lambda i: (i["due_date"], i.get("due_time") or ""))
    if dated:
        lines.append("This week")
        for i in dated:
            when = i["due_date"].strftime(_DAY) + (f" {i['due_time']}" if i.get("due_time") else "")
            state = " (undecided)" if i.get("status") == "proposed" else ""
            pay = f"\n  pay: {i['pay_url']}" if i.get("pay_url") else ""
            lines.append(f"· {when} — {i['title']}{state}{pay}")
    birthdays = [i for i in items if i["reason"] == "birthday"]
    if birthdays:
        lines.append("Birthdays: " + " · ".join(f"{i['title']} ({i['why']})" for i in birthdays))
    missed = [i for i in items if i["reason"] in ("missed", "overdue") and i.get("due_date") and i["due_date"] < today]
    if missed:
        lines.append(f"Gone by, nobody decided: {len(missed)} — " + "; ".join(i["title"] for i in missed[:3])
                     + (" …" if len(missed) > 3 else ""))

    handed = [i for i in items if i["reason"] == "assigned"]
    if handed:
        lines.append("")
        lines.append("Waiting on you")
        for i in handed:
            lines.append(f"· {i['title']} — {i['why']}")
    closed = [i for i in items if i["reason"] == "handled"]
    if closed:
        lines.append("")
        lines.append("Done this week")
        for i in closed:
            lines.append(f"· {i['title']} — {i['why']}")

    from familyos import suggest
    implied = [x for x in await suggest.for_member(p, today) if x["due_date"] <= until][:4]
    if implied:
        lines.append("")
        lines.append("Worth doing (not added yet)")
        for x in implied:
            lines.append(f"· {x['title']} — by {x['due_date'].strftime(_DAY)}: {x['why']}")

    open_todos = [t for t in await todos.list_for(p) if t["due_date"] is None or t["due_date"] <= until]
    if open_todos:
        lines.append("")
        lines.append("To-dos")
        for t in open_todos[:8]:
            who = await _name(t["assigned_to"]) if t["assigned_to"] else None
            lines.append(f"· {t['title']}" + (f" — by {t['due_date'].strftime(_DAY)}" if t["due_date"] else "")
                         + (f" — {who}" if who and t["assigned_to"] != p.member_id else ""))

    money = await ledger.overview(p, days=120)
    due = [r for r in money["recurring"] if today <= r["next_date"] <= until]
    if due:
        lines.append("")
        lines.append("Coming out of the account")
        lines.append(" · ".join(f"{r['merchant']} {_money(r['next_amount'], r['currency'])} on {r['next_date'].strftime('%-d %b')}"
                                for r in due))

    low = [r for r in money.get("running_low", []) if r["status"] in ("overdue", "soon")][:5]
    if low:
        lines.append("")
        lines.append("Running low")
        for r in low:
            lines.append(f"· {r['item']} — every ~{r['every_days']} days, last {r['last_on'].strftime('%-d %b')}"
                         + (f" — reorder: {r['reorder_url']}" if r.get("reorder_url") else f" ({r['merchant']})"))

    # Money this month against last, in one line, with the thing that moved it.
    from familyos import country
    home = (await country.locale(p.household_id))["currency"]
    month = ledger.spend(money["charges"], days=30, today=today, home=home)
    inr = [c for c in month["by_category"] if c["currency"] == home]
    total = sum(c["total"] for c in inr)
    previous = sum(c["previous"] for c in inr)
    if total or previous:
        lines.append("")
        lines.append("Money, last 30 days")
        swing = total - previous
        head = f"{_money(total, home)} on receipts"
        if month["comparable"] and abs(swing) >= 500:
            head += f", about {_money(abs(swing), home)} {'more' if swing > 0 else 'less'} than the 30 days before"
        elif not month["comparable"]:
            head += " (not enough earlier receipts to compare yet)"
        lines.append(head + ".")
        movers = sorted((c for c in inr if month["comparable"] and abs(c["delta"]) >= 500 and c["previous"] and c["total"]),
                        key=lambda c: -abs(c["delta"]))[:2]
        for c in movers:
            lines.append(f"· {c['category'].capitalize()} {_money(c['total'], home)}, {_money(abs(c['delta']), home)} "
                         f"{'more' if c['delta'] > 0 else 'less'}" + (f" — mostly {c['driver']}" if c.get("driver") else ""))

    # Once a month: the subscriptions, with where each is managed. Not "unused"
    # -- nobody can see that from a receipt -- just "still want these?".
    if today.day <= 7:
        subs = [r for r in money["recurring"] if r["category"] == "subscriptions"]
        if subs:
            lines.append("")
            lines.append("Still want these? (charged every month)")
            for r in subs:
                lines.append(f"· {r['merchant']} {_money(r['next_amount'], r['currency'])}"
                             + (f" — manage: {r['manage_url']}" if r.get("manage_url") else ""))

    waiting = [r for r in await inbox.feed(p, days=30, limit=100)
               if r["state"] == "todo" and r["category"] not in ("promo", "newsletter", "developer")]
    if waiting and not dated:
        lines.append("")
        lines.append(f"{len(waiting)} notice{'s' if len(waiting) != 1 else ''} still waiting for a yes or a no.")

    if not lines:
        lines.append("Nothing is due this week, nothing is waiting on you, and nothing was handed over. Enjoy it.")

    subject = f"Your week, {today.strftime(_DAY)} – {(until - dt.timedelta(days=1)).strftime(_DAY)}"
    return subject, "\n".join(lines)


async def _name(member_id: uuid.UUID | None) -> str | None:
    if member_id is None:
        return None
    return await pool().fetchval("SELECT display_name FROM members WHERE id = $1", member_id)


# ----------------------------------------------------------------------------
# sending, once
# ----------------------------------------------------------------------------

def period_for(local_now: dt.datetime) -> dt.date | None:
    """The digest day this moment belongs to, or None when it is not the day
    or not yet the hour."""
    if local_now.weekday() != settings.digest_weekday or local_now.hour < settings.digest_hour:
        return None
    return local_now.date()


async def send_to(p: Principal, period_start: dt.date, *, force: bool = False) -> dict:
    """Send this member their digest for the period, once. `force` is the
    button on the Household page: it sends again, and records that too."""
    async with pool().acquire() as conn:
        claimed = await conn.fetchrow(
            "INSERT INTO digests (id, household_id, member_id, period_start) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (member_id, period_start) DO NOTHING RETURNING id",
            uuid.uuid4(), p.household_id, p.member_id, period_start)
        if claimed is None and not force:
            return {"sent": False, "why": "already sent this week"}
    subject, body = await compose(p, period_start)
    channel = await notify.member(p.member_id, subject, body)
    await pool().execute(
        "UPDATE digests SET channel = $3, sent_at = NOW() WHERE member_id = $1 AND period_start = $2",
        p.member_id, period_start, channel)
    return {"sent": channel is not None, "channel": channel, "subject": subject}


async def sweep(now: dt.datetime | None = None) -> dict[str, int]:
    """Every adult of every active household, on their digest day."""
    now = now or dt.datetime.now(dt.UTC)
    out = {"sent": 0, "skipped": 0, "failed": 0}
    # Each household's own clock: Sunday morning in Dubai is not Sunday
    # morning in Chennai. Those whose digest hour has not come are skipped.
    rows = []
    for h in await pool().fetch("SELECT id, timezone FROM households WHERE status = 'active' AND weekly_digest"):
        try:
            local = now.astimezone(ZoneInfo(h["timezone"] or settings.timezone))
        except Exception:  # noqa: BLE001 - a zone the system does not know: the server's
            local = now.astimezone(ZoneInfo(settings.timezone))
        period = period_for(local)
        if period is None:
            continue
        rows += [dict(r, period=period) for r in await pool().fetch(
            "SELECT m.id, m.household_id, m.role, m.display_name FROM members m "
            "WHERE m.household_id = $2 AND m.role <> 'child' AND NOT EXISTS "
            "(SELECT 1 FROM digests d WHERE d.member_id = m.id AND d.period_start = $1)", period, h["id"])]
    if not rows:
        return out
    for r in rows:
        p = Principal(member_id=r["id"], household_id=r["household_id"], role=r["role"], display_name=r["display_name"])
        try:
            result = await send_to(p, period)
            out["sent" if result["sent"] else "skipped"] += 1
        except Exception:  # noqa: BLE001 - one member must not stop the rest
            logger.warning("digest failed for member %s", r["id"], exc_info=True)
            out["failed"] += 1
    return out


async def _handle(job: dict, ctx) -> dict:
    now = dt.datetime.now(dt.UTC)
    result = await sweep(now)
    return {**result, "next_run_at": (now + dt.timedelta(seconds=SWEEP_SECONDS)).isoformat()}


async def ensure_scheduled() -> dict | None:
    if not settings.digest_enabled:
        return None
    existing = await pool().fetchrow(
        "SELECT id FROM jobs WHERE kind = $1 AND status NOT IN ('succeeded', 'failed', 'cancelled') LIMIT 1", KIND)
    if existing is not None:
        return None
    return await jobs.create(KIND, {}, next_run_at=dt.datetime.now(dt.UTC))


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("digest_weekday", "digest_hour", "timezone"))


def describe() -> str:
    if not settings.digest_enabled:
        return "Weekly digest is off (FAMILYOS_DIGEST_ENABLED=false)."
    day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][settings.digest_weekday]
    return (f"Weekly digest is on: every {day} from {settings.digest_hour:02d}:00 {settings.timezone}, "
            "to each adult over Telegram, else email.")
