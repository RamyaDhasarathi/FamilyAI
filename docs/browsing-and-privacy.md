# How FamilyOS touches the web, and what stays private

A short note, written 10 Oct 2026 from the code. Four ways FamilyOS reaches
a website, two ways a phone hands a notice in, and the encryption under all
of it. Paths are relative to the repository root.

## 1. Reading the public web with no credential (class 1)

**What.** A fee schedule, a public booking page, a URL someone shared. Read
once, on request, never signed in.

**How.** `familyos/execution/disposable.py` fetches the page with plain HTTP
and receives no credential of any kind: no cookie jar, no token, no
household key. It cannot authenticate even if a page tries to talk it into
it. For JavaScript pages that return an empty shell to a plain fetch
(fares, availability), `research.py` asks a research provider (Parallel,
off unless configured) for ranked public pages and excerpts; the query is
built from a plan option's own words and scrubbed of every member's name
before it leaves. The reader announces itself in its user agent
(`FamilyOS/0.2 (+household agent; one page, on request; never signed in)`).

**What comes back.** Evidence, never fact: the URL it landed on, the page
hashed, the time. It is shown with its source and never becomes a claim or
an obligation on its own. A URL shared from a phone that turns out to need
a login is kept as the URL alone and said plainly.

## 2. Acting on a site the family is signed in to (class 2)

**What.** An errand: a booking, a purchase or a look on Urban Company or
another listed site, run only after a guardian approves the exact request
(its fingerprint, `errands.py`).

**How the sign-in gets in.** A member opens a *sitting*
(`execution/sessions.py`): a watched browser on the sign-in page, where the
person signs in themselves. FamilyOS never sees the password and never
re-authenticates on its own; when a session lapses the person signs in
again. At the end of the sitting only that site's origins are read out of
the browser and sealed under the household key as a *sealed session*; the
seal binds the household and the service into the ciphertext's AAD, so a
session for one will not open for another.

**How a run uses it.** The code that decides what to do (a runbook, the
generalist, a person) holds a *capability*: a name, a service and the
origins it may reach, and no cookie or token (`execution/capability.py`).
Only the *driver*, the code that steers the browser, is lent the session,
and only for the length of one task (`sessions.lease`). The browser for
that task is thrown away afterwards. Nothing re-authenticates by itself.

**Three browsers, one contract** (`open_at`, `open_with`, `context`,
`release`), so runbooks and sittings do not know which one they got:

| Browser | Where it runs | When | What it holds |
|---|---|---|---|
| **Steel** (`execution/steel.py`) | A rented container, Apache-2.0 and self-hostable; `FAMILYOS_STEEL_URL` | A hosted deployment with no phone open | A session for one task, released after; a live DevTools view the member can watch and take over |
| **Chromium** (`execution/local.py`) | Playwright's Chromium on the machine FamilyOS runs on; `FAMILYOS_BROWSER=local` or `auto` | Today, on the family's Mac: their own address, no bill per run, nothing leaves the house | One browser process per session with its own profile, discarded at release; a sitting opens a visible window |
| **WebKit** (`execution/phone.py`, `ios/FamilyOS/Views/ErrandView.swift`) | The app's WKWebView on the phone, while the person holds "Run on this phone" open | Attended runs with the family's own sign-ins and address | The phone's own cookies; nothing is sealed or uploaded; a needs_you is the same screen, touched |

The phone has a fourth pair of hands for apps with no web page at all: an
XCUITest runner on a paired phone reads the school's app through its
accessibility tree and hands the words in as a private notice
(`execution/apps.py`, `ios/Driver/`).

**The live view.** When a run needs a person, the console's websocket is
relayed by the server to the browser's own debugging socket
(`execution/livebridge.py`): a frame is a string in and the same string
out, nothing read, kept or logged on the way.

**The agent says what it is.** Every one of these browsers appends one
token to its real user agent: `FamilyOS/0.2 (+household agent; each run
approved by a guardian; never pays)` (`execution/agent.py`). It rides on
the browser's own string, never replaces it, so the string tells one story
and a site can tell a household's agent from a person without guessing
from the address. Signed requests (Web Bot Auth, RFC 9421) need a stable
HTTPS origin that serves the agent's key directory at
`/.well-known/http-message-signatures-directory`, since a verifier fetches
the key from the origin named in the request's `Signature-Agent` header.
That origin need not be the FamilyOS server: a domain FamilyOS owns in
front of a static host, or the Mac's ts.net name through Tailscale Funnel,
does it. Signing is feasible for the credential-free reader and the
Playwright-driven browsers through a request hook; the phone's web view
cannot sign every sub-request and stays on the token alone.

**Where a model reads a page.** A runbook never lets a model read the
page; it may answer one closed question over a short list the code
extracted (`execution/choose.py`). The generalist (`execution/generalist.py`,
the fallback for a site with no runbook) is the exception: the model sees a
screenshot or an accessibility tree of the page, through Anthropic's
browser toolset, inside a URL policy of the site's own hosts and a
confirmation gate that refuses any click that would pay, order or confirm.
It is skipped when the household runs local models.

## 3. The share sheet and Shortcuts: how a phone hands a notice in

**The purpose.** Most of a family's notices live where no API reaches: a
WhatsApp group, a school app, a screenshot, a PDF someone forwarded. The
share sheet is the one door every app on the phone already has.

**The share extension** (`ios/ShareExtension/`). From any app's share
sheet, "Send to FamilyOS" takes the photo, PDF, page or text, lets the
person tag a child and choose private or shared, and posts the raw bytes
to `POST /v1/inbound/share` with the app's device token. Offline, it waits
in an outbox and sends later.

**The Shortcut.** For a phone without the app, a Shortcut does the same
request with a device token pasted once (README). On iOS 27 the Shortcuts
*Notification* trigger can run it when a named app posts an alert, so a
school app's notice shares itself; Shortcut Input carries the text.

**App Intents** (`ios/FamilyOS/Intents.swift`). "Ask FamilyOS", "What's on
today" and "Share with FamilyOS" as Siri phrases and Shortcuts actions.

**What the server does with it** (`intake/gateway.receive_share`). The
phone says nothing about where a share came from, so the rail is the
plainest: the bytes, private to the member who shared them unless they
chose shared; deduplicated by hash; a child tag is accepted only when a
guardian has recorded consent for that child; a bare URL is read once as a
public page (class 1). Everything is sealed before it is stored and read by
the same reader as mail.

**The device token.** Issued per phone or shortcut, shown once, never
expires on its own, listed on the Household card and revocable there
without signing the app out. A token never used is replaced by the next
one under its label.

## 4. Encryption, and what it covers

**Keys.** Envelope encryption per household (`crypto.py`): a master key in
the environment wraps each household's 256-bit key, which wraps a key per
blob. Originals are sealed with AES-GCM before they reach the object store
(`blobstore.py`: S3-compatible in production, a local directory in
development), under opaque ids, never filenames or hashes, so the store
learns nothing about the content.

**Sealed under the household key:** every original (mail bodies, PDFs,
images, harvested page text); the Gmail refresh token; browser session
state from a sitting; biller consumer numbers are not stored at all, only
an HMAC under the household key, enough to match a bill. Session tokens,
sign-in links, device tokens and founding tickets are stored hashed.

**Not sealed, by design:** the projection. Claims, obligations, who a
notice is about, the sender and subject, members and households are plain
rows in Postgres, because the brief, the inbox and Money are queries over
them and could not sort or group over ciphertext. They rely on database
controls: disk encryption, one role per deployment, no shared credentials,
and an append-only audit. A deployment that needs the projection covered
can seal the sensitive claim columns and decrypt per request, at the cost
of SQL ordering; that is recorded as a decision, not assumed.

**Erasure.** Destroying a household's wrapped key is the first step of
erasure: from that moment every copy of its originals, in backups or a
lagging replica, and every sealed session, is unreadable. Withdrawing a
child's consent erases what names them in the same transaction.

**Projection, not twin.** Every fact on a screen is derived from a notice
and points back to it. There is no separate memory to leak, drift or
outlive an erasure.

## 5. The same things, seen as privacy

| Rail | What leaves the family | What a model sees | What is kept |
|---|---|---|---|
| Public read (class 1) | A plan option's own words, scrubbed of names; a URL | Nothing from the page as fact | The page hashed, as evidence |
| Runbook on a signed-in site | The leased session, into one throwaway browser, for one task | At most one closed question over a short list | Steps with pictures on the errand; the sealed session |
| Generalist | Page views of the site's own hosts, to Anthropic | The page, behind a gate that never pays | The same step log; skipped when local models are on |
| Steel | The leased session, into a rented container; released after | As above | Nothing: the container holds nothing of ours between sessions |
| Local Chromium | Nothing leaves the house | As above | A profile per session, discarded |
| Phone web view | Nothing: the page renders on the phone | Only the questions a runbook asks | The phone's own cookies, on the phone |
| Share sheet and Shortcut | The bytes, over the household's own server address | The reader (rules, local or opt-in remote model) | Sealed original; private to the sharer unless shared |
| Phone app driver | The screen's words, as a private notice | The reader | Sealed original |

Three walls hold across all of it: FamilyOS never holds a card, a UPI PIN
or a bank login, and never pays; a person approves every date, task and
errand; every read, write and run is in the audit. See
[architecture.md](architecture.md) for the whole picture.
