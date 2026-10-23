"""The daily brief: the few things that matter today, for one member.

The rest of the system answers *what is there* -- notices, claims, obligations,
reminders, amendments. A family does not want a list. It wants to be told the
two or three things that go wrong if nobody moves today. That is this.

It is a projection and deliberately not a table. Nothing here is stored: the
brief is derived from obligations, amendments and quarantine every time it is
asked for. So it needs no erasure path of its own -- destroy the household key
and there is nothing left to compute it from -- and it cannot drift out of step
with the records it describes. A stored brief would be a small twin, with all
the same problems as a large one.

What counts as mattering, worst first:

- **missed** -- dated, nobody decided, and the date has gone. The exact failure
  this product exists to prevent, so it leads.
- **mailbox** -- a connected mailbox has stopped being readable and needs
  reconnecting. Second, because it is the only line here about something the
  family cannot see: everything else in the brief is only as complete as
  intake, and a dead mailbox means notices are arriving nowhere. Worth saying
  loudly -- a Google client still in testing issues refresh tokens that expire
  in seven days, so this is a weekly event until CASA clears.
- **assigned** -- another member handed this notice to you, with a note, and
  something on it is still undecided. A person asked; that outranks a date.
- **overdue** -- the family accepted it and the date has gone.
- **today** -- whatever falls today, decided or not.
- **undecided** -- a proposal with a date coming up. The one that gets missed.
- **soon** -- accepted and coming up.
- **amendment** -- a later notice looks like it changes something, and nobody
  has confirmed that. Acting on the old date is the risk.
- **quarantine** -- something arrived that could not be trusted enough to read.
  A guardian has to vouch for it or it never becomes anything.

"Coming up" means here what it means to the reminder sweep: the widest of
`reminder_lead_days`. The brief and the reminders should never disagree about
what is near.

Visibility is the same rule as every other read, inlined from
`artifacts.VISIBLE_TO_MEMBER`: a private notice reaches its sender's brief and
nobody else's. Children have no brief -- they do not sign in, and an
obligation's subject is who it is *about*, not who is told.
"""
from __future__ import annotations

import datetime as dt
import logging

from familyos import artifacts, billers, calendar, grants, reconcile, reminders
from familyos.db import pool
from familyos.identity import Principal
from familyos.intake import mailbox

logger = logging.getLogger(__name__)

REASONS = ("missed", "mailbox", "assigned", "handled", "unbilled", "overdue", "today", "undecided", "soon",
           "amendment", "quarantine", "school_year", "birthday", "majority", "money", "prepare")
# A charge this much above a merchant's usual is said; a first charge from a
# merchant at least this big is said; the week's expected outgoings are said.
ANOMALY_RATIO = 1.25
NEW_MERCHANT_MIN = 1000.0
WATCH_DAYS = 7
BIRTHDAY_AHEAD = 7       # days before a birthday it is on the brief
MAJORITY_AGE = 18
# A class recorded this long ago, in the country's school-year window
# (country.py), is probably last year's.
CLASS_STALE_DAYS = 300
RANK = {reason: index for index, reason in enumerate(REASONS)}
DEFAULT_LIMIT = 3

# Past this, a date is history rather than today's business: a form due six
# weeks ago that nobody dismissed should not sit at the top of the brief for
# the rest of the year. It is still in the obligations list, which is where
# "what did we miss?" is answered.
STALE_DAYS = 30


def window() -> int:
    """How far ahead "coming up" reaches -- the same distance the reminder
    sweep uses, so the two never disagree about what is near."""
    return max(reminders.lead_days())


_OBLIGATIONS = f"""
SELECT o.id, o.artifact_id, o.claim_id, o.action, o.title, o.due_date, o.due_time, o.pay_url,
       o.optional, o.status, o.subject_member_id, c.subject_name,
       EXISTS (SELECT 1 FROM amendments am
               WHERE am.amends_claim_id = o.claim_id AND am.status = 'proposed') AS contested
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
LEFT JOIN claims c ON c.id = o.claim_id
WHERE {grants.VISIBLE_OBLIGATION}
  AND o.status IN ('accepted', 'proposed')
  AND o.superseded_at IS NULL
  AND o.due_date IS NOT NULL
  AND o.due_date BETWEEN $3::date AND $4::date
ORDER BY o.due_date, o.created_at
"""

_WHY = {
    "missed": "nobody accepted or dismissed this, and the date has gone",
    "overdue": "the family accepted this, and the date has gone",
    "today": "today",
    "undecided": "nobody has accepted or dismissed this yet",
    "soon": "coming up",
}


def when_words(due: dt.date, today: dt.date) -> str:
    days = (due - today).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    if days < 0:
        return f"{-days} days ago"
    return f"in {days} days"


def reason_for(status: str, due: dt.date, today: dt.date) -> str:
    """Which bucket a dated obligation falls in. Whether anyone decided
    matters more than the date: a thing nobody answered is the thing that
    gets missed."""
    if due == today:
        return "today"
    if due < today:
        return "missed" if status == "proposed" else "overdue"
    return "undecided" if status == "proposed" else "soon"


def _item(reason: str, title: str, why: str, **rest) -> dict:
    return {"reason": reason, "rank": RANK[reason], "title": title, "why": why, **rest}


async def _obligations(p: Principal, today: dt.date) -> list[dict]:
    rows = await pool().fetch(_OBLIGATIONS, p.household_id, p.member_id,
                              today - dt.timedelta(days=STALE_DAYS),
                              today + dt.timedelta(days=window()))
    # One query for every clash, rather than one per obligation.
    clashes = await calendar.clashes_for(p, [row["id"] for row in rows])
    out = []
    for row in rows:
        reason = reason_for(row["status"], row["due_date"], today)
        against = clashes.get(row["id"]) or []
        why = _WHY[reason]
        if against:
            # "Thursday is tight: clashes with the dentist at 15:30 -- move one?"
            # A clash is the thing a person would say first, so it leads.
            first = against[0]
            at = "" if first.get("all_day") else f" at {first['starts_at'].astimezone().strftime('%H:%M')}" if first.get("starts_at") else ""
            day = row["due_date"].strftime("%A") if row["due_date"] else "That day"
            why = f"{day} is tight: clashes with {first['summary']}{at}" + (" and more" if len(against) > 1 else "") + " \u2014 move one?"
        out.append(_item(
            reason, row["title"], why,
            when=when_words(row["due_date"], today),
            due_date=row["due_date"], due_time=row["due_time"], action=row["action"],
            optional=row["optional"], status=row["status"], contested=row["contested"],
            subject_member_id=row["subject_member_id"], subject_name=row["subject_name"],
            obligation_id=row["id"], artifact_id=row["artifact_id"], pay_url=row["pay_url"],
            # Said alongside the item rather than as a separate line: a clash is
            # a fact about this obligation, not another thing to do.
            clashes=[c["summary"] for c in against] or None))
    return out


RHYTHM_GRACE = dt.timedelta(days=5)


async def _unbilled(p: Principal) -> list[dict]:
    """A bill that normally arrives has not. The thing a pull model cannot say,
    because it only ever knows what it managed to fetch. Two sources: the
    billers a guardian named, and the rhythms the ledger found on its own --
    a merchant that charged every month and then did not."""
    out = []
    named = []
    for row in await billers.missing(p):
        late = row["days_late"]
        named.append((row["provider"] or "").lower())
        out.append(_item(
            "unbilled", f"No {row['label'].lower()} bill from {row['provider']}",
            f"this usually arrives every {row['every_days']} days, and is {late} "
            f"{'day' if late == 1 else 'days'} later than that",
            when="not arrived", biller_id=row["id"]))
    from familyos import ledger
    today = dt.date.today()
    try:
        rhythms = (await ledger.overview(p, days=200))["recurring"]
    except Exception:  # noqa: BLE001 - the ledger is a help here, not the point
        logger.warning("the ledger could not say what did not come", exc_info=True)
        rhythms = []
    for r in rhythms:
        if r["cadence"] == "stated" or r["times"] < 2 or not r.get("last_date"):
            continue
        if r["next_date"] + RHYTHM_GRACE >= today:
            continue
        merchant = r["merchant"].lower()
        if any(n and (n in merchant or merchant in n) for n in named):
            continue
        late = (today - r["next_date"]).days
        out.append(_item(
            "unbilled", f"No {r['merchant']} charge since {r['last_date'].strftime('%-d %b')}",
            f"it has come {r['cadence']} {r['times']} times, and this one is {late} {'day' if late == 1 else 'days'} later than that",
            when="not arrived", artifact_id=r["artifact_id"]))
    return out


async def _amendments(p: Principal) -> list[dict]:
    rows = await reconcile.list_for(p, "proposed")
    return [_item(
        "amendment", row["amends_title"],
        "a later notice looks like it changes this, and nobody has confirmed it",
        due_date=row["amends_date"], amendment_id=row["id"], artifact_id=row["artifact_id"],
        contested=True)
        for row in rows]


async def _mailboxes(p: Principal) -> list[dict]:
    """The member's own connected mailboxes that have gone quiet. Only they can
    reconnect one, and only they can see it.

    Quiet, not broken: a dead token is one cause, a message the poller cannot
    get past is another, and a poller that is not running at all is a third.
    The cause belongs in the console; what belongs here is the symptom, which
    is the same in every case -- mail is arriving in that mailbox and nowhere
    else."""
    return [_item(
        "mailbox", account["email"],
        ("FamilyOS can no longer read this mailbox, so notices in it are not arriving"
         if account["needs_reconnect"] else
         "this mailbox has not been read for a day, so notices in it may not be arriving"),
        mailbox_id=account["id"])
        for account in await mailbox.list_for(p) if mailbox.is_quiet(account)]


async def _assigned(p: Principal) -> list[dict]:
    """Notices handed to this member that still have an open date, or were
    handed over in the last week. The note travels with it: it is the reason
    the item exists."""
    from familyos.inbox import HEADLINE
    rows = await pool().fetch(
        f"SELECT a.id, a.assigned_note, a.assigned_at, m.display_name AS by_name, {HEADLINE} AS headline, "
        # "Can you pay this?" deserves the way to pay: the bill's link, on the
        # mail's own date or its statement's.
        f"(SELECT o.pay_url FROM obligations o WHERE o.pay_url IS NOT NULL AND o.superseded_at IS NULL AND o.status <> 'dismissed' "
        f" AND (o.artifact_id = a.id OR o.artifact_id IN (SELECT c.id FROM input_artifacts c WHERE c.parent_id = a.id)) "
        f" ORDER BY o.pay_url LIKE 'upi://%' DESC LIMIT 1) AS pay_url "
        f"FROM input_artifacts a LEFT JOIN members m ON m.id = a.assigned_by "
        # Handled, by a person or by a receipt, it is no longer in anyone's hands.
        f"WHERE {artifacts.VISIBLE_TO_MEMBER} AND a.assigned_to = $2 AND a.parent_id IS NULL AND a.handled_at IS NULL "
        f"AND (a.assigned_at > NOW() - interval '7 days' OR EXISTS "
        f"     (SELECT 1 FROM obligations o WHERE o.artifact_id = a.id AND o.status = 'proposed' AND o.superseded_at IS NULL)) "
        f"ORDER BY a.assigned_at DESC LIMIT 5", p.household_id, p.member_id)
    return [_item(
        "assigned", row["headline"] or "a notice",
        (f"{row['by_name']} asked: \u201c{row['assigned_note']}\u201d" if row["assigned_note"] and row["by_name"]
         else f"{row['by_name'] or 'someone'} handed this to you"),
        artifact_id=row["id"], assigned_by_name=row["by_name"], note=row["assigned_note"], pay_url=row["pay_url"])
        for row in rows]


async def _handled(p: Principal) -> list[dict]:
    """Notices this member handed over that somebody else has since handled,
    in the last day. The loop closing: the note is the answer to theirs,
    worth seeing once, not for a week."""
    from familyos.inbox import HEADLINE
    rows = await pool().fetch(
        f"SELECT a.id, a.handled_note, a.handled_at, m.display_name AS by_name, {HEADLINE} AS headline "
        f"FROM input_artifacts a LEFT JOIN members m ON m.id = a.handled_by "
        f"WHERE {artifacts.VISIBLE_TO_MEMBER} AND a.assigned_by = $2 AND a.handled_by IS DISTINCT FROM $2 "
        f"AND a.handled_at > NOW() - interval '1 day' AND a.parent_id IS NULL "
        f"ORDER BY a.handled_at DESC LIMIT 5", p.household_id, p.member_id)
    return [_item(
        "handled", row["headline"] or "a notice",
        (f"{row['by_name']} handled it: \u201c{row['handled_note']}\u201d" if row["handled_note"] and row["by_name"]
         # Nobody's hand: the house settled it from evidence, and says which.
         else f"settled on its own: {row['handled_note']}" if row["handled_note"]
         else f"{row['by_name'] or 'someone'} handled it"),
        artifact_id=row["id"], handled_by_name=row["by_name"], note=row["handled_note"])
        for row in rows]


async def _quarantine(p: Principal) -> list[dict]:
    """Guardians only, the same as the review queue itself: an item nobody can
    vouch for would otherwise sit there unread."""
    if not p.is_guardian:
        return []
    rows = await artifacts.list_quarantine(p)
    return [_item(
        "quarantine",
        row["filename"] or (row["source"] or {}).get("subject") or row["channel"],
        "arrived, but could not be trusted enough to read",
        artifact_id=row["id"])
        for row in rows]


async def _next_thing(p: Principal, today: dt.date) -> dict | None:
    """The first dated thing beyond the brief's horizon.

    A family forwards a circular about December, vouches for it, and the brief
    says nothing because it only looks a week ahead. That is correct and it
    reads as a product that did not work. Saying what is next -- without
    promoting it into today's business -- is the difference.
    """
    row = await pool().fetchrow(
        f"SELECT o.title, o.due_date FROM obligations o "
        f"JOIN input_artifacts a ON a.id = o.artifact_id "
        f"WHERE {grants.VISIBLE_OBLIGATION} AND o.status IN ('accepted', 'proposed') "
        f"AND o.superseded_at IS NULL AND o.due_date > $3::date "
        f"ORDER BY o.due_date LIMIT 1",
        p.household_id, p.member_id, today + dt.timedelta(days=window()))
    if row is None:
        return None
    away = (row["due_date"] - today).days
    return {"title": row["title"], "due_date": row["due_date"], "days_away": away,
            "when": when_words(row["due_date"], today)}


async def _school_year(p: Principal, today: dt.date) -> list[dict]:
    """At the start of a school year, a child whose class was recorded
    long ago is probably a class higher now. Said once a year, to guardians,
    until the record is updated: circulars are matched to the class on
    record, so a stale one misfiles the new year's notices."""
    if p.role != "guardian":
        return []
    from familyos import country
    if today.month not in country.profile((await country.locale(p.household_id))["country"])["school_year_months"]:
        return []
    rows = await pool().fetch(
        "SELECT m.id, m.display_name, m.class_label, m.school, "
        "COALESCE((SELECT max(since) FROM member_classes c WHERE c.member_id = m.id), m.created_at::date) AS since "
        "FROM members m WHERE m.household_id = $1 AND m.role = 'child' AND m.class_label IS NOT NULL", p.household_id)
    out = []
    for r in rows:
        if (today - r["since"]).days < CLASS_STALE_DAYS:
            continue
        out.append(_item("school_year", f"{r['display_name']} is still recorded in class {r['class_label']}. New year?",
                         f"recorded {r['since'].strftime('%-d %b %Y')}; circulars are matched to the class on record, "
                         f"so update it on the Household card when the new class begins",
                         subject_member_id=r["id"], subject_name=r["display_name"], when="this term"))
    return out


def _next_birthday(dob: dt.date, today: dt.date) -> dt.date:
    try:
        this_year = dob.replace(year=today.year)
    except ValueError:                       # 29 February
        this_year = dob.replace(year=today.year, day=28)
    if this_year >= today:
        return this_year
    try:
        return dob.replace(year=today.year + 1)
    except ValueError:
        return dob.replace(year=today.year + 1, day=28)


async def _birthdays(p: Principal, today: dt.date) -> list[dict]:
    """A birthday in the coming week, with the age; and, to guardians, a
    child who has come of age, whose records are now their own to hold."""
    rows = await pool().fetch("SELECT id, display_name, role, date_of_birth FROM members WHERE household_id = $1 AND date_of_birth IS NOT NULL",
                              p.household_id)
    out = []
    for r in rows:
        dob = r["date_of_birth"]
        nxt = _next_birthday(dob, today)
        days = (nxt - today).days
        if 0 <= days <= BIRTHDAY_AHEAD:
            age = nxt.year - dob.year
            when = "today" if days == 0 else ("tomorrow" if days == 1 else nxt.strftime("%A"))
            out.append(_item("birthday", f"{r['display_name']} turns {age} {when}" if days else f"{r['display_name']} turns {age} today",
                             nxt.strftime("%-d %B"), due_date=nxt, when=when, subject_member_id=r["id"], subject_name=r["display_name"]))
        if r["role"] == "child" and p.role == "guardian":
            age_now = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age_now >= MAJORITY_AGE:
                out.append(_item("majority", f"{r['display_name']} is {age_now}: their records are their own now",
                                 "a child who has come of age is an adult on the Household card; until then their notices "
                                 "stay under the consent a guardian gave", subject_member_id=r["id"], subject_name=r["display_name"]))
    return out


_EVENTS_SOON = f"""
SELECT o.id, o.artifact_id, o.title, o.due_date, o.due_time, o.subject_member_id, c.subject_name, c.requires
FROM obligations o
JOIN input_artifacts a ON a.id = o.artifact_id
LEFT JOIN claims c ON c.id = o.claim_id
WHERE {grants.VISIBLE_OBLIGATION}
  AND o.action = 'attend' AND o.status IN ('accepted', 'proposed') AND o.superseded_at IS NULL
  AND a.handled_at IS NULL
  AND o.due_date BETWEEN $3::date AND $4::date
ORDER BY o.due_date, o.due_time
"""


async def _prepare(p: Principal, today: dt.date) -> list[dict]:
    """The night before: what an event the family is going to still needs.
    The notice that announced it usually said -- a slip to return, a fee to
    pay, what to bring or wear -- as other dates and instructions on the same
    notice. Gathered into one line per event, due today or tomorrow, so
    the gate is seen before the day rather than at the gate."""
    until = today + dt.timedelta(days=1)
    events = await pool().fetch(_EVENTS_SOON, p.household_id, p.member_id, today, until)
    out = []
    for e in events:
        top = await pool().fetchval("SELECT COALESCE(parent_id, id) FROM input_artifacts WHERE id = $1", e["artifact_id"])
        gates = await pool().fetch(
            "SELECT o.title, o.action, o.due_date, o.status FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id "
            "WHERE COALESCE(a.parent_id, a.id) = $1 AND o.id <> $2 AND o.action IN ('submit', 'pay', 'sign') "
            "AND o.status IN ('accepted', 'proposed') AND o.superseded_at IS NULL AND (o.due_date IS NULL OR o.due_date <= $3) "
            "ORDER BY o.due_date NULLS LAST", top, e["id"], e["due_date"])
        instructions = await pool().fetch(
            "SELECT c.title FROM claims c JOIN input_artifacts a ON a.id = c.artifact_id JOIN extractions x ON x.id = c.extraction_id "
            "WHERE COALESCE(a.parent_id, a.id) = $1 AND c.kind = 'instruction' AND x.superseded_at IS NULL ORDER BY c.ordinal", top)
        needs = [f"{g['title']}" + (" (not decided)" if g["status"] == "proposed" else "") for g in gates]
        needs += [i["title"] for i in instructions]
        if "items_to_bring" in (e["requires"] or []) and not instructions:
            needs.append("bring what the notice lists")
        if not needs:
            continue
        when = "today" if e["due_date"] == today else "tomorrow"
        out.append(_item("prepare", f"Before {e['title']} {when}: {len(needs)} thing{'s' if len(needs) != 1 else ''}",
                         "; ".join(needs), artifact_id=e["artifact_id"], due_date=e["due_date"], due_time=e["due_time"], when=when,
                         subject_member_id=e["subject_member_id"], subject_name=e["subject_name"]))
    return out


async def _money_watch(p: Principal, today: dt.date) -> list[dict]:
    """What the ledger can say that a receipt alone cannot: a charge well
    above a merchant's usual, a merchant seen for the first time, and what
    is expected to come out this week. Said from the receipts' own amounts;
    nothing here is a guess about what should have been charged."""
    from familyos import country, ledger
    try:
        charges = await ledger.charges(p, days=180)
    except Exception:  # noqa: BLE001 - the ledger is a reading; a brief without it is still a brief
        return []
    if not charges:
        return []
    home = (await country.locale(p.household_id))["currency"]
    money = country.money
    out = []
    recent = [c for c in charges if not c.get("upcoming") and today - dt.timedelta(days=WATCH_DAYS) <= c["date"] <= today]
    by_merchant: dict[tuple[str, str], list[dict]] = {}
    for c in charges:
        if not c.get("upcoming"):
            by_merchant.setdefault((c["merchant"], c["currency"]), []).append(c)
    # "Above its usual" is only a finding for a merchant that charges on a
    # rhythm -- a bill, a subscription. A food order or a plumber's visit
    # varies by nature, and saying so every week would be noise.
    rhythmic = {(r["merchant"], r["currency"]) for r in ledger.recurring(charges, today=today)}
    said: set[tuple] = set()
    for c in recent:
        earlier = sorted(x["amount"] for x in by_merchant[(c["merchant"], c["currency"])] if x["date"] < c["date"])
        key = (c["merchant"], c["currency"], c["amount"])
        if key in said:
            continue
        if len(earlier) >= 3 and (c["merchant"], c["currency"]) in rhythmic:
            usual = earlier[len(earlier) // 2]
            if usual > 0 and c["amount"] >= usual * ANOMALY_RATIO:
                said.add(key)
                out.append(_item("money", f"{c['merchant']} charged {money(c['amount'], c['currency'])}, "
                                          f"{round((c['amount'] / usual - 1) * 100)}% above its usual {money(usual, c['currency'])}",
                                 f"on {c['date'].strftime('%-d %b')}; the usual is the middle of {len(earlier)} earlier charges",
                                 artifact_id=c["artifact_id"], due_date=c["date"], when=c["date"].strftime("%-d %b")))
        elif not earlier and c["amount"] >= NEW_MERCHANT_MIN and c["currency"] == home:
            said.add(key)
            out.append(_item("money", f"A first charge from {c['merchant']}: {money(c['amount'], c['currency'])}",
                             f"on {c['date'].strftime('%-d %b')}; no earlier receipt from them", artifact_id=c["artifact_id"],
                             due_date=c["date"], when=c["date"].strftime("%-d %b")))
    due = [r for r in ledger.recurring(charges, today=today) if today <= r["next_date"] <= today + dt.timedelta(days=WATCH_DAYS) and r["currency"] == home]
    if due:
        total = sum(r["next_amount"] for r in due)
        names = ", ".join(f"{r['merchant']} {money(r['next_amount'], r['currency'])} on {r['next_date'].strftime('%a')}" for r in due[:5])
        out.append(_item("money", f"About {money(total, home)} comes out this week", names + (" …" if len(due) > 5 else ""),
                         when="this week"))
    return out


async def today(p: Principal, *, on: dt.date | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """The brief, worst first. `counts` is everything found, not everything
    shown, so "and 4 more" is honest."""
    on = on or dt.date.today()
    found = (await _obligations(p, on) + await _mailboxes(p) + await _assigned(p) + await _handled(p) + await _unbilled(p)
             + await _amendments(p) + await _quarantine(p) + await _school_year(p, on) + await _birthdays(p, on)
             + await _money_watch(p, on) + await _prepare(p, on))
    found.sort(key=lambda i: (i["rank"], i.get("due_date") or dt.date.max, i["title"]))

    counts = {reason: 0 for reason in REASONS}
    for item in found:
        counts[item["reason"]] += 1
    shown = found if limit is None or limit < 0 else found[:limit]
    # Public context, when switched on: the weather, the holidays, leave-by times (publiccontext.py).
    household = await pool().fetchrow(
        "SELECT id, weather_lines, travel_time, public_holidays, home_place, home_lat, home_lon, work_place, work_lat, work_lon, country, timezone FROM households WHERE id = $1",
        p.household_id)
    context = None
    if household and (household["weather_lines"] or household["travel_time"] or household["public_holidays"]):
        from familyos import publiccontext
        context = await publiccontext.for_brief(dict(household), shown, on)
    return {"date": on, "member_id": p.member_id, "display_name": p.display_name, "context": context,
            "items": shown, "counts": counts, "more": len(found) - len(shown),
            # Only when there is nothing to say: a brief with work in it should
            # not also be advertising December.
            "next_thing": None if found else await _next_thing(p, on)}
