# Design checklist: ask before building, state the answers in the change (21 Oct 2026)

Every feature gets these questions answered in its first commit message or its doc section, even when the answer is "not applicable, because". The founder asked for this
after time zones and languages were found late: the first deployment (a household in India, a founder in Dubai) hid them.

**Standing rules (founder, 21 Oct 2026):** do not break old code or behaviour (call out and test any change to it); think wider than the case in front of you; be proactive; keep it simple, with no machinery for cases that do not exist yet.

**Who and where**
1. Which members does it touch: adult, guardian, child, caregiver, a person in two households, a member whose guardian changes (separation, a grandparent's care)?
2. Which household settings does it depend on: country, zone, currency, language, calendar (school year, weekend, holidays)? Is each read from the database, never from configuration or the machine?
3. What if the person is not where the household is (travelling, living abroad)? Whose day is "today"?

**Time, text, money**
4. Every time stored as UTC, every date as a date, shown in the person's zone and language? Any "today", "tomorrow", "this week", "overdue" computed with `clock`? Daylight saving, month ends, leap days, a date typed as `12/10`?
5. Every user-facing string: in the catalog (docs/i18n.md)? Plurals, lists, names, right-to-left, a longer language that clips?
6. Amounts as numbers with an ISO currency, shown with the right grouping and symbol; rounding stated; never parsed back out of display text.

**Trust and privacy**
7. Whose data does it read, and who can see the answer? Private, shared, a child's, a caregiver's, a group's? What does it show to a person who must not see it?
8. What can hostile text in a notice, a message, a page or a file make it do? Is it data or an instruction?
9. What does it cost the family if it is wrong (money, a missed pickup, a wrong child)? Is a person asked first?
10. Consent, retention, export and erasure: what rows and files does it create, and do export and erasure find them? Does the law of the household's country add a rule (India DPDP, UAE PDPL, GDPR, a child's age)?

**Running it**
11. Two workers, a restart in the middle, a retry, a duplicate delivery, a slow or down dependency: what happens?
12. Is there a limit (size, rate, cost, count), and what does a person see when it is hit?
13. Can it be tested without the real clock, the real network, the founder's `.env` or the founder's phone? (Several tests passed on this Mac and failed elsewhere: `.env`, the machine's zone.)
14. What will we want to know when it breaks: is it audited and logged without its content?

**People**
15. Does it work for someone who cannot read well, is not looking at a screen, has a small phone, a slow network, a screen reader, large text? Is there a non-app way (Telegram, a message)?
16. What does it say when it does not know?
