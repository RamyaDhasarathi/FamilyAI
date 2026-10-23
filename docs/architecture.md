# FamilyOS architecture

Read from the code on 10 Oct 2026. Paths are relative to the repository
root. The same picture, animated, with a walkthrough and the three flows:
[docs/architecture.html](architecture.html) (published at
https://claude.ai/artifact/6sq3a9An42Bduutfeoi5xf); a two-and-a-half-minute
clip of it is `famos-architecture-2026-10-10.mp4` in Arunmozhi's Downloads.
The to-do list, decisions and what is parked are in [todo.md](todo.md).

## One sentence

FamilyOS reads a household's own notices (school circulars, bills, receipts, forms) for what they ask of a person, proposes dates, tasks and reminders that a member accepts or dismisses, and stops one tap short of paying or booking. (`PRODUCT.md`, `README.md`)

## Hard constraints

- **Projection, not twin.** Every fact on screen is derived from a notice and points back to it. The brief, inbox, ledger and load are computed per request and never stored (`familyos/brief.py`, `inbox.py`, `ledger.py`, `load.py` docstrings). Destroying the household key leaves nothing readable to rebuild from.
- **Wall: no card, no UPI PIN, no bank login, never pays.** `errands.py` has no vault reference for a card. `paylinks.py` only returns a URL that was already in the person's mail. The action rail's `kind` check constraint (`reply`, `calendar`) is the deny-list (`docs/actions.md`, `actions.py`). Planned payment phases keep this wall (`docs/todo.md`, "Paying, with approval").
- **A person approves.** Obligations start `proposed` (`extraction/obligations.py`). Actions and errands are approved against a recomputed `params_sha256` fingerprint of the exact content (`actions.py`, `errands.fingerprint`). Chat proposes and a person confirms (`chat.py`).
- **No model reads a page in a runbook.** Runbooks are deterministic (`execution/runbooks.py`). The only model contact is one closed question over a short list that code extracted (`execution/choose.py`). **Exception in code:** the generalist (`execution/generalist.py`, setting `errand_generalist="fallback"` by default) lets an Anthropic model read the page through `browser_toolset_20260801` for a site with no runbook (or every look when set to `looks`). A confirmation gate refuses any click that would pay, order or confirm, and hands the browser to the person. It is skipped when the household has local models switched on (`errands._handle`).
- **Consent and visibility.** `artifacts.VISIBLE_TO_MEMBER` sits inside every query. A child cannot be named as a subject until a guardian records consent (`consent.py`, `409 consent_required`). Grants let a carer see named obligations, never the artifacts (`grants.py`).
- **Audit.** `audit_events` rejects UPDATE and DELETE with a trigger. Details carry ids, counts and hashes, never text (`audit.py`). Only a household erasure purges it.
- **Platform walls (outside anyone's control):** no API reads WhatsApp groups (only forwards to a business number); school apps have no API; iOS has no notification-access API. These are why the forwarding rail, the phone driver and the Shortcuts trigger exist (`docs/whatsapp.md`, `docs/native-app.md`, memory notes).

## Components

| Component | Responsibility | Key files | Data it owns | Talks to |
|---|---|---|---|---|
| Server process | One FastAPI app under uvicorn. Runs migrations at start, registers job handlers, starts the worker, serves `/v1` (138 routes), `/app` (console), `/classic` (old console), `/healthz` | `familyos/main.py`, `familyos/api/routes.py`, `familyos/settings.py` | none directly | everything |
| Identity and sign-in | Households, members (guardian, adult, child), bearer tokens, mailed sign-in links, Google sign-in, device tokens, founding tickets | `identity.py`, `grants.py` | `households`, `members`, `member_tokens`, `sign_in_links`, `google_sign_in_states`, `founding_tickets`, `grants`, `member_classes` | console, app, Telegram binding |
| Share sheet and App Intents (iOS) | Sends a photo, PDF, page or text; tags a child; outbox replays when offline | `ios/ShareExtension/ShareViewController.swift`, `ios/FamilyOS/Intents.swift` (Ask FamilyOS, What's on today, Share with FamilyOS), `ios/Kit/Outbox.swift` | outbox file in the app group | `POST /v1/inbound/share` |
| Upload and paste | Console upload or paste | `familyos/web/app.js`, `routes.py` | | `POST /v1/artifacts` |
| Forwarded mail | Per-household inbound address; provider webhook; DMARC/DKIM read from the provider's own Authentication-Results | `intake/email.py` | `trusted_sender_domains` | `POST /v1/inbound/email` |
| Gmail | `gmail.readonly` polling with a narrow query; refresh token sealed under the household key | `intake/google.py`, `intake/mailbox.py` | `google_accounts`, `google_auth_states` | Google APIs |
| Telegram | Bot webhook; only messages addressed to the bot in groups; binding by one-time link; also Ask and replies | `intake/telegram.py`, `routes.py` (`/inbound/telegram`, `/telegram/link`) | `members.telegram_chat_id` | Telegram Bot API |
| WhatsApp Cloud API | What a parent forwards to the business number; sender placed by verified phone | `intake/whatsapp.py` | | Meta Graph API |
| WhatsApp bridge | Development-only relay from unofficial clients; off by default, answers 404 when off | `intake/wa_bridge.py`, `docs/wa-bridge.md` | | `POST /v1/inbound/whatsapp/bridge` |
| The phone's own hands | XCUITest runner on a paired phone drives a native app (the school app) over the errand socket; `read_app` runbook hands the screen's words in as a private notice | `ios/Driver/DriverTests.swift`, `familyos/execution/apps.py` | | `/v1/errands/{id}/phone` websocket |
| Intake gateway | Receive, Identify, Decide (accept, quarantine, reject), Scope (private/shared). Sniffs type from bytes, dedups by SHA-256 and by message id, applies "children's notices shared" rule, consent check on tagging. No model runs before it | `intake/gateway.py`, `intake/sniff.py`, `artifacts.py`, `rules.py` | `input_artifacts`, `artifact_subjects`, `blobs` | blob store, extraction job |
| Quarantine | Unknown or unauthenticated mail waits, invisible, until a guardian accepts | `artifacts.py`, `/v1/quarantine` | status on `input_artifacts` | console |
| Parse sandbox | PyMuPDF, Pillow, Tesseract in a child process with no `FAMILYOS_` env, rlimits, timeout; fails closed | `extraction/sandbox.py`, `extraction/parse.py` | none | |
| Extractor (the reader) | `rules` (default, no network), `model`/`claude`/`openai` (remote, opt-in, names the provider in config), or local model per household (OpenAI-compatible endpoint, e.g. Ollama, `FAMILYOS_LOCAL_MODEL`) | `extraction/pipeline.py`, `extraction/llm.py`, `extraction/rules.py`, `migrations/0045_local_models.sql` | `extractions` | OpenAI / Anthropic (opt-in) or local model |
| Picture reader | Photo vs document verdict; transcription of a picture by the household's local model | `pictures.py` | | local model |
| Grounding and obligations | Each quote found in the page text (exact, normalised, fuzzy at 85%); ungrounded claims never become obligations; OCR, hearsay and ungrounded penalties; proposals as task or calendar | `extraction/ground.py`, `extraction/obligations.py`, `extraction/service.py` | `claims`, `obligations` | |
| Attribution, reconciliation, documents | Which child a notice is about (class, elimination); amendment links proposed for a person to confirm; same-bytes duplicates superseded; passports, policies, RCs with expiry | `extraction/attribute.py`, `reconcile.py`, `documents.py`, `schools.py` | `amendments`, `documents`, `schools`, `source_schools` | |
| Record (Postgres) | Store of record; 52 migrations | `familyos/db.py`, `familyos/migrations/*.sql` | 44 tables (listed below) | |
| Blob store and keys | Originals sealed with AES-GCM; master key wraps household key wraps blob key; per-member scope key for private notices; S3-compatible or local dir; opaque object keys | `crypto.py`, `blobstore.py` | sealed objects | |
| Job worker | Durable jobs with leases, checkpoints, recurring `next_run_at`; one worker per process | `jobs.py` (from Orbit, `docs/provenance.md`) | `jobs`, `job_events` | handlers: erasure, extraction, reminders, mailbox, actions, watches, calendar, digest, plans, errands |
| Brief | Today's few things, worst first (missed, mailbox down, assigned, overdue...), money line, night-before line; derived | `brief.py` | none (derived) | console, app |
| Reminders | `due` and `undecided`, lead days 7,1,0; claim-then-send with `FOR UPDATE SKIP LOCKED`; channels log, email, whatsapp, telegram; visibility re-checked at delivery | `reminders.py`, `mail.py` | `reminders` | SMTP, Telegram, WhatsApp |
| Digest | Sunday message per adult, Telegram else email, once per week | `digest.py` | `digests` | |
| Calendar | Read (clash checks) and write (accepted obligation becomes one event, via a reconciler job) | `calendar.py` | `calendar_events`, event id on the obligation | Google Calendar |
| Ledger and money | Charges, recurring, spend, services, running low; all derived from claims and receipt lines | `ledger.py`, `extraction/items.py`, `billers.py` | `receipt_items`, `billers` | |
| Loop closer | A receipt that matches a bill's biller and amount marks it handled | `loops.py` | | |
| Pay links | The bill's own pay URL or UPI intent, found in the mail or a PDF QR, kept on the pay obligation | `paylinks.py`, `migrations/0040_pay_url.sql` | `obligations.pay_url` | |
| To-dos, plans, suggestions | To-dos people write; plans drafted by a model with the household in view, candidate bookings as public links with watches; implied to-dos as suggestions | `todos.py`, `plans.py`, `suggest.py`, `watches.py` | `todos`, `plans`, `watches`, `suggestion_dismissals` | model, class-1 reader |
| Ask and chat | Answers from the visibility-scoped record with citations; proposes actions a person confirms | `ask.py`, `chat.py` | | chat model (remote or local) |
| Action rail | Reply to the school by mail, or an .ics; recipient derived, never supplied; fingerprint-bound approval; off by default | `actions.py`, `replies.py` | `actions` | SMTP, Telegram group reply |
| Errands | Spec, fingerprint, guardian approval, job, step log with pictures, stop rules, needs_you hand-over | `errands.py` | `errands` | drivers below |
| Runbooks | Scripted per site (Urban Company today), the model answers at most one closed question | `execution/runbooks.py`, `execution/choose.py`, `execution/sites.py` | | browser |
| Generalist | Anthropic browser toolset for sites with no runbook; URL policy, confirmation gate | `execution/generalist.py` | | Anthropic API, browser |
| Sign-in sittings and sealed sessions | Member signs in to a listed site in a watched browser; only that site's origins are sealed under the household key; leased for one run | `execution/sessions.py`, `execution/livebridge.py`, `execution/capability.py` | `sign_in_sittings`, `sealed_sessions` | browser |
| Browsers | Steel (rented, `FAMILYOS_STEEL_URL`), local Chromium via Playwright (`FAMILYOS_BROWSER=local`/`auto`), phone WKWebView over `/v1/errands/{id}/phone`, phone app driver (XCUITest) | `execution/steel.py`, `execution/local.py`, `execution/phone.py`, `execution/apps.py` | | |
| Class-1 reading and harvest | Credential-free public reads (`disposable.py`, `research.py` via Parallel); assisted harvest of a portal with a person present | `execution/disposable.py`, `execution/research.py`, `execution/harvest.py` | `harvests`, `harvest_candidates` | |
| Console | Static SPA, vanilla JS, hash routes: today, family, life, space/:key, memories, chat, notices, notices/:id, waiting, money, plans, plans/:id, quarantine, revisions, collect, household, sign-in, errands, errands/:id, audit | `familyos/web/app.js` (ROUTES at line 199), `index.html`, `app.css` | token in localStorage | `/v1` |
| iPhone app | SwiftUI; Today, Family, Ask, Life, Memories, Inbox, Notice, Errand, Settings; Live Activity for errands; App Intents | `ios/project.yml` targets `FamilyOS`, `FamilyOSShare`, `FamilyOSLive`, `FamilyOSDriver`; `ios/Kit/*.swift` | token in Keychain, outbox | `/v1` |
| Notify | One message to one member (Telegram if linked, else mail) when something is handed to them | `notify.py` | | |
| Consent, erasure, export | Consent per child; erasure as jobs (household key destroyed first); export streamed, never stored | `consent.py`, `erasure.py`, `export.py` | `consent_records`, `erasure_log` | |
| Intake gaps | What the family says FamilyOS missed and where it lived; counted, never read downstream | `gaps.py` | `intake_gaps` | |
| Country profile | Country, time zone, currency; India full, UAE day-one | `country.py` | columns on `households` | |

Tables (from `familyos/migrations`): households, members, member_tokens, blobs, input_artifacts, artifact_subjects, consent_records, audit_events, erasure_log, jobs, job_events, extractions, claims, obligations, reminders, amendments, google_accounts, google_auth_states, intake_gaps, actions, sign_in_links, grants, watches, calendar_events, sealed_sessions, billers, harvests, harvest_candidates, trusted_sender_domains, google_sign_in_states, source_schools, founding_tickets, todos, digests, plans, receipt_items, suggestion_dismissals, sign_in_sittings, errands, documents, member_classes, schools. There is no `ledger` table: the ledger is derived.

## Main flows

### A notice arrives (share sheet, mail, Telegram)

1. Share sheet: `ShareViewController.swift` posts raw bytes with `X-Tag`, `X-Note`, `X-Visibility` to `POST /v1/inbound/share` (outbox retries offline). Mail: provider webhook to `/v1/inbound/email`, or Gmail poll job (`mailbox.sweep`). Telegram: webhook `/v1/inbound/telegram`, refused unless addressed to the bot.
2. `gateway.receive_*`: Identify (member token, verified sender, bound Telegram id, matched phone), Decide (accept / quarantine / reject), Scope (private unless shared; a child tag needs consent; children's notices shared with adults by rule). Original sealed (`crypto.py`) into the blob store, deduped by SHA-256; `input_artifacts` row; audit row; `extract_artifact` job queued in the same transaction.
3. `extraction/service.py` job: `sandbox.parse_isolated` (text layer or OCR), extractor (rules / remote / local), `ground.py`, `pipeline.py` decides actionable, `obligations.propose`. Stored as `extractions`, `claims`, `obligations` (status `proposed`). Amendment links proposed (`reconcile.py`); duplicates by hash superseded.
4. Seen as: Today and the brief (`brief.py`), Inbox, the notice page with quotes drawn on the original (console) or Accept/Dismiss in the app.
5. Accepted: calendar reconciler writes one Google Calendar event (`calendar.py`). Reminders sweep schedules `due`/`undecided` at 7, 1, 0 days (`reminders.py`) over mail or Telegram; Sunday digest (`digest.py`).

### An errand

1. Proposed from Ask or the Errands page (`POST /v1/errands`): kind (look / booking / purchase), service, spec, stop rules; fingerprinted (`errands.fingerprint`).
2. Guardian approves with `params_sha256` (`POST /v1/errands/{id}/approve`, optional `run_on=phone`). A sealed session for the site must exist (sign-in sitting, `sessions.py`).
3. Job `errands._handle`: phone runs are skipped by the server and run while the app holds the socket (`run_on_phone`); otherwise the generalist if no runbook (and not local-models), else the runbook.
4. Driver: runbook in Steel or local Chromium (`steel.current_browser`), sealed session leased for the run only; or the phone's WKWebView (`phone.py`); or for app looks the XCUITest driver (`apps.py`).
5. Each step written on the errand with a picture; stop rules halt; `needs_you` hands over the live view (`livebridge.py`); the run never pays. Audit rows. Live Activity on the phone shows state (`ios/Kit/ErrandActivity.swift`, `ios/LiveActivity`).

### Money

1. Receipts and bills arrive like any notice (mostly Gmail and forwarded mail).
2. Extracted as payment claims; receipt lines parsed deterministically (`extraction/items.py`, `receipt_items`).
3. `ledger.py` derives charges, recurring, spend, services, running low; `billers.py` notices a bill that did not come.
4. `loops.py` closes a bill when a matching receipt arrives (marked handled, reminders stop).
5. Money page and the money line on the brief and digest; Pay link beside Accept (`paylinks.py`): the person pays in the biller's page or their UPI app.

## Trust boundaries

- **Household data inside the server**: originals sealed per household (master key, household key, blob key, member scope key); Gmail refresh tokens and site sessions sealed; derived facts (claims, obligations) are plain rows protected by database controls (`docs/architecture.md`, "What the household key covers").
- **Parse sandbox**: a process boundary inside the server for untrusted bytes (`docs/sandbox.md`).
- **Leaving the deployment, opt-in**: notice text to OpenAI or Anthropic only when `FAMILYOS_EXTRACTOR` names a model; Ask and plans send scoped facts to the chat model; the generalist sends page views to Anthropic. A household can switch to a local model (`households.local_models`).
- **The family's own devices**: iPhone app and share extension, the phone web view, the XCUITest driver, the local Chromium on the family's Mac (and the server itself on that Mac today).
- **Rented browser (Steel)**: single container, one session at a time; egress unrestricted; DevTools endpoint unauthenticated (`docs/harvest-security.md`). Only the leased site session enters it.

## Deployment today

- One Python process (FastAPI under uvicorn) on the Mac, bound to 127.0.0.1:8088, published to the phone by Tailscale Serve (tailnet only). Postgres (`familyos_dev`); blobs in a local dir or S3/MinIO (`docker-compose.yml`). Docker image builds (`Dockerfile`). (`docs/deploy.md`)
- Workers, sweeps and polling run inside the same process (`main.lifespan`, `jobs.worker`).
- iOS app: developer build from `ios/project.yml` via XcodeGen; `ios/build.sh` (simulator), `ios/release.sh` (needs paid team, not yet). Driver runs from the Mac with `xcodebuild test`.
- External services when configured: SMTP, Google (sign-in, Gmail, Calendar), Telegram, Meta WhatsApp, OpenAI/Anthropic, Steel, Parallel.

## Planned

- Push notifications (APNs) with a Handled action, also for the Live Activity; universal links for sign-in (needs a real host).
- Phone actions over Telegram with an allow-list.
- Errands on Instamart, Swiggy and the school portal; a second guardian taking over a needs_you errand; errand closing from its invoice.
- Paying with approval: phase 2 UPI AutoPay mandates, phase 3 scoped virtual cards. Phase 1 (pay links) is built.
- DigiLocker as a Requester (researched, not built).
- Linq iMessage rail (US only, parked).
- Production browsers: one ephemeral browser per run, default-deny egress, auth on the browser endpoint (parked).
- Reading the school app on a schedule; moving the session token off the socket query string.
- Tamil and Hindi copy and OCR packs; Android; rate limiting in front (no Redis yet); sealing derived claim columns is a per-deployment decision.

# In depth

The sections below are the original design notes for the trust layer,
kept because the code still follows them.

## The trust gateway

Every item, from any channel, goes through the same four steps before it is
stored:

1. **Receive.** The channel adapter turns what arrived into an `InboundEnvelope`.
2. **Identify.** A signed-in member for uploads. For email, the From address
   must belong to a member of the household the message was sent to, and the
   receiving provider must have authenticated it (DMARC pass, or DKIM pass for
   the From domain exactly). The verdict is read only from the
   `Authentication-Results` header whose authserv-id is
   `FAMILYOS_INBOUND_AUTHSERV_ID`: anyone can write that header, and the id is
   what tells our provider's verdict from the sender's own. Unset, nothing
   authenticates and every message waits in quarantine.
3. **Decide.** Accept, quarantine or reject. Mail from an unknown or
   unauthenticated sender is quarantined: stored, but invisible until a
   guardian accepts it and says whose it is. Rejected items (empty, too large,
   an unsupported type, an unknown household address) are not stored.
4. **Scope.** Everything starts private to the member who sent it, unless they
   chose shared.

## Visibility

v1 has two levels, `private` and `shared`. The rule lives in one SQL
fragment, `artifacts.VISIBLE_TO_MEMBER`, used inside every query:

> a member sees an accepted artifact of their household when it is shared, or when they submitted it.

Guardians get no special view of other members' private items. Children do
not sign in. Attachments always have their email's visibility. Delegated use
("Dad is busy at 4pm" without saying why) is deliberately left for later.

One household rule sits on top, on by default: **a notice tagged with a child
is shared with every adult the moment it is tagged.** A school circular is
both parents' business whichever phone it arrived on. It is applied in
`artifacts.share_for_children` at every place subjects are written -- on
arrival, on the phone's tag, on a parent's tap, on an inferred class -- and
never on read, so the `visibility` column stays the one truth and the blob's
sealing follows it (the key is re-wrapped from the member's scope to the
household's). A guardian turns it off for the household at
`PUT /v1/household/rules`; a notice made private by hand afterwards is left
alone until it is tagged again. Every application is an audit row with
`rule: childrens_notices_shared`. "Every adult" means everyone who signs in
to the household, which is what `shared` has always meant.

## Signing in to a site with no API

Some things a family needs are only on a site or an app: a home-services
booking, a school portal. FamilyOS never takes a password for one. Instead a
**sign-in sitting** (`execution/sessions.py`, `POST /v1/sign-ins`) opens a
browser the member watches and drives, on the site's own sign-in page; they
sign in as they would on their phone, OTP and all; and when they press "I'm
signed in", what the browser holds *for that site's origins only* -- cookies,
localStorage, sessionStorage -- is sealed under the household key as a
class-2 session (`sessions.store`), and the browser is released. Trackers'
cookies and other origins are dropped with the browser. A task later opens
the session for its own length (`sessions.lease`) in a fresh browser holding
that state, and no longer. Sign out revokes it; erasing the household makes
it unreadable. The sites are a short, checked list (`execution/sites.py`):
custody of a session is taken only for a site whose flow has been looked at.
One browser serves the deployment, so one sitting is open at a time.

## Rules, not workflows

There is no workflow builder, on purpose. A family accepts a default and
perhaps flips a switch once; it does not wire flows, and asking it to would
hand the mental load back. So the household's rules are a short list in
`familyos/rules.py`, each a sentence a parent would say, with a switch a
guardian can flip (`GET`/`PUT /v1/household/rules`) or marked built in and
said so. The switch is honoured where the thing happens -- the digest sweep
skips the household, the calendar reconciler queues nothing -- never by a
second code path. What the household has taught by a tap ("this group is
that school") is listed beside them, read-only. A rule that does not map to
a switch is a product request, not a flow.

## Originals

- Bytes are stored once per household, keyed by SHA-256 (`blobs`). A second
  member sending the same file gets their own envelope over the same blob.
- The same member sending the same bytes again, or the provider delivering the
  same Message-ID twice, gets back the artifact made the first time.
- Blobs are sealed with AES-GCM using the household's own data key before they
  reach the object store. Object keys are random ids, never hashes or names.
- Every read of an original is audited and re-checked against its hash.

### What the household key covers, and what it does not

The key hierarchy is master key → household key → per-blob data key (and a
per-member scope key for private notices). Under it sit the things that are
documents or secrets:

- every original: mail bodies, PDFs, images (`blobs`), and harvested page
  text;
- the Gmail refresh token and browser session state;
- biller consumer numbers, which are not stored at all -- only an HMAC under
  the household key, enough to match a bill and useless outside the family;
- session tokens, sign-in links and founding tickets, which are hashed.

What is *not* under it is the projection: the facts read out of the
documents and shown on the screen. `claims` (title, quote, amount, date,
place, a child's name), `obligations`, `artifact_subjects`, the assignment
note, and `input_artifacts.source` (sender, subject, date) are plain rows in
Postgres, as are `members` and `households`. The brief, the inbox, the
calendar and the Money page are queries over those rows; they could not sort
by date or group by sender over ciphertext without decrypting everything on
every request.

So the honest statement is: **originals are sealed per household; derived
facts rely on database controls** -- disk encryption, one role per
deployment, no shared credentials, and the audit trail. A database leak
exposes what the family would see on the inbox; the documents behind it stay
unreadable without the master key. If a deployment needs the projection
covered too, the sensitive claim columns can be sealed under the household
key and decrypted in Python per request, at the cost of SQL ordering and
search on them. That is a decision for the deployment, recorded here so it is
made rather than assumed.

## Consent and erasure (DPDP Act 2023)

- A guardian records consent for each child, with the notice version and how
  the guardian was verified. Until then nothing can name that child as its
  subject (`409 consent_required`).
- Withdrawing consent starts, in the same transaction, a job that erases every
  artifact naming the child and any original no longer referenced. The consent
  record stays, as evidence that consent existed and ended.
- Erasing a child member does the same and removes the member.
- Erasing the household stops sign-in and intake at once, then a job destroys
  the household key (so every copy of the originals, including backups, is
  unreadable), deletes the objects, then deletes the rows and the household's
  audit trail. `erasure_log` keeps what was done, without personal data.

## Audit

`audit_events` rejects UPDATE and DELETE with a trigger; only a household
erasure can purge it. Events carry ids, counts, sizes and hashes, never
filenames, subjects or text.

## Errands: a runbook, or the generalist

An errand is a booking, a purchase or a look on a site a member signed in to (`familyos/errands.py`). It runs in a browser that holds the sealed session for the length of the run, on the site's own hosts and nowhere else, and every step is written on the errand with a picture.

Two things can drive it. A **runbook** (`familyos/execution/runbooks.py`) is a script for one site: it knows the pages, extracts short lists, and asks the model one closed question over a list when the words do not settle it (`familyos/execution/choose.py`). The model never sees a page. The **generalist** (`familyos/execution/generalist.py`) is Anthropic's `browser_toolset_20260801` over the same browser: the model reads the page as an accessibility tree with references, or a screenshot, and chooses each step. It takes a site with no runbook, and every look when `FAMILYOS_ERRAND_GENERALIST=looks`. Its URL policy is the site's hosts; its confirmation gate reads the words of every control before a click and refuses one that would commit the household (pay, place the order, confirm the booking), at which point the run hands the browser to the person. Scripts, uploads, console and network reads and extra tabs are never enabled. Neither driver ever pays: payment is after the service, or a UPI request on the person's own phone.
