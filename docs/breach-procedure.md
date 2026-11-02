# If personal data is exposed: the breach procedure (21 Oct 2026)

A working procedure, not legal advice. The India timings come from Rule 7 of the DPDP Rules 2025 as summarised on dpdpa.com (read 21 Oct 2026): confirm them against the Gazette text. The UAE
side has no breach clock we could verify (the PDPL Executive Regulations are unresolved, see docs/children-data-compliance.md): ask counsel.

## What counts

Any time household data may have been read, copied, changed or lost by someone who should not have: a leaked master key or family key, a stolen backup, a database or object-store exposure, a
session token or device token out in a log, a sandbox escape, a model provider's incident, a lost phone with an open session, a mailbox or WhatsApp profile taken. When unsure, treat it as one.

## First hour (whoever sees it)

1. **Say so** to the founder at once; open a private incident note (date, who found it, what was seen). Do not paste personal data into it: ids, counts, hashes.
2. **Contain.** Revoke what is exposed: member and device tokens (`member_tokens`), agent keys, sealed sessions; lock a household's family key; rotate the master key or an API key; take a service off the network. The audit log is append-only and holds no text, so it can be read freely.
3. **Keep evidence**: logs (token, ticket and link are redacted from access logs), the database state, timestamps. Change nothing you do not have to.

## Within a day

4. **Scope it from the audit and the tables**: which households, which members (children first), which kinds of data (notices and their sealed text, documents, contacts, locations, health), and from when to when.
5. **Decide whether the law requires notice.** India: the fiduciary tells **each affected person** without delay, and the **Board** at once, with a detailed report **within 72 hours** of becoming aware (or longer if the Board allows on written request). Check the UAE and any other country the household lives in.
6. **Fix the cause**, and write down what would have stopped it.

## Telling a family (India's content list, plain words)

Send it through the account or the contact they registered (email, Telegram, the app). Say: **what happened** (nature, extent, when); **what it could mean for you**; **what we have done and are doing**;
**what you can do** (change a password, watch for calls, cancel a card); and **who to write to** (the privacy contact: not named yet, see docs/children-data-compliance.md). Short, no jargon, no blame. A guardian is told for a child.

## After

7. A written report: timeline, cause, who was affected and told, what changed. Keep it with the audit trail. Add the lesson to docs/todo.md and a test that would have caught it.
8. Rehearse this once a year with a pretend incident (a token in a log): can we list the affected households in ten minutes?

## What is missing to make this real

A named privacy contact and an incident owner; the Board's reporting channel once the Rules start (about May 2027); a way to message every affected household at once (a `GET`-only query of members by household is easy; the sending is not built); and counsel's view per country.
