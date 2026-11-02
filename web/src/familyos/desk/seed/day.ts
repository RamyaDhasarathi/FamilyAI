// Seed: proposals read from the notices, what accepting them put on the
// family's day (agenda + to-dos), and the one clash FamilyOS noticed. Every
// record keeps its noticeId / proposalId; every quote is an exact substring
// of its notice body (checked in desk.test.ts).
import { fmtLongDay, m } from '../format';
import type { AgendaItem, Conflict, Proposal, Todo } from '../types';
import type { SeedCtx } from './ctx';
import { ID } from './people';

export function seedProposals(c: SeedCtx): Proposal[] {
  const tmr = c.day(1);
  const seatsBy = c.day(Math.max(1, c.offset(c.saturday) - 1));
  const acc = (d: number, by: string, hh = 10) => ({ state: 'accepted' as const, decidedAt: c.past(d, hh, 15), decidedBy: by });
  return [
    // Accepted: on the calendar or the to-do list already.
    { id: 'p_electric', noticeId: 'n_electric', kind: 'calendar', agent: 'household', spaceId: 'household', title: 'Electrician visit, 4:00 pm', due: c.at(0, 16), dueKind: 'time', forMemberId: ID.michael, createdAt: c.past(0, 7, 50), quote: 'today at 4:00 pm', created: { agendaId: 'a_electrician' }, ...acc(0, ID.michael) },
    { id: 'p_mortgage', noticeId: 'n_mortgage', kind: 'payment', agent: 'finance', spaceId: 'finance', title: `Mortgage, ${m(2150)}, due`, due: c.today, dueKind: 'eod', amount: 2150, createdAt: c.at(-5, 6, 12), quote: `payment of ${m(2150)} is due on ${fmtLongDay(c.today)}`, created: { agendaId: 'a_mortgage' }, ...acc(-4, ID.sarah, 19) },
    { id: 'p_final', noticeId: 'n_final', kind: 'calendar', agent: 'education', spaceId: 'education', title: 'Ethan’s math final', due: c.at(1, 14), dueKind: 'time', forMemberId: ID.ethan, createdAt: c.at(-2, 15, 7), quote: `${fmtLongDay(tmr)} from 2:00 pm to 4:00 pm in Room 204`, created: { agendaId: 'a_final' }, ...acc(-2, ID.michael, 18) },
    { id: 'p_client', noticeId: 'n_client', kind: 'calendar', agent: 'calendar', spaceId: 'calendar', title: 'Quarterly review call', due: c.at(1, 14), dueKind: 'time', forMemberId: ID.michael, createdAt: c.at(-4, 10, 4), quote: `${fmtLongDay(tmr)} at 2:00 pm for an hour`, created: { agendaId: 'a_client_call' }, ...acc(-4, ID.michael, 11) },
    { id: 'p_furnace', noticeId: 'n_furnace', kind: 'calendar', agent: 'household', spaceId: 'household', title: 'Furnace service', due: c.at(12, 10), dueKind: 'time', createdAt: c.at(-1, 13, 24), quote: `${fmtLongDay(c.day(12))} at 10:00 am`, created: { agendaId: 'a_furnace' }, ...acc(-1, ID.michael, 14) },
    { id: 'p_filtersize', noticeId: 'n_furnace', kind: 'task', agent: 'household', spaceId: 'household', title: 'Check the furnace filter size', due: c.day(11), dueKind: 'allDay', forMemberId: ID.michael, createdAt: c.at(-1, 13, 24), quote: 'Please check the filter size before the visit.', created: { todoId: 't_filtersize' }, ...acc(-1, ID.michael, 14) },
    { id: 'p_recital', noticeId: 'n_recital', kind: 'calendar', agent: 'calendar', spaceId: 'education', title: 'Mia’s fall recital', due: c.at(c.offset(c.saturday), 14), dueKind: 'time', forMemberId: ID.mia, createdAt: c.at(-3, 16, 42), quote: `${fmtLongDay(c.saturday)} at 2:00 pm at Riverside Hall`, created: { agendaId: 'a_recital' }, ...acc(-3, ID.sarah, 20) },
    { id: 'p_rehearsal', noticeId: 'n_recital', kind: 'calendar', agent: 'calendar', spaceId: 'education', title: 'Recital rehearsal', due: c.at(0, 15, 30), dueKind: 'time', forMemberId: ID.mia, createdAt: c.at(-3, 16, 42), quote: 'The final rehearsal is today at 3:30 pm.', created: { agendaId: 'a_rehearsal' }, ...acc(-3, ID.sarah, 20) },
    { id: 'p_science', noticeId: 'n_science', kind: 'task', agent: 'education', spaceId: 'education', title: 'Finish Mia’s science project', due: c.friday, dueKind: 'allDay', forMemberId: ID.mia, createdAt: c.at(-6, 19, 17), quote: `poster and model due ${fmtLongDay(c.friday)}`, created: { todoId: 't_science' }, ...acc(-6, ID.sarah, 20) },
    { id: 'p_conference', noticeId: 'n_conference', kind: 'calendar', agent: 'education', spaceId: 'education', title: 'Parent-teacher conference', due: c.at(9, 17, 30), dueKind: 'time', forMemberId: ID.ethan, createdAt: c.at(-5, 9, 2), quote: `${fmtLongDay(c.day(9))} at 5:30 pm`, created: { agendaId: 'a_conference' }, ...acc(-5, ID.michael, 12) },
    { id: 'p_dentist', noticeId: 'n_dentist', kind: 'calendar', agent: 'calendar', spaceId: 'health', title: 'Dentist', due: c.at(1, 9, 30), dueKind: 'time', forMemberId: ID.michael, createdAt: c.at(-2, 12, 2), quote: `${fmtLongDay(tmr)} at 9:30 am`, created: { agendaId: 'a_dentist' }, ...acc(-2, ID.michael, 13) },
    { id: 'p_pt', noticeId: 'n_pt', kind: 'calendar', agent: 'calendar', spaceId: 'health', title: 'Physical therapy', due: c.at(0, 9), dueKind: 'time', forMemberId: ID.linda, createdAt: c.at(-7, 14, 2), quote: `${fmtLongDay(c.today)} at 9:00 am with Jordan`, created: { agendaId: 'a_pt' }, ...acc(-7, ID.linda, 15) },
    { id: 'p_gutters', noticeId: 'n_weather', kind: 'task', agent: 'household', spaceId: 'household', title: 'Clear the gutters before the rain', due: c.day(-1), dueKind: 'allDay', forMemberId: ID.michael, createdAt: c.at(-4, 6, 3), quote: 'Clear gutters and drains', created: { todoId: 't_gutters' }, ...acc(-4, ID.michael, 8) },
    // Changed: the coach moved practice after it was accepted; the calendar still says 5 pm.
    { id: 'p_soccer', noticeId: 'n_soccer', kind: 'calendar', agent: 'calendar', spaceId: 'education', title: 'Soccer practice now starts at 5:30 pm', due: c.at(0, 17, 30), dueKind: 'time', forMemberId: ID.ethan, state: 'changed', createdAt: c.past(0, 11, 6), quote: 'practice today moves to 5:30 pm on field 2', changedFrom: { due: c.at(0, 17), dueKind: 'time' }, created: { agendaId: 'a_soccer' }, prevState: 'accepted' },
    // Waiting on someone.
    { id: 'p_tripform', noticeId: 'n_tripform', kind: 'task', agent: 'education', spaceId: 'education', title: 'Sign Ethan’s field trip form', due: c.today, dueKind: 'eod', forMemberId: ID.ethan, state: 'proposed', createdAt: c.at(-3, 11, 32), quote: `must be signed and returned by ${fmtLongDay(c.today)}` },
    { id: 'p_rx', noticeId: 'n_pharmacy', kind: 'task', agent: 'household', spaceId: 'health', title: 'Pick up Linda’s prescription', due: c.today, dueKind: 'eod', forMemberId: ID.linda, state: 'proposed', createdAt: c.past(0, 9, 42), quote: 'ready for pickup today until 8:00 pm' },
    { id: 'p_seats', noticeId: 'n_recital', kind: 'task', agent: 'education', spaceId: 'education', title: 'Reserve four seats for the recital', due: seatsBy, dueKind: 'allDay', forMemberId: ID.mia, state: 'proposed', createdAt: c.at(-3, 16, 42), quote: `reserve up to four seats by ${fmtLongDay(seatsBy)}` },
    { id: 'p_insurance', noticeId: 'n_insurance', kind: 'payment', agent: 'finance', spaceId: 'finance', title: `Renew car insurance, ${m(184)}`, due: c.day(5), dueKind: 'allDay', amount: 184, state: 'proposed', createdAt: c.at(-2, 8, 47), quote: `renews on ${fmtLongDay(c.day(5))}` },
    { id: 'p_trip', noticeId: 'n_trip', kind: 'calendar', agent: 'calendar', spaceId: 'travel', title: 'Hold the long weekend for Santa Fe', due: c.day(28), dueKind: 'allDay', forMemberId: ID.sarah, state: 'proposed', createdAt: c.at(-6, 21, 2), quote: 'Santa Fe for four days?' },
    { id: 'p_flu', noticeId: 'n_flu', kind: 'task', agent: 'household', spaceId: 'health', title: 'Book flu shots for the family', state: 'proposed', createdAt: c.at(-4, 7, 2), quote: 'Book a family slot online' },
    { id: 'p_library', noticeId: 'n_library', kind: 'task', agent: 'education', title: 'Return or renew Mia’s library books', due: c.day(-1), dueKind: 'allDay', forMemberId: ID.mia, state: 'proposed', createdAt: c.at(-6, 8, 2), quote: 'Renew online or return them to any branch.' },
    // The date has gone and nobody decided.
    { id: 'p_picture', noticeId: 'n_picture', kind: 'calendar', agent: 'calendar', spaceId: 'education', title: 'Picture day', due: c.at(-1, 8, 30), dueKind: 'time', forMemberId: ID.mia, state: 'proposed', createdAt: c.at(-8, 15, 2), quote: `${fmtLongDay(c.day(-1))} at 8:30 am` },
    { id: 'p_streamly', noticeId: 'n_streamly', kind: 'reminder', agent: 'finance', spaceId: 'finance', title: 'Decide on Streamly before it renews', due: c.day(-1), dueKind: 'allDay', amount: 15.49, state: 'proposed', createdAt: c.at(-7, 6, 2), quote: 'Cancel any time before then.' },
    { id: 'p_yearbook', noticeId: 'n_yearbook', kind: 'reminder', agent: 'education', spaceId: 'education', title: 'Order Ethan’s yearbook', due: c.day(-2), dueKind: 'allDay', forMemberId: ID.ethan, state: 'missed', createdAt: c.at(-10, 10, 2), quote: `Yearbook orders close on ${fmtLongDay(c.day(-2))}.` },
    // Dismissed.
    { id: 'p_promo', noticeId: 'n_promo', kind: 'reminder', agent: 'grocery', spaceId: 'grocery', title: 'Use the 20% off code before Sunday', state: 'dismissed', createdAt: c.at(-1, 9, 2), quote: 'Use code FALL20 for 20% off your next order until Sunday.', decidedAt: c.at(-1, 12, 30), decidedBy: ID.sarah, prevState: 'proposed' },
  ];
}

export function seedAgenda(c: SeedCtx): AgendaItem[] {
  const sat = c.offset(c.saturday);
  return [
    { id: 'a_pt', agent: 'calendar', spaceId: 'health', kind: 'event', title: 'Linda’s physical therapy', when: c.at(0, 9), end: c.at(0, 10), dueKind: 'time', memberIds: [ID.linda], place: 'Riverbend Physical Therapy', details: [['When', '9:00 – 10:00 am'], ['With', 'Jordan'], ['Where', 'Riverbend Physical Therapy']], createdAt: c.at(-7, 15, 5), noticeId: 'n_pt', proposalId: 'p_pt' },
    { id: 'a_rehearsal', agent: 'calendar', spaceId: 'education', kind: 'event', title: 'Mia’s recital rehearsal', when: c.at(0, 15, 30), end: c.at(0, 16, 30), dueKind: 'time', memberIds: [ID.mia], place: 'Riverside Hall', details: [['When', '3:30 – 4:30 pm'], ['Where', 'Riverside Hall'], ['Pickup', 'Sarah']], createdAt: c.at(-3, 20, 5), noticeId: 'n_recital', proposalId: 'p_rehearsal' },
    { id: 'a_electrician', agent: 'household', spaceId: 'household', kind: 'visit', title: 'The electrician arrives at 4 pm', short: 'Electrician 4 pm', when: c.at(0, 16), dueKind: 'time', memberIds: [ID.michael], place: 'Home', details: [['Visit', 'Today, 4:00 pm'], ['Fixing', 'Hallway circuit'], ['Quote', m(180)], ['Company', 'Bright Wire Electric']], createdAt: c.past(0, 10, 15), noticeId: 'n_electric', proposalId: 'p_electric' },
    { id: 'a_soccer', agent: 'calendar', spaceId: 'education', kind: 'event', title: 'Ethan’s soccer practice', when: c.at(0, 17), end: c.at(0, 18, 30), dueKind: 'time', memberIds: [ID.ethan], place: 'Lakeside High, field 2', details: [['When', '5:00 – 6:30 pm'], ['Where', 'Lakeside High, field 2'], ['Coach', 'Coach Daniels']], createdAt: c.at(-20, 9, 0), noticeId: 'n_soccer', proposalId: 'p_soccer' },
    { id: 'a_delivery', agent: 'grocery', spaceId: 'grocery', kind: 'delivery', title: `Your cart is ready: 14 items, ${m(86.4)}. Delivery at 6 pm.`, short: 'Delivery 6 pm', when: c.at(0, 18), end: c.at(0, 18, 30), dueKind: 'time', details: [['Items', '14'], ['Total', m(86.4)], ['Delivery', 'Today, 6:00 – 6:30 pm'], ['Saved', m(11)]], createdAt: c.past(0, 7, 22), noticeId: 'n_cart' },
    { id: 'a_reserve', agent: 'finance', spaceId: 'finance', kind: 'update', title: `Reserve is ${m(12450)}, up 4.2% this month.`, short: 'Reserve up 4.2%', when: c.today, dueKind: 'notSpecified', details: [['Projected reserve', m(12450)], ['This month', '▲ 4.2%'], ['Card spending', m(4200)]], createdAt: c.past(0, 6, 32), noticeId: 'n_balance' },
    { id: 'a_mortgage', agent: 'finance', spaceId: 'finance', kind: 'bill', title: `The mortgage, ${m(2150)}, is due today.`, short: 'Mortgage due', when: c.today, dueKind: 'eod', details: [['Amount', m(2150)], ['Due', 'Today'], ['Paid by', 'Autopay from checking (set up at the bank)'], ['Lender', 'First Harbor Mortgage']], createdAt: c.at(-4, 19, 5), noticeId: 'n_mortgage', proposalId: 'p_mortgage' },
    { id: 'a_final_reminder', agent: 'education', spaceId: 'education', kind: 'reminder', title: 'Ethan’s math final is tomorrow.', when: c.today, dueKind: 'allDay', remindsOf: c.day(1), memberIds: [ID.ethan], details: [['Final', 'Tomorrow, 2:00 – 4:00 pm'], ['Drop-off', '1:45 pm · no bus on final days'], ['Room', '204']], createdAt: c.past(0, 7, 0), noticeId: 'n_final', proposalId: 'p_final' },
    { id: 'a_dentist', agent: 'calendar', spaceId: 'health', kind: 'event', title: 'Dentist', when: c.at(1, 9, 30), end: c.at(1, 10, 15), dueKind: 'time', memberIds: [ID.michael], place: 'Lakeside Dental', details: [['When', '9:30 am'], ['Where', 'Lakeside Dental, 12 min from home']], createdAt: c.at(-2, 13, 5), noticeId: 'n_dentist', proposalId: 'p_dentist' },
    { id: 'a_final', agent: 'education', spaceId: 'education', kind: 'event', title: 'Ethan’s math final', when: c.at(1, 14), end: c.at(1, 16), dueKind: 'time', memberIds: [ID.ethan, ID.michael], place: 'Lakeside High, Room 204', details: [['When', '2:00 – 4:00 pm'], ['Drop-off', '1:45 pm · Michael drives'], ['Where', 'Lakeside High, Room 204']], createdAt: c.at(-2, 18, 5), noticeId: 'n_final', proposalId: 'p_final' },
    { id: 'a_client_call', agent: 'calendar', spaceId: 'calendar', kind: 'event', title: 'Your client call (quarterly review)', when: c.at(1, 14), end: c.at(1, 15), dueKind: 'time', memberIds: [ID.michael], details: [['When', '2:00 – 3:00 pm'], ['With', 'Dana Whitfield'], ['Can move to', '3:30 pm']], createdAt: c.at(-4, 11, 5), noticeId: 'n_client', proposalId: 'p_client' },
    { id: 'a_recital', agent: 'calendar', spaceId: 'education', kind: 'event', title: 'Mia’s recital', when: c.at(sat, 14), end: c.at(sat, 15, 30), dueKind: 'time', memberIds: [ID.mia, ID.michael, ID.sarah, ID.linda, ID.ethan], place: 'Riverside Hall', details: [['When', 'Saturday, 2:00 pm'], ['Where', 'Riverside Hall']], createdAt: c.at(-3, 20, 5), noticeId: 'n_recital', proposalId: 'p_recital' },
    { id: 'a_conference', agent: 'education', spaceId: 'education', kind: 'event', title: 'Parent-teacher conference', when: c.at(9, 17, 30), end: c.at(9, 18), dueKind: 'time', memberIds: [ID.michael, ID.sarah], place: 'Lakeside High', details: [['With', 'Ms. Alvarez'], ['When', '5:30 pm']], createdAt: c.at(-5, 12, 5), noticeId: 'n_conference', proposalId: 'p_conference' },
    { id: 'a_furnace', agent: 'household', spaceId: 'household', kind: 'visit', title: 'Furnace service', when: c.at(12, 10), dueKind: 'time', place: 'Home', details: [['When', '10:00 am'], ['Company', 'Northside Heating']], createdAt: c.at(-1, 14, 5), noticeId: 'n_furnace', proposalId: 'p_furnace' },
  ];
}

export function seedTodos(c: SeedCtx): Todo[] {
  return [
    { id: 't_science', title: 'Finish Mia’s science project', due: c.friday, dueKind: 'allDay', ownerId: ID.sarah, done: false, agent: 'education', spaceId: 'education', proposalId: 'p_science', noticeId: 'n_science', createdAt: c.at(-6, 20, 5) },
    { id: 't_gutters', title: 'Clear the gutters before the rain', due: c.day(-1), dueKind: 'allDay', ownerId: ID.michael, done: false, agent: 'household', spaceId: 'household', proposalId: 'p_gutters', noticeId: 'n_weather', createdAt: c.at(-4, 8, 5) },
    { id: 't_filtersize', title: 'Check the furnace filter size', due: c.day(11), dueKind: 'allDay', ownerId: ID.michael, done: false, agent: 'household', spaceId: 'household', proposalId: 'p_filtersize', noticeId: 'n_furnace', createdAt: c.at(-1, 14, 5) },
    // The Santa Fe plan's to-dos (planId pl_santafe).
    { id: 't_pl_dates', title: 'Agree the dates with Linda', ownerId: ID.sarah, done: true, doneAt: c.at(-4, 20, 0), planId: 'pl_santafe', spaceId: 'travel', noticeId: 'n_trip', createdAt: c.at(-6, 21, 5) },
    { id: 't_pl_assist', title: 'Ask the airline for assistance for Linda', due: c.day(20), dueKind: 'allDay', ownerId: ID.michael, done: false, planId: 'pl_santafe', spaceId: 'travel', noticeId: 'n_trip', createdAt: c.at(-6, 21, 5) },
    { id: 't_pl_mail', title: 'Ask the neighbors to collect the mail', due: c.day(25), dueKind: 'allDay', ownerId: ID.sarah, done: false, planId: 'pl_santafe', spaceId: 'travel', noticeId: 'n_trip', createdAt: c.at(-6, 21, 5) },
    { id: 't_pl_class', title: 'Pick a day for the cooking class', ownerId: ID.sarah, done: false, planId: 'pl_santafe', spaceId: 'travel', noticeId: 'n_trip', createdAt: c.at(-6, 21, 5) },
    { id: 't_pl_maps', title: 'Download offline maps', due: c.day(27), dueKind: 'allDay', ownerId: ID.ethan, done: false, planId: 'pl_santafe', spaceId: 'travel', noticeId: 'n_trip', createdAt: c.at(-6, 21, 5) },
  ];
}

export const seedConflicts = (c: SeedCtx): Conflict[] => [
  {
    id: 'c_tomorrow',
    aId: 'a_client_call',
    bId: 'a_final',
    title: 'Tomorrow looks tight.',
    message: 'Your 2 pm client call clashes with Ethan’s math final. You are driving him there at 1:45 pm. One of them has to move.',
    fixes: [{ id: 'fix_call_330', label: 'Move your client call to 3:30 pm tomorrow. Dana offered that time; the final stays at 2 pm.', agendaId: 'a_client_call', newWhen: c.at(1, 15, 30), newEnd: c.at(1, 16, 30) }],
  },
];
