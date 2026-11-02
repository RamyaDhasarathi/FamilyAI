"""Standing obligations: what a family owes on a rhythm no notice announces.

Rent has no mail. A landlord is paid on the fifth by a standing habit, and the
month it is forgotten is the month nobody was told. So a household can write
the rule once, "rent, ₹18,000, on the 5th, to Mr Raman", and each month the
obligation is made by itself, a fortnight ahead, as an accepted task on the
calendar with the payee's pay link when one was given.

It is made exactly the way a read notice makes one: a small note kept as the
notice, a payment claim, an obligation. So everything downstream is the same
code: the brief, the reminders, the bill's pay link, the care view, and the
loop closer, which marks it paid when a UPI alert or a receipt for the same
amount names the payee. Nothing is paid here, ever; FamilyOS reminds and the
person pays, in their own app.

Created by a member; visible as they chose (private or shared); a caregiver
sees it only if a guardian hands it to them, like any other notice.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
import uuid

from familyos import artifacts, audit, circle, clock, sealing
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal

logger = logging.getLogger(__name__)

AHEAD_DAYS = 14   # the month's obligation is made this long before it is due


def due_in(day_of_month: int, today: dt.date) -> dt.date:
    """The next date on or after today (or in the last few days, so a rule
    made on the 7th for the 5th is not skipped) that falls on the day."""
    this = dt.date(today.year, today.month, min(day_of_month, calendar.monthrange(today.year, today.month)[1]))
    if this >= today - dt.timedelta(days=3):
        return this
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return dt.date(year, month, min(day_of_month, calendar.monthrange(year, month)[1]))


async def create(p: Principal, *, title: str, payee: str, amount: float, currency: str = "INR", day_of_month: int,
                 pay_url: str | None = None, subject_member_id: uuid.UUID | None = None, visibility: str = "shared") -> dict:
    if p.role == "child":
        raise NotAllowed("a child cannot set a standing payment")
    title, payee = " ".join((title or "").split()), " ".join((payee or "").split())
    if not title or not payee:
        raise Invalid("say what it is and who is paid")
    if not 1 <= day_of_month <= 28:
        raise Invalid("the day of the month is 1 to 28")
    if not 0 < amount <= 10_000_000:
        raise Invalid("the amount has to be above zero")
    if visibility not in ("private", "shared"):
        raise Invalid("visibility is private or shared")
    if pay_url and not pay_url.lower().startswith(("https://", "upi://")):
        raise Invalid("a pay link is an https:// or upi:// link")
    if subject_member_id and not await pool().fetchval("SELECT 1 FROM members WHERE id = $1 AND household_id = $2", subject_member_id, p.household_id):
        raise NotFound("member")
    row = await pool().fetchrow(
        "INSERT INTO standing_obligations (id, household_id, created_by, title, payee, amount, currency, day_of_month, subject_member_id, pay_url, visibility) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *",
        uuid.uuid4(), p.household_id, p.member_id, title[:120], payee[:120], amount, (currency or "INR").upper()[:3], day_of_month,
        subject_member_id, pay_url, visibility)
    await audit.record(p.household_id, "standing.created", actor_member_id=p.member_id, target_type="standing", target_id=row["id"],
                       detail={"day": day_of_month, "currency": row["currency"]})
    await make_due(p.household_id)
    return dict(row)


async def list_for(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        "SELECT s.*, m.display_name AS subject_name FROM standing_obligations s LEFT JOIN members m ON m.id = s.subject_member_id "
        # A caregiver sees only what they made or were handed, never what the household shares (the same rule as a notice).
        "WHERE s.household_id = $1 AND s.active AND ((s.visibility = 'shared' AND NOT EXISTS (SELECT 1 FROM members cg WHERE cg.id = $2 AND cg.circle_role = 'caregiver')) "
        "OR s.created_by = $2) ORDER BY s.day_of_month, s.title",
        p.household_id, p.member_id)
    today = clock.today()
    return [{**dict(r), "next_due": due_in(r["day_of_month"], today)} for r in rows]


async def stop(p: Principal, standing_id: uuid.UUID) -> None:
    row = await pool().fetchrow("SELECT created_by, visibility FROM standing_obligations WHERE id = $1 AND household_id = $2 AND active", standing_id, p.household_id)
    # A private rule is its maker's alone, a guardian included; a shared one is not a caregiver's to see, still less to stop.
    if row is None or (row["created_by"] != p.member_id and (
            row["visibility"] == "private" or await circle.is_caregiver(p.member_id))):
        raise NotFound("standing payment")
    if row["created_by"] != p.member_id and not p.is_guardian:
        raise NotAllowed("only whoever set it, or a guardian, can stop it")
    await pool().execute("UPDATE standing_obligations SET active = FALSE WHERE id = $1", standing_id)
    await audit.record(p.household_id, "standing.stopped", actor_member_id=p.member_id, target_type="standing", target_id=standing_id)


async def make_due(household_id: uuid.UUID | None = None, today: dt.date | None = None) -> int:
    """Make the obligation for every rule whose date is within the next
    fortnight and not yet made for that month. Safe to repeat."""
    rules = await pool().fetch(
        "SELECT * FROM standing_obligations WHERE active" + (" AND household_id = $1" if household_id else ""), *([household_id] if household_id else []))
    made = 0
    for r in rules:
        # Each rule's own household's day, unless a day was given.
        day = today or clock.today(await clock.timezone_of(r["household_id"]))
        due = due_in(r["day_of_month"], day)
        month = due.replace(day=1)
        if r["last_month"] == month or due > day + dt.timedelta(days=AHEAD_DAYS):
            continue
        try:
            async with pool().acquire() as conn, conn.transaction():
                claimed = await conn.fetchval("UPDATE standing_obligations SET last_month = $2 WHERE id = $1 AND last_month IS DISTINCT FROM $2 RETURNING id", r["id"], month)
                if claimed is None:
                    continue
                await _make(conn, r, due)
            made += 1
        except Exception:  # noqa: BLE001 - one rule must not stop the rest
            logger.warning("could not make the standing obligation %s", r["id"], exc_info=True)
    return made


async def _make(conn, r, due: dt.date) -> None:
    title = f"{r['title']} — {due.strftime('%B %Y')}"
    note = (f"{r['title']}: {r['currency']} {float(r['amount']):,.2f} to {r['payee']}, due {due.isoformat()}. "
            "Made from a standing payment the household set; nothing is paid by FamilyOS.")
    art, _ = await artifacts.create(conn, r["household_id"], artifacts.NewArtifact(
        data=note.encode(), media_type="text/plain", channel="upload", visibility=r["visibility"], status="accepted",
        submitted_by=r["created_by"], filename=f"standing-{due.isoformat()}.txt",
        source={"via": "standing", "from": r["payee"], "subject": title, "standing_id": str(r["id"])},
        dedup_key=f"standing:{r['id']}:{due.strftime('%Y-%m')}"), actor_kind="system")
    extraction_id, claim_id = uuid.uuid4(), uuid.uuid4()
    key, hid = await sealing.write_key(conn, r["household_id"]), r["household_id"]
    await conn.execute(
        "INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) "
        "VALUES ($1, $2, $3, 'standing', 'v1', 'v1', TRUE, 1)", extraction_id, r["household_id"], art["id"])
    await conn.execute(
        "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, date, amount, currency, amount_text, "
        "subject_name, requires, quote, confidence) VALUES ($1, $2, $3, $4, 0, 'deadline', $5, $6, $7, $8, $9, NULL, ARRAY['payment'], $10, 1.0)",
        claim_id, extraction_id, hid, art["id"], sealing.seal(key, hid, sealing.CLAIM_TITLE, title), due, r["amount"], r["currency"],
        f"{r['currency']} {float(r['amount']):,.2f}", sealing.seal(key, hid, sealing.QUOTE, note[:300]))
    await conn.execute(
        "INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, status, "
        "decided_by, decided_at, pay_url) VALUES ($1, $2, $3, $4, $5, 'task', 'pay', $6, $7, 'accepted', $8, NOW(), $9)",
        uuid.uuid4(), hid, art["id"], claim_id, r["subject_member_id"], sealing.seal(key, hid, sealing.OBLIGATION_TITLE, title), due, r["created_by"], r["pay_url"])
    if r["subject_member_id"]:
        await conn.execute("INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, FALSE) ON CONFLICT DO NOTHING",
                           art["id"], r["subject_member_id"])
