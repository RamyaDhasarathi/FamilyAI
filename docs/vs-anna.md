# How FamilyOS differs from Anna (hianna.ai)

Written 23 Oct 2026. Two kinds of claim are kept apart.

- **Anna** is described from the company's own pages, read on 23 Oct 2026: hianna.ai (home, `/faq`, `/pricing`, `/security`, `/privacy`, `/terms`, `/about`,
  `/what-anna-does`, `/skills`, `/founding-families`, `/support`) and the sign-in screen at app.hianna.ai. Privacy policy and terms are dated 29 Sep 2026.
  Anything the pages do not say is marked "not stated", which is not the same as "does not". Nothing here comes from using the product past its sign-in,
  and we have no way to check how it behaves.
- **FamilyOS** is described from this repository, with the file that backs each line. Where a feature is built but has not been proved on a real
  household, it says so.

## The short version

Anna and FamilyOS do the same job: read what reaches a family (mail, calendar, school portals, WhatsApp), turn it into dated tasks, remind, and follow up.
They differ in who they are built for and what they promise about the family's data.

| | Anna (its own pages) | FamilyOS (this repo) |
|---|---|---|
| Built for | Busy parents; US dollars, a US company, California law, servers in the US | A family in India or the UAE first: rupees, UPI, the school circular, two country profiles (`familyos/country.py`). Nothing is translated yet; language fields exist and the plan is in `docs/i18n.md` |
| Children | Users must be 18+; children's data "not addressed" on the security page; "we do not knowingly solicit" under 18 in the policy | Children are members with their own rules: no email or sign-in, school and class matching, a guardian declaration and consent records, and a child's private journal that guardians cannot read unless the child shares an entry (`docs/children-data-compliance.md`, `familyos/consent.py`, `familyos/kid.py`) |
| Who sees what | "Everyone has their own profile" while Anna coordinates the shared picture; no per-item control stated | Each notice is private or shared; a caregiver sees only what is handed to them; a guardian cannot read another adult's mailbox (`docs/care-circle.md`, `familyos/intake/mailbox.py`) |
| Models that see your words | Anthropic, Google Gemini, and Tencent Cloud as a gateway for DeepSeek and Moonshot Kimi (privacy policy). The security page says only "several providers". | The household chooses per task, with a floor it can never be sent below. A model on the family's own machine is an option; a hosted model needs an explicit yes (`familyos/modelroute.py`, `familyos/rules.py`). |
| Key | Encrypted in transit and at rest; Anna operates the service and holds the keys (not stated otherwise) | An optional family-held key: FamilyOS cannot open the household without an adult (`docs/family-key.md`). See "What we do not promise" below. |
| Acting for you | Drafts and sends only after the first go-ahead; no calls; no purchases; groceries go to a cart you check out yourself | Proposes, never acts behind your back: every action shows exactly what it will do and is approved against its fingerprint (`familyos/actions.py`); payments exist only behind a guardian switch and are off by default (`docs/payments-design.md`) |
| Undo and record | Not stated | A ledger of what FamilyOS did, with undo and receipts (Settings, Activity; `familyos/activity.py`); every step is audited |
| Deleting | Delete the account in Settings; logs go within 60 days; backups overwritten in about two weeks | Erasure of a member or the household, and an export first (`familyos/erasure.py`, `docs/export.md`); destroying the key makes derived data unreadable by design |
| Price | US$20 a month or US$192 a year after 14 days free | Not priced; not on sale |

## Where Anna is ahead today

Be plain about these. A parent comparing the two will see them first.

- **It is a product people can sign up for.** FamilyOS is not on sale and runs on one household's machine.
- **Channels.** iMessage and RCS texting in selected countries, WhatsApp, web, iOS and Android, on one account. FamilyOS has the web console, an iPhone app, Telegram,
  and WhatsApp for sending it things; an iMessage line is parked (`docs/architecture.md`) and there is no Android app.
- **Sign-in and setup.** Google or Apple sign-in, a few minutes to connect. FamilyOS now has Google and a first-run flow on the phone and the web
  (`docs/first-run.md`), but no Sign in with Apple until the paid Apple team exists, and the whole path has been tried on a throwaway household only.
- **Skills a parent notices.** Party RSVPs that message each parent and nudge the ones who have not replied, a weekly meal plan that becomes a shopping cart,
  birthday-party booking, voice input. FamilyOS has none of those as finished flows.
- **School portals** (ParentSquare, ClassDojo). FamilyOS reads a school app by driving it on the parent's own phone; it is proved on one school app only
  (`docs/todo.md`, "School-app read on the phone").
- **Reach in the US**, including Gmail, Outlook and iCloud mail connected from Settings.

## Where FamilyOS is different, and why it matters

1. **India and the UAE are the home market, not an afterthought.** Rupee amounts, UPI payee checks, public holidays and the two countries'
   children's-data rules are in the design. Anna's pages name no country outside the US, and its policy does not mention India.
2. **Children are first-class and protected.** Under 18 is a child in India's law, and children here are members: a guardian's declaration and consent are recorded, and a child's own
   journal is theirs unless they share an entry (`familyos/kid.py`). A notice tagged with a child is shared with the household's adults by a rule a guardian can switch off
   (`childrens_notices_shared`), so this is a default, not a wall. The compliance checklist lists what is still open (`docs/children-data-compliance.md`). Anna is for adults and says little more.
3. **The family decides which model reads its words.** Not "several providers": a visible list, a floor, and a refusal rather than a quiet fallback.
4. **Nothing is done behind your back.** Proposals, fingerprints, a ledger and undo. Money is off unless a guardian turns it on.
5. **Mixed trust is expected.** Grandparents, a babysitter, a child and two guardians see different things, and the rules are written down and shown (Settings, Rules and access).
6. **Text from strangers is treated as data.** Ask fences what it reads and refuses instructions inside a notice; the same care is in the sandbox for reading files
   (`familyos/chat.py`, `familyos/extraction/sandbox.py`). Anna's pages do not say how they handle prompt injection.

## What we do not promise

- Not "we can never see your data". While a household is unlocked, the server decrypts what it needs to read a notice, and the model provider it uses sees the text
  it is sent. The default extraction model is a hosted one (`familyos/settings.py`); a household can move to its own machine, and then a hosted model is not used.
- The family key's promise reaches the original files, the mailbox connection and signed-in sessions. Extracted text is sealed only as far as `docs/todo.md`
  ("Encrypt the extracted text") says it is.
- Reading WhatsApp uses a member's own linked session. WhatsApp's guidelines list unofficial clients among things not to do, so the number can be restricted;
  the member is told this before agreeing and it is off by default (`docs/whatsapp-reading.md`). It has been built but not yet proved on a real account.
- The children's-data checklist is working notes from secondary sources, not legal advice, and counsel must confirm it before a public launch.

## What to borrow from Anna (and what we already took)

Taken: the first-run flow's shape (one question a screen, a "why" fold-out, skip everywhere but the name, a permission list before Google's own), the idea of a
"ripple effect" check, and delegate-then-follow-up. Open: party RSVPs as an errand, the weekly meal plan to a shopping list, and a plain statement in our own
policy of which models see what. All are in `docs/todo.md`, Watch list.

## How to keep this honest

Re-read Anna's `/privacy`, `/security` and `/pricing` before quoting anything here: the policy was last updated 29 Sep 2026 and a young company's pages change.
If a line above cannot be backed by a page or a file, delete it.
