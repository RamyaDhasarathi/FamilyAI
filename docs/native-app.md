# The native app

Decided 8 Oct 2026: FamilyOS gets a native iPhone app beside the web console.
Not a port of the console. The phone is where notices arrive and where a
parent has thirty seconds, so the app does the four things that need to be
one tap away and leaves the rest to the console.

## Why native, and why now

- **The share sheet.** Today a photo or a PDF reaches FamilyOS through a
  Shortcut that needs a pasted token, Tailscale up, and a request body the
  Shortcuts editor fights over ("not able to set Shortcut Input as value for
  item"). A share extension is the same `POST /v1/inbound/share` with none of
  that: pick FamilyOS in the share sheet, tag a child, done.
- **Decisions in the moment.** Accept, dismiss, "handled", hand to Archana:
  the things the Telegram rail does with words, done with a thumb.
- **Later, what only an app can do:** push notifications (a reminder that is
  a tap away from "handled"), App Intents so Siri and Shortcuts call the app
  directly, a widget with the next thing, the phone actions allow-list from
  plan item 2.

## The look (8 Oct 2026)

Built to a mockup Arunmozhi supplied: warm paper, a coral primary, one hue
per space, serif for the greeting, cards with soft corners, and a bar of
our own with Ask as the orb in the middle. Five places on the bar: Home,
Family, Ask, Life, Memories. Inbox and the profile hang off Home (the bell
and the avatar); Search off Family, Life and Memories. Nothing on any
screen is invented: the greeting photo is the family's latest memory, the
"FamilyOS noticed" card is a real clash from the brief, the suggestions on
Ask are built from the household's children and bills.

Later the same day: every type size became a text style (Dynamic Type),
icon-only controls got labels and 44pt targets, and on iOS 26 the
navigation layer is Liquid Glass (the floating bar with the orb as its one
tinted element, the bell, avatar and search circles, the Ask input, the two
big buttons); earlier iOS keeps the flat look. Siri and the Shortcuts app
get three App Intents, "Ask FamilyOS", "What's on today" and "Share with
FamilyOS", the last of which makes a notification automation one step. An
errand that is running or needs you is a Live Activity on the lock screen
and in the Dynamic Island, moved along when the app refreshes (no push
yet) and ended with its final word.

**The outbox (9 Oct 2026).** A share from the sheet or a tap in the app that
cannot reach the server is kept in a file under the app group with a
request id, and replayed in order the next time the app or the extension
runs with a connection. Only a transient failure is kept (no network, a
timeout, a 5xx); a refusal is dropped. The server ignores a share it has
by content hash and treats a decision made twice as made once, so a
replay is safe. The profile shows what is waiting, with Send now.

**The phone as the errand's browser (9 Oct 2026).** An errand can run in
the app's own web view instead of a rented browser. A guardian taps
"Approve and run on this phone" (or the asker taps "Run on this phone" on
an approved one); the app opens the site in WKWebView, holds a socket to
`/v1/errands/{id}/phone`, and answers the runbook's questions by id: goto,
url, text, screenshot, buttons, links, press, click_text, close, with the
same page scripts the server's Chromium driver runs. The page stays in
front of the person with the family's own sign-ins and address; a
needs_you is the same screen, touched, and "Mark it done" closes it. The
run ends with the socket; the commit marks say whether an interrupted
step may have landed. Runbook sites only (Urban Company today); the
generalist still needs a Chromium. Not yet exercised against the real site
from a phone.

## What ships first (v1, in this repo under `ios/`)

| Screen | API it uses | What it does |
|---|---|---|
| Sign in | `POST /v1/sign-in/request`, `POST /v1/sign-in/redeem`, `GET /v1/sign-in/google?native=true` | Server address, then Continue with Google (a system web session; the callback returns on `familyos://signed-in#token=…`) or email and the mailed link pasted in (or opened as `familyos://signin?link=…&server=…`). Token kept in the Keychain, shared with the extension. |
| Life | `GET /v1/inbox`, `/v1/plans`, `/v1/errands`, `/v1/money`, `/v1/brief` | The spaces with their counts, this week, what is being done, the plans, Home's notices and ledger. Each space opens as its own page (coming up, what arrived, spent here, charges again); Money opens the ledger. |
| Home | `GET /v1/brief`, `/v1/calendar/upcoming`, `/v1/artifacts` | The greeting, the people, today's timeline from the brief and the calendar, what FamilyOS noticed, what is coming up. |
| Today | `GET /v1/brief`, `/v1/calendar/upcoming` | A week to pick a day from, that day's timeline, and what waits on you with Accept and Dismiss. |
| Family | `GET /v1/household`, `/v1/inbox`, `/v1/brief`, `/v1/documents`, `/v1/todos` | Everyone in a row, one picked: their day, their school and health notices, their documents, their to-dos. |
| Memories | `GET /v1/artifacts`, `/artifacts/{id}/picture` | The latest photo as a highlight, the rest as a grid. Pictures sorted as documents stay out. |
| Search | `GET /v1/inbox`, `/v1/plans`, `/v1/documents` | People, notices, plans and documents by a few letters. |
| Inbox | `GET /v1/inbox` | Every notice the member can see, newest first, searchable. |
| Notice | `GET /v1/artifacts/{id}`, `/extraction`, `/picture`, `/original`, `POST …/handled`, `…/assign`, `/v1/obligations/{id}/decision` | What was read, the picture if it is one, the dates with Accept/Dismiss, Handled, hand to a member. |
| Ask | `POST /v1/chat` | A conversation against the record with citations, and what the model proposes as cards: Do runs the ordinary endpoint (assign, to-do, handled, decide, plan). Errands stay on the console. |
| Settings | `GET /v1/me`, `/v1/household`, `/v1/devices`, `POST /v1/signout` | Who is signed in, the server, the phone's own device token, sign out. |
| Share extension | `POST /v1/inbound/share` (raw body, `X-Tag`, `X-Note`, `X-Visibility`) | A photo, a PDF, a page or a text from any app. Tag a child, say private or shared, see the one-line answer. |

Nothing in the app does anything the API does not already do: same
tokens, same visibility, same audit. No new server routes for v1.

## Rules the app keeps

- The token lives in the Keychain under the app group, never in a file or
  a log. Sign out ends it on the server (`POST /v1/signout`) and forgets it.
- The share extension sends with a device token issued at sign-in
  (`POST /v1/devices`, label "iPhone app"), so it shows on the Devices card
  and can be revoked without signing the app out. If issuing one fails the
  extension uses the session token.
- Nothing is cached on the phone but the member, the household's members
  (for the tag picker) and the server address. Pictures and originals are
  fetched when looked at.
- No analytics, no third-party SDKs. URLSession, SwiftUI, Security.

## How it is built

- `ios/project.yml` is the source of truth; `xcodegen generate` writes
  `FamilyOS.xcodeproj` (ignored by git). `brew install xcodegen` once.
- Targets: `FamilyOS` (app), `FamilyOSShare` (share extension),
  `FamilyOSLive` (the errand Live Activity, a WidgetKit extension). The first
  two compile `ios/Kit/` directly; the third takes only the activity's
  attributes from it. No framework to embed.
- iOS 17, SwiftUI, Swift 5 language mode. Bundle ids `com.arunmozhi.familyos` and
  `com.arunmozhi.familyos.share`; app group `group.com.arunmozhi.familyos`. Set your
  team in Xcode's Signing tab (or `DEVELOPMENT_TEAM` in project.yml) to run on
  a phone.
- `ios/build.sh` generates the project and builds both targets for the
  simulator, ad-hoc signed with their entitlements (the Keychain refuses an
  app with no identity at all, even in the simulator). Pass
  `DEVELOPMENT_TEAM=XXXXXXXXXX` to it for a real team; none is needed to
  build. `xcodebuild -downloadPlatform iOS` once, for the simulator runtime.
- A debug build honours launch arguments so a script can drive the
  simulator without touching the screen: `-signinLink <link> -server <url>`
  signs in, `-tab inbox|ask|settings` picks the tab, `-notice <id>` opens a
  notice. None of it exists in a release build.
- Verified 8 Oct 2026 in the iOS 26.1 simulator against a scratch server
  and database: sign-in by link, Today, Inbox, a notice, Ask, Settings, the
  device token issued for the share sheet. The share extension itself needs
  a real share sheet; it sends the same request the shortcut does.

## Server address

The server is wherever the console is: on Tailscale today
(`http://<mac>.<tailnet>.ts.net:8000`), later a real host. The app asks
for it once on the sign-in screen and keeps it in the app group. Shares
from the extension need the phone to reach it, so Tailscale stays on until
there is a public host.

## The design (9 Oct 2026)

Calm, warm, native. Warm paper and ink, one coral accent for the one
primary action, one hue per space; system type mapped to text styles so
Dynamic Type works everywhere; serif only for the greeting and the big
questions. Content sits on opaque cards; Liquid Glass is for the
navigation layer alone (the tab bar, the header buttons, the orb, the
composer) and falls back to a flat capsule before iOS 26 and whenever
Reduce Transparency is on (`GlassShape` in Theme.swift). Increase
Contrast firms the hairlines; Reduce Motion removes the springs and the
skeleton shimmer (`Motion`). Tokens: `Theme` colours with semantic
aliases, `Spacing` on a 4-point grid, `Theme.font(size, weight, design)`.

Three directions for Today were built as named previews
(`FamilyOS/Previews/TodayDirections.swift`, sample content in
`PreviewData.swift`, clearly labelled preview data):

| Preview | Organising idea | Verdict |
|---|---|---|
| Morning Paper | one calm scroll: greeting and one sentence, next up, needs you, the day | chosen |
| Day Planner | the week strip first, the timeline dominant | its strip was taken into Morning Paper |
| Family Board | people with counts, then a grid of tiles | the crowded one; kept to see it |

Morning Paper won because the product's promise is "what matters now",
and a scroll says priority by position where a grid says everything at
once. The day strip from Day Planner sits inside the Today section so a
parent can still look at Thursday.

The pieces every screen is made of (`Components.swift`): `ScreenHeader`
with the profile as the way to Settings, `TaskRow`, `ListCard`,
`EmptyState`, `LoadingRows`, `ErrorState` with retry, `OfflineBanner`
(the outbox), `PermissionDenied`, `AgentStatusBadge` and
`ApprovalSummary`. The agent's states are one vocabulary (`AgentState`:
suggested, needs approval, approved-starting, working, needs you, done,
failed, stopped, cancelled) used on Today, in Ask, on an errand and by
the Live Activity. A suggestion in Ask is "Suggested" until tapped, then
"Done" with Undo where the server allows it (hand-over, to-do, handled;
not a decision or a plan). An errand shows exactly what is approved:
the action, every line of the spec, who it affects, what never happens,
and the fingerprint the approval is bound to. Nothing is shown as done
that the server has not said is done.

Onboarding is three pages and a way in, before sign-in, with no
permission asked; permissions are asked where used (today only the
photo picker in Ask, which the system handles itself).

Verified 9 Oct 2026 in the iOS 26.1 simulator against the dev server
with the household's real data: Today, Ask, Family, Life, Settings, an
errand awaiting approval, a finished errand with its step pictures, the
welcome, in light and dark; at the accessibility-medium text size; and on
the iPhone 16e. Screenshots in the session's scratchpad, not the repo.

Missing API contracts, said on the screens rather than hidden: inviting
a member (the console mails the link today), notification preferences
and push (reminders go by mail and Telegram), connected services beyond
the mail-in address and Telegram (Gmail is managed on the console),
linking Telegram from the phone.

## The phone's own hands: the driver (9 Oct 2026)

A school's parent app has no API and no web page; its notices live on a
screen. `ios/Driver/` is an XCUITest target (`FamilyOSDriver`) that turns
a phone into an errand driver for native apps, the way the app's web view
is one for sites. Started from a Mac, it holds a socket to the server and
answers the same questions a runbook asks a browser: `open` (an app by
bundle id, `XCUIApplication(bundleIdentifier:).activate()`), `text` (the
screen's accessibility labels, flattened), `screenshot`, `click_text`,
`buttons`, `links`, `press`, `swipe`, `goto` (a URL, in Safari), `url`,
`close`. The server side is
`familyos/execution/apps.py`: a short registry of apps (`myclassboard` →
the MCB Parent App; `iossettings` for a trial run) and one runbook,
`read_app`, which opens the app, taps one word to reach the notices,
reads the screen and hands the words in as the asker's private notice
through the same gate a shared screenshot uses.

What an app errand is: a *look* only (`kind: look`), proposed with
`service: myclassboard` and `spec.what` (the word to tap, e.g.
"Announcements"), approved on the spot like any look, bound to the phone
(`outcome.run_on = "phone"`), never queued on the server. No sealed
session: the sign-in lives in the app, on the phone, and stays there.
Every tap is a commit mark; nothing is typed; nothing is bought.

How to run it, from the Mac the phone is paired with (wired, unlocked,
Developer Mode on). The phone's UDID is the long id in
`xcrun xctrace list devices`, not devicectl's; the team is in
`project.yml` (`DEVELOPMENT_TEAM`, the personal team the profiles were
issued to; regenerating the project no longer clears it):

```
TEST_RUNNER_FAMILYOS_SOCKET='wss://<server>/v1/errands/<id>/phone?token=<session token>' \
TEST_RUNNER_FAMILYOS_MINUTES=5 \
xcodebuild test -project ios/FamilyOS.xcodeproj -scheme FamilyOSDriver \
  -destination 'id=<phone udid>' -allowProvisioningUpdates
```

(`TEST_RUNNER_<VAR>` reaches the test runner with the prefix stripped:
`man xcodebuild`, checked 9 Oct 2026.) The errand screen in the app shows
an app errand with a "Copy the driver's address" button instead of "Run on
this phone". The session token must be the asker's own: only the person
who proposed the errand may run it on their phone.

Verified 9 Oct 2026, three runs:
- the simulator against the scratch server: Settings opened, General
  tapped, 296 characters handed in, done in 55 s with three step pictures;
- Arunmozhi's iPhone 15 Pro over Tailscale against the dev server:
  Settings read, 459 characters, done;
- the same phone on the school's MyClassBoard app ("Aachi global school",
  bundle `com.mcb.aachiGlobal`): the Announcement page read, 2,153
  characters handed in as a private notice, done in 18 s. The tree carries
  each notice's full text, not the two lines the screen shows before "View
  More..": a career-fair invitation, the Term 2 fee reminder with its
  Friday, the club-hour note, the workbook reminder.

What the runs taught, and what changed for it:
- MyClassBoard ships one app per school under the school's own bundle id;
  `spec.bundle` names it (checked against a bundle-id shape). The apps on a
  paired phone are listed by `xcrun devicectl device info apps --device
  <udid> --include-all-apps`.
- The accessibility tree is empty for a moment after an app comes to the
  front (the first school-app run read nothing behind a full page): the
  driver now waits two seconds after `open`. When the tree still names
  nothing (an app that draws its own screen), the runbook hands in
  pictures of up to three screens, swiping between them, for the picture
  reader; it never keeps text of its own from a picture.
- An app that will not open is an error answer, not the end of the run
  (`continueAfterFailure`), so the row says "not on this phone".
- A phone that drops off mid-question used to leave the errand "running"
  for ever: the socket's task was cancelled and nothing wrote the row. The
  route now fails the waiting questions and gives the runbook fifteen
  seconds to end as needs_you before cancelling.

The limits are the platform's, not ours: a test runner needs a developer
build on a paired phone, so this suits a household that builds its own
phone, not the store. It is what Open Minis's iCTRL announcement
describes, done with Apple's own framework. Open: a run on a schedule,
and the session token off the socket's query string (uvicorn's access log
prints it).

## Next, in order

1. Universal links: serve `/.well-known/apple-app-site-association` and let
   the mailed sign-in link open the app directly. Needs a real host.
2. Family, Memories, chat with proposals, the finder and calendar upcoming
   (asked for 8 Oct 2026; Google sign-in and Life were built first).
3. Push: APNs token per member (`POST /v1/push-devices`), reminders sent
   as pushes beside mail and Telegram, a notification action "Handled".
4. (Done 8 Oct) App Intents. Next on them: a "Hand to" intent and the
   MyClassBoard automation rebuilt on "Share with FamilyOS".
5. The phone actions allow-list (plan item 2) lives in the app's Settings
   once there is one; Telegram remains the rail for a phone without the app.
6. Android, when there is a family that needs it: same Kit shape in Kotlin.
