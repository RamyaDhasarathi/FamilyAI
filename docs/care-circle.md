# Caring for a parent from far away

Built 12 Oct 2026 for the pilot in docs/todo.md: an adult child abroad
coordinating an ageing parent in India. Three additions on the existing engine,
none of them a new permission system.

## The circle's roles

`members.circle_role` (parent, sibling, spouse, caregiver, other) is a label a
guardian sets (`PUT /v1/members/{id}/circle-role`). It words the family page and
the constitution and grants nothing, with one deliberate exception: a
**caregiver** does not see what the household shares. The delegation design
already here (grants.py: "a carer sees the pickup and nothing else") needed the
carer to be a member who sees only what they send and what a guardian hands them,
so the role makes that a name a family can use. It is one change to
`artifacts.VISIBLE_TO_MEMBER` and its twelve inline copies (billers, calendar
events, reminders, gaps, plans, reconcile), and a caregiver's to-dos, plans and
errands are limited the same way. A guardian cannot be a caregiver; a child has no
circle role. What a caregiver *is* handed is a grant (`POST /v1/grants`): dated
obligations by action (attend, prepare, pay ...), about someone or anyone, for up
to a year, with a reason written where the family can read it. They see the
obligation, never the notice it came from.

What is not true: a caregiver can still be sent things by the household over
Telegram or mail if a guardian forwards them; and an adult who is not a caregiver
sees everything shared, as before. "Parent" is a label, not a lesser view: the
parent's own private notices stay private from the child abroad, which is the
point.

## The constitution

`GET /v1/household/constitution`, page `#/constitution` in the cockpit ("Rules
and access"): what is always true (five sentences, none switchable), the circle
(for each person, what they see, in sentences *derived* from the role, the
visibility rule and the live grants, never written by hand), and the household's
rules. Two new rules with real effect: **Scam guard** (a switch, on) and two
numbers, **Documents, warned early** (days added to every kind's lead, both for
the status chip and for the date of a proposed renewal) and **A bill well above
its usual** (the percent above the middle of its earlier charges at which the
brief says so; default 25, the old constant). Numbers are bounded in the model
and in the database.

## Scam guard

`familyos/scamguard.py`. Patterns, not a model: each matching shape adds a weight
and a reason in a parent's words; six or more is high, three is medium. Shapes: a
"digital arrest" or an investigation by video call, authority plus a threat, a
request to share an OTP/PIN/CVV/password (only when not negated: a bank's own
"never share your OTP" is not a request), a KYC block with a link, a "safe" or
"verification" account, a remote-control app, a prize or a job that pays too well,
a relative on a new number asking for money, a service cut off tonight unless you
call, a shortened or odd link. A genuine OTP message and a sender the mail
provider vouched for from a bank or government domain are discounted.

A **high** reading: proposes nothing (no task, no document is kept), is
remembered on the notice (`input_artifacts.suspicion`), leads the brief as
"Looks like a scam", and tells the guardians once on Telegram or mail with what to
do. A **medium** reading is flagged and still read as usual. Anyone can report a
call or message (`POST /v1/scam/reports`, "Report a call" on Today and More): it is
filed as a shared notice, read at once, and always answered with what to do, even
when nothing matches. It says "matches", never "is"; nothing is blocked, deleted
or reported for anyone.

The advice is from sources, checked 12 Oct 2026:
RBI's advisories (a bank never asks for a PIN, OTP, CVV or full card number, by
call, SMS, email or link; https://taxguru.in/rbi/rbi-advisory-cyber-threats-frauds.html)
and the Indian Cyber Crime Coordination Centre (there is no "digital arrest";
police, CBI and courts do not arrest anyone or demand money over a video call;
report at helpline 1930 or https://cybercrime.gov.in;
https://www.etvbharat.com/en/!bharat/cbi-ed-police-dont-arrest-people-through-video-calls-indian-cyber-crime-coordination-centre-enn24100602996).
Outside India the advice names no helpline.

Limits: it reads text. A phone call is not text until someone types or forwards
what was said (or a screenshot of the call log or the SMS, which the OCR reads);
nothing listens to calls. Patterns will miss new scripts and will occasionally
flag a real message; the cost of a false flag is a "dealt with" tap, the cost of
a miss is unchanged from today, and the weights are meant to be tuned from real
reports.

## One person's care view

`GET /v1/members/{id}/care`, page `#/care/{id}`: their documents with what is
expiring (a passport, a policy, a licence), bills (dated obligations to pay, with
the biller's own pay link; FamilyOS never pays), unusual charges (the brief's
money line, limited to receipts about them), appointments in the next 45 days, and
messages that looked wrong. Read through the caller's own visibility: a caregiver
opening it sees only what has been handed over.

## Medicines and standing payments (11 Oct 2026)

**Medicines.** A prescription or a doctor's note is read for one claim per
medicine (`kind: medication`: the drug with its strength, `dose_text` as the
doctor wrote it, `times_per_day`, the first and last day, the prescriber, the
patient when named). `familyos/medications.py` keeps each as a row, the way a
document is kept: a newer prescription of the same drug for the same patient
supersedes the older; a child is a patient only with consent; a private
prescription is its sender's alone. A **refill** is proposed five days before the
supply ends (`REFILL_LEAD_DAYS`), as an ordinary task a person accepts. "Today's
doses" is derived (dose and times a day, while the supply lasts). Nothing is a
diagnosis or advice, and nothing is marked taken here. `GET /v1/medications`, and
the care view carries each person's.

**Standing payments.** Rent has no mail. `POST /v1/standing` writes the rule
once (what, whom, how much, the day 1 to 28, an optional pay link, whom it is
for, private or shared). `familyos/standing.py` makes each month's obligation a
fortnight ahead, from the reminders sweep, exactly the way a read notice makes
one (a kept note, a payment claim, an accepted obligation), so the brief,
reminders, pay link, care view and the loop closer all work unchanged: a UPI alert
or receipt for the same amount that names the payee marks it paid. Once per
month per rule. A private rule is its maker's alone; a shared one can be stopped
by its maker or a guardian. Nothing is ever paid by FamilyOS.

Not built: a caregiver's "dose taken" acknowledgement and escalation to a
sibling when a reminder goes unanswered; doctors as contacts (a record of name,
clinic and phone attached to a person); insurance claims as tasks tied to a
policy; the phone app's screens for either (the web care page has both).
