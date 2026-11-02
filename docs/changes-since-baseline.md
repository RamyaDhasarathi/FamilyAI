# Changes since the shared baseline

From `v0.2.1-cockpit-baseline` (commit `84a7de9`, 11 Oct 2026; the repo `famos-v0.2-baseline`) to the latest code, 24 Oct 2026. 304 commits plus uncommitted work.
Feature log, not a code diff. Test-only changes, styling, regenerated schema docs and todo edits are left out.

## Unreleased (20–24 Oct 2026)

### Added
- **Family wallet** (optional module, test networks only). Two switches, both off: the deployment, then a guardian per household. Off, it is invisible. Link a wallet and sign in with it; a guardian names the family wallet and its limits (one transfer, a day, a month); a transfer is proposed, a guardian approves it by signing the exact text with their own wallet, sends it themselves, and the chain is read afterwards. Turning it off keeps the data; a typed confirmation deletes it. A console card in Settings. See `docs/wallet.md`.
- **Passkey-held family key.** A trusted device's secret lives inside the passkey instead of the browser. Each member can keep their share of a split key in their own passkey; enough members opening theirs opens the household.
- **Share with FamilyOS shortcut** for people without the app: a personal, signed file with the member's phone token inside, child names asked, the share tagged. Offered on the Phones card.
- **Errands close themselves** when the service's own confirmation or invoice mail arrives (own domain, authenticated sender, confirming subject). Urban Company only so far.
- **First run, on the phone and the web:** one-screen sign-in, then name, family, Telegram and mail, once; the mailbox consent is native on the iPhone.
- **iPhone:** Activity and undo; Rules and access; Held mail; Emergency card; school copilot; What FamilyOS knows. A phone self-check that walks Settings, Profile and WhatsApp (opt-in, read-only).
- **Ask** proposes rule switches (never the model, pictures or money ones); a timed to-do is checked against the calendar.
- **Telegram family group:** a guardian makes a group the family's own; there "today" and "week" answer from what the household shared with everyone.
- **Consent:** a guardian's declaration of guardianship goes with a child's consent (off by default). A working India and UAE children's-data checklist and a breach procedure.
- **Per-person time zone and language.** Reminders go at the person's own morning hour, daylight saving included; background work runs on each household's own day.
- **UPI:** the payee is shown and flagged the first time it appears; first-time pay hosts are flagged.
- **`docs/vs-anna.md`:** how we differ from Anna, each line from a source.

### Changed
- **Sealing is on by default** and now covers claim titles, subject names, issuers and date titles as well as quotes. Searches that matched those in SQL now run after opening. An old row is sealed by the sweep; the sweep has not been run on the real household.
- **Console sign-in** uses an HttpOnly session cookie, not a token in local storage, with a CSRF check.
- **The one-time sign-in link** travels in the URL fragment, out of logs and Referer headers.
- **Strict script policy** on all consoles, `/pay` and `/docs`; the API reference is our own page with Swagger UI pinned and integrity-checked.
- **Phone shortcut tokens** can only send to the inbox and can't open the teach or skill sockets. Keychain items are tied to this device.
- **Gmail** reads every page of new mail after the first pass; mail it cannot parse, or that has stray control characters, is refused or skipped and no longer stalls a mailbox for good.
- **Caregivers:** no offers, no sight of standing payments, no reading, finishing or cancelling the household's errands, and Ask hides the household's structure.
- **Second worker, groundwork:** tickets, the unlocked key, failed-try counts and taught lessons move to Postgres when multi-worker is on; assistant tasks name their worker; one helper replaces 13 recurring-job copies.
- **Meals plan** dropped (with its eight open to-dos).
- **Pinned** the payment SDK to 4.11.0 (was "latest").

### Fixed
- A phone ticket is re-checked each time it is used.
- Several "Still open" banners on one evening are one.
- Signing out of the iPhone app empties the outbox, so the next person can't send it.
- A child's name is never said back into a Telegram group; no payment appears in a group's answer.
- A WhatsApp chat name that two chats answer to is not read, and the reader says so.
- School class filter reads "4A" and "4-A" alike.
- Forwarded-mail duplicates are matched by sender plus Message-ID.
- Mailbox connection only completes in the browser that began it.
- An errand's response no longer carries its live browser's address or session id.

## 0.3.1 (17–20 Oct 2026)

### Security
- Device tokens may only call the share endpoints; WebSocket tickets are one-use; logs redact `token`, `ticket` and `link`.
- Google sign-in is bound to the browser; every response carries `Referrer-Policy: no-referrer`; rate limits on sign-in and household creation.
- The server-side fetch guard resolves a host once and connects to the vetted address, re-checking every redirect.
- Console security headers; a school's portal link must be https.
- A member granted everything no longer reads other households' dates through the brief, Ask or suggestions.
- Telegram errors no longer carry the bot token; Postgres and object storage bind to localhost only.

### Added
- An interactive database schema page.
- The iPhone member profile (your number, Telegram, work place by map search, usual start, and for a guardian allergies and blood group).
- Real names, school apps and the Apple team id moved out of tracked files into local config; a test keeps them out.

## 0.3.0 (11–17 Oct 2026)

### Added: care, health and money
- **Care circle** for a parent far away: roles, a constitution, a care view and a scam guard; a caregiver gets narrow scopes (pickups only, medicine reminders, one child's school, while we travel).
- **Medicines:** a prescription kept per medicine with a refill proposed; grouped by person with clinic, doctor and date; a wrong date or patient can be corrected; handwriting is read in a sandbox and flagged.
- **Standing payments:** rent made each month by a rule and closed by the receipt that names the payee.
- **Health from the phone** (opt-in, off by default): steps, sleep, resting heart rate, workouts, with two-week charts.
- **Finance:** a cash-flow timeline, budgets, return and warranty dates, savings goals, bill splits, a per-member purchase limit; a shop invoice with a warranty becomes a card; an expiring document becomes a card with a renewal to-do.
- **Purchases:** a payments switch (off by default) with per-purchase and monthly limits; a guardian approves each one; a Crossmint allowance made in the cardholder's browser, with a `/pay` page. Product options are searched live in a shop catalogue, only when a guardian allows it.
- **Mental-load balance** (opt-in, private, never a score) and a what-if simulator that changes nothing.

### Added: Ask, chat and voice
- **Chat-native Telegram:** today, needs and help in a member's own chat with Accept and Not this buttons; a question becomes a Confirm card; routines set in chat; a morning message once a day.
- **Ask** opens with what needs you, asks back when a request is ambiguous, retrieves older notices by meaning, and cites medicines, documents and standing payments.
- **Voice:** speech turned into words on your own server, audio never kept.
- **Search by meaning** using a model on your own machine.
- **Reminders on the phone** with Done and Snooze, scheduled a fortnight ahead.

### Added: school and the day
- **Today redesigned:** next up first, one Needs you list, weather and holiday pills, the school run, a day card.
- **Decision queue:** each card shows its source, a fixed recommendation and the cost of waiting; conflicts say who could cover (free/busy only).
- **School copilot:** what each child needs tomorrow, forms still to return, an absence note drafted for editing.
- **Source-backed memory:** each fact shows its source and who corrected it.
- **Autopilot:** routines fire on a clock or an event, with an approval policy, a pause switch and a history.
- **Activity ledger:** every action is a receipt; undo only while nothing has changed since.
- **Closed-loop hand-offs:** the assignee answers, a backup takes it if nobody does, the sender is told.
- **Emergency mode:** one card shared by an expiring, revocable, audited link.
- **Child and teen mode:** a separate narrow key, the child's own day, an "I need a grown-up" button.
- **School app read on the phone;** Ask proposes it and uses the named child's own school app.

### Added: connections and agents
- **WhatsApp reader:** reads only the chats a member names, every 30 minutes; off by default, consent first; pictures included; chats tagged to a school and its children; link code or QR on the iPhone.
- **FamilyOS as an MCP server** (your own assistant, your own key, proposes for you to confirm) and as an **MCP client** (outside servers, tools you tick).
- **Assistant tasks:** send an instruction to your own Claude or Grok.
- **Teach by demonstration:** show a task once on a phone app or public page; risky labels are refused.
- **Household graph and Family map:** what touches what, each link citing its notice; heads-up cards pushed once to each adult.
- **Model routing:** named profiles with a privacy floor, per household.
- **Location sharing:** opt-in per adult, latest point only.
- **Invitations:** single-use links good for a week.
- **Settings** grouped into People, Privacy and security, Connections, Notifications and rules, Your data, Advanced. The console nav merges Activity/Audit, Quarantine/Revisions and Money/Money plan into tabbed pages, with the rarely used ones under "More pages".

### Added: landing page and onboarding
- **A landing page at `/`** (12–17 Oct), which is also the console's signed-out front page: a chat-first hero with two examples, a live notice-to-decision demo, the five steps, every feature, and the things FamilyOS never does.
- **Privacy above the fold:** the hero line and a "Privacy you can check" section (an 18-second animation of the family key: sealed, three word shares, any two open it, locked again) come first, and the nav leads with Privacy. A "How it works" animation opens with the problem (a week scattered across five places) and resolves into one board. A home-focused section shows a smarter family home.
- **Sign in or start a household on the page itself,** in a dialog that makes the console's own calls.
- **Example names on the page are made up,** and the no-personal-data test covers it.
- **First-run checklist** (14 Oct): sign in, name the home, add the family, make it private. A guardian takes one tap per step; existing households start dismissed.
- **Invitations:** a guardian's Invite button gives a single-use link good for a week, emailed too when mail is set up; a member shows as waiting to join until they do.

### Added: privacy
- **Family key:** word shares, or one tap with a recovery phrase and trusted devices; text read out of notices is stored sealed.
- **Passkeys:** sign in with Face ID or device unlock; only the public key is kept.
- **First-run checklist:** sign in, name the home, add the family, make it private.
- **iPhone parity:** My day, Family map, Security, WhatsApp, Settings in eight groups.
