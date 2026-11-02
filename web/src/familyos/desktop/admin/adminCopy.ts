// Phase 5 copy (MASTER_AGENT.md §10, §3.3.5 "each page has a one-sentence
// description of what it is and what it will never do"). Short, plain,
// honest; the Carter household and USD only — nothing from the reference
// video's family.
import type { ErrandStatus } from '../../desk/types';

export const ADMIN_COPY = {
  errands: {
    description:
      'A booking or a purchase on a site you are signed in to, written down in full before anything happens — what, when, the most it may cost, how it is paid — and approved by a guardian against exactly that. FamilyOS keeps only a card’s last four digits.',
    ask: 'Ask for one',
    askPrefill: 'Write down an errand for me: what, when, on which site, the most it may cost, and how it is paid.',
    empty: 'No errands yet. Ask for one: FamilyOS writes it down in full and waits for a guardian.',
    lineProposed: 'waiting for a guardian · nothing runs until one approves exactly this',
    status: { proposed: 'proposed', approved: 'approved', done: 'done', cancelled: 'cancelled' } satisfies Record<ErrandStatus, string>,
    detail: 'Written down in full before anything happens. If anything written down changes, the approval no longer applies.',
    fpNote: 'Approval is of exactly this; if anything about it changes, the approval no longer applies.',
    howItRuns: [
      'In a fresh browser holding your signed-in session for the site, for the length of the run only.',
      'Every page it reaches is checked against the site’s own addresses. A screenshot is kept at each step.',
      'If a rule stops it, it stops and says why; if it needs you, you get the browser. Afterwards nothing is kept but the screenshots and the receipt.',
    ],
  },
  collect: {
    description:
      'For a site that has no other way in — a school portal, a utility account. One sitting: you sign in yourself, pages are collected for you to read, and nothing is kept afterwards but what you pick.',
    promise: 'FamilyOS takes no password and stores no session. When the sitting ends, the browser is gone.',
    preview: 'In this preview no browser opens; the sitting is recorded, and written to the Audit.',
  },
  quarantine: {
    description:
      'Notices from senders the family has not heard from. Nothing in here is read into proposals, and no link or attachment is opened, until someone releases it.',
    empty: 'Nothing is held. A notice from a sender the family has not heard from will wait here.',
  },
  revisions: {
    description: 'Every change to a family record: who changed what, from what to what, and when. Revert where it is allowed; a revert is a new change, nothing is deleted.',
    empty: 'No record has been changed yet.',
  },
  audit: {
    description: 'Who did what to which record. Nothing here can be edited or deleted; only a household erasure may purge it. Rows carry ids and counts — never passwords or message text.',
  },
  settings: {
    description: 'Guardians manage the household and consent for the children. Children are not accounts and do not sign in. Every change here is written to the Audit.',
    consentWarning:
      'Withdrawing consent starts an erasure in the same step. Every notice naming that child goes, along with anything read from it. The consent record itself stays, as proof it existed and ended.',
    mailboxes:
      'FamilyOS asks for one permission — read-only — and reads only mail that looks like a notice for the family. It cannot send, change or label anything. Erasing the household also ends this.',
    telegram: (bot: string) => `The household’s bot is ${bot}. Linked, it brings notices in from the groups it is in, answers a question ending in “?”, and carries reminders and replies.`,
    phone: '“Send to FamilyOS” in any app’s share sheet sends a screenshot, a bank text or a school email on its own. Each phone gets its own token: shown once, never expires, revoked here.',
    watching: 'FamilyOS reads a public page on a schedule and tells you when the answer changes. It never signs in, holds no password for the site, and does nothing on your behalf.',
    takeAll: (name: string) =>
      `One file with everything FamilyOS holds for ${name}: members, notices, proposals, the calendar, to-dos, errands, plans, revisions, connections and the whole Audit.`,
    eraseAll:
      'Erases every notice, proposal, to-do, errand, plan, connection and the Audit itself. Members stay so a guardian can still sign in; one Audit row records that the erasure happened. This cannot be undone — download everything first if you want a copy.',
  },
};
