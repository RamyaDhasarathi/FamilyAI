# Deploying FamilyOS

How the server and the phone app go out, and what was checked before they
could. Written 9 Oct 2026 at the end of the readiness pass.

## The server

**What it is.** One Python process (FastAPI under uvicorn) that serves the
API, the console at `/app/` (and the old one at `/classic/`), and runs its
own sweeps: jobs, reminders, Gmail polling, calendar sync, the digest. It
needs Postgres and, for originals, either a local blob directory or S3.

**Build.** `docker build -t familyos .` from the repo root. The image is
Python 3.12 with Tesseract (English) and every runtime dependency from
`pyproject.toml`. It starts as `nobody` on port 8000 and answers
`/healthz`.

**Configure.** Every setting is an environment variable with the
`FAMILYOS_` prefix. `.env.example` lists all 95 with their defaults and a
line on each. The ones a deployment must set:

| Setting | What |
|---|---|
| `FAMILYOS_DATABASE_URL` | Postgres. Migrations run at startup, in order, once each. |
| `FAMILYOS_CONSOLE_URL` | The public address of `/app/`. Sign-in links and Google's callback are built from it. |
| `FAMILYOS_MASTER_KEY` | Wraps every household's key. Lose it and every original is unreadable, which is the design. |
| `FAMILYOS_BLOB_DIR` or the `FAMILYOS_S3_*` settings | Where sealed originals live. |
| `FAMILYOS_SMTP_*` | Sign-in links, reminders, the digest and replies go out by mail. Without SMTP nobody can sign in by link. |
| `FAMILYOS_GOOGLE_CLIENT_ID` / `_SECRET` | Google sign-in, Gmail and Calendar. Register two redirect URIs on the console's host: `/v1/sign-in/google/callback` and `/v1/google/callback`. |
| `FAMILYOS_TELEGRAM_BOT_TOKEN` / `_USERNAME` | The bot. Point its webhook at `/v1/inbound/telegram`. |
| `FAMILYOS_OPENAI_API_KEY` or `FAMILYOS_ANTHROPIC_API_KEY`, or `FAMILYOS_LOCAL_MODEL*` | The reader, Ask, the drafted reply. |

**Where it runs today.** On the Mac, bound to 127.0.0.1:8088, published to
the phone by Tailscale Serve at `https://your-host.your-tailnet.ts.net`
(tailnet only, TLS by Tailscale). That is a sound way to run it for one
family. A second family needs a host with a name: the same image, Postgres
beside it, TLS in front (Caddy or the host's own), `CONSOLE_URL` set to that
name, and the Google and Telegram callbacks moved to it.

**Checked 9 Oct 2026.** 684 tests pass; ruff is clean; the image builds and
imports every module; a container against a scratch database answers
`/healthz`, `/app/` and `/v1/me`; every console page loads with zero
script errors and zero 5xx (Home, Today, Family, Life, Memories, Ask,
Inbox, Money, Plans, Errands, Household, Quarantine, Revisions, Collect,
Audit, the four spaces, a notice, the classic console).

**Not done, by choice.** No CORS (the console is same-origin and the token
is a bearer header). No rate limiting in the app (put it in front). Backups
are the database's and the blob store's own.

## The phone app

**What it is.** `ios/`, generated from `project.yml` with XcodeGen: the app,
the share extension, the Live Activity extension. iOS 17 and up; glass on
iOS 26.

**Build and run.** `ios/build.sh` builds for the simulator with no team.
`ios/release.sh` archives and exports for TestFlight or the store with
`DEVELOPMENT_TEAM=XXXXXXXXXX`; it needs the paid Apple Developer Program
(a personal team can only install on its own phones from Xcode, for seven
days at a time). `ExportOptions.plist` says `app-store-connect`; change it
to `ad-hoc` for a few named phones.

**Checked 9 Oct 2026.** Release builds for the simulator and for the
device SDK compile clean. The bundle carries a privacy manifest for each
of the three targets (no tracking; email, name, photos and user content
collected for app functionality, linked to the user; UserDefaults declared
with reason CA92.1). App Transport Security allows HTTPS only, plus plain
http to local addresses for the simulator. The app icon, the launch
screen, Dynamic Type, VoiceOver labels and the App Intents metadata are in
the bundle. Version 0.1.0 (1).

**Before the store, still.** A paid team (TestFlight, push). Universal
links for the mailed sign-in link (needs the real host). A privacy policy
URL and the App Store nutrition label matching the manifest. Screenshots.
The "Could not archive SSU artifacts" line from the intents trainer in
unsigned builds is expected; it goes away on a signed archive.

## Pinned dependencies

`requirements.lock` holds the exact version of every Python package the suite passed on (20 Oct 2026, Python 3.14.4), pins only, no hashes. Install with
`pip install -c requirements.lock .` so a deployment does not drift to whatever is newest. The Dockerfile still installs from `pyproject.toml` alone (it builds on
Python 3.12, and a pin file made on 3.14 has not been tried there); switch it to `-c requirements.lock` once an image has been built and tested with it.
`web_pay/package-lock.json` pins the payment page's JavaScript; its built `public/bundle.js` is committed.

## The order for a new deployment

1. Postgres up; blob dir or bucket made; the env file written from
   `.env.example`; the master key generated and kept somewhere safe.
2. Start the image. Watch the log for the migrations and "Application
   startup complete". Hit `/healthz`.
3. Open `/app/`, start the household with the founding mail, sign in.
4. Google: register the two callbacks on the real host; connect Gmail and
   Calendar from the Household card. Telegram: set the webhook; link from
   Settings.
5. Phone: `release.sh` with the team; TestFlight to each adult; the server
   address on first launch is the real host.


## One worker (enforced at boot), and more than one process

Run one app worker under one server. The server refuses to start when `WEB_CONCURRENCY` is above 1 (`familyos/main.py`, `check_single_worker`).
That stays true with `FAMILYOS_MULTI_WORKER=true`: workers started by one uvicorn share an environment and take connections from one socket, so
they cannot be routed to the process that holds a phone socket, and cannot be told apart for "the WhatsApp worker".

What the process holds, and where each piece stands (20 Oct 2026):

| State | One process (default) | `FAMILYOS_MULTI_WORKER=true` |
|---|---|---|
| WebSocket tickets (live view, taken-over errand, phone socket) | Postgres (`socket_tickets`) | the same: a ticket issued by one process is redeemed by any |
| Unlocked family key | this process's memory; a restart locks every private household | memory in each process, as with one: an unlock reaches only the process that took it, and a lock only that process (use sticky routing). Setting `FAMILYOS_FAMILY_KEY_SHARE_UNLOCK=true` also writes `family_key_unlocks`: the key **wrapped under the master key**, gone at expiry, on lock and with the household; another process asks the table when its copy is older than 5 s, so a lock on any process is a lock on all within seconds. **That copy means a database snapshot plus the master key can open a household whose key the family holds, for as long as the unlock lasts (hours); leave it off unless you accept that.** |
| Failed-unlock counter | memory | `family_key_attempts` (rows, counted over the last hour, cleared by a success) |
| Taught lessons | memory | `taught_lessons` rows: the 3-lesson limit counts every process; a lesson held by another process answers **409 `held_by_another_worker`**. The lesson's browser or phone socket cannot move: **pinned** |
| Running assistant tasks | memory plus the row | the row names its process and beats every 20 s (`owner`, `heartbeat_at`); any process fails a task silent for 90 s, and a late answer cannot revive it |
| WhatsApp reader | one browser at a time in this process | a Postgres advisory lock per member on the profile; only the process with `FAMILYOS_WHATSAPP_WORKER=true` opens profiles, the others answer where to ask and decline the sweep job. The profile directories are on that machine's disk: **pinned** |
| Phone-driver sockets (errands, lessons, skills) | `execution.phone._phones` | **pinned**: the phone is connected to one process |

What stays pinned, and what the operator does about it. A phone socket, a lesson's browser and the WhatsApp profiles live in one process. Requests that
need them must reach that process:
- the phone app's socket and its errand requests: route by errand id (`/v1/errands/{id}/...`);
- a taught lesson: route by lesson id (`/v1/me/teach/{id}...`, `/v1/teach/{id}/phone`);
- WhatsApp reading (`/v1/household/whatsapp...`): route to the process with `FAMILYOS_WHATSAPP_WORKER=true`, on the machine whose disk holds the profiles.
A request that lands elsewhere is refused with a plain answer, never run on a guess.

More than one process, then, means separate single-worker processes behind a proxy that does that routing, each with `FAMILYOS_MULTI_WORKER=true`, exactly one
of them with `FAMILYOS_WHATSAPP_WORKER=true` if WhatsApp reading is on. The server cannot check the routing; it logs at boot what this process holds. Without
the setting a second process silently keeps its own memory (an unlock on one looks locked on the other), so set it on all of them or run one.

Shared does not mean free. With the setting on, the unlocked key sits in the database, wrapped under the master key, for the unlock window (default 8 hours):
a backup taken in that window, together with the master key, opens that household. With one process nothing is written, which is why it is the default.
Jobs are safe across processes (claimed in Postgres); so are the recurring sweeps.


## Hosting for the family key (planned)

A household that holds its key as Shamir shares (`docs/family-key.md`) needs the unlocked key to live in exactly one place, or in a store that is
useless on its own. With one process that is its memory. With `FAMILYOS_MULTI_WORKER=true` it is also a row wrapped under the master key (see above);
attested key release (`docs/family-key.md`, "TEE hosting") is what would remove the master-key-wrapped copy.


## Passkeys and the address they are bound to

A passkey is bound to the web address it was made at, so one made at `localhost` does not work at the Tailscale address, and the reverse. `FAMILYOS_WEBAUTHN_ORIGINS` lists the exact origins allowed to register and use them (default: localhost on 8088 and 8000). For a deployment families use, set it to the one real https address and keep that address stable, because changing the host orphans every passkey made at the old one (members then sign in with the emailed link or Google and add a new one). The `webauthn` library does the verification (`familyos/passkeys.py`); challenges are one-use and last five minutes.
