"""Household finance intelligence: the coordination layer above the accounts. Not a bank, and nothing here moves money.

- A cash-flow timeline: what is expected to go out in the next weeks (bills with a due date, subscriptions and rhythms with
  their next date, standing payments, return and warranty deadlines), by day and by week, per currency, no conversion.
- Budgets by category for the month so far, from the receipts FamilyOS has read.
- Purchases and warranties: the return window and the warranty end, surfaced before they pass.
- Savings goals with what has been put in. Bills split between adults with who has settled.
- A limit per member on what one person may ask to buy, inside the household's own limits (payments.py enforces it).

Every figure comes from a receipt, a bill, a standing payment or something a person typed; none is estimated.
"""
from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections import defaultdict

from familyos import audit, clock, ledger, standing
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, NotFound, Principal


def _d(v) -> float:
    return float(v) if v is not None else 0.0


# ---------------------------------------------------------------- cash-flow timeline

async def timeline(p: Principal, days: int = 45, today: dt.date | None = None) -> dict:
    today = today or clock.today()
    end = today + dt.timedelta(days=max(1, min(days, 180)))
    items: list[dict] = []
    seen: set[tuple] = set()
    charges = await ledger.charges(p, days=120)
    for c in charges:
        if c.get("upcoming") and c.get("due") and today <= c["due"] <= end:
            seen.add((c["merchant"], c["due"]))
            items.append({"date": c["due"], "title": c["merchant"], "kind": "bill", "amount": c["amount"], "currency": c["currency"], "artifact_id": c["artifact_id"]})
    for r in ledger.recurring(charges, today):
        if today <= r["next_date"] <= end and (r["merchant"], r["next_date"]) not in seen:
            items.append({"date": r["next_date"], "title": r["merchant"], "kind": "recurring", "amount": r["next_amount"], "currency": r["currency"], "artifact_id": r["artifact_id"]})
    for s in await standing.list_for(p):
        due = standing.due_in(s["day_of_month"], today)
        if today <= due <= end:
            items.append({"date": due, "title": s["title"], "kind": "standing", "amount": _d(s["amount"]), "currency": s["currency"], "artifact_id": None})
    for w in await warranties(p):
        for key, label in (("return_by", "Return window ends"), ("warranty_until", "Warranty ends")):
            if w[key] and today <= w[key] <= end:
                items.append({"date": w[key], "title": f"{label}: {w['title']}", "kind": "deadline", "amount": None, "currency": None, "artifact_id": w["artifact_id"]})
    items.sort(key=lambda i: (i["date"], i["title"]))
    by_day: dict[dt.date, list[dict]] = defaultdict(list)
    for i in items:
        by_day[i["date"]].append(i)
    weeks: dict[dt.date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    totals: dict[str, float] = defaultdict(float)
    for i in items:
        if i["amount"] is not None:
            monday = i["date"] - dt.timedelta(days=i["date"].weekday())
            weeks[monday][i["currency"]] += i["amount"]
            totals[i["currency"]] += i["amount"]
    return {"from": today, "to": end,
            "days": [{"date": d, "items": v} for d, v in sorted(by_day.items())],
            "weeks": [{"week_of": w, "totals": {c: round(a, 2) for c, a in t.items()}} for w, t in sorted(weeks.items())],
            "totals": {c: round(a, 2) for c, a in totals.items()}}


# ---------------------------------------------------------------- budgets

async def set_budget(p: Principal, category: str, monthly_limit: float, currency: str = "INR") -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sets the household budget")
    category = " ".join(category.lower().split())[:40]
    if not category or monthly_limit <= 0:
        raise Invalid("a budget is a category and an amount above zero")
    await pool().execute(
        "INSERT INTO budgets (household_id, category, monthly_limit, currency) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (household_id, category, currency) DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit",
        p.household_id, category, decimal.Decimal(str(monthly_limit)), currency.upper())
    await audit.record(p.household_id, "budget.set", actor_member_id=p.member_id, detail={"category": category, "limit": str(monthly_limit)})
    return {"category": category, "monthly_limit": monthly_limit, "currency": currency.upper()}


async def clear_budget(p: Principal, category: str, currency: str = "INR") -> None:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sets the household budget")
    await pool().execute("DELETE FROM budgets WHERE household_id = $1 AND category = $2 AND currency = $3", p.household_id, category.lower(), currency.upper())


async def budgets(p: Principal, today: dt.date | None = None) -> list[dict]:
    today = today or clock.today()
    month_start = today.replace(day=1)
    spent: dict[tuple[str, str], float] = defaultdict(float)
    for c in await ledger.charges(p, days=62):
        if not c.get("upcoming") and month_start <= c["date"] <= today:
            spent[(c["category"], c["currency"])] += c["amount"]
    out = []
    for r in await pool().fetch("SELECT category, monthly_limit, currency FROM budgets WHERE household_id = $1 ORDER BY category", p.household_id):
        limit = float(r["monthly_limit"])
        s = round(spent.get((r["category"], r["currency"]), 0.0), 2)
        out.append({"category": r["category"], "currency": r["currency"], "monthly_limit": limit, "spent": s, "left": round(limit - s, 2),
                    "percent": round(100 * s / limit, 1), "over": s > limit})
    return out


# ---------------------------------------------------------------- warranties and return windows

async def add_warranty(p: Principal, *, title: str, merchant: str | None = None, purchased_on: dt.date | None = None,
                       return_days: int | None = None, warranty_months: int | None = None, artifact_id: uuid.UUID | None = None) -> dict:
    if p.role == "child":
        raise NotAllowed("children cannot add purchases")
    title = " ".join(title.split())[:160]
    if not title:
        raise Invalid("say what was bought")
    if artifact_id is not None:
        # The notice it is filed against must be one this member may see in their own household (NotFound otherwise).
        from familyos import artifacts
        await artifacts.get_visible(p, artifact_id)
    bought = purchased_on or clock.today()
    return_by = bought + dt.timedelta(days=return_days) if return_days else None
    warranty_until = _add_months(bought, warranty_months) if warranty_months else None
    row = await pool().fetchrow(
        "INSERT INTO warranties (household_id, title, merchant, purchased_on, return_by, warranty_until, artifact_id, created_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *", p.household_id, title, (merchant or None), bought, return_by, warranty_until, artifact_id, p.member_id)
    await audit.record(p.household_id, "warranty.added", actor_member_id=p.member_id, detail={"title": title[:80]})
    return dict(row)


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.date(year, month, day)


# A warranty filed against a receipt or notice is that member's to see unless they may read the notice: the household's own purchases (no notice behind
# them) and any whose notice is visible to this member. $1 = household, $2 = member, as in artifacts.VISIBLE_TO_MEMBER.
def _warranty_visible() -> str:
    from familyos import artifacts

    return f"(w.artifact_id IS NULL OR EXISTS (SELECT 1 FROM input_artifacts a WHERE a.id = w.artifact_id AND ({artifacts.VISIBLE_TO_MEMBER})))"


async def warranties(p: Principal) -> list[dict]:
    rows = await pool().fetch(f"SELECT w.* FROM warranties w WHERE w.household_id = $1 AND w.closed_at IS NULL AND {_warranty_visible()} "
                              "ORDER BY COALESCE(w.return_by, w.warranty_until), w.created_at", p.household_id, p.member_id)
    return [dict(r) for r in rows]


async def close_warranty(p: Principal, warranty_id: uuid.UUID) -> None:
    done = await pool().execute(f"UPDATE warranties w SET closed_at = NOW() WHERE w.id = $3 AND w.household_id = $1 AND w.closed_at IS NULL AND {_warranty_visible()}",
                                p.household_id, p.member_id, warranty_id)
    if done.endswith(" 0"):
        raise NotFound("purchase")


# ---------------------------------------------------------------- savings goals

async def add_goal(p: Principal, title: str, target_amount: float, currency: str = "INR", by_date: dt.date | None = None,
                   owner_member_id: uuid.UUID | None = None) -> dict:
    if p.role == "child":
        raise NotAllowed("children cannot set household goals")
    title = " ".join(title.split())[:120]
    if not title or target_amount <= 0:
        raise Invalid("a goal is a name and an amount above zero")
    if owner_member_id is not None:
        if not p.is_guardian:
            raise NotAllowed("only a guardian sets a goal for a child")
        if not await pool().fetchval("SELECT 1 FROM members WHERE id = $1 AND household_id = $2 AND role = 'child'", owner_member_id, p.household_id):
            raise NotFound("child")
    row = await pool().fetchrow(
        "INSERT INTO savings_goals (household_id, title, target_amount, currency, by_date, created_by, owner_member_id) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        p.household_id, title, decimal.Decimal(str(target_amount)), currency.upper(), by_date, p.member_id, owner_member_id)
    return (await goals(p, row["id"]))[0]


async def contribute(p: Principal, goal_id: uuid.UUID, amount: float, note: str | None = None) -> dict:
    if p.role == "child":
        raise NotAllowed("children cannot add to household goals")
    if not await pool().fetchval("SELECT 1 FROM savings_goals WHERE id = $1 AND household_id = $2 AND closed_at IS NULL", goal_id, p.household_id):
        raise NotFound("goal")
    if amount == 0:
        raise Invalid("an amount other than zero")
    await pool().execute("INSERT INTO goal_contributions (goal_id, member_id, amount, note) VALUES ($1, $2, $3, $4)", goal_id, p.member_id, decimal.Decimal(str(amount)), (note or "")[:200] or None)
    return (await goals(p, goal_id))[0]


async def goals(p: Principal, only: uuid.UUID | None = None) -> list[dict]:
    rows = await pool().fetch(
        "SELECT g.*, COALESCE((SELECT sum(amount) FROM goal_contributions c WHERE c.goal_id = g.id), 0) AS saved FROM savings_goals g "
        "WHERE g.household_id = $1 AND g.closed_at IS NULL AND (g.owner_member_id IS NULL OR $2::uuid IS NOT NULL) AND ($2::uuid IS NULL OR g.id = $2) ORDER BY g.created_at", p.household_id, only)
    out = []
    for r in rows:
        target, saved = float(r["target_amount"]), float(r["saved"])
        out.append({"id": r["id"], "title": r["title"], "currency": r["currency"], "target": target, "saved": round(saved, 2), "left": round(max(0.0, target - saved), 2),
                    "percent": round(min(100.0, 100 * saved / target), 1), "by_date": r["by_date"], "done": saved >= target})
    return out


# ---------------------------------------------------------------- splitting a bill between adults

async def split(p: Principal, title: str, amount: float, currency: str, paid_by: uuid.UUID, shares: list[dict]) -> dict:
    """shares: [{member_id, percent}] or [{member_id, amount}], adding up to the bill. Records who owes whom; moves nothing."""
    if p.role == "child":
        raise NotAllowed("children cannot split bills")
    total = decimal.Decimal(str(amount))
    adults = {r["id"] for r in await pool().fetch("SELECT id FROM members WHERE household_id = $1 AND role IN ('guardian', 'adult')", p.household_id)}
    if paid_by not in adults or not shares or any(s["member_id"] not in adults for s in shares):
        raise Invalid("a bill is split between the household's adults")
    amounts = []
    for s in shares:
        amounts.append(decimal.Decimal(str(s["amount"])) if s.get("amount") is not None else (total * decimal.Decimal(str(s["percent"])) / 100).quantize(decimal.Decimal("0.01")))
    if abs(sum(amounts) - total) > decimal.Decimal("0.05"):
        raise Invalid("the shares have to add up to the bill")
    async with pool().acquire() as conn, conn.transaction():
        sid = await conn.fetchval("INSERT INTO bill_splits (household_id, title, amount, currency, paid_by) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                                  p.household_id, " ".join(title.split())[:160], total, currency.upper(), paid_by)
        for s, a in zip(shares, amounts, strict=True):
            # The one who paid has nothing to settle with themselves.
            await conn.execute("INSERT INTO bill_split_shares (split_id, member_id, amount, settled_at) VALUES ($1, $2, $3, $4)",
                               sid, s["member_id"], a, dt.datetime.now(dt.UTC) if s["member_id"] == paid_by else None)
        await audit.record(p.household_id, "split.created", actor_member_id=p.member_id, detail={"title": title[:80], "amount": str(total)}, conn=conn)
    return (await splits(p, sid))[0]


async def splits(p: Principal, only: uuid.UUID | None = None) -> list[dict]:
    rows = await pool().fetch("SELECT * FROM bill_splits WHERE household_id = $1 AND ($2::uuid IS NULL OR id = $2) ORDER BY created_at DESC LIMIT 50", p.household_id, only)
    names = {r["id"]: r["display_name"] for r in await pool().fetch("SELECT id, display_name FROM members WHERE household_id = $1", p.household_id)}
    out = []
    for r in rows:
        shares = await pool().fetch("SELECT member_id, amount, settled_at FROM bill_split_shares WHERE split_id = $1 ORDER BY member_id", r["id"])
        out.append({"id": r["id"], "title": r["title"], "amount": float(r["amount"]), "currency": r["currency"], "paid_by": names.get(r["paid_by"]), "paid_by_id": r["paid_by"],
                    "shares": [{"member_id": s["member_id"], "name": names.get(s["member_id"]), "amount": float(s["amount"]), "settled": s["settled_at"] is not None} for s in shares],
                    "owed": [{"name": names.get(s["member_id"]), "to": names.get(r["paid_by"]), "amount": float(s["amount"])} for s in shares if s["settled_at"] is None]})
    return out


async def settle(p: Principal, split_id: uuid.UUID, member_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT paid_by FROM bill_splits WHERE id = $1 AND household_id = $2", split_id, p.household_id)
    if row is None:
        raise NotFound("split")
    if p.member_id not in (member_id, row["paid_by"]) and not p.is_guardian:
        raise NotAllowed("the person who owes, the one who paid, or a guardian marks it settled")
    done = await pool().execute("UPDATE bill_split_shares SET settled_at = NOW() WHERE split_id = $1 AND member_id = $2 AND settled_at IS NULL", split_id, member_id)
    if done.endswith(" 0"):
        raise NotFound("share")
    return (await splits(p, split_id))[0]


# ---------------------------------------------------------------- a limit per member

async def set_member_limit(p: Principal, member_id: uuid.UUID, limit: float | None) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sets what one person may ask to buy")
    done = await pool().execute("UPDATE members SET payment_limit = $3 WHERE id = $1 AND household_id = $2",
                                member_id, p.household_id, None if limit is None else decimal.Decimal(str(limit)))
    if done.endswith(" 0"):
        raise NotFound("member")
    await audit.record(p.household_id, "member.payment_limit_set", actor_member_id=p.member_id, target_type="member", target_id=member_id, detail={"limit": None if limit is None else str(limit)})
    return {"member_id": member_id, "payment_limit": limit}
