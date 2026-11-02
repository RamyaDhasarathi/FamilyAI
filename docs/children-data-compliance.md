# Children's data: what India and the UAE ask, and where we stand (21 Oct 2026)

**Not legal advice.** A working checklist from secondary sources (law-firm and compliance summaries, read 21 Oct 2026), to be confirmed against the official texts by counsel in each
country before a public launch. Where sources disagreed, it says so. "We do" lines were checked in this repository on the same day.

## What the laws say (as far as the sources agree)

**India, Digital Personal Data Protection Act 2023 and the DPDP Rules 2025.**
- A child is anyone under 18. Section 9: before processing a child's data, get **verifiable consent of the parent or lawful guardian**; no **tracking, behavioural monitoring or
  targeted advertising** aimed at children. Rule 10 asks the data fiduciary to check, with technical and organisational measures, that the person claiming to be the parent is an
  identifiable adult (routes include reliable details already held, or a digital locker token). Some classes of fiduciary and purposes are exempt (healthcare, education, child
  transport appear in summaries), within stated conditions: "education" is not a blanket exemption.
- The Rules were notified 13 Nov 2025; most obligations, Rule 10 among them, start **18 months later (a tracker says 14 May 2027)**. Sources differ on details: read the Gazette.

**UAE.**
- **PDPL (Federal Decree-Law 45 of 2021):** one review of the Arabic text finds **no provision on minors** (no age of digital consent, no guardian-consent mechanism) and no fines in the
  text. The general rule (no processing without the owner's consent, with exceptions) applies. Its **Executive Regulations**: careful sources say not yet published, commercial sites
  say issued; unresolved here.
- **Child Digital Safety Law (Federal Decree-Law 26 of 2025):** in force 1 Jan 2026, compliance by about **Jan 2027** unless extended. A child is under 18. Platforms that operate in the UAE
  **or target UAE users** may not collect or use personal data of a child **under 13** without **verified parental consent**; no advertising use of children's data; parents must be able
  to withdraw easily; clear privacy disclosures; age verification is in scope (standards not in the summaries). A Cabinet Resolution 106 of 2026 on children's access to social media exists (Arabic only; not read).

## Where we stand

| Ask | What we do (checked) | Gap or question |
|---|---|---|
| Guardian consent for a child's data | `consent_records`: a guardian's consent per child and purpose, with `notice_version` and a `verification_method` field; nothing about the child is read or attributed without active consent; withdrawing consent starts erasure as one change (`consent.py`, `erasure.py`) | Nothing **verifies** that the guardian is the parent or lawful guardian: the founder names guardians. Needs a verification route per country (DigiLocker is documented in docs/digilocker.md; not built) |
| No tracking or behavioural monitoring of children | Children are not located (`locations.py`), do not sync health (`health.py`); no advertising anywhere | Review kid mode, the household graph and "pickup" features for anything that profiles a child; confirm the education exemption does not need relying on |
| Age | `role = child`, date of birth optional, a child's own key for kid mode | No rule at 13 or 18; DOB is empty for most members; no teen mode. Decide what changes at each age and per country |
| Notice | `notice_version` stored with each consent | The notice text itself, in the guardian's language (docs/i18n.md), needs writing and review by counsel |
| Withdrawal, erasure | Per child and per household; a linked browser profile is removed first; audit events hold ids, never text | Backups and logs: does an erased child survive in a backup or in a model provider's logs? State it |
| Access, export, correction | `GET /v1/export`, `GET /v1/members/{id}/export` (a guardian, for a child), streamed and never stored; amendments for corrected notices | Correction of a child's own record by a guardian is not a named flow |
| Security, breach | Family key, sealed text, immutable audit, sandboxed parsing | No written **breach procedure** (who is told, within what time, how an affected family is told): write one |
| Processors and transfers | Cloud models only where the household's floor allows (`modelroute`); local models possible | List every processor (model providers, hosting, mail, SMS, browsers) with what each sees; cross-border rules for India and the UAE; where data is hosted (docs/family-key.md, Confidential VMs) |
| Contact and grievance | none | A named contact for privacy requests and grievances in the product and the notice |
| Self-hosted vs hosted | Not decided in writing | Who is the data fiduciary when we host, and when a family hosts itself, changes who owes what |

## Suggested order

1. Decide who the fiduciary is in each deployment, and name a privacy contact. (Founder.)
2. Counsel in India and the UAE read this page against the official texts: Gazette (DPDP Rules, commencement), the UAE Legislation portal (PDPL regulations, Decree-Law 26).
3. Verification of guardianship: one simple route first (a signed-in guardian over a verified email or phone plus a recorded declaration), then DigiLocker where it exists.
4. Write the breach procedure and the processor list; add backups to the erasure statement.
5. Age rules: store date of birth when a child is added; decide the 13 and 18 behaviour; keep kid mode free of anything that profiles.

## Sources (read 21 Oct 2026)

- DPDP Rules 2025: dpdpa.com (Rule 10), EY and Baker McKenzie summaries, dpdpa.dcomply.in (tracker of effective dates)
- UAE PDPL: EdLaw review of the Arabic text; business-ciso.com and businessdubai.ae on the Executive Regulations; DLA Piper
- UAE Child Digital Safety Law: Bird & Bird, Latham & Watkins, Clyde & Co, Reed Smith, u.ae government page
