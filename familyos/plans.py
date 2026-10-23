"""Plans: the open-ended ask, kept to what this system can stand behind.

"Plan a week in Europe for the family" is where assistant products
overpromise. What FamilyOS does with it is three things it already does well,
and one it refuses:

- **The plan is written with the household in view.** The model is given
  what the member may see -- the members and their ages, the dates already
  spoken for, what the family pays out every month -- and asked for an
  itinerary, a handful of candidate bookings, and the legwork. Not a generic
  brochure: *this* family's week.
- **Candidate bookings are public pages, read without signing in.** Each
  option carries a URL the family can open, and -- when the model names a
  phrase to look for -- a watch (watches.py) that re-reads the page and
  reports what it said. No price is invented: the page's own words, with the
  date they were read.
- **The legwork becomes to-dos** with names and dates, on the digest like
  everything else; the confirmation mail lands in the inbox like any other
  notice.
- **Nothing is booked.** A booking is a payment and a passport number. "Open
  to book" is a link to the provider; the family pays in the provider's own
  app. The action deny-list is unchanged.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from familyos import audit, chat, jobs, todos, watches
from familyos.db import pool
from familyos.execution import research
from familyos.identity import Invalid, NotFound, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

MAX_OPTIONS = 8
MAX_TODOS = 12
MAX_WATCHES = 5
MAX_BRIEF = 2000

SYSTEM = """You are FamilyOS, planning something for {name}'s household on {today}. You write the plan; the family books.

Use the FACTS below: the members (and ages where given), the dates already spoken for, what the family pays out
each month. Respect them -- do not place a trip over a date that is already taken; keep the budget honest against
the monthly outgoings.

Return JSON with:
- title: a few words.
- starts_on, ends_on: ISO dates, or null if the brief leaves them open.
- budget_amount, budget_currency: the budget the brief states, else a sensible one with the currency the family uses.
- summary: three or four plain sentences: where, when, why this shape, what it will roughly cost.
- itinerary: one entry per day: day (1..n), date (ISO or null), title, notes (one or two sentences).
- options: up to {max_options} candidate bookings the family would open themselves. Each: kind (flight | stay |
  transport | activity | insurance | visa), label, provider (the site's name), url (a PUBLIC search or listing page
  on that provider -- never a checkout, never a page that needs a login), estimate (a number) and currency, note
  (what to look at on that page), look_for (3-6 words that will appear on that page when the option is available,
  e.g. the destination name, or null).
- todos: up to {max_todos} pieces of legwork: title, due_date (ISO or null), member (an adult's name from FACTS or
  null), note. Include passports/visa checks, insurance, school leave letters, packing, currency -- what this
  family actually has to do.
Never put passport numbers, card numbers or personal identifiers anywhere. Prices are estimates and say so.
"""

SYSTEM_MEALS = """You are FamilyOS, planning a week of meals for {name}'s household on {today}. You write the plan; the family cooks and shops.

Use the FACTS below: the members (children and their ages matter), the dates already spoken for (a late PTM means a
quick dinner that day), and RECENT GROCERIES and RECENT MEALS -- what this household actually buys and orders. Plan
what they will eat, not what a magazine would: their staples, their cuisine, a treat where they already order one.

Return JSON with:
- title: "Meals, <week>" or similar.
- starts_on, ends_on: the seven days (ISO).
- budget_amount, budget_currency: a sensible grocery budget for the week in the family's currency.
- summary: three plain sentences: the shape of the week, what is cooked vs ordered, roughly what it costs.
- itinerary: one entry per day: day (1..7), date (ISO), title ("Mon: idli, sambar rice, dal-roti"), notes (one line:
  prep, leftovers, who is out).
- options: the grocery list, up to {max_options} items, each kind "grocery", label (the item, with amount: "Eggs x12",
  "Toor dal 1 kg"), provider (the shop they already use from RECENT GROCERIES, else "Instamart"), url null,
  estimate and currency, note null, look_for null.
- todos: up to {max_todos}: title, due_date, member (an adult's name or null), note -- "Order groceries", "Soak the
  chana Friday night", "Take out the chicken to thaw".
Never invent a child's name. Prices are estimates and say so.
"""

PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "starts_on": {"type": ["string", "null"]},
        "ends_on": {"type": ["string", "null"]},
        "budget_amount": {"type": ["number", "null"]},
        "budget_currency": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "itinerary": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"day": {"type": "integer"}, "date": {"type": ["string", "null"]},
                           "title": {"type": "string"}, "notes": {"type": ["string", "null"]}},
            "required": ["day", "date", "title", "notes"]}},
        "options": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"kind": {"type": "string", "enum": ["flight", "stay", "transport", "activity", "insurance", "visa", "grocery"]},
                           "label": {"type": "string"}, "provider": {"type": "string"}, "url": {"type": "string"},
                           "estimate": {"type": ["number", "null"]}, "currency": {"type": ["string", "null"]},
                           "note": {"type": ["string", "null"]}, "look_for": {"type": ["string", "null"]}},
            "required": ["kind", "label", "provider", "url", "estimate", "currency", "note", "look_for"]}},
        "todos": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"title": {"type": "string"}, "due_date": {"type": ["string", "null"]},
                           "member": {"type": ["string", "null"]}, "note": {"type": ["string", "null"]}},
            "required": ["title", "due_date", "member", "note"]}},
    },
    "required": ["title", "starts_on", "ends_on", "budget_amount", "budget_currency", "summary", "itinerary",
                 "options", "todos"],
}


def _date(text) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except (TypeError, ValueError):
        return None


SHAPES = ("trip", "meals", "other")


async def _recent_lines(p: Principal) -> list[str]:
    """What the household actually buys and orders, from receipt lines."""
    rows = await pool().fetch(
        "SELECT r.merchant, r.item, r.bought_on FROM receipt_items r JOIN input_artifacts a ON a.id = r.artifact_id "
        "WHERE a.household_id = $1 AND (a.visibility = 'shared' OR a.submitted_by = $2) "
        "AND r.bought_on > CURRENT_DATE - 60 ORDER BY r.bought_on DESC LIMIT 80", p.household_id, p.member_id)
    groceries = [f"{r['item']} ({r['merchant']}, {r['bought_on'].isoformat()})" for r in rows
                 if r["merchant"] not in ("Swiggy", "Zomato")]
    meals = [f"{r['item']} ({r['merchant']}, {r['bought_on'].isoformat()})" for r in rows
             if r["merchant"] in ("Swiggy", "Zomato")]
    out = []
    if groceries:
        out.append("RECENT GROCERIES: " + "; ".join(groceries[:40]))
    if meals:
        out.append("RECENT MEALS ORDERED: " + "; ".join(meals[:20]))
    return out


KIND = "plan_write"
HANDLER_VERSION = "1"


async def start(p: Principal, brief: str, *, shape: str = "trip", enqueue: bool = True) -> dict:
    """Ask for a plan. The row exists at once, as "writing", so the page can
    open on it; the writing itself is a job, because it takes a minute and a
    disabled button for a minute reads as nothing happening."""
    if shape not in SHAPES:
        raise Invalid("shape must be trip, meals or other")
    brief = " ".join((brief or "").split())
    if not brief:
        raise Invalid("say what to plan")
    if len(brief) > MAX_BRIEF:
        raise Invalid(f"keep the brief under {MAX_BRIEF} characters")
    if not settings.ask_enabled:
        raise chat.ask.NoAnswerer("planning is off on this deployment (FAMILYOS_ASK_ENABLED=false)")
    if isinstance(chat.current_model(), chat.RefusingModel):
        raise chat.ask.NoAnswerer("no model is configured to write a plan on this deployment")
    plan_id = uuid.uuid4()
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO plans (id, household_id, created_by, title, brief, shape, status) VALUES ($1, $2, $3, $4, $5, $6, 'writing')",
            plan_id, p.household_id, p.member_id, brief[:160], brief, shape)
        await audit.record(p.household_id, "plan.requested", actor_member_id=p.member_id, target_type="plan",
                           target_id=plan_id, detail={"shape": shape}, conn=conn)
        if enqueue:
            await jobs.create(KIND, {"plan_id": str(plan_id)}, household_id=p.household_id, member_id=p.member_id, conn=conn)
    return await get(p, plan_id)


async def write(plan_id: uuid.UUID) -> dict:
    """The job: write a requested plan in the name of whoever asked. A failure
    is written on the row, so the page can say so and offer to try again."""
    row = await pool().fetchrow(
        "SELECT p.*, m.role, m.display_name FROM plans p JOIN members m ON m.id = p.created_by WHERE p.id = $1", plan_id)
    if row is None:
        return {"skipped": "gone"}
    if row["status"] != "writing":
        return {"skipped": row["status"]}
    p = Principal(member_id=row["created_by"], household_id=row["household_id"], role=row["role"], display_name=row["display_name"])
    try:
        await _write(p, dict(row))
    except Exception as exc:  # noqa: BLE001 - whatever it was, the row says so
        # Our own exceptions already say it plainly; an SDK's gets a sentence.
        said = str(exc) if isinstance(exc, (Invalid, RuntimeError)) else chat.said_by_provider(exc)
        await pool().execute("UPDATE plans SET status = 'failed', error = $2, updated_at = NOW() WHERE id = $1", plan_id, said[:500])
        await audit.record(row["household_id"], "plan.failed", actor_kind="system", target_type="plan", target_id=plan_id,
                           detail={"error": str(exc)[:200]})
        raise
    return {"written": str(plan_id)}


async def draft(p: Principal, brief: str, *, shape: str = "trip") -> dict:
    """Ask and write in one go, for a caller that waits (tests, a script)."""
    made = await start(p, brief, shape=shape, enqueue=False)
    await write(made["id"])
    return await get(p, made["id"])


async def _handle(job: dict, ctx) -> dict:
    return await write(uuid.UUID(job["spec"]["plan_id"]))


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION, settings_keys=("chat_model", "web_research"))


async def _write(p: Principal, plan: dict) -> None:
    """Write the plan for this household onto its row, with its to-dos and
    its watches."""
    brief, shape, plan_id = plan["brief"], plan["shape"], plan["id"]
    facts = await chat.context(p)
    template = SYSTEM_MEALS if shape == "meals" else SYSTEM
    extra = await _recent_lines(p) if shape == "meals" else []
    system = (template.format(name=p.display_name, today=dt.date.today().isoformat(),
                              max_options=MAX_OPTIONS if shape != "meals" else 30, max_todos=MAX_TODOS)
              + "\n\nFACTS:\n" + "\n".join(facts.lines + extra))
    answer = await (await chat.model_for(p.household_id)).reply(system, [{"role": "user", "content": brief}], schema=PLAN_SCHEMA)

    from familyos import ledger
    options = []
    for o in (answer.get("options") or [])[:(30 if shape == "meals" else MAX_OPTIONS)]:
        url = (o.get("url") or "").strip()
        if o.get("kind") == "grocery" and not url.startswith("https://"):
            # A grocery line's link is a search on the shop the family uses.
            url = ledger.reorder_url(o.get("provider") or "Instamart", o.get("label") or "") or \
                ledger.reorder_url("Instamart", o.get("label") or "") or ""
        if not url.startswith("https://"):
            continue
        options.append({
            "id": uuid.uuid4().hex[:8], "kind": o.get("kind") or "activity", "label": (o.get("label") or "")[:120],
            "provider": (o.get("provider") or "")[:60], "url": url[:500],
            "estimate": o.get("estimate"), "currency": o.get("currency"), "note": (o.get("note") or "")[:300] or None,
            "look_for": (o.get("look_for") or "")[:60] or None, "watch_id": None, "chosen": False, "booked_at": None,
        })
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "UPDATE plans SET title = $2, starts_on = $3, ends_on = $4, budget_amount = $5, budget_currency = $6, "
            "summary = $7, itinerary = $8, options = $9, status = 'draft', error = NULL, updated_at = NOW() "
            "WHERE id = $1 RETURNING *",
            plan_id, (answer.get("title") or "A plan")[:160],
            _date(answer.get("starts_on")), _date(answer.get("ends_on")), answer.get("budget_amount"),
            (answer.get("budget_currency") or None), (answer.get("summary") or "")[:2000] or None,
            [{"day": int(i.get("day") or n + 1), "date": i.get("date"), "title": (i.get("title") or "")[:120],
              "notes": (i.get("notes") or "")[:400] or None}
             for n, i in enumerate((answer.get("itinerary") or [])[:21])],
            options)
        await audit.record(p.household_id, "plan.drafted", actor_member_id=p.member_id, target_type="plan",
                           target_id=plan_id, detail={"options": len(options), "todos": len(answer.get("todos") or [])},
                           conn=conn)

    # The legwork, as to-dos the digest will carry.
    members = facts.members
    for t in (answer.get("todos") or [])[:MAX_TODOS]:
        who, _ = chat._adult(t.get("member"), members)
        try:
            made = await todos.add(p, t.get("title") or "", due_date=_date(t.get("due_date")),
                                   assigned_to=who["id"] if who else None, note=t.get("note"))
            await pool().execute("UPDATE todos SET plan_id = $2 WHERE id = $1", made["id"], plan_id)
        except Invalid:
            continue

    # Evidence under each option, when a research provider is on: a real page
    # with an excerpt and the time it was read, for the family to open. The
    # query is the option's own words, scrubbed of every member's name.
    names = [m["display_name"] for m in members]
    when = " ".join(x for x in (row["starts_on"].isoformat() if row["starts_on"] else "",
                                row["ends_on"].isoformat() if row["ends_on"] else "") if x)
    if research.configured():
        for o in options[:6]:
            objective = research.scrub(f"{o['label']} on {o['provider']} {when}".strip(), names)
            try:
                hits = await research.current().search(objective, [research.scrub(o["label"], names)], limit=3)
            except Exception as exc:  # noqa: BLE001 - evidence is a courtesy; the option stands without it
                logger.info("no evidence for option %s: %s", o["label"], exc)
                hits = []
            if hits:
                top = hits[0]
                o["evidence"] = {"url": top.url, "title": top.title, "excerpt": top.excerpt,
                                 "read_at": top.read_at.isoformat(), "via": top.via}
                await audit.record(p.household_id, "plan.evidence_read", actor_kind="system", target_type="plan",
                                   target_id=plan_id, detail={"via": top.via, "host": top.url.split("/")[2]})
        await pool().execute("UPDATE plans SET options = $2 WHERE id = $1", plan_id, options)

    # Candidate pages, watched: the page's own words, re-read without signing in.
    watched = 0
    for o in options:
        if watched >= MAX_WATCHES or not o["look_for"] or o["kind"] == "grocery":
            continue
        try:
            w = await watches.create(p, url=o["url"], look_for=o["look_for"], label=f"{row['title']}: {o['label']}"[:80],
                                     every_hours=24, days=min(60, max(7, ((row["starts_on"] or dt.date.today()) - dt.date.today()).days + 7)))
            o["watch_id"] = str(w["id"])
            watched += 1
        except Invalid as exc:
            logger.info("option not watched: %s", exc)
    if watched:
        await pool().execute("UPDATE plans SET options = $2 WHERE id = $1", plan_id, options)


_PLAN = "SELECT * FROM plans WHERE household_id = $1"


async def list_for(p: Principal) -> list[dict]:
    rows = await pool().fetch(_PLAN + " AND status <> 'dropped' ORDER BY created_at DESC LIMIT 50", p.household_id)
    return [await _with_extras(dict(r)) for r in rows]


async def get(p: Principal, plan_id: uuid.UUID) -> dict:
    row = await pool().fetchrow(_PLAN + " AND id = $2", p.household_id, plan_id)
    if row is None:
        raise NotFound("plan")
    return await _with_extras(dict(row))


async def _with_extras(plan: dict) -> dict:
    """The plan's to-dos and what each watched page last said."""
    plan["todos"] = [dict(r) for r in await pool().fetch(
        "SELECT id, title, note, due_date, assigned_to, done_at FROM todos WHERE plan_id = $1 "
        "ORDER BY done_at IS NOT NULL, due_date NULLS LAST, created_at", plan["id"])]
    ids = [uuid.UUID(o["watch_id"]) for o in plan["options"] if o.get("watch_id")]
    seen = {str(r["id"]): dict(r) for r in await pool().fetch(
        "SELECT id, last_found, last_excerpt, last_checked_at, last_error FROM watches WHERE id = ANY($1::uuid[])", ids)} if ids else {}
    for o in plan["options"]:
        w = seen.get(o.get("watch_id") or "")
        o["page"] = {"found": w["last_found"], "excerpt": w["last_excerpt"], "checked_at": w["last_checked_at"],
                     "error": w["last_error"]} if w else None
    if plan.get("budget_amount") is not None:
        plan["budget_amount"] = float(plan["budget_amount"])
    return plan


async def choose(p: Principal, plan_id: uuid.UUID, option_id: str, *, booked: bool) -> dict:
    """The family picked (or booked) an option. Booked means the confirmation
    is on its way through the mailbox; the watch on that page can stop."""
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(_PLAN + " AND id = $2 FOR UPDATE", p.household_id, plan_id)
        if row is None:
            raise NotFound("plan")
        options = list(row["options"])
        hit = next((o for o in options if o["id"] == option_id), None)
        if hit is None:
            raise NotFound("option")
        for o in options:
            if o["kind"] == hit["kind"]:
                o["chosen"] = o["id"] == option_id
        hit["booked_at"] = dt.datetime.now(dt.UTC).isoformat() if booked else None
        status = "active" if row["status"] == "draft" else row["status"]
        await conn.execute("UPDATE plans SET options = $2, status = $3, updated_at = NOW() WHERE id = $1",
                           plan_id, options, status)
        await audit.record(p.household_id, "plan.option_booked" if booked else "plan.option_chosen",
                           actor_member_id=p.member_id, target_type="plan", target_id=plan_id,
                           detail={"kind": hit["kind"]}, conn=conn)
    if booked and hit.get("watch_id"):
        try:
            await watches.cancel(p, uuid.UUID(hit["watch_id"]))
        except NotFound:
            pass
    return await get(p, plan_id)


async def set_status(p: Principal, plan_id: uuid.UUID, status: str) -> dict:
    if status not in ("draft", "active", "done", "dropped"):
        raise Invalid("status must be draft, active, done or dropped")
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("UPDATE plans SET status = $3, updated_at = NOW() WHERE household_id = $1 AND id = $2 "
                                  "RETURNING id", p.household_id, plan_id, status)
        if row is None:
            raise NotFound("plan")
        dropped = 0
        if status == "dropped":
            # The legwork went with the plan: an open to-do of a dropped plan
            # is nobody's any more, and should not sit on Home.
            gone = await conn.fetch("DELETE FROM todos WHERE plan_id = $1 AND done_at IS NULL "
                                    "RETURNING id, calendar_event_id, calendar_account_id", plan_id)
            dropped = len(gone)
            # A to-do that was put on the calendar comes off it too: the row
            # is gone, so the event's own ids ride in the job (as todos.remove does).
            from familyos import calendar
            for t in gone:
                if t["calendar_event_id"] and t["calendar_account_id"]:
                    await calendar.enqueue_event_removal(conn, p.household_id, t["calendar_account_id"], t["calendar_event_id"])
        await audit.record(p.household_id, f"plan.{status}", actor_member_id=p.member_id, target_type="plan", target_id=plan_id,
                           detail={"todos_removed": dropped} if status == "dropped" else None, conn=conn)
    return await get(p, plan_id)
