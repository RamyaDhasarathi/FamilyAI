// Seed: what arrived (MASTER_AGENT.md §3.2 Inbox, 3:50). 24 notices across
// every space and source, 3 of them held in Quarantine (unknown senders).
// Senders and addresses are fictional (`.example`); bodies are the text the
// proposals in seed/day.ts quote from.
import { fmtLongDay, fmtShortDay, fmtWeekday, m } from '../format';
import type { Notice, QuarantineItem } from '../types';
import type { SeedCtx } from './ctx';
import { ID } from './people';

type N = Omit<Notice, 'receivedAt'> & { receivedAt: string };

export function seedNotices(c: SeedCtx): Notice[] {
  const tmr = c.day(1);
  const sat = c.saturday;
  const fri = c.friday;
  const list: N[] = [
    { id: 'n_electric', source: 'email', sender: 'Bright Wire Electric', senderAddress: 'bookings@brightwire.example', receivedAt: c.past(0, 7, 48), category: 'home', spaceId: 'household', memberIds: [ID.michael],
      title: 'Your visit is confirmed for 4:00 pm today', summary: 'Electrician visit today at 4 pm to fix the hallway circuit.',
      body: `Hi Michael, this confirms your visit with Bright Wire Electric today at 4:00 pm. Our technician will look at the hallway circuit. The approved quote is ${m(180)}. Please make sure someone is home.` },
    { id: 'n_mortgage', source: 'email', sender: 'First Harbor Mortgage', senderAddress: 'statements@firstharbor.example', receivedAt: c.at(-5, 6, 10), category: 'bills', spaceId: 'finance', memberIds: [ID.michael, ID.sarah], attachments: 1,
      title: 'Your mortgage payment is due', summary: `${m(2150)} due ${fmtShortDay(c.today)}; autopay from checking is on.`,
      body: `Your monthly mortgage payment of ${m(2150)} is due on ${fmtLongDay(c.today)}. Autopay from your checking account is on, so no action is needed if your balance covers it.` },
    { id: 'n_balance', source: 'email', sender: 'Cedar Bank alerts', senderAddress: 'alerts@cedarbank.example', receivedAt: c.past(0, 6, 30), category: 'bills', spaceId: 'finance',
      title: 'Your weekly balance summary', summary: 'Reserve up 4.2% this month.',
      body: `Weekly summary for accounts ending 2210 and 7781. Projected reserve: ${m(12450)}. Change this month: up 4.2%. Card spending this month: ${m(4200)}.` },
    { id: 'n_cart', source: 'email', sender: 'FreshCart', senderAddress: 'orders@freshcart.example', receivedAt: c.past(0, 7, 20), category: 'shopping', spaceId: 'grocery',
      title: 'Your weekly cart is ready', summary: `14 items, ${m(86.4)}, delivery today at 6 pm.`,
      body: `Your cart for this week is ready: 14 items, ${m(86.4)}. Delivery is booked for today between 6:00 pm and 6:30 pm. You saved ${m(11)} with this week’s swaps.` },
    { id: 'n_final', source: 'email', sender: 'Lakeside High School', senderAddress: 'office@lakesidehigh.example', receivedAt: c.at(-2, 15, 5), category: 'school', spaceId: 'education', memberIds: [ID.ethan], attachments: 1,
      title: 'Grade 11 math final', summary: `Ethan’s math final is ${fmtWeekday(tmr)} at 2:00 pm; drop-off by 1:45 pm.`,
      body: `Dear families, the Grade 11 math final takes place on ${fmtLongDay(tmr)} from 2:00 pm to 4:00 pm in Room 204. There is no bus on final days, so please drop students off by 1:45 pm. Calculators are provided.` },
    { id: 'n_tripform', source: 'email', sender: 'Lakeside High School', senderAddress: 'office@lakesidehigh.example', receivedAt: c.at(-3, 11, 30), category: 'school', spaceId: 'education', memberIds: [ID.ethan], attachments: 1,
      title: 'Field trip permission form', summary: 'Sign and return the science museum field trip form by today.',
      body: `The Grade 11 science museum field trip permission form must be signed and returned by ${fmtLongDay(c.today)}. Students without a signed form will stay at school.` },
    { id: 'n_client', source: 'email', sender: 'Dana Whitfield', senderAddress: 'dana@northwindpartners.example', receivedAt: c.at(-4, 10, 2), category: 'family', spaceId: 'calendar', memberIds: [ID.michael],
      title: 'Invitation: quarterly review call', summary: `Client call ${fmtWeekday(tmr)} at 2:00 pm.`,
      body: `Michael, can we hold the quarterly review on ${fmtLongDay(tmr)} at 2:00 pm for an hour? I can move to 3:30 pm if that is easier.` },
    { id: 'n_furnace', source: 'email', sender: 'Northside Heating', senderAddress: 'service@northsideheating.example', receivedAt: c.at(-1, 13, 22), category: 'home', spaceId: 'household',
      title: 'Furnace service booked', summary: `Service on ${fmtShortDay(c.day(12))} at 10:00 am.`,
      body: `Your annual furnace service is booked for ${fmtLongDay(c.day(12))} at 10:00 am. Same technician as last year. Please check the filter size before the visit.` },
    { id: 'n_recital', source: 'email', sender: 'Riverside Elementary', senderAddress: 'frontdesk@riverside-elem.example', receivedAt: c.at(-3, 16, 40), category: 'school', spaceId: 'education', memberIds: [ID.mia],
      title: 'Fall recital and rehearsal', summary: `Recital ${fmtWeekday(sat)} at 2 pm; rehearsal today at 3:30 pm.`,
      body: `Our fall recital is on ${fmtLongDay(sat)} at 2:00 pm at Riverside Hall. Families may reserve up to four seats by ${fmtLongDay(c.day(Math.max(1, c.offset(sat) - 1)))}. The final rehearsal is today at 3:30 pm.` },
    { id: 'n_science', source: 'phone', sender: 'Sarah’s phone · school app', receivedAt: c.at(-6, 19, 15), category: 'school', spaceId: 'education', memberIds: [ID.mia],
      title: 'Screenshot: science project', summary: `Mia’s science project is due ${fmtWeekday(fri)}.`,
      body: `Science fair project: poster and model due ${fmtLongDay(fri)}. Progress check: 90% done.` },
    { id: 'n_conference', source: 'email', sender: 'Lakeside High School', senderAddress: 'office@lakesidehigh.example', receivedAt: c.at(-5, 9, 0), category: 'school', spaceId: 'education', memberIds: [ID.ethan],
      title: 'Parent-teacher conference booked', summary: `With Ms. Alvarez on ${fmtShortDay(c.day(9))} at 5:30 pm.`,
      body: `Your parent-teacher conference with Ms. Alvarez is booked for ${fmtLongDay(c.day(9))} at 5:30 pm.` },
    { id: 'n_insurance', source: 'email', sender: 'Keystone Auto Insurance', senderAddress: 'renewals@keystoneauto.example', receivedAt: c.at(-2, 8, 45), category: 'bills', spaceId: 'finance', attachments: 1,
      title: 'Your policy renews soon', summary: `Car insurance, ${m(184)}, renews ${fmtShortDay(c.day(5))}.`,
      body: `Your auto policy renews on ${fmtLongDay(c.day(5))}. The premium is ${m(184)} for the month, the same coverage as now. Renew online any time before then.` },
    { id: 'n_dentist', source: 'email', sender: 'Lakeside Dental', senderAddress: 'hello@lakesidedental.example', receivedAt: c.at(-2, 12, 0), category: 'health', spaceId: 'health', memberIds: [ID.michael],
      title: 'Appointment reminder', summary: `Dentist ${fmtWeekday(tmr)} at 9:30 am.`,
      body: `This is a reminder of your appointment on ${fmtLongDay(tmr)} at 9:30 am. We are 12 minutes from your home address.` },
    { id: 'n_soccer', source: 'whatsapp', sender: 'Coach Daniels', receivedAt: c.past(0, 11, 5), category: 'school', spaceId: 'education', memberIds: [ID.ethan],
      title: 'Practice moved to 5:30', summary: 'Soccer practice today starts at 5:30 pm, not 5.',
      body: 'Heads up team: practice today moves to 5:30 pm on field 2 because of the rain. Same end time.' },
    { id: 'n_pharmacy', source: 'phone', sender: 'Maple Street Pharmacy', receivedAt: c.past(0, 9, 40), category: 'health', spaceId: 'health', memberIds: [ID.linda],
      title: 'Prescription ready for pickup', summary: 'Linda’s prescription is ready; pick up today.',
      body: 'A prescription for Linda Carter is ready for pickup today until 8:00 pm at the Maple Street counter.' },
    { id: 'n_pt', source: 'email', sender: 'Riverbend Physical Therapy', senderAddress: 'care@riverbendpt.example', receivedAt: c.at(-7, 14, 0), category: 'health', spaceId: 'health', memberIds: [ID.linda],
      title: 'Your weekly session', summary: 'Linda’s physical therapy today at 9:00 am.',
      body: `Linda, your weekly session is on ${fmtLongDay(c.today)} at 9:00 am with Jordan.` },
    { id: 'n_flu', source: 'email', sender: 'Lakeside Family Clinic', senderAddress: 'news@lakesideclinic.example', receivedAt: c.at(-4, 7, 0), category: 'newsletter', spaceId: 'health',
      title: 'Flu shots are available', summary: 'Book flu shots for the family; walk-ins also welcome.',
      body: 'Flu shots are now available for all ages. Book a family slot online or walk in on weekday mornings.' },
    { id: 'n_library', source: 'email', sender: 'Maple Grove Library', senderAddress: 'notices@maplegrovelib.example', receivedAt: c.at(-6, 8, 0), category: 'family', memberIds: [ID.mia],
      title: 'Books due soon', summary: `Two books on Mia’s card were due ${fmtShortDay(c.day(-1))}.`,
      body: `Two items on Mia Carter’s card are due on ${fmtLongDay(c.day(-1))}. Renew online or return them to any branch.` },
    { id: 'n_picture', source: 'email', sender: 'Riverside Elementary', senderAddress: 'frontdesk@riverside-elem.example', receivedAt: c.at(-8, 15, 0), category: 'school', spaceId: 'education', memberIds: [ID.mia],
      title: 'Picture day', summary: `Class photos on ${fmtShortDay(c.day(-1))} at 8:30 am.`,
      body: `Picture day for Grade 5 is ${fmtLongDay(c.day(-1))} at 8:30 am. Order forms are attached.` },
    { id: 'n_streamly', source: 'email', sender: 'Streamly', senderAddress: 'billing@streamly.example', receivedAt: c.at(-7, 6, 0), category: 'subscription', spaceId: 'finance',
      title: 'Your plan renews soon', summary: `Streamly Premium, ${m(15.49)}, renewed ${fmtShortDay(c.day(-1))}.`,
      body: `Your Streamly Premium plan renews automatically on ${fmtLongDay(c.day(-1))} for ${m(15.49)}. Cancel any time before then.` },
    { id: 'n_yearbook', source: 'email', sender: 'Lakeside High School', senderAddress: 'office@lakesidehigh.example', receivedAt: c.at(-10, 10, 0), category: 'school', spaceId: 'education', memberIds: [ID.ethan],
      title: 'Yearbook orders close', summary: `Order Ethan’s yearbook by ${fmtShortDay(c.day(-2))}.`,
      body: `Yearbook orders close on ${fmtLongDay(c.day(-2))}. Late orders cannot be accepted.` },
    { id: 'n_weather', source: 'email', sender: 'County Weather Service', senderAddress: 'alerts@countyweather.example', receivedAt: c.at(-4, 6, 0), category: 'home', spaceId: 'household',
      title: 'Heavy rain this week', summary: 'Clear gutters and drains before the rain.',
      body: 'Heavy rain is expected from Wednesday afternoon. Clear gutters and drains, and move outdoor furniture.' },
    { id: 'n_promo', source: 'email', sender: 'FreshCart', senderAddress: 'deals@freshcart.example', receivedAt: c.at(-1, 9, 0), category: 'promo', spaceId: 'grocery',
      title: '20% off your next order', summary: 'A discount code valid until Sunday.',
      body: 'Use code FALL20 for 20% off your next order until Sunday.' },
    { id: 'n_receipt', source: 'email', sender: 'Home Supply Co.', senderAddress: 'receipts@homesupply.example', receivedAt: c.at(-40, 12, 0), category: 'receipt', spaceId: 'household',
      title: 'Your receipt', summary: `Furnace filters 16×25×1, 2-pack, ${m(38.99)}; laundry pods ${m(13.99)}.`,
      body: `Thank you for your order. Furnace filters 16×25×1, 2-pack: ${m(38.99)}. Laundry pods, 81 count: ${m(13.99)}. Paid with Visa ending 4417.` },
    { id: 'n_brokerage', source: 'email', sender: 'Summit Brokerage', senderAddress: 'statements@summitbrokerage.example', receivedAt: c.at(-3, 5, 0), category: 'trading', spaceId: 'investments', attachments: 1,
      title: 'Your monthly statement', summary: 'October statement is ready.',
      body: `Your statement is ready. Auto-invest bought ${m(1500)} of Total Market Index. A dividend of ${m(42.18)} was paid.` },
    { id: 'n_trip', source: 'paste', sender: 'Sarah (pasted)', receivedAt: c.at(-6, 21, 0), category: 'travel', spaceId: 'travel', memberIds: [ID.sarah],
      title: 'Trip ideas: Santa Fe', summary: 'Four days in Santa Fe over the long weekend.',
      body: `Santa Fe for four days? Fly in, two days in town, one day out to the canyons. Adobe Court Inn looks good. Budget around ${m(3000)}.` },
    { id: 'n_photo', source: 'phone', sender: 'Sarah’s phone', receivedAt: c.at(-1, 18, 30), category: 'family', spaceId: 'memories', memberIds: [ID.mia], attachments: 1,
      title: 'Photo: first rehearsal', summary: 'Mia on stage at the first rehearsal.',
      body: 'A photo shared from Sarah’s phone: Mia at the first recital rehearsal.' },
    // Unknown senders: held in Quarantine until a person releases them.
    { id: 'n_q_parcel', source: 'email', sender: 'Parcel Notice', senderAddress: 'alerts@parcel-track.example', receivedAt: c.past(0, 5, 12), category: 'promo', quarantined: true,
      title: 'Your package could not be delivered', summary: 'Asks you to pay a redelivery fee through a link.',
      body: `We could not deliver your package. Pay the redelivery fee of ${m(1.99)} at the link below within 24 hours.` },
    { id: 'n_q_invoice', source: 'email', sender: 'Billing Center', senderAddress: 'accounts@billing-center.example', receivedAt: c.at(-1, 23, 40), category: 'bills', quarantined: true, attachments: 1,
      title: 'Invoice #4471 overdue', summary: 'An invoice from a sender the family has never heard from.',
      body: 'Invoice #4471 is overdue. Open the attached file to see the amount and pay today to avoid fees.' },
    { id: 'n_q_camp', source: 'email', sender: 'Camp Pinecrest', senderAddress: 'hello@camppinecrest.example', receivedAt: c.at(-2, 10, 15), category: 'promo', quarantined: true, memberIds: [ID.mia],
      title: 'Summer camp early-bird places', summary: 'A camp the family has not been in touch with before.',
      body: 'Early-bird places for next summer are open. Ages 9 to 12. Reserve before the end of the month.' },
  ];
  return list;
}

export const seedQuarantine = (c: SeedCtx): QuarantineItem[] => [
  { id: 'q_parcel', noticeId: 'n_q_parcel', heldAt: c.past(0, 5, 12), reason: 'Unknown sender, and it asks for a payment through a link.' },
  { id: 'q_invoice', noticeId: 'n_q_invoice', heldAt: c.at(-1, 23, 40), reason: 'Unknown sender with an attachment.' },
  { id: 'q_camp', noticeId: 'n_q_camp', heldAt: c.at(-2, 10, 15), reason: 'Unknown sender. It mentions Mia.' },
];
