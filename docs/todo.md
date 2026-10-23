# To do

What is open, who it waits on, and why. Kept in the repo so it survives a
conversation. Dates are absolute. Done items are deleted, not ticked.

## Waiting on Arunmozhi

- **"School reopens" is accepted twice** (the restored row and the re-read's
  proposal, both accepted 8 Oct): dismiss one on the notice page, and delete
  its twin in Google Calendar if it appears twice.
- **Link Telegram** from the Settings page, then ask the bot a question ending
  in "?" (Ask over Telegram, built 8 Oct).
- **Share a passport's photo page, the car's policy PDF and the RC** from the
  phone: the Documents card and the trip check (built 8 Oct) have no real
  documents yet.
- **School-app notifications, now possible.** The phone is on iOS 27 and
  the Shortcuts Notification trigger works (9 Oct 2026, 20:45: four
  Reminders alerts arrived as four notices within a second). What carries
  the text is **Shortcut Input**; the trigger's Notification variable put in
  the Text field makes the action send nothing. What arrives is the title
  and the second line ("Incoming alert / Today, 20:45"). Next, on the phone:
  change the automation's app from Reminders to **Aachi global school** and
  wait for a real notice; then say whether the body came whole or only the
  first lines. The Mac side is done (9 Oct 2026, late): macOS 27.0.1,
  Xcode 27.0, the app and the driver rebuilt and the app reinstalled on the
  phone.
- **The driver on the phone, once more.** The cold-start fix (wait for the
  screen, tap the child, match "Announcement") is committed and unit-tested
  but not yet run on the phone: every try on the night of 9 Oct met a locked
  phone. Unlock, set Auto-Lock to Never for the minute, say "run".
- **The demo video (10 Oct 2026).** `~/Downloads/famos-demo-2026-10-10.mp4`,
  6 min 42 s: the console, then the iPhone app with the share sheet and the
  App Intents, on the real household. Waiting on you: a screen recording
  from the phone of the Notification trigger firing (Control Centre, then a
  Reminders alert or a real school notice); drop it in Downloads and name it,
  and it goes in before the end card. Decide whether `ios/Driver/DemoTests.swift`
  (uncommitted, runs only with FAMILYOS_DEMO set) and the three recording
  scripts (session scratchpad: demo-web.py, demo-mobile.sh, demo-stitch.py)
  go into the repo under `scripts/demo/`, so the video can be re-cut after
  any change.
- **Bank SMS automation** (Message trigger, sender = the bank's ID, same send
  actions). Less urgent now: the banks' UPI alerts are read from mail.
- **The children's class dates.** Class history was added 9 Oct 2026 and
  backfilled as "since 1 June 2026" for Sashreek (4-A) and Varali (KG-1). If
  either class began on another date, set it once with `since` on the
  school call, or leave it: it only times next June's "new year?" nudge.
- **Birthdays.** Every member's date of birth is empty (9 Oct 2026). Set
  them on the Household card (the "birthday" button on each row): ages on
  the person card, birthdays on the brief and in the digest, and the day a
  child's records become their own all come from it.
- **Archana's role.** She is an adult, not a guardian: sees shared notices,
  cannot flip rules, record consent or set a school. One tap on her member
  row if that should change.
- Optional: in the share shortcut, "If there's no input → Stop and Respond",
  so pressing ▶ in the editor explains itself instead of "network
  connection was lost".

## Orbit (built 11 Oct 2026, from the Master UI/UX spec)

A third console at `/orbit/` (`familyos/web_orbit/`, same API, same
sign-in), built to the spec's pages: OLED-black ambient home, the
household's procedural avatar with the five spaces in orbit (Finance,
Education, Household, Calendar, Grocery mapped to Money, school, home and
errands, dated items, running low), orbital notifications with a frosted
modal and real Accept/Not this, the swipe-up 90% dashboard sheet with the
bento grid, lateral deep layers (hero figure plus a stream of what FamilyOS
read, proposed, reminded, handed over), the three escape routes, one FAB
(tap to chat, hold to hear the day), eight age stages with their looks and
type (`?persona=` to preview), and the senior layout. Tag before it:
`before-orbit-ui-2026-10-11`. `/app` and `/classic` are untouched. Verified
by `scripts/demo/demo-orbit.py` (22 checks, a captioned clip in Downloads).
Where it departs from the spec: the copy says what FamilyOS did and never
"auto-paid" or "negotiated"; "Emotional" is Memories; errand approval opens
/app (needs the fingerprint and run_on). What the build found on the API,
worth fixing: 23 obligations have `decided_at` with no `decided_by`;
`errand.outcome.pictures` ids 404 on `/artifacts/{id}/picture` (step
pictures work); `/obligations?status=` omits 3 obligations the brief has;
`brief.items[].clashes` is always null here, so its shape is unverified.
Google sign-in lands on /app; add an Orbit return. Decided 11 Oct 2026:
Orbit stays a third address; `/app` remains the console and `/classic` the
old one.

## Decisions

- **Which console ships.** The old console is at `/classic/` (files in `familyos/web_classic/`, frozen at commit 02b28d8) next to the new one at `/app/`, for a side-by-side comparison. Same API, same sign-in. When the comparison is done, delete `web_classic/` and its mount in `main.py`, or fold what won into `/app/`.

- Drop the demo meals-plan to-dos? (Dropping the plan takes its open to-dos
  with it, and since 10 Oct 2026 their calendar events too.)
- **The employment contract as a family to-do.** "Sign and Return Offer
  Letter" comes from your own contract arriving as a mail attachment and is
  read as a household task (EOD, undecided). Decide whether a private
  document of one adult should raise obligations at all, or only private ones.

## Facts the record now holds (9 Oct 2026)

Built as one family of gap: a child's class with its history; where the
household lives; birthdays and the coming-of-age nudge; the school as a
record of its own (children, portal, mapped groups); the reader told how
the country writes dates. Still open from the same list: language per
household and member (Tamil and Hindi OCR packs, the digest's voice);
homes and vehicles as things documents and services attach to; people
around the family (tutor, driver, doctor) as contacts; a member's chosen
reminder channel; a half-day entry's time as a start and an end.

## Ask, as it is written (11 Oct 2026)

Built: `POST /v1/chat/stream` sends the answer as newline-delimited events
(say deltas, then the finished turn with citations and proposals, or an
error event); the console, Orbit and the iPhone app paint the sentence as
it arrives. On the dev model the first words land in under two seconds
and the whole turn in five, against fifteen to twenty before. A provider
that will not stream answers whole. Open: the model sometimes writes a
reference as "(n4)" instead of "[n4]" and the parser then finds no
citation; accept both shapes in `chat._REF`, `verify_citations` and the
three clients' replacement.

## Generative UI (parked 11 Oct 2026)

A pilot was built and left at `/guide/?plan=<id>` (`familyos/web_guide/`,
`familyos/guide.py`, `POST /v1/plans/{id}/guide`): the model composes a
page for one plan in OpenUI Lang from the plan's own facts, line by line,
from the OpenUI chat library's components; the server joins wrapped
statements and forwards one only if every call names a library component
and every @step is OpenUrl or ToAssistant, so no line can book, pay or
change the record. Rendered by the OpenUI browser bundle (0.1.7, about
800 KB with CSS). On "Five Days in Madurai" with the dev model: 28 to 37
lines, first in about a second, all in 25 s, nothing dropped once the
assembler was in; an invented "Arjun" on the first run led to the members
being named in the facts.

Parked because it is not useful enough as a page: the plan page already
shows the same facts instantly and deterministically, the generated layout
differs run to run, and a page can still state a wrong fact that the gate
cannot catch. The idea earns its place where the question changes, not
the page: Ask answering with a table, a side-by-side or a short timeline
from the same allow-listed library behind the same gate. When that is
wanted, the pieces to reuse are `guide.Statements`, `guide.gate`,
`guide.allowed_components`, the library prompt file and the two
providers' `stream_text`. Stays mounted; nothing links to it.

## Public context, behind switches (built 11 Oct 2026)

Four rails that read without any credential, each a household switch off
by default on the rules card (`familyos/publiccontext.py`, migration
0054): **where home is** (a town typed once, geocoded by Open-Meteo);
**the weather** for today and tomorrow on the brief's day line; **leave
by** (a drive time from home for a dated thing with a place, via
Nominatim and the OSRM demo server; only the place's words and the home
town leave the house); **public holidays** in the next two weeks from
Google's public calendar for the country; **exam date sheets** (a board's
page per school on the Household card, read daily, handed in as a shared
notice of the school's when its text changes). The brief carries
`context` and items carry `leave_by`; the console and the phone show them.
Turned on for the dev household on 11 Oct: "Today: 34°, overcast.
Tomorrow: 33°, light drizzle." Caveats: Google's India calendar lists
observances too (Navratri days), not only gazetted holidays, so the line
can be busy; the OSRM demo server is for pilots, not a deployment; no
school has a date-sheet URL set yet.

### The day tile, places and the school run (11 Oct 2026)

Today carries a day tile: the weather for today and tomorrow, the school
run from home to each school and the commute to the office, the holidays
coming. **Places** (migrations 0055, 0056): home, the office and each
school are picked on the Household card by a map search (`GET
/v1/places/search`, `PUT /v1/household/places/{home|work}`, school `PUT`
with `lat`/`lon`): typed words go to the public map (Nominatim, preferred
around home's point), a pasted Google Maps link resolves to the pin it
carries, a share.google link to the words it searches, a pair of
coordinates to itself. Only the words typed leave the house. The dev
household's three pins are in (home on Halls Road, the office at Prestige
Palladium Bayan, both schools from the user's Maps links). **School
timings** (`starts_at`/`ends_at` on the school) give a leave-by on the
tile and place the morning check.

**Live traffic** needs a key: TomTom's Routing API (`FAMILYOS_TOMTOM_API_KEY`,
20,000 requests a month free, no card; verified at docs.tomtom.com/pricing
on 11 Oct 2026). It is the one keyed public source and the one request
that carries two of the family's points, so it runs only in the two hours
before school and the hour before pick-up, and on a weekday morning for the
commute. The morning check (`school_run_alert`, one job per household,
placed 75 minutes before the earliest start on the next school day that is
not a public holiday) tells the guardians on Telegram or mail only when the
drive is 8 minutes worse than usual for the hour, with a leave-by. Without
the key the tile says the drive without traffic from public maps (OSRM
free-flow, optimistic in Chennai) and nothing is sent. The Gmail sign-in
cannot supply traffic: Google's traffic is Maps Platform (a billed API
key), not an OAuth scope. The phone's own MapKit could give a live ETA on
the device without any key: open.

The key went into `.env` on 11 Oct 2026. With it, the tile's number is
TomTom's usual for the hour (historic traffic for a departure half an
hour before the school's start, or 08:30 for the office), not OSRM's
free-flow, which had said 4 minutes for a commute Google Maps puts at 14;
and the map search goes to TomTom's search first, which knew the apartment
building ("Shivanee", Halls Road, Kilpauk) that the public map placed on
the wrong Halls Road. Home was moved to it. The schools' timings are set
(Aachi Global 08:45 to 15:00, First Cry 09:00 to 12:40); the morning check
is placed for Monday 07:30. Open: the Nominatim
usage policy (one request a second, a real user agent) is fine for a pilot
and not for a deployment, which wants its own geocoder or a keyed one; the
iOS app shows the runs on Today but has no Places editor yet.

### Duplicates seen in the calendar (found 11 Oct 2026)

Three kinds, looked at in the dev data. (1) A re-read of a notice that
superseded an accepted date left its Google event behind ("School reopens"
three times on 26 Oct): fixed, the reconciler is queued for a superseded
row regardless of the switch, and a dismissal takes the event off even
after the switch was turned off. The two stale events from before the fix
are still on the calendar: queue the reconciler for the two superseded
rows to remove them. (2) Across notices nothing dedupes: three notices
about the same date (Telegram group, the app, a forward) each propose it,
and each accepted one is written. The rails ledger records the echo but
does not act. Open: when a proposal says what a live accepted or proposed
obligation already says on the same date, mark it an echo of that one
instead of asking again, and say "also from the Telegram group" on the
first. (3) A plan drafted twice ("Five Days in Madurai", 7 Oct and 11
Oct) wrote its to-dos twice: data, not code; dropping the duplicate plan
removes its to-dos and their events.

## Sessions (11 Oct 2026)

A session is ended one at a time only by its own holder ("sign out") or
all at once per member ("sign out everywhere"); the list on the Household
page cannot end one chosen session. Open: a per-session end for guardians,
and the demo and smoke scripts should sign out the sessions they open.
Cleaned up on 11 Oct: every unlabelled session but the active browser's
was revoked by hand; the phone's labelled tokens were left.

## Intelligence and action (9 Oct 2026)

Built: Offers on Family (10 Oct 2026, `familyos/offers.py`): standing
behaviours the record suggests, said in the family's names, each with what
it will do and what it will not; Accept flips the switch or opens Ask with
the question, Not now is remembered. Today: hand bills to the adult who
handles them; a receipt will close a bill due soon (said once); a sender
on a rhythm gone quiet (said once); a trip on an accepted school date,
checked in Ask. The money line on the brief (a rhythmic merchant a quarter above its
usual, a first charge of a thousand or more, what comes out this week);
the night-before line (what tomorrow's event still needs, from the same
notice); the drafted reply to the sender (mail or the Telegram group),
sent only on a parent's tap, text not kept. Still open from the same list:
the tight-day detector across children; "who usually handles what" as a
one-tap hand-over; the tax pack by financial year; reorder from running
low (needs the errand sites); escalation of an unacknowledged reminder to
the other adult. The reply goes from the server's mail address with the
parent's name in the signature; a Reply-To of the parent's own address is
the next step, and WhatsApp replies wait on the bridge.

## Country profiles (decided 9 Oct 2026)

A household carries country, time zone and home currency (`country.py`);
India is the full profile, the UAE has the day-one facts (Asia/Dubai, AED,
September school year, card and page rails). Step 2, when a Dubai family
exists: the sender-domain table, document kinds, errand sites and
integrations (UAE Pass, Noon, Talabat) keyed by the country profile. What
never depends on country: consent, visibility, the audit, the walls on
cards and credentials, the reading itself.

## To build, when said

**Decided 11 Oct 2026: the top of the order is one promise, "nothing from
the school is ever missed".** Every date, fee, form and holiday from each
child's school lands on both parents' calendars and reminds them, whatever
rail it came by (the school app read by the phone's own hands, a WhatsApp
group forward, a photographed circular, mail), and once a week the family
sees what the school asked, what is still open, and the capture number
("41 of 41 school notices this term"). Built 11 Oct: the rail ledger (`familyos/rails.py`,
`rail_deliveries`, `GET /v1/rails`): every school notice is recorded with
the rail it came by (school app read by the phone, WhatsApp, share sheet,
mail, Telegram, portal) and whether it was first to carry its dates, an
echo of an earlier notice, or carried none; the score per rail is
Beta-smoothed from those rows and the family is told the numbers as an
Offer once a school has four notices. Backfilled on the dev household:
Aachi 9 notices (3 first, 6 with no date), First Cry 6 (3 first, 2
echoes), all by the share sheet so far. What it still needs, in order: the
scheduled read of the school app (and the Notification automation pointed
at it); push, for the asks with a clock; Tamil reading and a Tamil digest
voice; a "school this week" view with the capture number from the
intake-gaps count; and the adaptive pieces that make it feel like it knows
the family: who handles what per sender, each child's school rhythm
(fees, PTMs, holiday lists anticipated from a term of circulars), where and
when each parent acts, what to keep quiet. Then the order below.

1. **Phone actions over Telegram.** A fixed message shape from the bot
   ("Pay: <upi link>", "Open: <live view>"), a Notification automation on
   the phone running one shortcut that dispatches on the word, and a card on
   Settings listing the phone actions the household permits, each off by
   default (the allow-list from Finn Voorhees's Pi demo). Also makes the
   MyClassBoard notification automation a two-minute setup. An afternoon.
2. **Errands on two more sites.** Instamart and Swiggy for the usual
   reorder, looks first; then the school portal for fees. The generalist
   covers a site with no runbook; a runbook once the flow is seen.
3. **A second guardian can take over a needs_you errand.** The household
   version of several people steering one run.
4. **Re-score the local model on extract-v6.** The prompt changed twice
   since the 8 Oct score; run `--local --jobs 4` again and keep the number.

- **Urban Company, next steps.** Done: sitting, sealed session, proposal with
  approval and stop rules, the runbook to the checkout, hand-over with live
  view, the generalist for the long tail. Open: (4) the confirmation and the
  invoice reconciling the errand through the Inbox (the loop closer does the
  bill; the errand row should close too). Unknown until a full run: session
  lifetime, pay-after-service on the chosen service.
- **Push notifications** (asked 10 Oct 2026: "alert the user for expired
  login, OTP"). Blocked on a paid Apple Developer Program team: the Push
  Notifications entitlement is not given to a personal team. Once enrolled,
  drop the APNs auth key (.p8) path and key id here. Then: a device table
  per member, a "needs you" push (time-sensitive) when a run hits a sign-in
  wall or an OTP, reminders as pushes with a Handled action, Live Activity
  updates by push, and a "still signed in?" look before a scheduled errand
  with a push the day before. Stopgap built 10 Oct: a run that ends
  needs_you, or stops because the sign-in lapsed, tells the asker at once
  over notify (Telegram when linked, else mail) with why and the link to
  take over (`runbooks.Run._tell`). A run in the phone's own web view says
  nothing: the person is looking at it.
- **The native app** (decided and scaffolded 8 Oct 2026, `ios/`, plan in
  `docs/native-app.md`): the share extension replaces the share shortcut for
  anyone with the app. Next on it, in order: universal links for the mailed
  sign-in link (needs a real host), push with a "Handled" action and for
  the Live Activity, the phone actions allow-list in its Settings. From the
  9 Oct design pass, the API the app still lacks: invite a member from the
  phone, notification preferences, link Telegram from the phone, a list of
  connected services (Gmail state). Done 8
  Oct: Google sign-in, the designed screens, Dynamic Type and VoiceOver,
  Liquid Glass on iOS 26, App Intents for Siri, the errand Live Activity. Waiting on Arunmozhi: the iOS platform finishing its download in
  Xcode, then a run on the phone with a team set in Signing.
- **Shortcut distribution for end users** who will not install the app:
  rebuild the share shortcut with the token as an Import Question, publish
  its iCloud link, add a Household card with three-line instructions. Later:
  server-signed `.shortcut` files (`shortcuts sign --mode anyone` on a Mac).
- **Ask proposes rule switches.** "Always share Varali's notices with Archana"
  should map to the existing switch at `PUT /v1/household/rules` and be
  proposed like a to-do.
- **Calendar read for to-dos.** Clash checks today cover obligations only; a
  to-do at Monday 11:00 is not checked against the real calendar.
- **Linq managed iMessage line** (2026-10-07). A fourth rail beside Telegram,
  WhatsApp and the share sheet: webhook route, per-member link by texting the
  line once, same quarantine and attribution, replies through `notify`. About
  a day, on the Telegram rail's shape. Setup per Linq's docs: token from the
  dashboard (API → Overview → Generate new token) or a representative; Linq
  provisions a pool of US sending lines and picks the line per send;
  `POST /v3/messages` with E.164 recipients; `POST /v3/webhook-subscriptions`
  for `message.received`; honour STOP keywords. Pricing and sandbox limits
  were not readable from the docs; check in the dashboard. **Not for the India
  wedge** (US numbers, iMessage a minority, notices arrive by WhatsApp, email
  and SMS). Build when there is a US customer or an iMessage-first family.
  Sources: linqapp.com/imessage-api, docs.linqapp.com/channel/imessage/.
- **Paying, with approval** (asked 2026-10-07: "we need auto pay at some point
  with approval"). The wall stays: FamilyOS never holds a card, a UPI PIN or a
  bank login. Three phases that respect it:
  1. *Pay links* -- done 2026-10-07 (`familyos/paylinks.py`): the bill's own
     pay URL or UPI intent, found in the notice, kept on the pay obligation,
     shown beside Accept, on Today and in the digest. Still to come in this
     phase: the receipt reconciling the obligation to "paid" on its own.
  2. *UPI AutoPay mandates, India.* For recurring billers the ledger already
     knows, propose "set up AutoPay" and open the biller's mandate flow; the
     bank and the UPI app hold everything, the parent approves once in their
     app, FamilyOS tracks the mandate from its confirmation mail and SMS and
     reminds before each debit. Limits per RBI's e-mandate framework (secondary
     sources say ₹15,000 per debit without a fresh PIN, higher for insurance,
     mutual funds and card bills; verify against the RBI/NPCI text first).
  3. *Scoped virtual cards for non-UPI bills (Dubai, international).* Stripe
     Issuing for agents: a single-use virtual card per approved payment, with
     merchant-category and per-authorisation limits, and a real-time
     authorisation webhook that approves only the amount and merchant the
     parent approved; executed in a cloud browser session (class 3). Stripe
     Issuing is not offered in India or the UAE, so this needs a local issuing
     partner or a different wedge. Approval model for all phases: a "proposed
     payment" on the obligation, approved by a guardian in the console or over
     Telegram, with a per-merchant cap, a monthly cap, known billers only, and
     a second approval for any new payee; every step an audit row.
  Sources: docs.stripe.com/issuing/agents; upstox.com and razorpay.com on the
  e-mandate framework (secondary).
- Older offers: an "Execution — when and how" tab in the Intake Reality Check
  doc (from the purchase-agent PDF review); Goshen as an inbound-mail
  provider; a PACT (openpactprotocol) watch-list entry; a sessions card in the
  console.

## The agent says what it is (decided 10 Oct 2026)

Every browser FamilyOS drives carries one token on its real user agent
(`familyos/execution/agent.py`): the local Chromium, Steel, the phone's
web view, and the class-1 reader. On the family's own devices the address
is already the truth; the token makes the rest true. The sitting and the
run carry the same token, so a sealed session is used by the browser that
made it. Open: (1) a sign-in sitting and a run on Urban Company with the
token, to see whether Turnstile or the site treat it differently; a sealed
session made before 10 Oct carries the plain user agent, so its first run
with the token is the one to watch. (2) Web Bot Auth, which needs a stable HTTPS origin for the key directory
(`/.well-known/http-message-signatures-directory`), not a hosted
deployment: a domain FamilyOS owns in front of a static host, or the
Mac's ts.net name through Tailscale Funnel (ports 443, 8443, 10000; the
`funnel` node attribute; whether one path alone can be funnelled is to be
checked). The directory's origin is the agent's name to the world, so a
domain is the better name. Then: an Ed25519 key per deployment, the
directory response signed with created and expires (Cloudflare requires
it; the draft recommends it) and re-signed before it expires, request
signatures from the credential-free reader and the Playwright-driven
browsers through a request hook; the phone's web view cannot sign every
sub-request and stays on the token. Only sites that verify (in practice,
behind Cloudflare) act on it; consider carrying the approval fingerprint
with it, so a site can see the run was approved by a guardian. About a
day once there is a domain.
Sources: datatracker.ietf.org/doc/html/draft-ietf-webbotauth-httpsig-protocol,
developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth.

## Browsers (9 Oct 2026)

Three now, one contract: Steel (rented, `FAMILYOS_STEEL_URL`), the local
Chromium on the machine FamilyOS runs on (`FAMILYOS_BROWSER=local`, or
`auto` when no Steel URL is set: the family's own address, no session
bill, a sitting opens a window on the Mac), and the phone's own web view
for runbook errands (approve "on this phone" in the app). Open: the
generalist on the phone (needs a Chromium), the egress exit node is now
moot for local and phone runs, and the 7 Oct note below still holds for a
hosted deployment that is not a Mac.

- **The phone's own hands (built 9 Oct 2026).** iCTRL's shape, done with
  XCTest: `ios/Driver/` is a test runner that drives native apps on the
  phone over the errand socket, and `familyos/execution/apps.py` reads an
  app's notices and hands them in (`docs/native-app.md`, "The phone's own
  hands"). Verified on Arunmozhi's iPhone against the school's MyClassBoard
  app (`com.mcb.aachiGlobal`): the announcements page came in as a private
  notice, each notice's full text (the tree is not cut at "View More..").
  Open: (1) a proposed "read the school app" on a schedule, or from the
  MyClassBoard notification automation; (2) move the session token off
  the socket's query string, since uvicorn's access log prints it
  (affects the web-view runs too); (3) a run from a cold start of the
  school app on the phone itself: the 23:35 run on 9 Oct caught the splash
  and the list of children and handed in pictures, so the runbook now
  waits for the screen to settle and taps the child by name (unit-tested
  with a scripted cold start; the phone was locked before it could be run
  again). Errand 18866e5a on the dev DB is approved and waiting for that
  run. Open Minis's own repo
  (openminis.app, GPL v3) is an on-device agent app, not the driver; iCTRL
  is still "coming soon" there.

## Browsers in production (decided 2026-10-07, parked 9 Oct 2026)

Not needed while errands run in the phone's own web view (attended, the
family's IP and sign-in) or in the local Chromium on the machine FamilyOS
runs on (unattended, the home network when the server is at home). Needed
only if both become true: a hosted deployment serving many families, and
errands that must run with no phone open (a nightly fee check, a scheduled
reorder). The generalist needs a Chromium either way, so it rides on the
local or the rented browser, never the web view.


- One ephemeral browser per run, never per household and never shared: the
  sealed session is put in at the start and wiped at the end, as the code
  does today; the container itself is thrown away after. Self-hosted Steel
  (one container per session, orchestrated) in our own region, or Kernel's
  per-session microVM browsers with the same contract. Not Steel's single
  shared container, whose profile leaked a sign-in between sessions.
- Egress through the household's own network where a site challenges
  datacenter addresses: a Tailscale exit node on the family's own device,
  so the site sees the family's IP, which is the truth. Try before buying
  residential proxies.
- No model reads the page in a runbook (prompt injection is the agent's
  weak point); runbooks stay deterministic. A model may answer one closed
  question -- "which of these cards is the service?" -- from a short list,
  never from the page, and never on the payment path. The one exception
  is the generalist (`familyos/execution/generalist.py`, on by default as
  the fallback for a site with no runbook): there a model does read the
  page, through Anthropic's browser toolset, behind a confirmation gate
  that refuses any click that would pay, order or confirm and hands the
  browser to the person; it is skipped when the household runs local
  models. Browser-use-style agents are otherwise for authoring runbooks
  at dev time, not for running them.

## Known rough edges

- Plans: three Switzerland drafts exist (6 Oct, and two from 7 Oct of which
  two are dropped). Keep one before testing booking flows.
- Two accepted Airtel obligations for the same bill, one by each parent; the
  older one is superseded, so only Archana's is on the calendar.
