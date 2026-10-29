"""The first-run checklist for a new household: sign in, name the home, add the family, a channel, a mailbox, make it private.

Each step is read off the household where it can be (members added, a family-held key on) and only the choices a person makes are stored:
that the name looks right, that "make it private" can wait, that the checklist is dismissed. Existing households start dismissed.
Only a guardian answers it. Nothing here does anything on its own: each step points at the place it is done.
"""
from __future__ import annotations

import json

from familyos import audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, Principal

CHOICES = ("named", "skip_private", "skip_channel", "skip_mail", "dismissed")


async def status(p: Principal) -> dict:
    row = await pool().fetchrow(
        "SELECT h.name, h.key_mode, h.onboarding, (SELECT count(*) FROM members m WHERE m.household_id = h.id AND m.id <> $2) AS others, "
        "(SELECT telegram_chat_id IS NOT NULL FROM members WHERE id = $2) AS channel, "
        "EXISTS (SELECT 1 FROM google_accounts g WHERE g.member_id = $2 AND g.disconnected_at IS NULL) AS mail "
        "FROM households h WHERE h.id = $1", p.household_id, p.member_id)
    flags = row["onboarding"] if isinstance(row["onboarding"], dict) else json.loads(row["onboarding"] or "{}")
    private = row["key_mode"] == "family"
    steps = [
        {"key": "signed_in", "title": "You are signed in", "detail": "Your own sign-in, nobody else’s.", "done": True, "optional": False},
        {"key": "named", "title": "Name your home", "detail": row["name"], "done": bool(flags.get("named")), "optional": False},
        {"key": "family", "title": "Add your family", "detail": "Invite the adults with a link; add the children.", "done": row["others"] > 0, "optional": False},
        {"key": "channel", "title": "Message it from your phone", "detail": "Link Telegram once; the day's brief and your replies go there.",
         "done": bool(row["channel"]) or bool(flags.get("skip_channel")), "optional": True, "on": bool(row["channel"])},
        {"key": "mail", "title": "Connect your mail and calendar", "detail": "Read-only to start. Sending is a separate choice, made later.",
         "done": bool(row["mail"]) or bool(flags.get("skip_mail")), "optional": True, "on": bool(row["mail"])},
        {"key": "private", "title": "Make it private to your family",
         "detail": "One tap: you keep a recovery phrase, your devices open the home with a passkey, and FamilyOS keeps no key it can open it with alone. You can do this later.",
         "done": private or bool(flags.get("skip_private")), "optional": True, "on": private},
    ]
    complete = all(s["done"] for s in steps)
    show = p.is_guardian and not complete and not flags.get("dismissed")
    # `wizard`: a brand-new home that has not been through the first-run screens. Answering the name step (`named`) ends it for good,
    # so the screens appear once and everything after is the checklist.
    return {"steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps), "complete": complete,
            "dismissed": bool(flags.get("dismissed")), "show": show, "wizard": show and not flags.get("named")}


async def choose(p: Principal, choice: str) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian sets up the home")
    if choice not in CHOICES:
        raise Invalid("named, skip_private or dismissed")
    await pool().execute("UPDATE households SET onboarding = onboarding || jsonb_build_object($2::text, TRUE) WHERE id = $1", p.household_id, choice)
    await audit.record(p.household_id, "household.setup_step", actor_member_id=p.member_id, detail={"step": choice})
    return await status(p)
