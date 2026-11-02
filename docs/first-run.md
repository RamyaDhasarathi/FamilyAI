# First run: sign in, set up the family, in a few calm screens

Built 23 Oct 2026 from a comparison with another family assistant's first run (see the Watch list in todo.md). The aim: a new parent
signs in with Google, answers one question at a time, and lands on a first brief, on the phone and on the web, with no console step.

## The contract (server, already in main)

- `POST /v1/households` founds a home from a Google or mailed founding ticket (`#found=` and `email=` in the redirect fragment).
- `GET /v1/household/onboarding` returns `steps` (signed_in, named, family, channel, mail, private), `show`, and `wizard`.
  `wizard` is true for a guardian whose home has never answered the name step. Posting `named` ends it for good.
- `POST /v1/household/onboarding/{named|skip_channel|skip_mail|skip_private|dismissed}` records a choice. Guardian only.
- `PATCH /v1/household {name}` renames the home. Guardian only.
- `POST /v1/household/members` adds a child (name, `date_of_birth`) or an adult (name, email, role). Children get no sign-in.
- `POST /v1/members/{id}/invite` mails an adult their sign-in link.
- `POST /v1/telegram/link` gives the deep link (503 where no bot is set up: the step is hidden).
- `POST /v1/google/mailboxes/authorize` gives the Google URL for mail and calendar, read only (503 where Google is not set up).
  `?native=true` is the phone's way: the callback connects nothing, it parks Google's one-use code and returns to `familyos://mailbox?finish=<token>`;
  the app then calls `POST /v1/google/mailboxes/finish {finish}` as the signed-in member. A consent forwarded to someone else's phone is refused there.
  The browser path keeps its cookie binding unchanged.

## The screens (same order on the phone and the web)

1. **Your name and the home's name.** "What should I call you?" (first name) and "What is your family called?" with a suggested
   "The <name> family". Answering posts `named` and renames the home.
2. **Who is in your family.** Children: first name and age (stored as a mid-year date of birth, so the age is right for the year).
   A partner or another adult: name and email, invited by mail, no mailbox needed on their side. A "Why I ask" fold-out says it is
   used to tell whose school mail is whose, and that nothing else is kept. Skip is allowed.
3. **Message it from your phone.** A mock of the morning brief and a reply. Connect opens the Telegram deep link; the bot says hello
   and the step ticks. Skip posts `skip_channel`.
4. **Your mail and calendar.** A mock of what it does, then the permission list shown before Google shows it: reading mail and
   calendar is asked, sending is not asked at all. Connect opens Google. Skip posts `skip_mail`.
5. **Done.** Lands on Today (or Home on the web) with the checklist card still showing what is left (privacy, more family).

Rules kept on every screen: one question; a "why" fold-out on the personal ones; Skip on everything but the name; back and a
progress bar; nothing asked that the feature does not use.

## Sign-in screen

One screen: the mark, a line, Continue with Google, and "email me a link" below it. The server address, which only matters while the
server is on a private network, sits under "Advanced". Sign in with Apple is not offered: it needs the paid Apple team.
A Google address nobody uses opens Start a household with the verified address already filled in, then the screens above.

## Not here

Sign in with Apple, iMessage as a channel, WhatsApp as a channel to message you on (the WhatsApp reader is separate and is linked
from Settings), and collecting anything about children beyond a first name and a year of birth.

## Built

23 Oct 2026: server (rename, steps, wizard flag, native mailbox consent), web (`familyos/web/firstrun.js`, tried in a browser on a throwaway
database), iPhone (`FirstRunView`, `SignInView`, `Kit/FirstRun.swift`; built, and the first screen seen in the simulator after sign-in; the
rest of the screens, Telegram and Google on a phone are not yet exercised by hand).
