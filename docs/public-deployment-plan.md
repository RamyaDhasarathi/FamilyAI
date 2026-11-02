# Public deployment plan (draft, 15 Oct 2026)

Goal: move FamilyOS from one family on a Mac behind Tailscale to a named, public, secure host that other families can use,
in rings, without losing the rules that make it trustworthy (nothing is done without a person's yes, every fact has a source,
private stays private, payments off by default). Prices, quotas and legal points below are **not checked**; each needs a
quote or counsel before it is relied on.

## 0. Decisions only you can make

| Decision | Options | My lean |
|---|---|---|
| Who is ring 1 | friends and family only, a waitlist, open sign-up | friends and family, 5 to 10 households, India first |
| Region | India (data stays near users), UAE as well later | one region in India first; say so in the policy |
| Host | a mainstream cloud region in India, or an Indian provider, or a single rented server | one VM plus managed Postgres and an S3-compatible bucket; compare 3 quotes |
| Domain | a name for the product, a sub-domain for the app | buy it first: sign-in links, Google and Apple all depend on it |
| Models | cloud model for everyone, or your own model for yours | cloud for ring 1 with a per-household monthly cap; your own model stays optional |
| Legal entity | personal now, a company before ring 2 | a company before any stranger's data (counsel) |


## Now: a closed team-test instance (decided 15 Oct 2026)

The immediate need is smaller than a public release: let a few team members connect their own assistants (Grok Bot and others)
to FamilyOS, which needs an address on the internet. The family's real household stays private.

- **A second instance, not the family's.** Its own database (`familyos_team`), its own port (8090), a test household with the
  team as adult members and invented notices. Nothing of the family's is reachable from it. The family's instance stays on 8088
  behind Tailscale Serve, tailnet only.
- **Exposure: Tailscale Funnel on port 8443 to port 8090.** Funnel can only use 443, 8443 and 10000, exposes a whole port and
  cannot share a port with Serve (Tailscale's Funnel docs), so 443 stays private for the phone and 8443 is the public one. It
  needs the `funnel` node attribute in the tailnet policy, which only an admin of the tailnet can add. It is one command to
  start and one to stop (`tailscale funnel --https=8443 off`).
- **Guard rails before it is switched on:** a per-IP rate limit and a lower limit on failed sign-ins and failed `/mcp`
  authentications; a daily cap on model calls per household so a connected assistant cannot spend the model budget; the
  separate database; and the instance taken down when the test ends.
- **Joining:** the owner creates the members and hands each a one-time sign-in link; each person makes their own assistant key on
  My day, My assistant, and adds `https://<name>.ts.net:8443/mcp` as a custom MCP connector.
- **What it proves:** that a real hosted assistant can call the tools, that proposals land as cards and confirm, that sharing
  needs the permission, and what an assistant does with untrusted text in a result. What it does not prove: scale, backups,
  Google or Apple production access, or any legal readiness.

## 1. What goes live, and what stays off

On: notices in (mail, forwarding, Telegram, share sheet), reading, Needs you, reminders, Ask, routines, hand-offs, the web console,
the phone app (TestFlight), the emergency card, product search (per household), connected assistants (per person, off until set up).
Off at launch, each behind a household switch: errands in a server browser (Steel), payments, the Health option, location,
kid keys until the household turns them on. Reason: each of these either runs code against the open web, holds money, or holds
the most sensitive data, and the sandbox acceptance suite (docs/todo.md) is not written.

## 2. The target shape (small, boring)

- One app VM running the existing image (`Dockerfile`), behind Caddy (automatic TLS) or the host's load balancer.
- Postgres: managed, with point-in-time recovery and encryption at rest. pgvector is not needed in production today.
- Object storage: an S3-compatible bucket with versioning and a lifecycle for deleted originals (`FAMILYOS_S3_*`).
- Mail: a transactional SMTP provider with SPF, DKIM and DMARC set (sign-in links depend on it).
- Secrets: in the host's secret store, not in `.env` on disk. The master key is kept in two places; losing it loses every original
  (that is the design, so it needs a custody plan: who holds it, how it is restored).
- One process runs its own sweeps (jobs, reminders, routines, morning, hand-offs, calendar, mail). Before a second instance, check
  that the job claims are safe under two workers (they are database rows; verify with a test, do not assume).

## 3. Work, in order

**A. The platform (days)**
1. A production compose file or manifest: app, Caddy, healthchecks, restart policy, resource limits, non-root, read-only filesystem
   where possible; build and push the image from CI.
2. Config from the secret store; a startup check that refuses to run in production with a default key or a dev database.
3. Backups and a restore drill: database PITR, bucket versioning, a script that restores to a scratch environment and runs the
   key-destruction erasure check.
4. Observability: `/healthz` uptime check, structured logs shipped off the box, an error tracker, alerts on job queue depth,
   failed jobs, model spend and disk.

**B. Edge and abuse (days)**
5. Rate limits in front for sign-in, uploads, `/mcp`, `/e/<token>` (emergency links), `/kid/` and the Telegram webhook;
   request size caps; HSTS and security headers; a WAF or the provider's equivalent.
6. Per-household caps: uploads a day, model spend a month, connected-assistant calls (60 a minute per key exists).
7. A household-separation sweep: every route, including the new ones (decisions, activity, memory, finance, emergency, kid, mcp),
   called with another household's ids must answer 404 or 403. Generate it from the route table so a new route cannot skip it.

**C. External accounts (long lead, start now)**
8. Google: move the OAuth app to production. Gmail and Calendar read scopes are sensitive or restricted, which brings Google's
   verification and possibly a security assessment. Read Google's current requirements before promising dates.
9. Apple: the paid developer programme, TestFlight, push notifications, universal links for the sign-in mail, the privacy policy
   URL and nutrition label that match the privacy manifest.
10. Meta: business verification for WhatsApp (already waiting).
11. Telegram: the production bot and webhook.
12. Crossmint, Stripe Link, Shop pay: stay off. Product search (read-only) can be on.

**D. Trust and law (counsel)**
13. Privacy policy, terms, a data processing statement, a breach process, a support address, and an in-app way to export and
    erase (both exist). Children's data and verifiable parental consent under India's data protection law; the grievance contact.
    These are for counsel to confirm; I have not verified what the law requires.
14. An outside security review before ring 2. The sandbox suite before errands are turned on for anyone.

**E. Scale gate (before ring 2)**
15. A synthetic 1,000-household load script: sign-in, upload, extraction queue, Ask, reminder sweep, morning sweep. Watch queue
    latency, database connections, memory (the small embedding model), model spend. Fix what it finds.

## 4. Rings

| Ring | Who | Gate to enter |
|---|---|---|
| 0 | your household, on the public host | A, B, backups restored once, TLS, mail delivering |
| 1 | 5 to 10 households you know | C started, D drafted, household-separation sweep green, a week of ring 0 without a surprise |
| 2 | 50 to 100 by invitation | E, outside security review, Google verified or a plan, company in place |
| 3 | open | sandbox suite if errands are offered, support in place, costs known |

Exit from any ring: a household can export and erase itself today, and a switch pauses new sign-ups.

## 5. What I can build next in this repo

Production compose with Caddy and health checks; the startup safety check; a backup and restore-drill script; the household
separation sweep generated from the route table; rate-limit configuration; a load script; a `docs/runbook.md` (deploy, rollback,
restore, rotate the master key, revoke every token, pause sign-ups). Not buildable here: the accounts, the quotes, the legal text.
