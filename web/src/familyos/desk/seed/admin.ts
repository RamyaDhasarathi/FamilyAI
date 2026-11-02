// Seed: Errands (one per state, with their runs), Revisions and ~45 Audit
// rows over the last week (MASTER_AGENT.md §3.2 5:50–7:20). Audit rows are
// in time order; the store only ever appends to them.
import { fingerprint } from '../fingerprint';
import { fmtShortDay, m } from '../format';
import type { AuditEntry, Errand, ErrandTerms, Revision } from '../types';
import type { SeedCtx } from './ctx';
import { ID } from './people';

const CARD = 'Visa ending 4417';

export function seedErrands(c: SeedCtx): Errand[] {
  const make = (e: Omit<Errand, 'fingerprint'> & ErrandTerms): Errand => ({ ...e, fingerprint: fingerprint(e) });
  const filters = make({
    id: 'e_filters', title: 'Reorder the furnace filters', agent: 'household', status: 'approved', requestedBy: ID.michael, createdAt: c.at(-2, 8, 40), steps: [], noticeId: 'n_receipt',
    what: 'Furnace filters 16×25×1, 2-pack, the same item as the last order', when: `Before ${fmtShortDay(c.day(12))}, standard shipping`, where: 'homesupply.example, signed in as Michael',
    atMost: 48, paidBy: 'On the site, at checkout', card: CARD, stopsIf: 'The price is over the limit, the size is different, or the site asks for anything new',
    approvedBy: ID.michael, approvedAt: c.at(-2, 9, 0),
  });
  const labfees = make({
    id: 'e_labfees', title: 'Pay Mia’s lab fees', agent: 'education', status: 'done', requestedBy: ID.sarah, createdAt: c.at(-26, 18, 0), noticeId: 'n_science',
    what: 'Grade 5 science lab fee for Mia Carter', when: `By ${fmtShortDay(c.day(-24))}`, where: 'Riverside Elementary payments portal, signed in as Sarah',
    atMost: 65, paidBy: 'School payments portal', card: CARD, stopsIf: `The fee is not exactly ${m(65)}, or the student is not Mia`,
    approvedBy: ID.sarah, approvedAt: c.at(-25, 8, 30),
    steps: [
      { text: 'Opened the school payments portal in a sealed browser', at: c.at(-24, 9, 1), image: 'shot-portal' },
      { text: 'Found “Grade 5 science lab fee” for Mia Carter', at: c.at(-24, 9, 2), image: 'shot-fee' },
      { text: `Checked the amount: ${m(65)}, within the limit`, at: c.at(-24, 9, 2) },
      { text: 'Paid with the card on file and saved the receipt', at: c.at(-24, 9, 3), image: 'shot-receipt' },
      { text: 'Closed the browser; nothing was kept', at: c.at(-24, 9, 3) },
    ],
  });
  const cleaner = make({
    id: 'e_cleaner', title: 'Book a deep clean', agent: 'household', status: 'cancelled', requestedBy: ID.sarah, createdAt: c.at(-5, 20, 0), steps: [], cancelledReason: 'It fell on the recital day, so Sarah cancelled it before it ran.',
    what: '3-hour deep clean, two cleaners', when: `${fmtShortDay(c.saturday)}, 9:00 am`, where: 'sparklehome.example, signed in as Sarah',
    atMost: 240, paidBy: 'On the site, at checkout', card: CARD, stopsIf: 'No slot before noon, or the price is over the limit',
  });
  const insurance = make({
    id: 'e_insurance', title: 'Renew the car insurance', agent: 'finance', status: 'proposed', requestedBy: ID.michael, createdAt: c.past(-2, 9, 0), steps: [], noticeId: 'n_insurance',
    what: 'One-month auto policy renewal, the same coverage as now', when: `Before ${fmtShortDay(c.day(5))}`, where: 'keystoneauto.example, signed in as Michael',
    atMost: 184, paidBy: 'On the site, at checkout', card: CARD, stopsIf: `The premium is above ${m(184)}, or the coverage changes`,
  });
  return [
    { ...filters, approvedFingerprint: filters.fingerprint },
    { ...labfees, approvedFingerprint: labfees.fingerprint },
    cleaner,
    insurance,
  ];
}

export const seedRevisions = (c: SeedCtx): Revision[] => [
  { id: 'rv_budget', at: c.at(-4, 21, 30), actor: ID.sarah, recordType: 'plan', recordId: 'pl_santafe', recordLabel: 'Four Days in Santa Fe', field: 'budget', before: 2800, after: 3200, revertible: true },
  { id: 'rv_science', at: c.at(-6, 20, 8), actor: ID.sarah, recordType: 'todo', recordId: 't_science', recordLabel: 'Finish Mia’s science project', field: 'title', before: 'Mia’s science project', after: 'Finish Mia’s science project', revertible: true },
  { id: 'rv_gutters', at: c.at(-3, 7, 50), actor: ID.michael, recordType: 'todo', recordId: 't_gutters', recordLabel: 'Clear the gutters before the rain', field: 'due', before: c.day(-3), after: c.day(-1), revertible: true },
  { id: 'rv_dentist', at: c.at(-2, 13, 6), actor: 'FamilyOS', recordType: 'agenda', recordId: 'a_dentist', recordLabel: 'Dentist', field: 'when', before: c.at(2, 11), after: c.at(1, 9, 30), revertible: true },
  { id: 'rv_electric', at: c.past(0, 10, 16), actor: 'FamilyOS', recordType: 'agenda', recordId: 'a_electrician', recordLabel: 'The electrician arrives at 4 pm', field: 'when', before: c.at(0, 15), after: c.at(0, 16), revertible: false },
  { id: 'rv_filters', at: c.at(-2, 8, 55), actor: ID.michael, recordType: 'errand', recordId: 'e_filters', recordLabel: 'Reorder the furnace filters', field: 'atMost', before: 40, after: 48, revertible: false },
  { id: 'rv_ethan', at: c.past(0, 7, 30), actor: 'FamilyOS', recordType: 'member', recordId: ID.ethan, recordLabel: 'Ethan', field: 'statusLine', before: 'At Lakeside High', after: 'At Lakeside High · soccer at 5', revertible: true },
];

export function seedAudit(c: SeedCtx): AuditEntry[] {
  const F = 'FamilyOS';
  type Row = [number, number, number, string, string, string, Record<string, unknown>?];
  const rows: Row[] = [
    [-6, 8, 0, F, 'FamilyOS read “Books due soon” from Maple Grove Library', 'notice.read', { noticeId: 'n_library' }],
    [-6, 8, 2, ID.michael, 'Michael signed in', 'member.signed_in', { via: 'google' }],
    [-6, 8, 3, F, 'FamilyOS proposed “Return or renew Mia’s library books”', 'proposal.created', { proposalId: 'p_library' }],
    [-6, 8, 4, F, 'FamilyOS synced the family calendar: kept 17, dropped 0', 'calendar.synced', { kept: 17, dropped: 0 }],
    [-6, 19, 15, ID.sarah, 'Sarah shared a screenshot from the school app', 'notice.received', { noticeId: 'n_science', via: 'phone', tokenId: 'tk_sarah' }],
    [-6, 20, 5, ID.sarah, 'Sarah accepted “Finish Mia’s science project”', 'proposal.accepted', { proposalId: 'p_science', todoId: 't_science' }],
    [-6, 20, 8, ID.sarah, 'Sarah renamed the to-do “Mia’s science project”', 'todo.updated', { todoId: 't_science', revisionId: 'rv_science' }],
    [-6, 21, 0, ID.sarah, 'Sarah pasted “Trip ideas: Santa Fe”', 'notice.received', { noticeId: 'n_trip', via: 'paste' }],
    [-6, 21, 5, ID.sarah, 'Sarah started the plan “Four Days in Santa Fe”', 'plan.created', { planId: 'pl_santafe' }],
    [-5, 6, 12, F, 'FamilyOS read “Your mortgage payment is due” from First Harbor Mortgage', 'notice.read', { noticeId: 'n_mortgage' }],
    [-5, 9, 2, F, 'FamilyOS proposed “Parent-teacher conference”', 'proposal.created', { proposalId: 'p_conference' }],
    [-5, 12, 15, ID.michael, 'Michael accepted “Parent-teacher conference”', 'proposal.accepted', { proposalId: 'p_conference', agendaId: 'a_conference' }],
    [-5, 20, 0, ID.sarah, 'Sarah asked for an errand: “Book a deep clean”', 'errand.requested', { errandId: 'e_cleaner' }],
    [-4, 6, 3, F, 'FamilyOS proposed “Clear the gutters before the rain”', 'proposal.created', { proposalId: 'p_gutters' }],
    [-4, 8, 15, ID.michael, 'Michael accepted “Clear the gutters before the rain”', 'proposal.accepted', { proposalId: 'p_gutters', todoId: 't_gutters' }],
    [-4, 10, 4, F, 'FamilyOS read “Invitation: quarterly review call” from Dana Whitfield', 'notice.read', { noticeId: 'n_client' }],
    [-4, 11, 15, ID.michael, 'Michael accepted “Quarterly review call”', 'proposal.accepted', { proposalId: 'p_client', agendaId: 'a_client_call' }],
    [-4, 19, 15, ID.sarah, `Sarah accepted “Mortgage, ${m(2150)}, due”`, 'proposal.accepted', { proposalId: 'p_mortgage', agendaId: 'a_mortgage' }],
    [-4, 20, 0, ID.sarah, 'Sarah ticked “Agree the dates with Linda”', 'todo.done', { todoId: 't_pl_dates' }],
    [-4, 20, 30, ID.sarah, 'Sarah cancelled the errand “Book a deep clean”', 'errand.cancelled', { errandId: 'e_cleaner' }],
    [-4, 21, 30, ID.sarah, `Sarah changed the trip budget from ${m(2800)} to ${m(3200)}`, 'plan.updated', { planId: 'pl_santafe', revisionId: 'rv_budget' }],
    [-3, 7, 50, ID.michael, 'Michael moved the gutters to-do to yesterday', 'todo.updated', { todoId: 't_gutters', revisionId: 'rv_gutters' }],
    [-3, 8, 12, ID.michael, 'Michael opened the original of “Your monthly statement”', 'artifact.original_read', { noticeId: 'n_brokerage' }],
    [-3, 11, 32, F, 'FamilyOS proposed “Sign Ethan’s field trip form”', 'proposal.created', { proposalId: 'p_tripform' }],
    [-3, 16, 42, F, 'FamilyOS proposed 3 items from “Fall recital and rehearsal”', 'proposal.created', { noticeId: 'n_recital', count: 3 }],
    [-3, 20, 15, ID.sarah, 'Sarah accepted “Mia’s fall recital” and “Recital rehearsal”', 'proposal.accepted', { proposalIds: ['p_recital', 'p_rehearsal'] }],
    [-2, 8, 40, ID.michael, 'Michael asked for an errand: “Reorder the furnace filters”', 'errand.requested', { errandId: 'e_filters' }],
    [-2, 9, 0, ID.michael, 'Michael approved “Reorder the furnace filters”', 'errand.approved', { errandId: 'e_filters' }],
    [-2, 10, 15, F, 'FamilyOS held “Summer camp early-bird places” in Quarantine: unknown sender', 'quarantine.held', { noticeId: 'n_q_camp' }],
    [-2, 13, 15, ID.michael, 'Michael accepted “Dentist”', 'proposal.accepted', { proposalId: 'p_dentist', agendaId: 'a_dentist' }],
    [-2, 15, 7, F, 'FamilyOS proposed “Ethan’s math final”', 'proposal.created', { proposalId: 'p_final' }],
    [-2, 18, 15, ID.michael, 'Michael accepted “Ethan’s math final”', 'proposal.accepted', { proposalId: 'p_final', agendaId: 'a_final' }],
    [-1, 12, 30, ID.sarah, 'Sarah dismissed “Use the 20% off code before Sunday”', 'proposal.dismissed', { proposalId: 'p_promo' }],
    [-1, 13, 24, F, 'FamilyOS proposed “Furnace service” and “Check the furnace filter size”', 'proposal.created', { proposalIds: ['p_furnace', 'p_filtersize'] }],
    [-1, 14, 15, ID.michael, 'Michael accepted “Furnace service”', 'proposal.accepted', { proposalId: 'p_furnace', agendaId: 'a_furnace' }],
    [-1, 18, 30, ID.sarah, 'Sarah shared a photo from her phone', 'notice.received', { noticeId: 'n_photo', via: 'phone', tokenId: 'tk_sarah' }],
    [-1, 23, 40, F, 'FamilyOS held “Invoice #4471 overdue” in Quarantine: unknown sender', 'quarantine.held', { noticeId: 'n_q_invoice' }],
    [0, 5, 12, F, 'FamilyOS held “Your package could not be delivered” in Quarantine: unknown sender', 'quarantine.held', { noticeId: 'n_q_parcel' }],
    [0, 6, 0, F, 'FamilyOS checked 3 pages you are watching; 1 changed', 'watcher.checked', { checked: 3, changed: 1 }],
    [0, 6, 32, F, 'FamilyOS read “Your weekly balance summary” from Cedar Bank alerts', 'notice.read', { noticeId: 'n_balance' }],
    [0, 7, 0, F, 'FamilyOS added a reminder: “Ethan’s math final is tomorrow”', 'reminder.created', { agendaId: 'a_final_reminder' }],
    [0, 7, 30, F, 'FamilyOS updated Ethan’s status line', 'member.updated', { memberId: ID.ethan, revisionId: 'rv_ethan' }],
    [0, 7, 55, F, 'FamilyOS synced 2 mailboxes: 4 new notices', 'mailbox.synced', { mailboxes: 2, notices: 4 }],
    [0, 9, 41, ID.michael, 'Michael sent “Prescription ready for pickup” from his iPhone', 'notice.received', { noticeId: 'n_pharmacy', via: 'phone', tokenId: 'tk_michael' }],
    [0, 9, 42, F, 'FamilyOS proposed “Pick up Linda’s prescription”', 'proposal.created', { proposalId: 'p_rx' }],
    [0, 10, 15, ID.michael, 'Michael accepted “Electrician visit, 4:00 pm”', 'proposal.accepted', { proposalId: 'p_electric', agendaId: 'a_electrician' }],
    [0, 11, 6, F, 'FamilyOS saw that soccer practice moved to 5:30 pm and asked the family to confirm', 'proposal.changed', { proposalId: 'p_soccer', from: '5:00 pm', to: '5:30 pm' }],
    [0, 11, 10, F, 'FamilyOS noticed a clash: your client call and Ethan’s math final, tomorrow at 2 pm', 'conflict.detected', { conflictId: 'c_tomorrow' }],
  ];
  return rows.map(([d, hh, mm, actor, sentence, code, raw], i) => ({
    id: `au_${String(i + 1).padStart(3, '0')}`,
    at: c.past(d, hh, mm),
    actor,
    sentence,
    code,
    raw,
  }));
}
