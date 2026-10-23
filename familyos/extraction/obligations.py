"""From claims to proposed obligations: what the family might do about a notice.

Nothing here is decided for the family. Each obligation starts `proposed`
and a member accepts or dismisses it. Two kinds:

- task: something to do (sign and return a form, pay, attend, apply).
- calendar: a dated event to know about (a trip day, a holiday, an exam).

Only grounded claims (their quote was found in the original) become
obligations; an ungrounded claim stays visible for review and nothing more.
Nothing ever pays: a payment task is a reminder, never an instruction.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from familyos import categories
from familyos.extraction.claims import Claim


@dataclass
class ProposedObligation:
    claim_index: int
    kind: str                    # task | calendar
    action: str                  # sign | pay | attend | submit | prepare | note
    title: str
    due_date: dt.date | None
    end_date: dt.date | None
    due_time: str | None
    optional: bool


def _action(claim: Claim) -> str:
    req = set(claim.requires)
    if claim.kind == "form" or "parent_signature" in req or "form_return" in req:
        return "sign"
    if claim.kind == "payment" or "payment" in req:
        return "pay"
    if "parent_attendance" in req:
        return "attend"
    if "items_to_bring" in req:
        return "prepare"
    return "submit" if claim.kind == "deadline" else "note"


_PAID = re.compile(r"\b(paid|debited|payment (?:received|successful|successfully|confirm\w*|complete\w*|done)|receipt for|"
                   r"thank you for (?:your |the )?payment|transaction (?:successful|id|reference)|amount received|has been (?:paid|received))\b", re.I)


def propose(claims: list[Claim], reference_date: dt.date | None = None) -> list[ProposedObligation]:
    out: list[ProposedObligation] = []
    # A form whose return date is also stated as a deadline gets one task, from the deadline.
    deadline_forms = any(c.kind == "deadline" and ({"form_return", "parent_signature"} & set(c.requires)) for c in claims)
    for i, c in enumerate(claims):
        if not c.grounded:
            continue
        if c.kind == "deadline":
            out.append(ProposedObligation(i, "task", _action(c), c.title, c.date, None, c.time, c.optional))
        elif c.kind == "form":
            if deadline_forms:
                continue
            out.append(ProposedObligation(i, "task", "sign", c.title, c.date, None, None, c.optional))
        elif c.kind == "payment":
            # Money already gone -- "paid", "debited", "payment received" --
            # is a record for the ledger, never something to pay.
            if _PAID.search(f"{c.title} {c.quote}"):
                continue
            out.append(ProposedObligation(i, "task", "pay", c.title, c.date, None, None, c.optional))
        elif c.kind == "event":
            if "parent_attendance" in c.requires:
                out.append(ProposedObligation(i, "task", "attend", c.title, c.date, c.end_date, c.time, c.optional))
            elif c.date is not None and not c.uncertain:
                out.append(ProposedObligation(i, "calendar", "note", c.title, c.date, c.end_date, c.time, c.optional))
        elif c.kind == "amendment" and c.date is not None:
            out.append(ProposedObligation(i, "calendar", "note", c.title, c.date, c.end_date, c.time, c.optional))
        elif c.kind == "document" and c.end_date is not None:
            # A renewal, proposed with the lead the kind needs: a passport
            # takes months, a PUC an afternoon.
            from familyos.documents import lead_for
            due = c.end_date - dt.timedelta(days=lead_for(c.document_kind))
            out.append(ProposedObligation(i, "task", "submit", f"Renew {c.title}", due, None, None, False))
    if reference_date is not None:
        # A notice read long after it was issued should not propose work for days already gone.
        out = [o for o in out if o.due_date is None or (o.end_date or o.due_date) >= reference_date - dt.timedelta(days=1)]
    return out


@dataclass
class Filtered:
    kept: list[ProposedObligation]
    withheld: int      # a promotion's or newsletter's: never the family's
    recorded: int      # already happened, or a receipt: a record, not a task


def category_for_filter(category: str, *, tagged_with_child: bool) -> str:
    """A notice a parent tagged with a child is a school notice whatever
    its sender looked like: a circular shared from the phone has no domain."""
    return "school" if tagged_with_child and category not in KEEPS_TODAY_CATEGORIES and categories.may_obligate(category) else category


KEEPS_TODAY_CATEGORIES = categories.KEEPS_TODAY


def for_category(proposed: list[ProposedObligation], category: str,
                 reference_date: dt.date | None) -> Filtered:
    """What a category does to a notice's proposals. The reference date is
    the day the notice was sent, not the day it was read.

    - A promotion or newsletter proposes nothing (categories.NEVER_OBLIGATES).
    - Where the sender is a shop, a broker, a bank or a service
      (categories.RECORDS_THE_PAST): an event that has started by the day
      after sending is a record ("your order was delivered", "subscription
      period from the 7th"); and a payment or submission with no date is a
      receipt or boilerplate ("invoice total", "report any discrepancy within
      7 days") -- a bill says when.
    - Everywhere but a school or a clinic, a dated event that has already
      started is a record too ("date of communication: the 23rd"). A
      circular sent the morning of the PTM is still an invitation.
    - An undated ask outside the transactional categories is kept: the tax
      office's "kindly respond" is real.
    """
    if not proposed:
        return Filtered([], 0, 0)
    if not categories.may_obligate(category):
        return Filtered([], len(proposed), 0)
    transactional = category in categories.RECORDS_THE_PAST
    kept, recorded = [], 0
    for o in proposed:
        started = (reference_date is not None and o.due_date is not None
                   and o.due_date <= reference_date + dt.timedelta(days=1))
        # Outside the transactional categories, an event still running on the
        # day after sending (half days until the 16th) is a calendar entry,
        # not a record; a subscription period that has started is a record
        # however long it runs.
        over = o.end_date is None or (reference_date is not None and o.end_date <= reference_date + dt.timedelta(days=1))
        if o.action == "note" and started and (transactional or over) and category not in categories.KEEPS_TODAY:
            recorded += 1
        elif transactional and o.due_date is None and o.action in ("pay", "submit", "note"):
            recorded += 1
        else:
            kept.append(o)
    return Filtered(kept, 0, recorded)
