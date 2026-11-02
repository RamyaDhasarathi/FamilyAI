# What changed in FamilyOS: 11 Oct to 24 Oct 2026

For business and technical readers. Each item says what a family can now do, then what it rests on.
Baseline: tag `v0.2.1-cockpit-baseline` (commit `84a7de9`, 11 Oct 2026). Latest: `c9bc757` on `main`. The fuller changelog, with every fix, is `docs/changes-since-baseline.md`.

**Checked against the baseline on 25 Oct 2026.** Each feature below was looked for in the tag's code. Items that already existed at the baseline (public context, outcome-scored rails, errands, billers, Ask, invitation sign-in links, a household time zone, the Telegram bot) are described here only where something new was added to them.

## In numbers

| | Baseline | Now |
|---|---|---|
| Commits since the baseline | | 305 |
| Server modules (`familyos/*.py`) | 49 | 102 |
| Database migrations | 56 | 103 |
| Test files | 80 | 165 |
| iPhone app source files | 33 | 102 |
| Lines changed | | +61,363 / −1,647 across 490 files |

## For the business

**1. A parent far away is looked after, not just reminded.**
A care circle with roles (parent, sibling, spouse, caregiver) and a view of what needs doing. A scam guard flags messages that try to pry out an Aadhaar number, bank details or a SIM. A caregiver sees only what the family allows, for example pickups, medicine reminders or one child's school.
*Technical:* `circle.py`, `scamguard.py`; narrow grant scopes; caregivers get no offers and cannot see standing payments or the household's errands.

**2. Health and medicines.**
A prescription is kept per medicine, with a refill proposed before it runs out. Handwriting is read in a sandbox and flagged. Steps, sleep, resting heart rate and workouts come from the phone, off by default.
*Technical:* `medications.py`, `health.py`; HealthKit on the iPhone; opt-in per person.

**3. Money, kept honest.**
A cash-flow timeline, budgets, warranty and return dates, savings goals and bill splits. Rent is made each month by a rule and closed by the receipt that names the payee. A UPI payee is shown, and flagged the first time it appears. A bill that did not arrive is noticed.
*Technical:* `finance.py`, `standing.py`, `billers.py`, `scenarios.py`; all amounts are for people to act on, and FamilyOS never moves money.

**4. Purchases behind a guardian switch (off by default).**
A guardian sets a per-purchase and monthly limit and approves each one. A shop catalogue is searched only when a guardian allows it.
*Technical:* `payments.py`, `shopsearch.py`, a Crossmint allowance made in the cardholder's browser at `/pay`; the payment SDK is pinned to 4.11.0.

**5. School and the day.**
A redesigned Today (what is next first, one "Needs you" list, weather and holiday pills, the school run). A school copilot shows what each child needs tomorrow and the forms still to return, and drafts an absence note for a parent to edit. A decision queue shows the source, a fixed recommendation and the cost of waiting.
*Technical:* `schoolday.py`, `decisions.py`, `conflicts.py`; the recommendation is fixed text, not a model's guess.

**6. It works where the family already talks.**
Telegram shows today, needs and help in a person's own chat, with Accept and Not this buttons. A guardian can make a Telegram group the family's own, and there "today" and "week" answer from what was shared with everyone. WhatsApp reading is opt-in, consent-first, and limited to the chats a member names. A Shortcut file lets people without the app share to FamilyOS. The iPhone app gained first-run in one screen, Activity and undo, Rules and access, Held mail, the Emergency card and What FamilyOS knows.
*Technical:* `chat_actions.py`, `telegram_group.py`, `whatsapp_watch.py`, `shortcut.py`; the iPhone app grew from 33 to 102 Swift files, each screen pinned by a server shape test.

**7. Errands close themselves.**
When the service's own confirmation or invoice mail arrives, the errand is marked done. It works for Urban Company only so far.
*Technical:* the sender must be on the service's own domain and authenticated, and the subject must confirm.

**8. Two ways in for the family's own assistant.**
Ask also proposes rule switches, and checks a timed to-do against the calendar. FamilyOS can be an MCP server, so a person's own Claude or Grok can read and propose using their own key. It can also be an MCP client, calling outside servers with tools the person has ticked. Both have a screen on the iPhone (Settings, My assistants) and a section on the console's My day.
*Technical:* `mcp.py`, `mcp_client.py`, `assistant_tasks.py`; task keys last minutes and are revoked when the task ends; the client only reaches public https servers.

**9. Optional family wallet, test networks only, off by default.**
Two switches (deployment, then a guardian per household); off, it is invisible. Guardians approve each transfer by signing the exact text with their own wallet. Limits per transfer, per day and per month. Turning it off keeps the data; a typed confirmation deletes it. A console card in Settings. Not for real money until a legal review.
*Technical:* `familyos/wallet/` (one package, one entry point); FamilyOS holds no key and never sends; EIP-4361 sign-in, EIP-191 approvals, the chain is read afterwards to confirm the transfer matched.

## Landing page and onboarding

**A new front door.** FamilyOS has a landing page at `/`, which is also the console's signed-out page. It leads with privacy ("Privacy you can check", an 18-second animation of the family key), then shows the problem a family has (a week scattered across five places) and how FamilyOS resolves it, a live notice-to-decision demo, the features, and the things it never does. A person can sign in or start a household in a dialog on the page itself.
**A shorter first run.** One-screen sign-in on the phone and the web, then name, family, Telegram and mail, once. A first-run checklist (sign in, name the home, add the family, make it private) takes a guardian one tap per step; households that already existed start with it dismissed.
**Inviting the family.** A guardian's Invite button gives a single-use link good for a week, emailed too when mail is set up. A member shows as waiting to join until they do.
*Technical:* `familyos/web_welcome/` and `familyos/web_home/` are new, as are `FirstRunView.swift` and `ios/Kit/FirstRun.swift`. The landing page's example names are made up and the no-personal-data test covers it. Dates: 12–17 Oct (page), 14 Oct (checklist, invitations), 23 Oct (first run).

## Privacy and security

**Family key (new in this period).** The household's key is split into Shamir shares (SLIP-39). It is switched on in two confirmed steps and any adult can lock or unlock it. A recovery phrase and trusted devices give a one-tap option. Text read out of notices is stored sealed under that key and opened on read.
**Passkeys (new).** Sign in with Face ID or device unlock; only the public key is kept. Later, a trusted device's secret can live inside the passkey, and each member can keep their share in their own passkey.
**Sealing is on by default** and now covers claim titles, subject names, issuers and date titles as well as quotes.
**Console sign-in** uses an HttpOnly session cookie with a CSRF check, not a token in local storage. The one-time sign-in link travels in the URL fragment, out of logs and Referer headers. All consoles have a strict script policy.
**Security review (17 Oct) fixed:** device tokens that could do too much; one-use WebSocket tickets; token, ticket and link redacted from logs; sign-in bound to the browser; a fetch guard that resolves a host once and rechecks every redirect; a member with "everything" no longer reads other households' dates; Telegram errors no longer carry the bot token; the database and object storage listen on localhost only.
**Children's data.** A working India and UAE checklist, a breach procedure, and a guardian's declaration of guardianship on a child's consent (off by default, to be turned on before May 2027).
**Names kept out of the code.** Real names, school apps and the Apple team id moved to local config, and a test keeps them out.

## Reliability

- Gmail reads every page of new mail after the first pass; mail it cannot parse is skipped and no longer stalls a mailbox.
- Reminders go at each person's own morning hour (per-person time zone and language), including daylight saving; background work runs on each household's own day.
- Groundwork for a second worker: tickets, the unlocked key and failed-try counts can move to Postgres when multi-worker is on.
- A dozen fixes, including duplicate "Still open" banners, forwarded-mail duplicates, a child's name never said into a group, and sign-out emptying the phone's outbox.

## Not done, or not yet proven

- **The sealing sweep for old rows has not been run on the real household.** New text is sealed; old rows wait for it.
- **Wallet:** no iPhone screen, no "Sign in with a wallet" button, no real-browser or real-wallet run, no legal review. Test networks only.
- **MCP client and assistant tasks:** screens exist on the iPhone and the console, but no task has been run against a real Claude or Grok key yet.
- **Errand closing** works for one service. **Bill tagging** misses some mail (EMI, FASTag, society dues); see `docs/todo.md`.
- **Children's-data compliance:** the guardian declaration is off by default; DigiLocker, a processor list and age rules are still to build.
- The dev database has not yet applied migrations 0100–0103; the next server start does it.
