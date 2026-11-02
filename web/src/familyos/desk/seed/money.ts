// Seed: Money (recurring merchants), Investments (statements), Grocery's
// "Order again · from your receipts", and the one Travel plan — a fictional
// long weekend in Santa Fe, four weeks out (MASTER_AGENT.md §3.2 3:00–3:40).
import { m } from '../format';
import type { OrderAgainItem, Plan, RecurringMerchant, Statement } from '../types';
import type { SeedCtx } from './ctx';
import { ID } from './people';

export const seedRecurring = (c: SeedCtx): RecurringMerchant[] => [
  { id: 'r_mortgage', merchant: 'First Harbor Mortgage', kind: 'loan', cadence: 'monthly', amount: 2150, last: c.day(-30), next: c.today, spaceId: 'finance', url: 'https://firstharbor.example/account', noticeId: 'n_mortgage' },
  { id: 'r_insurance', merchant: 'Keystone Auto Insurance', kind: 'insurance', cadence: 'monthly', amount: 184, last: c.day(-26), next: c.day(5), spaceId: 'finance', url: 'https://keystoneauto.example/policy', noticeId: 'n_insurance' },
  { id: 'r_power', merchant: 'Brightline Power', kind: 'bill', cadence: 'monthly', amount: 142.3, last: c.day(-24), next: c.day(6), spaceId: 'household', url: 'https://brightline.example/bill', noticeId: 'n_balance' },
  { id: 'r_fiber', merchant: 'Lakeside Fiber', kind: 'bill', cadence: 'monthly', amount: 70, last: c.day(-18), next: c.day(12), spaceId: 'household', url: 'https://lakesidefiber.example', noticeId: 'n_balance' },
  { id: 'r_mobile', merchant: 'Northwind Mobile', kind: 'bill', cadence: 'monthly', amount: 95, last: c.day(-15), next: c.day(15), spaceId: 'finance', url: 'https://northwindmobile.example', noticeId: 'n_balance' },
  { id: 'r_streamly', merchant: 'Streamly Premium', kind: 'subscription', cadence: 'monthly', amount: 15.49, last: c.day(-1), next: c.day(29), spaceId: 'finance', url: 'https://streamly.example/account', noticeId: 'n_streamly' },
  { id: 'r_tunewave', merchant: 'Tunewave Family', kind: 'subscription', cadence: 'monthly', amount: 16.99, last: c.day(-9), next: c.day(21), spaceId: 'finance', url: 'https://tunewave.example', noticeId: 'n_balance' },
  { id: 'r_cloud', merchant: 'CloudKeep 2 TB', kind: 'subscription', cadence: 'monthly', amount: 9.99, last: c.day(-12), next: c.day(18), spaceId: 'memories', url: 'https://cloudkeep.example', noticeId: 'n_balance' },
  { id: 'r_coaching', merchant: 'Rivera Math Coaching', kind: 'subscription', cadence: 'monthly', amount: 180, last: c.day(-27), next: c.day(3), spaceId: 'education', url: 'https://riveramath.example', noticeId: 'n_balance' },
  { id: 'r_gym', merchant: 'FitLane Gym', kind: 'subscription', cadence: 'monthly', amount: 45, last: c.day(-20), next: c.day(10), spaceId: 'health', url: 'https://fitlane.example', noticeId: 'n_balance' },
];

export const seedStatements = (c: SeedCtx): Statement[] => [
  { id: 's_oct', institution: 'Summit Brokerage', kind: 'statement', title: 'Monthly statement', summary: 'Balance, activity and fees for the month.', date: c.day(-3), noticeId: 'n_brokerage' },
  { id: 's_dividend', institution: 'Summit Brokerage', kind: 'dividend', title: 'Dividend paid', summary: 'Total Market Index fund quarterly dividend, reinvested.', date: c.day(-8), amount: 42.18, noticeId: 'n_brokerage' },
  { id: 's_autoinvest', institution: 'Summit Brokerage', kind: 'trade', title: `Auto-invest bought ${m(1500)} of Total Market Index`, summary: `Within the ${m(2000)} a month auto-invest limit.`, date: c.day(-9), amount: 1500, noticeId: 'n_brokerage' },
  { id: 's_529', institution: 'Summit Brokerage', kind: 'statement', title: 'Ethan’s college savings: quarterly statement', summary: 'The 529 plan for Ethan, contributions and growth this quarter.', date: c.day(-20), noticeId: 'n_brokerage' },
  { id: 's_notice', institution: 'Summit Brokerage', kind: 'notice', title: 'Fee schedule update', summary: 'No change for accounts like yours. Nothing to do.', date: c.day(-31), noticeId: 'n_brokerage' },
];

export const seedOrderAgain = (c: SeedCtx): OrderAgainItem[] => [
  { id: 'o_milk', item: 'Oat milk, 64 oz', store: 'FreshCart', lastDate: c.day(-7), price: 4.29, url: 'https://freshcart.example/item/oat-milk', noticeId: 'n_cart' },
  { id: 'o_eggs', item: 'Eggs, one dozen', store: 'FreshCart', lastDate: c.day(-7), price: 3.49, url: 'https://freshcart.example/item/eggs', noticeId: 'n_cart' },
  { id: 'o_sauce', item: 'Pasta sauce, store brand', store: 'FreshCart', lastDate: c.day(-7), price: 2.79, url: 'https://freshcart.example/item/pasta-sauce', noticeId: 'n_cart' },
  { id: 'o_filters', item: 'Furnace filters 16×25×1, 2-pack', store: 'Home Supply Co.', lastDate: c.day(-40), price: 38.99, url: 'https://homesupply.example/item/filters-16x25', noticeId: 'n_receipt' },
  { id: 'o_pods', item: 'Laundry pods, 81 count', store: 'Home Supply Co.', lastDate: c.day(-40), price: 13.99, url: 'https://homesupply.example/item/laundry-pods', noticeId: 'n_receipt' },
];

export function seedPlans(c: SeedCtx): Plan[] {
  const s = 28;
  return [
    {
      id: 'pl_santafe',
      title: 'Four Days in Santa Fe',
      status: 'draft',
      start: c.day(s),
      end: c.day(s + 3),
      budget: 3200,
      authorId: ID.sarah,
      summary: 'A long weekend for all five of us: two easy days in town, one day out to the canyons, and a slow last morning before the flight home. Nothing is booked or paid until someone books it.',
      itinerary: [
        { day: 1, date: c.day(s), title: 'Arrive and settle in', text: 'Morning flight, rental car at the airport, check in at the inn. Short walk around the plaza; early dinner.' },
        { day: 2, date: c.day(s + 1), title: 'Museums and the market', text: 'Folk art museum in the morning (Linda’s pick), lunch at the market, a cooking class in the afternoon.' },
        { day: 3, date: c.day(s + 2), title: 'Canyon day', text: 'Drive out to the canyon trails. Ethan and Michael take the longer loop; the rest take the river walk.' },
        { day: 4, date: c.day(s + 3), title: 'Slow morning, fly home', text: 'Breakfast at the inn, return the car, afternoon flight.' },
      ],
      bookings: [
        { id: 'b_flights', option: 'Round-trip flights for 5', provider: 'SkyWay Air', estCost: 1240, sourceSnippet: 'Morning nonstop, returning mid-afternoon; fares change daily.', sourceUrl: 'https://skyway.example/fares', watch: 'watching · not read yet', booked: false, noticeId: 'n_trip' },
        { id: 'b_inn', option: 'Two rooms, 3 nights', provider: 'Adobe Court Inn', estCost: 780, sourceSnippet: 'Family rooms with two queens; breakfast included.', sourceUrl: 'https://adobecourt.example/rates', watch: 'watching · read', booked: false, noticeId: 'n_trip' },
        { id: 'b_car', option: 'Midsize SUV, 4 days', provider: 'Mesa Car Rental', estCost: 220, sourceSnippet: 'Pick up and return at the airport counter.', sourceUrl: 'https://mesacars.example', watch: 'not watched', booked: true, noticeId: 'n_trip' },
        { id: 'b_class', option: 'Family cooking class', provider: 'Casa Cocina School', estCost: 180, sourceSnippet: 'Three-hour class, ages 10 and up.', sourceUrl: 'https://casacocina.example/classes', watch: 'not watched', booked: false, noticeId: 'n_trip' },
        { id: 'b_park', option: 'Canyon day passes', provider: 'Canyon trails visitor center', estCost: 80, sourceSnippet: 'Day passes per vehicle; timed entry on weekends.', sourceUrl: 'https://canyontrails.example/passes', watch: 'not watched', booked: false, noticeId: 'n_trip' },
      ],
      todoIds: ['t_pl_dates', 't_pl_assist', 't_pl_mail', 't_pl_class', 't_pl_maps'],
      noticeIds: ['n_trip'],
    },
  ];
}
