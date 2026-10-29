"""Writes docs/database-schema.md from the live database: tables, columns, keys, indexes and relations.

Schema only, never data. Run against any FamilyOS database (default: FAMILYOS_DATABASE_URL):
    .venv/bin/python scripts/schema_docs.py
"""
import asyncio
import datetime as dt
from pathlib import Path

import asyncpg

from familyos.settings import settings

GROUPS = [
    ("Household and people", {
        "households": "One row per family: name, locale, the household's switches and limits, its wrapped data key.",
        "members": "The adults and children of a household; role, contact, Telegram link, opt-ins.",
        "member_classes": "A child's class by school year.",
        "member_tokens": "Sign-in sessions (hashed), one per device or browser.",
        "sign_in_links": "One-time links by mail, for sign-in and for binding Telegram.",
        "google_accounts": "A connected Google account: mail and calendar read access.",
        "mailbox_failures": "A Gmail message id that would not store, counted per poll; after a few tries it is skipped so the mailbox moves on. Ids only, no mail.",
        "google_auth_states": "State of a Google connect flow in progress.",
        "google_sign_in_states": "State of a Google sign-in flow in progress.",
        "founding_tickets": "Invitation tickets for starting a household.",
        "consent_records": "A guardian's recorded consent for a child.",
        "grants": "Delegated views: who may see which obligations, about whom, until when.",
        "member_locations": "Latest shared position of an adult who opted in; one row each, never a trail.",
    }),
    ("Notices and reading", {
        "input_artifacts": "Everything that arrived: a notice, mail, photo, forward. Visibility, source, channel, hand-over state.",
        "blobs": "Pointers to the sealed original files in object storage.",
        "artifact_subjects": "Which member a notice is about.",
        "extractions": "One reading of a notice: extractor, model, pages, whether it asked anything.",
        "claims": "A fact read from a notice with its quote and where it sat on the page.",
        "amendments": "A later notice that changes an earlier claim, awaiting a person's confirmation.",
        "intake_gaps": "What FamilyOS could not read or place.",
        "trusted_sender_domains": "Senders the household has taught as the school's or a trusted source.",
        "schools": "Schools the household has taught.",
        "source_schools": "Which source (a mail domain, a Telegram group) belongs to which school.",
        "harvests": "A pass that collected notices from a source.",
        "harvest_candidates": "Candidate notices found by a harvest.",
        "watches": "A public page watched for a change.",
        "digests": "Weekly digests sent.",
    }),
    ("Dates, tasks and reminders", {
        "obligations": "What a notice asks of someone: a date or a task, proposed, accepted or dismissed.",
        "reminders": "A reminder due for an obligation and member: when, channel, state.",
        "todos": "A to-do the family wrote or accepted from a suggestion.",
        "suggestion_dismissals": "Suggestions a person waved away.",
        "calendar_events": "Events read from a connected calendar.",
        "standing_obligations": "Rules that make a payment each month, such as rent.",
        "plans": "A trip, a meal plan or another open-ended plan.",
        "actions": "A proposed action from Ask awaiting confirmation.",
    }),
    ("Money and health", {
        "billers": "Billers and their arrival rhythm.",
        "receipt_items": "Lines read from receipts, used for rhythm and reorder nudges.",
        "purchases": "A purchase asked for, its limits and approval, and the provider's allowance id. No card data.",
        "medications": "One medicine read from a prescription: dose, supply end, clinic, patient.",
        "documents": "Passports, licences and other documents with expiry.",
    }),
    ("Errands and execution", {
        "errands": "A booking or look written down in full, fingerprinted, approved, and its outcome with steps.",
        "sealed_sessions": "A site login sealed with the household key for errands.",
        "sign_in_sittings": "A live sign-in sitting to capture a site login.",
        "rail_deliveries": "Delivery state of messages sent over a rail such as Telegram or WhatsApp.",
    }),
    ("Privacy, keys and sign-in", {
        "family_keys": "The household's data key wrapped by a secret only the family holds (a recovery phrase or Shamir shares); pending until confirmed.",
        "family_key_unlocks": "With more than one process only: the unlocked household key, wrapped under the master key, until it expires or the household is locked.",
        "family_key_attempts": "With more than one process only: failed unlock tries in the last hour, per member.",
        "family_key_devices": "A trusted device's own wrapped copy of the household key; the server stores only the wrapped copy.",
        "member_passkeys": "A member's passkey public keys (WebAuthn); the private key never leaves their device.",
        "telegram_family_groups": "A Telegram group a guardian made the family's own: the bot answers `today` and `week` in it from what the household shared with everyone.",
        "socket_tickets": "One-use tickets (hashed) for the live view, a taken-over errand and the phone driver socket, kept for a minute.",
        "webauthn_challenges": "One-use challenges for passkey registration and sign-in, kept for minutes.",
    }),
    ("Assistants and outside tools", {
        "assistant_connections": "A member's own Claude, Grok or Claude Code connection; the vendor key is sealed.",
        "assistant_tasks": "An instruction sent to a connected assistant and the text it handed back.",
        "agent_keys": "Keys for an outside assistant to call FamilyOS tools as a member (hashed, expiring, revocable).",
        "agent_calls": "A log of which tool an agent key called, and when.",
        "external_mcp": "Outside MCP servers a member chose to use, with a sealed access key and the tools allowed.",
        "taught_lessons": "With more than one process only: a lesson in progress and the process that holds its browser or phone socket.",
        "taught_skills": "A short routine a person showed FamilyOS on a screen (open, tap, swipe, read only).",
        "pending_actions": "An action staged for a person's confirmation (a card's yes or no), with an expiry.",
    }),
    ("Routines, nudges and learning", {
        "routines": "A rule a member wrote: what to say, when, and whether it prepares buttons.",
        "routine_runs": "Each time a routine ran, why, and what it said.",
        "morning_runs": "The once-a-day morning message, per member, so it goes once.",
        "proactive_log": "Everything FamilyOS said unprompted, for the daily cap and quiet hours.",
        "insight_notified": "Heads-ups already told to a member, so each goes once.",
        "suggestion_feedback": "What a member did with each kind of suggestion (accepted or waved away).",
    }),
    ("Children's own space", {
        "kid_tokens": "A child's own key to their page (hashed, expiring).",
        "kid_routine": "A child's morning and evening routine set by a guardian.",
        "kid_checks": "What a child ticked on a given day.",
        "kid_journal": "A child's journal entries; only the ones they chose to share are visible to guardians.",
        "kid_requests": "A child's question to a parent and the answer.",
    }),
    ("Money extras, health and safety", {
        "budgets": "A monthly limit per spending category.",
        "savings_goals": "A savings goal with a target and date.",
        "goal_contributions": "Money put toward a goal, by whom.",
        "bill_splits": "A shared bill and who paid it.",
        "bill_split_shares": "Each member's share of a split bill and whether it is settled.",
        "warranties": "A purchase with its return window and warranty end, linked to the invoice.",
        "health_daily": "A member's daily Health summary (steps, sleep, resting heart rate), only when they switch it on.",
        "emergency_profile": "The household's emergency card: contacts, pickup authorisations, home access.",
        "emergency_shares": "A shared link to the emergency card: hashed, expiring, with an open count.",
        "safe_checkins": "A member's I-am-safe check-in with an optional note.",
    }),
    ("Channels", {
        "whatsapp_watches": "A member's own WhatsApp reading: the chats they named, consent given, the last pass.",
    }),
    ("Platform", {
        "jobs": "The background queue: extraction, reminders, calendar, errands.",
        "job_events": "Steps and events of a job.",
        "audit_events": "A record of every action, who did it and when, rendered as a sentence.",
        "erasure_log": "Which household was erased and when, without its content.",
        "schema_migrations": "Which migrations have been applied.",
    }),
]


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url)
    tables = [r["table_name"] for r in await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1")]
    cols = {}
    for r in await conn.fetch("SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default, character_maximum_length, numeric_precision, numeric_scale "
                              "FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name, ordinal_position"):
        cols.setdefault(r["table_name"], []).append(r)
    fks = await conn.fetch("""
        SELECT c.conrelid::regclass::text AS tbl, c.confrelid::regclass::text AS ref,
               pg_get_constraintdef(c.oid) AS def, a.attname AS col
        FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.contype='f' AND c.connamespace='public'::regnamespace ORDER BY 1, 2""")
    pks = {r["tbl"]: r["cols"] for r in await conn.fetch(
        "SELECT i.indrelid::regclass::text AS tbl, string_agg(a.attname, ', ' ORDER BY a.attnum) AS cols FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indisprimary GROUP BY 1")}
    idx = {}
    for r in await conn.fetch("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND indexname NOT LIKE '%_pkey' ORDER BY 1, 2"):
        idx.setdefault(r["tablename"], []).append(r)
    checks = {}
    for r in await conn.fetch("SELECT conrelid::regclass::text AS tbl, pg_get_constraintdef(oid) AS def FROM pg_constraint WHERE contype='c' AND connamespace='public'::regnamespace ORDER BY 1"):
        checks.setdefault(r["tbl"], []).append(r["def"])
    applied = await conn.fetchval("SELECT count(*) FROM schema_migrations")
    await conn.close()

    fk_by = {}
    for f in fks:
        fk_by.setdefault((f["tbl"], f["col"]), f["ref"])
    purposes = {t: d for _, g in GROUPS for t, d in g.items()}
    grouped = {t for _, g in GROUPS for t in g}
    groups = GROUPS + ([("Other", {t: "" for t in tables if t not in grouped})] if set(tables) - grouped else [])

    def ctype(c):
        t = c["data_type"]
        if t == "character varying":
            return f"varchar({c['character_maximum_length']})" if c["character_maximum_length"] else "varchar"
        if t == "numeric" and c["numeric_precision"]:
            return f"numeric({c['numeric_precision']},{c['numeric_scale']})"
        if t == "ARRAY":
            return c["udt_name"].lstrip("_") + "[]"
        return {"timestamp with time zone": "timestamptz", "double precision": "float8", "USER-DEFINED": c["udt_name"]}.get(t, t)

    out = ["# FamilyOS database schema", "",
           f"PostgreSQL. Generated {dt.date.today().isoformat()} from the live schema ({applied} migrations applied, {len(tables)} tables). Schema only, no data.",
           "Regenerate with `.venv/bin/python scripts/schema_docs.py`.", "",
           "## Conventions", "",
           "- Every table that belongs to a household carries `household_id` and cascades on delete.",
           "- Primary keys are UUIDs. Timestamps are `timestamptz` in UTC.",
           "- Originals are never in the database: `blobs` points at sealed objects in object storage (see `object-storage.md`).",
           "- Derived facts (`claims`, `obligations`, `medications`, `receipt_items`) point back at the notice they were read from. Deleting the notice removes them.",
           "- Card numbers, passwords and one-time codes are never stored. A payment card is the provider's id only.",
           "- Visibility (private or shared, handed to a person, a child's consent) is enforced in queries, not by row-level security.", ""]
    out += ["## Relationships", "", "Arrows point from the table holding the key to the table it references.", "", "```mermaid", "flowchart LR"]
    seen = set()
    for f in fks:
        if f["tbl"] != f["ref"] and (f["tbl"], f["ref"]) not in seen:
            seen.add((f["tbl"], f["ref"]))
            out.append(f"    {f['tbl']} --> {f['ref']}")
    out += ["```", "", "## Tables", ""]
    for title, members in groups:
        out += [f"### {title}", ""]
        for t in tables:
            if t not in members:
                continue
            out += [f"#### `{t}`", ""]
            if purposes.get(t):
                out += [purposes[t], ""]
            out += ["| Column | Type | Null | Default | References |", "|---|---|---|---|---|"]
            for c in cols.get(t, []):
                d = (c["column_default"] or "").replace("|", "\\|")
                d = "" if d.startswith("nextval") else d[:40]
                out.append(f"| `{c['column_name']}` | {ctype(c)} | {'yes' if c['is_nullable'] == 'YES' else 'no'} | {d} | {('`' + fk_by[(t, c['column_name'])] + '`') if (t, c['column_name']) in fk_by else ''} |")
            out.append("")
            if pks.get(t):
                out += [f"Primary key: `{pks[t]}`", ""]
            if checks.get(t):
                out += ["Checks:", ""] + [f"- `{x}`" for x in checks[t]] + [""]
            if idx.get(t):
                out += ["Indexes:", ""] + [f"- `{i['indexname']}`: `{i['indexdef'].split(' USING ', 1)[-1] if ' USING ' in i['indexdef'] else i['indexdef']}`" + (" (unique)" if "UNIQUE" in i["indexdef"] else "") for i in idx[t]] + [""]
    Path(__file__).parent.parent.joinpath("docs", "database-schema.md").write_text("\n".join(out))
    print("wrote docs/database-schema.md,", len(tables), "tables")


asyncio.run(main())
