"""Reminders: telling the family before the date passes.

Intake stores a notice, extraction reads obligations out of it, and until now
that was the end of it: a dated thing sat in a list and nobody was told. This
module closes that gap, as one recurring job on `jobs.py` (whose `next_run_at`
has been there, unused, since it came over from Orbit).

Two reasons to be reminded:

- **due** -- an accepted obligation is coming up. The family agreed to it.
- **undecided** -- a proposal nobody has accepted or dismissed, and its date is
  near. This is the one that actually gets missed, so it is worth one nudge.

Who is told follows the same visibility rule as every read: a shared notice
reminds the adults and guardians of the household, a private one reminds only
the member who sent it. Never a child; they do not sign in, and an obligation's
subject is who it is *about*, not who is told.

Sending is idempotent by construction. One row per (obligation, person, reason,
lead time) with a unique index, so the sweep can run as often as it likes: a
row that exists is not made again, and a row already `sent` is not sent again.
"""
from __future__ import annotations

import datetime as dt
import logging

from familyos import artifacts, audit, billers, jobs, mail
from familyos.db import pool
from familyos.identity import Principal
from familyos.intake import telegram
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "send_reminders"
HANDLER_VERSION = "1"


def lead_days() -> list[int]:
    """Days before the date to remind on, nearest last so the first row made
    is the earliest one."""
    out = []
    for piece in (settings.reminder_lead_days or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            value = int(piece)
        except ValueError:
            continue
        if value >= 0 and value not in out:
            out.append(value)
    return sorted(out, reverse=True) or [0]


# ----------------------------------------------------------------------------
# scheduling
# ----------------------------------------------------------------------------

# One row per person who may see the obligation, at one lead time. The
# visibility test is artifacts.VISIBLE_TO_MEMBER written against the join:
# a member sees an accepted artifact when it is shared, or they submitted it.
_SCHEDULE = """
INSERT INTO reminders (id, household_id, obligation_id, member_id, reason, lead_days, send_after, channel)
SELECT gen_random_uuid(), o.household_id, o.id, m.id, $1, $2,
       (o.due_date::timestamptz - make_interval(days => $2)), $3
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
JOIN members m ON m.household_id = o.household_id AND m.role <> 'child'
WHERE o.due_date IS NOT NULL
  AND o.superseded_at IS NULL
  AND o.status = $4
  AND a.status = 'accepted'
  AND (a.visibility = 'shared' OR a.submitted_by = m.id)
  AND o.due_date >= $5::date
ON CONFLICT (obligation_id, member_id, reason, lead_days) DO NOTHING
RETURNING id
"""


async def schedule(conn, today: dt.date) -> dict[str, int]:
    """Make the reminder rows that do not exist yet. Safe to repeat."""
    made = {"due": 0, "undecided": 0}
    for lead in lead_days():
        for reason, status in (("due", "accepted"), ("undecided", "proposed")):
            rows = await conn.fetch(_SCHEDULE, reason, lead, settings.reminder_channel, status, today)
            made[reason] += len(rows)
    # Scheduling asks who may see an obligation *now*; a row made yesterday
    # was answered with yesterday's visibility. Three things can make a
    # pending row wrong after it exists, and all three cancel it:
    #
    #   - the obligation was decided, so its reason no longer applies;
    #   - a later notice superseded it, so the date it names may not hold;
    #   - the notice was made private, so this member may no longer see it.
    #
    # The last is the one that matters most. A reminder is a sentence about a
    # notice, so sending it to somebody who can no longer open that notice
    # leaks the notice.
    cancelled = await conn.fetch(
        "UPDATE reminders r SET status = 'cancelled' FROM obligations o, input_artifacts a "
        "WHERE o.id = r.obligation_id AND a.id = o.artifact_id AND r.status = 'pending' AND ("
        "  (r.reason = 'undecided' AND o.status <> 'proposed') OR"
        "  (r.reason = 'due' AND o.status <> 'accepted') OR"
        "  o.superseded_at IS NOT NULL OR"
        "  a.status <> 'accepted' OR"
        "  NOT (a.visibility = 'shared' OR a.submitted_by = r.member_id)) RETURNING r.id")
    made["cancelled"] = len(cancelled)
    return made


# ----------------------------------------------------------------------------
# delivery
# ----------------------------------------------------------------------------

_DUE_WORDS = {
    "sign": "needs signing",
    "pay": "needs paying",
    "attend": "needs someone there",
    "submit": "needs submitting",
    "prepare": "needs getting ready",
    "note": "is coming up",
}


def compose(row: dict) -> tuple[str, str]:
    """Subject and body. The notice's own words are not repeated here: a
    reminder says what and when, and points at the record."""
    when = row["due_date"]
    days = (when - dt.date.today()).days if when else None
    if days is None:
        timing = ""
    elif days < 0:
        timing = "was due " + when.isoformat()
    elif days == 0:
        timing = "is due today"
    elif days == 1:
        timing = "is due tomorrow"
    else:
        timing = "is due in " + str(days) + " days, on " + when.isoformat()

    if row["reason"] == "undecided":
        subject = "Still to decide: " + row["title"]
        body = ("Nobody has accepted or dismissed this yet, and it " + timing + ".\n\n"
                + row["title"] + "\n")
    else:
        subject = row["title"] + " " + (_DUE_WORDS.get(row["action"]) or "is coming up")
        body = row["title"] + " " + timing + ".\n\n"

    if row.get("contested"):
        # The link is only proposed, so the reminder still goes out -- being
        # reminded about something already changed is a nuisance; not being
        # reminded about something that still stands is the real harm.
        body += ("\nA later notice looks like it changes this, and nobody has confirmed that yet. "
                 "Check before acting on it.\n")
    if row.get("subject_name"):
        body += "For: " + row["subject_name"] + "\n"
    body += "From a notice received " + row["received_at"].date().isoformat() + ".\n"
    return subject, body


async def _send_log(row: dict, subject: str, body: str) -> None:
    logger.info("reminder %s for member %s: %s", row["id"], row["member_id"], subject)


async def _send_email(row: dict, subject: str, body: str) -> None:
    if not row.get("email"):
        raise RuntimeError("that member has no email address")
    await mail.send(row["email"], subject, body)


class OutsideWindow(RuntimeError):
    """Meta refused a free-text message because nobody has written to us in
    twenty-four hours. Retrying will not help; only a template will."""


# Meta's code for "re-engagement message": the 24-hour customer service window
# has closed, so free text is refused however many times it is tried.
_OUTSIDE_WINDOW = {131047, 131026}


def whatsapp_payload(to: str, subject: str, body: str) -> dict:
    """What to send, which depends on whether anyone is allowed to hear it.

    A reminder is business-initiated by definition -- nobody asked for it at
    7am -- so it falls outside the 24-hour customer service window unless that
    parent happened to message us yesterday. Free text is then refused.

    So a configured deployment always sends the template, and only a
    deployment without one falls back to text and works for recently-active
    members alone. The template carries two slots because a reminder is two
    things: what it is, and when.
    """
    name = settings.whatsapp_template_name
    if not name:
        return {"messaging_product": "whatsapp", "to": to, "type": "text",
                "text": {"body": subject + "\n\n" + body}}
    return {
        "messaging_product": "whatsapp", "to": to, "type": "template",
        "template": {
            "name": name,
            "language": {"code": settings.whatsapp_template_language},
            "components": [{
                "type": "body",
                # Meta rejects a parameter containing a newline or a run of
                # spaces, which a wrapped reminder body certainly has.
                "parameters": [{"type": "text", "text": _one_line(subject)},
                               {"type": "text", "text": _one_line(body)}],
            }],
        },
    }


def _one_line(text: str, limit: int = 900) -> str:
    flat = " ".join((text or "").split())
    return (flat[: limit - 1] + "\u2026") if len(flat) > limit else (flat or "-")


async def _send_whatsapp(row: dict, subject: str, body: str) -> None:
    """Where the parent is already looking. Email is checked on Sundays;
    WhatsApp is checked at traffic lights."""
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        raise RuntimeError("FAMILYOS_WHATSAPP_ACCESS_TOKEN and _PHONE_NUMBER_ID are not set")
    if not row.get("phone"):
        raise RuntimeError("that member has no phone number")
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{settings.whatsapp_api_base}/{settings.whatsapp_phone_number_id}/messages",
            headers={"Authorization": "Bearer " + settings.whatsapp_access_token},
            json=whatsapp_payload(row["phone"], subject, body))
        if r.status_code >= 400:
            code = None
            try:
                code = ((r.json() or {}).get("error") or {}).get("code")
            except ValueError:
                pass
            if code in _OUTSIDE_WINDOW:
                # Said once, plainly, rather than retried until the attempt
                # budget runs out and the reminder is marked failed for the
                # wrong reason.
                raise OutsideWindow(
                    "WhatsApp refused a free-text reminder: nobody has messaged this number in 24 hours. "
                    "Set FAMILYOS_WHATSAPP_TEMPLATE_NAME to an approved utility template.")
            r.raise_for_status()


async def _send_telegram(row: dict, subject: str, body: str) -> None:
    """The same reminder, without the paperwork.

    This is the rail WhatsApp's `_send_whatsapp` has to work around. There is
    no customer service window to fall outside of and no utility template to
    get approved, so the reminder is sent as what it is: two paragraphs of
    text, at 7am, to a parent who never messaged us yesterday. `OutsideWindow`
    has no counterpart here because the condition does not exist.

    What it costs instead is a binding step -- a member has to open the deep
    link once -- where WhatsApp needed only a number a guardian had typed.
    """
    if not settings.telegram_bot_token:
        raise RuntimeError("FAMILYOS_TELEGRAM_BOT_TOKEN is not set")
    if not row.get("telegram_chat_id"):
        raise RuntimeError("that member has not linked Telegram")
    await telegram.send_message(
        row["telegram_chat_id"], subject + "\n\n" + body,
        bot_token=settings.telegram_bot_token, api_base=settings.telegram_api_base)


CHANNELS = {"log": _send_log, "email": _send_email, "whatsapp": _send_whatsapp,
            "telegram": _send_telegram}


def describe_whatsapp() -> str:
    """Said at boot, because a reminder rail that silently reaches only
    recently-active members is worse than one that is plainly off."""
    if settings.reminder_channel != "whatsapp":
        return "WhatsApp reminders are off."
    if not (settings.whatsapp_access_token and settings.whatsapp_phone_number_id):
        return "WhatsApp reminders are MISCONFIGURED: no access token or phone number id."
    if not settings.whatsapp_template_name:
        return ("WhatsApp reminders have NO TEMPLATE, so they reach only members who messaged this "
                "number in the last 24 hours. Everyone else is refused by Meta. "
                "Set FAMILYOS_WHATSAPP_TEMPLATE_NAME to an approved utility template.")
    return (f"WhatsApp reminders send the template {settings.whatsapp_template_name!r} "
            f"({settings.whatsapp_template_language}), so the 24-hour window does not apply.")


def describe_telegram() -> str:
    """Said at boot for the same reason as WhatsApp's: a rail that reaches
    nobody should say so rather than look like one that works."""
    if settings.reminder_channel != "telegram":
        return "Telegram reminders are off."
    if not settings.telegram_bot_token:
        return "Telegram reminders are MISCONFIGURED: no bot token."
    return ("Telegram reminders send plain text -- no template and no 24-hour window -- "
            "and reach only members who have linked their Telegram account.")

# A claim held this long belonged to a worker that died mid-send. Taking it
# back risks a duplicate; leaving it means the reminder is never sent at all,
# which is the worse of the two.
CLAIM_TTL = dt.timedelta(minutes=10)

# Select and claim in one statement. SKIP LOCKED is what makes a second worker
# step over a row this one is taking rather than queue behind it.
#
# The visibility rule is applied again here, not only when the row was made:
# the cancel sweep runs between deliveries, and a notice made private in that
# gap must not be reminded about. Scheduling decides who would be told;
# delivery decides again, because delivery is the moment it matters.
_CLAIM = """
WITH due AS (
    SELECT r.id
    FROM reminders r
    JOIN obligations o ON o.id = r.obligation_id
    JOIN input_artifacts a ON a.id = o.artifact_id
    WHERE r.send_after <= $1
      AND (r.status = 'pending' OR (r.status = 'sending' AND r.claimed_at < $1 - $3::interval))
      AND o.superseded_at IS NULL
      AND a.status = 'accepted'
      AND (a.visibility = 'shared' OR a.submitted_by = r.member_id)
    ORDER BY r.send_after
    LIMIT $2
    FOR UPDATE OF r SKIP LOCKED
)
UPDATE reminders r SET status = 'sending', claimed_at = $1, attempts = r.attempts + 1
FROM due, obligations o, members m, input_artifacts a
WHERE r.id = due.id AND o.id = r.obligation_id AND m.id = r.member_id AND a.id = o.artifact_id
RETURNING r.id, r.household_id, r.obligation_id, r.member_id, r.reason, r.lead_days, r.channel,
          r.attempts, r.send_after, r.status, r.sent_at,
          o.title, o.action, o.due_date, o.subject_member_id, m.email, m.display_name,
          m.phone, m.telegram_chat_id, a.received_at,
          (SELECT c.subject_name FROM claims c WHERE c.id = o.claim_id) AS subject_name,
          EXISTS (SELECT 1 FROM amendments am
                  WHERE am.amends_claim_id = o.claim_id AND am.status = 'proposed') AS contested
"""


async def send_due(now: dt.datetime, limit: int = 200) -> dict[str, int]:
    """Claim what is due, then send it. The claim is what stops a second
    worker -- or an ordinary restart -- sending the same reminder twice."""
    counts = {"sent": 0, "failed": 0}
    rows = await pool().fetch(_CLAIM, now, limit, CLAIM_TTL)
    for raw in rows:
        row = dict(raw)
        send = CHANNELS.get(row["channel"]) or _send_log
        try:
            subject, body = compose(row)
            await send(row, subject, body)
        except Exception as exc:  # noqa: BLE001 - recorded on the row, retried next sweep
            counts["failed"] += 1
            logger.warning("reminder %s could not be sent", row["id"], exc_info=True)
            await pool().execute(
                # attempts was already counted when the row was claimed, so
                # the claim is released rather than counted again.
                "UPDATE reminders SET error = $2, claimed_at = NULL, "
                "status = CASE WHEN attempts >= $3 THEN 'failed' ELSE 'pending' END WHERE id = $1",
                row["id"], f"{type(exc).__name__}: {exc}"[:500], settings.reminder_max_attempts)
            continue
        counts["sent"] += 1
        async with pool().acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE reminders SET status = 'sent', sent_at = NOW(), error = NULL WHERE id = $1",
                row["id"])
            # Counts and ids, never the notice's words.
            await audit.record(row["household_id"], "reminder.sent", actor_kind="system",
                               target_type="obligation", target_id=row["obligation_id"],
                               detail={"reminder_id": str(row["id"]), "member_id": str(row["member_id"]),
                                       "reason": row["reason"], "lead_days": row["lead_days"],
                                       "channel": row["channel"]}, conn=conn)
    return counts


# ----------------------------------------------------------------------------
# the recurring job
# ----------------------------------------------------------------------------

async def _handle(job: dict, ctx: jobs.JobContext) -> dict:
    now = dt.datetime.now(dt.UTC)
    await ctx.plan(["Note which bills arrived", "Work out what needs remembering",
                    "Tell whoever may see it"])

    await ctx.step("bills")
    # Cheap, and it rides the sweep that already runs: a biller is only ever
    # "late" relative to the last bill we actually saw.
    noted = 0
    for row in await pool().fetch("SELECT id FROM households WHERE status = 'active'"):
        try:
            noted += await billers.note_arrivals(row["id"])
        except Exception:  # noqa: BLE001 - one household must not stop the rest
            logger.warning("could not note bill arrivals for %s", row["id"], exc_info=True)
    await ctx.finish_step("bills")

    await ctx.step("0")
    async with pool().acquire() as conn, conn.transaction():
        # Before anything is scheduled: a past optional date, or a past note,
        # files itself, so no reminder and no "missed" is made of it.
        from familyos.extraction import service as extraction
        filed = await extraction.file_the_past(conn, now.date())
    # A sign-in sitting nobody finished: the browser is released with its clock.
    try:
        from familyos.execution import sessions as sealed
        await sealed.sweep_sittings()
    except Exception:  # noqa: BLE001 - never the sweep's problem
        logger.warning("could not sweep sign-in sittings", exc_info=True)
    async with pool().acquire() as conn, conn.transaction():
        made = await schedule(conn, now.date())
    await ctx.finish_step("0")

    await ctx.step("1")
    sent = await send_due(now)
    await ctx.finish_step("1")

    every = max(60.0, settings.reminder_sweep_seconds)
    return {"bills_noted": noted, "filed": filed, "scheduled": made, **sent, "next_run_at": (now + dt.timedelta(seconds=every)).isoformat()}


async def ensure_scheduled() -> dict | None:
    """One sweep job for the whole deployment. A system job: it belongs to no
    household, so it outlives any of them."""
    if not settings.reminders_enabled:
        return None
    existing = await pool().fetchrow(
        "SELECT id FROM jobs WHERE kind = $1 AND status NOT IN ('succeeded', 'failed', 'cancelled') LIMIT 1", KIND)
    if existing is not None:
        return None
    return await jobs.create(KIND, {}, next_run_at=dt.datetime.now(dt.UTC))


# ----------------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------------

async def list_for(p: Principal, limit: int = 100) -> list[dict]:
    """What this member is going to be told, and was told. A member only ever
    has rows for obligations they can see, so no extra filter is needed."""
    rows = await pool().fetch(
        "SELECT r.id, r.obligation_id, r.reason, r.lead_days, r.send_after, r.channel, r.status, r.sent_at, "
        "o.title, o.action, o.due_date, o.subject_member_id "
        "FROM reminders r JOIN obligations o ON o.id = r.obligation_id "
        "JOIN input_artifacts a ON a.id = o.artifact_id "
        # Not "the rows made for this member" but "the rows this member may
        # still be shown". A notice made private takes its reminders out of
        # the other members' lists, the already-sent ones included: the row
        # stays for the audit trail and stops being readable. The argument
        # order is the visibility rule's own, so the fragment goes in as it is.
        f"WHERE r.member_id = $2 AND {artifacts.VISIBLE_TO_MEMBER} "
        "ORDER BY r.send_after LIMIT $3",
        p.household_id, p.member_id, limit)
    return [dict(r) for r in rows]


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION,
                  settings_keys=("reminder_lead_days", "reminder_channel", "reminder_sweep_seconds"))
