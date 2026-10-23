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
the phone by Tailscale Serve at `https://arunmozhis-macbook-pro.tail333c17.ts.net`
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
