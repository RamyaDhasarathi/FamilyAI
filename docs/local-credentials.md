# Testing with your own accounts, before any approval

Neither Google CASA nor a verified WhatsApp business account blocks local
testing. Both platforms have a sanctioned developer mode that works today, with
your own mailbox and your own phone. This is how to use them, and what each one
will and will not let you do.

Real values go in `.env`, which is gitignored. `.env.example` holds placeholders
only — a key leaked out of it once, so keep it that way.

## 1. Mail, in two minutes, with no accounts at all

Reminders, replies and sign-in links all go out over SMTP. For local work you
want to *see* them rather than deliver them:

```sh
pip install aiosmtpd
python -u -m aiosmtpd -n -l localhost:1025 -c aiosmtpd.handlers.Debugging stdout
```

Both the `-u` and the `-c aiosmtpd.handlers.Debugging stdout` matter: without
the handler it accepts mail and prints nothing, and without `-u` Python buffers
the output so nothing appears until it exits. Messages arrive quoted-printable,
so a link reads `link=3Dlnk_...` in the raw capture — that is `=` encoded, and
any mail client decodes it.

```ini
FAMILYOS_SMTP_HOST=localhost
FAMILYOS_SMTP_PORT=1025
FAMILYOS_SMTP_STARTTLS=false
FAMILYOS_SMTP_FROM=familyos@localhost
```

Every sign-in link, reminder and school reply now appears in that terminal.
Nothing leaves the machine. This alone is enough to exercise magic-link
sign-in, invitations, grants, the brief and the action rail end to end.

## 2. Gmail — Google Cloud "Testing" mode

**CASA is for production. Testing mode needs no review.**

1. Google Cloud console → new project → **APIs & Services → OAuth consent
   screen** → External → keep the publishing status at **Testing**.
2. Add your own Gmail address under **Test users**. Up to 100.
3. **Credentials → Create credentials → OAuth client ID → Web application.**
   Authorised redirect URI: `http://localhost:8000/v1/google/callback`.
4. Put the client id and secret in `.env`:

```ini
FAMILYOS_GOOGLE_CLIENT_ID=...apps.googleusercontent.com
FAMILYOS_GOOGLE_CLIENT_SECRET=...
FAMILYOS_GOOGLE_REDIRECT_URI=http://localhost:8000/v1/google/callback
```

You will see an "unverified app" warning on the consent screen. That is correct
for Testing mode — continue past it with a test-user account.

**What Testing mode costs you.** Refresh tokens expire after **7 days**, so a
connected mailbox stops polling once a week and has to be reconnected. That is
the mode behaving as documented, not a bug in the poller — `mailbox.poll()`
marks the account `refused` and the console shows it as needing reconnection.

Scope stays `gmail.readonly` throughout. CASA is what lets you leave Testing
mode and serve families who are not on your test-user list; it changes nothing
about how the code works.

## 3. WhatsApp — the Cloud API test number

**No business verification, no Meta review.**

1. developers.facebook.com → create an app → add **WhatsApp**.
2. The app gives you a **test phone number** and a temporary access token
   (24 hours; generate a System User token for something longer-lived).
3. Under **To**, add your own phone number as a recipient. Up to 5.
4. Point the webhook at your machine. The webhook must be reachable from
   Meta, so tunnel it:

```sh
cloudflared tunnel --url http://localhost:8000      # or ngrok http 8000
```

   Callback URL: `https://<tunnel>/v1/inbound/whatsapp`
   Verify token: whatever you put in `FAMILYOS_WHATSAPP_VERIFY_TOKEN`.
   Subscribe to the **messages** field.

```ini
FAMILYOS_WHATSAPP_APP_SECRET=...
FAMILYOS_WHATSAPP_VERIFY_TOKEN=pick-any-string
FAMILYOS_WHATSAPP_ACCESS_TOKEN=...
FAMILYOS_WHATSAPP_PHONE_NUMBER_ID=...
FAMILYOS_WHATSAPP_BUSINESS_NUMBER=+15550000000
```

**What the test number costs you.** Only the five numbers you listed can reach
it, and the 24-hour customer-service window still applies to replies. Signature
verification works exactly as it will in production, so
`whatsapp.verify_signature` is genuinely exercised.

**It still cannot read a group.** That is the Cloud API's shape, not a limit of
the test number, and a verified business account does not change it.

## 4. Forwarding — no vendor needed

The highest-yield channel needs nothing from anybody. Each household has an
inbound address, and the webhook secret is yours to set:

```ini
FAMILYOS_INBOUND_DOMAIN=in.familyos.local
FAMILYOS_INBOUND_WEBHOOK_SECRET=pick-any-string
```

Post a raw message straight at the API to simulate a forward:

```sh
curl -X POST localhost:8000/v1/inbound/email \
  -H "X-Inbound-Secret: $FAMILYOS_INBOUND_WEBHOOK_SECRET" \
  -H 'Content-Type: message/rfc822' --data-binary @notice.eml
```

To receive real forwards, point an inbound route at that endpoint
(Postmark, SES or Cloudflare Email Workers all do this) and set
`FAMILYOS_INBOUND_AUTHSERV_ID` to the authserv-id your provider stamps.
Leave it unset and every forward waits in quarantine — which is the safe
default, and worth seeing at least once.

## 5. Extraction, without sending anything anywhere

```ini
FAMILYOS_EXTRACTOR=rules
```

Notices are read by the offline rule-based extractor and their text never
leaves the machine. Swap to a model only when you want to measure quality —
and the boot log will say, in one line, that the full text of every accepted
notice is going to that provider.

## What you can exercise today, with none of the above approved

- Magic-link sign-in and invitations (local SMTP)
- Grants: a carer seeing one child's pickup and nothing else
- Forwarding, upload, paste
- Extraction, grounding, the brief, reminders, the action rail
- Export and erasure

What genuinely waits on approval: serving families who are not on your
test-user list (CASA), and messaging numbers you have not listed (WhatsApp
business verification). Neither is on the critical path for proving the
product works.
