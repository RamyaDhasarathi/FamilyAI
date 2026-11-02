# FamilyOS

FamilyOS reads the notices a household receives (school circulars, bills, receipts,
prescriptions, forms) and turns them into dates and tasks a person accepts, reminders that
reach the right person, and a record that points back to the page each fact came from.

It carries the mental load by noticing, not by doing. Nothing is added, sent, booked or paid
without a person's yes, and payments are off until a guardian switches them on.

Principles, in the order they win arguments:

1. **Noticing over doing.** Proposals, never surprises.
2. **Nothing on screen without its source.** Every date, amount and dose quotes the line it was read from.
3. **Private by default, shared on purpose.** Who can see a thing is always visible; a child's notices follow a guardian's consent.
4. **A projection, never a twin.** What FamilyOS knows is computed from the notices a family shared and can be rebuilt from them. Destroy the household key and it is unreadable.

## What is built

**Getting notices in**
- Mail: a connected Gmail mailbox, or a private forwarding address.
- Telegram: forward anything to the bot in your own chat. In a group it reads only a message that names it or replies to it.
- Phone: the iPhone share sheet and camera, pasted text, and Shortcuts (an iOS 27 notification automation can share a school app's notifications).
- School app on the phone: a read-only driver (an XCUITest target started from a Mac) reads a school's parent app.
- WhatsApp: the Cloud API adapter is written; it is not live until Meta verifies a business number. See `docs/whatsapp.md`.

**Reading**
- PDFs, scans, photos and handwriting (OCR in a sandbox, plus a picture model). English, with Devanagari and Tamil detected.
- Facts become claims with a quote and a box on the page; a claim it cannot ground becomes nothing.
- One-time codes are discarded at the door. Promotions and newsletters propose nothing. A scam shape is named.
- Revisions are matched to the notice they change and confirmed by a person.

**Deciding and being told**
- Today: the next thing up, what needs you, what is late, the school run, weather and holidays.
- Accept or dismiss each proposed date. Late items stay until someone acts.
- Reminders by mail, Telegram and phone banners with Done and Snooze, plus an evening follow-up on the due day.
- Telegram commands in your own chat: `today`, `needs` (Accept and Not this buttons), `help`, and questions ending with `?`.

**Decide, hand over, undo** (added 14 Oct 2026)
- **Needs you** is only what waits on a person: a date to accept, a revision to confirm, a notice handed to you, a child's question, and for a guardian an errand or purchase to approve. Each card carries its source quote, what FamilyOS suggests and why, what waiting costs, and buttons that are the existing endpoints (`/v1/decisions`). A clash with a timed date says which other adult looks free then (free or busy only, never the event).
- **Hand-offs close the loop:** the person handed a notice says yes, or can't and suggests someone; if nobody answers within the household's wait it moves to a backup or the sender is told; a waiting-on list and plain per-adult counts.
- **Activity ledger:** every action as a receipt (observed, read, rule, approved by, changed) with undo only while nothing has changed since (`/v1/activity`).
- **What it knows:** each fact with its source, how it is known, who corrected it and when it was last confirmed; ask why, confirm, or correct a child's school (`/v1/memory`).
- **Autopilot routines** fire on a clock or on an event (a bill, a changed date, travel coming up, a clash), tell you or prepare buttons, can be paused, and keep a history of every run.
- **My day** (per person): needs, ideas ordered by what you accept, how FamilyOS reaches you, your routines, what it has counted about you, and an opt-in gentle word when you carry most of one kind of thing.
- **What if:** an impact map for a member away, a purchase, or school reopening earlier. It changes nothing.

**School, family finance, safety, children**
- **School copilot:** what each child needs tomorrow, forms still to come back, an absence note drafted for editing.
- **Money plan:** a cash-flow timeline, budgets, return and warranty dates, savings goals, bills split between adults, a per-member purchase limit. Nothing moves money.
- **Emergency card:** contacts, pickup authorisations, allergies and medicines, insurance and travel documents, optional home access, shared by an expiring, revocable, audited link; I'm-safe check-ins.
- **Care circle scopes:** pickups only, medicine reminders, one child's school notices, while we travel, the emergency card.
- **Kids:** a separate narrow key per child for their own day (`/kid/`): routine and ticks, asking a parent, their savings, a private journal they may share from, and a button that tells the grown-ups.

**Money, health, documents**
- Bills and UPI alerts, recurring charges, a bill well above its usual, a receipt that closes the bill it matches.
- Standing payments (for example rent) made each month by a rule and closed by the receipt. Nothing is paid.
- Prescriptions become one line per medicine, grouped by person, with clinic, date and a refill reminder days before the supply ends.
- Passport, licence, policy and PUC expiry warnings.

**Anticipation**
- Implied to-dos from events (a birthday suggests a gift) and a Reorder nudge for what the household buys on a rhythm. You add them, or you do not. What is suggested is ordered by what each person accepts: counts per kind over 90 days, a kind dismissed three times without an acceptance goes quiet (unless its date is a day away), and you can read or clear the counts at `/v1/me/learned`.

**The household as a graph, and heads-ups**
- A Family map (`#/map`): a click-through picture of how people, notices, dates, documents, warranties, medicines, shops and clinics connect, with the notice behind every link. Built per request from the record as the signed-in person may see it; nothing is stored (`familyos/graph.py`, `GET /v1/graph/find`, `/v1/graph/touches`).
- Heads-ups, told once and only inside a person's quiet hours and daily cap: a pile of dated things for one person, a prescription or document tied to no one, a warranty about to end (`graph.insights`, `nudges.py`).

**Documents, returns and warranties**
- Passports, licences, policies, RC and PUC are read from what the family shares; an expired or soon-expiring one is a card with a renewal to-do, and sharing the renewed card clears it.
- A shop invoice that states a warranty or a return period becomes a card to track it, filled in for a person to confirm (`warranty_hints.py`). A notification that only points at an announcement inside a school app becomes a card to read the app (`pointers.py`).

**Bring your own assistant, and teach by showing**
- FamilyOS is an MCP server (`POST /mcp`): a person's own assistant (Claude, Grok, OpenClaw, any MCP client) connects with a key of their own, reads as them and proposes for them to confirm; it shares with the family only if allowed (`docs/mcp.md`).
- The other direction: send an instruction to your own Claude or Grok from My day and read the answer as text (`assistant_tasks.py`); call outside MCP servers you register, only the tools you allow, public https only (`mcp_client.py`).
- Show it a task once on a phone app or a public page and it keeps the steps by the words on the screen; a skill only opens, taps, swipes and reads, never types, pays or submits (`taught.py`).
- Invite a family member with a single-use link good for a week, to paste into a message.
- Sign in with a passkey (Face ID or the device unlock): add one on each device from the Household page; FamilyOS keeps only a public key bound to the address it was made at. Google and the emailed link remain. Set `FAMILYOS_WEBAUTHN_ORIGINS` to the exact https address families use (`familyos/passkeys.py`).

**Privacy: a family-held key**
- Originals are sealed per household. A household may opt in to holding that key itself. **Make it private** is one tap: a single recovery phrase (a 1-of-1 SLIP-39 share) is shown once and never stored, and each trusted device holds its own device secret; opening the household on a device takes a recent passkey sign-in plus that secret, and the phrase opens it when no device is to hand. The several-people option splits the key into SLIP-39 Shamir word shares (any t of n open it). Either way the server keeps no key it can open the household with alone, drops its own copy only after the switch is proven, and the key sits in memory while an adult has unlocked the household (`familykey.py`, `docs/family-key.md`).
- The text read out of notices can be sealed under the same key too (`seal_extracted_text`, off by default; backfilled for old rows, opened transparently on read, `sealing.py`). Titles and names are not yet.
- What this does not claim: while a household is unlocked the server and the AI it calls see what is shared.
- Next, and not deployed yet: the family has its own TEE and end-to-end hosting. The plan is attested key release (the shares are sent only to an enclave whose code the family's app has verified, so the unlocked key never exists outside it) and then end-to-end storage with on-device processing for the most sensitive kinds. The design, the order and the honest claim at each stage are in `docs/family-key.md`.

**Ask, search, voice**
- Ask answers from a numbered list of facts the member may see and proposes actions as cards that happen only on confirmation.
- Search by meaning (a small local embedding model, vectors held in memory only) with a words fallback. Voice notes are transcribed locally by default.

**Errands**
- A booking or look is written down in full, fingerprinted and approved against exactly that. One scripted site (Urban Company) with stop rules; a model-driven agent for registered sites without a script, which never takes a committing click.
- Read-only looks at a school app run on the phone.

**People and place**
- Roles: guardian, adult, child, and a care circle for a caregiver who sees only what is shared.
- Location sharing between adults, opt-in each, latest point only, arrival at home or the office.

**Payments (off by default, staging only)**
- A guardian switches on "Payments for the family", sets a per-purchase and a monthly limit, and approves each purchase. The payment provider (Crossmint) holds the card; FamilyOS keeps only ids. The allowance flow is proven in Crossmint's staging; actually buying needs their checkout, which runs on production and is not built.

## Surfaces

| Surface | Where |
|---|---|
| Public front page, with sign-in and start-a-household in a dialog | `/` |
| Web console | `/app/` (also `/cockpit/`, `/orbit/`, `/classic/`); Family map at `/app/#/map` |
| Guardian's card and verification screens for payments | `/pay/` |
| iPhone app (SwiftUI, iOS 17+) | `ios/`, see `ios/README.md` and `docs/native-app.md` |
| Telegram bot | `docs/telegram.md` |
| API docs | `/docs` |

## How it fits together

- **Server:** FastAPI and asyncpg on PostgreSQL. Background jobs (extraction, reminders, calendar, errands) run from a database queue.
- **Originals:** sealed with a per-household AES-GCM key and stored in S3-compatible object storage (a local directory in development). See `docs/object-storage.md`.
- **Models:** the extractor and Ask use a cloud model or the household's own model (a server you run); the setting says where it runs. Pictures can use a separate picture model.
- **Browser for errands:** a self-hosted Steel browser in Docker; sealed logins are loaded for one run only.
- **Schema:** `docs/database-schema.md`, regenerated from the live database by `scripts/schema_docs.py`.

## Run it

```sh
docker compose up -d                 # Postgres + MinIO
cp .env.example .env                 # then set FAMILYOS_MASTER_KEY (and a model key)
brew install tesseract               # OCR; apt-get install tesseract-ocr on Linux
pip install -e ".[dev]"              # Python 3.11 or newer
uvicorn familyos.main:app --reload   # applies migrations on start
```

Open http://localhost:8000/ for the front page, http://localhost:8000/app/ for the console and
http://localhost:8000/docs for the API. The console is served by the API itself, so requests are
same-origin and need no CORS rule.

Optional pieces, each off until configured:

| For | Set |
|---|---|
| Telegram | `FAMILYOS_TELEGRAM_BOT_TOKEN`, `FAMILYOS_TELEGRAM_WEBHOOK_SECRET`, `FAMILYOS_TELEGRAM_BOT_USERNAME` |
| Gmail and calendar | `FAMILYOS_GOOGLE_CLIENT_ID`, `FAMILYOS_GOOGLE_CLIENT_SECRET` and the redirect URIs |
| A model of your own | `FAMILYOS_LOCAL_MODEL`, `FAMILYOS_LOCAL_MODEL_URL` |
| Search by meaning | `FAMILYOS_EMBED_MODEL` (for example EmbeddingGemma through Ollama) |
| Voice | `FAMILYOS_VOICE_ENGINE` (local by default) |
| Errands | `FAMILYOS_STEEL_URL` (Steel container on port 3000) |
| Payments | `FAMILYOS_PAYMENTS_PROVIDER`, `FAMILYOS_PAYMENTS_API_KEY`, `FAMILYOS_PAYMENTS_CLIENT_KEY`, `FAMILYOS_PAYMENTS_PROJECT_ID`, `FAMILYOS_PAYMENTS_ENVIRONMENT` (keep `staging`) |
| Object storage | `FAMILYOS_BLOB_BACKEND=s3` and the `FAMILYOS_S3_*` settings |

A private option, not a product feature: `FAMILYOS_HEALTH_ENABLED=true` lets one member send a daily Health summary (steps, sleep, resting heart rate, workouts) from the phone, charted on their own Health page and available to their own Ask. Off by default; every screen and route is absent unless it is set.

Real values go in `.env`, which is gitignored. Never put them in `.env.example`.

The iPhone app is built with XcodeGen; see `ios/README.md`. Reminders on the phone are local
notifications scheduled from `GET /v1/reminders/phone` (the free Apple developer account cannot use
push), so they refresh whenever the app opens or the system allows.

## Getting notices in today

- **Paste it.** *Add a notice, then Paste a message.* Copied text reads better than a screenshot of it.
- **Share a screenshot or PDF** from the iPhone share sheet.
- **Forward by mail.** Point an inbound mail provider at `POST /v1/inbound/email` with the
  `X-FamilyOS-Webhook-Secret` header; each household's address is `inbound_address` on `GET /v1/household`.
- **Telegram.** Link your account once from the console, then forward to the bot.
- **School app notifications.** An iOS 27 Shortcut with a notification trigger that runs *Share with
  FamilyOS* with *Shortcut Input* as the text.

## Test

Tests need a Postgres database they can wipe:

```sh
scripts/test.sh            # always the test database; refuses any other, forgets .env
ruff check .
```

Live checks of third-party services (Crossmint staging, Telegram, models) are run by hand and recorded in
`docs/todo.md`; the suite uses fakes for them.

## API (v1)

The full, current list is at `/docs`. Groups:

| Area | Paths |
|---|---|
| Households and people | `/v1/households`, `/v1/me`, `/v1/household`, `/v1/household/members`, `/v1/household/rules`, `/v1/consents`, `/v1/sessions` |
| Notices | `/v1/artifacts`, `/v1/inbox`, `/v1/quarantine`, `/v1/inbound/email`, `/v1/inbound/telegram`, `/v1/inbound/whatsapp` |
| Reading and decisions | `/v1/artifacts/{id}/extraction`, `/v1/obligations`, `/v1/amendments`, `/v1/brief`, `/v1/reminders`, `/v1/reminders/phone` |
| Anticipation | `/v1/suggestions`, `/v1/offers`, `/v1/money` |
| Health and documents | `/v1/medications`, `/v1/prescriptions`, `/v1/documents` |
| Ask and search | `/v1/chat`, `/v1/search`, `/v1/voice/transcribe` |
| Errands | `/v1/errands` and its approve, finish and live routes |
| Location | `/v1/location`, `/v1/location/sharing`, `/v1/location/family` |
| Payments | `/v1/payments`, `/v1/payments/session`, `/v1/payments/card`, `/v1/purchases` and its decision, allowance, refresh and cancel routes |
| Audit and erasure | `/v1/audit`, `/v1/members/{id}/erase`, `/v1/household/erase` |

## Not done, on purpose or yet

- **No buying.** Payments stop at an approved, verified allowance. Checkout runs only on the provider's production environment and needs a decision on real money.
- **WhatsApp** waits for Meta's business verification; no API reads a group, so parents forward.
- **iOS push** needs the paid Apple programme; the phone schedules its own reminders for the next fortnight.
- **Android** is not built.
- **Per-merchant errands** are limited to Urban Company. Other shops get a hand-off link, and official programmes where they exist.
- **The family key is opt-in and in one process.** The unlocked key lives in one worker's memory; several workers need a shared memory-only cache first. Sealing the extracted text is off until switched on. TEE hosting and end-to-end storage are planned, not deployed (`docs/family-key.md`).
- **Chat as the main interface** is in progress: Telegram has the first commands, and Ask in the app and console proposes actions but retrieves by recency, not by meaning.

## Docs

| Doc | About |
|---|---|
| `docs/architecture.md` | How the pieces fit together |
| `docs/family-key.md` | The family-held key (Shamir shares), sealing the extracted text, and the TEE and end-to-end plan |
| `docs/mcp.md` | FamilyOS as an MCP server and client, assistant tasks |
| `docs/public-deployment-plan.md` | The rings for a public release and the closed team test |
| `docs/database-schema.md`, `docs/object-storage.md` | PostgreSQL tables and the S3 layout |
| `docs/extraction.md` | Reading notices, claims, scoring against the test set |
| `docs/reconciliation.md` | Revised notices |
| `docs/reminders.md` | How the family is told |
| `docs/telegram.md`, `docs/whatsapp.md`, `docs/wa-bridge.md` | The chat channels and their limits |
| `docs/gmail.md` | Mailbox and calendar |
| `docs/native-app.md` | The iPhone app, the reminders, the phone driver |
| `docs/care-circle.md` | Caregivers and what they see |
| `docs/actions.md`, `docs/sandbox.md`, `docs/harvest-security.md` | Errands, the sandbox, and what a sealed login can reach |
| `docs/browsing-and-privacy.md` | What the browser may reach and why |
| `docs/deploy.md` | How the server and the phone app go out |
| `docs/local-credentials.md` | Testing with your own accounts |
| `docs/digilocker.md`, `docs/export.md`, `docs/capture.md`, `docs/provenance.md` | Document access, export, capture, and code taken from Orbit |
| `docs/todo.md` | Open work, decisions, the watch list and live-check notes |
