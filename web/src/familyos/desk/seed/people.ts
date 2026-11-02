// Seed: the Carter household (mocks/data.ts FAMILY_SEED, same member ids as
// the family store), the children's schools, spaces, settings, consents and
// connections. Fictional names and `.example` addresses only.
import { colors } from '../../theme/tokens';
import { NAMES, profile, todayBrief } from '../../mocks/data';
import type {
  ChildInfo, Consent, HouseholdSettings, HouseholdToggle, Mailbox, Member, PhoneToken, Space, TelegramLink, Watcher, Weather,
} from '../types';
import type { SeedCtx } from './ctx';

export const ID = { michael: 'm_michael', sarah: 'm_sarah', linda: 'm_linda', ethan: 'm_ethan', mia: 'm_mia' } as const;

export function seedMembers(): Member[] {
  return [
    { id: ID.michael, name: NAMES.me, fullName: `${NAMES.me} Carter`, initial: 'M', role: 'guardian', hasAccount: true, age: 42, status: 'busy', statusLine: 'Client work until 5 pm', email: profile.email },
    { id: ID.linda, name: NAMES.grandma, fullName: `${NAMES.grandma} Carter`, initial: 'L', role: 'adult', hasAccount: true, age: 68, status: 'home', statusLine: 'Back from physical therapy' },
    { id: ID.sarah, name: NAMES.partner, fullName: `${NAMES.partner} Carter`, initial: 'S', role: 'guardian', hasAccount: true, age: 40, status: 'free', statusLine: 'Nothing scheduled', email: 'sarah@example.com' },
    { id: ID.ethan, name: NAMES.son, fullName: `${NAMES.son} Carter`, initial: 'E', role: 'child', hasAccount: false, age: 16, status: 'away', statusLine: 'At Lakeside High · soccer at 5', school: 'Lakeside High', grade: 'Grade 11' },
    { id: ID.mia, name: NAMES.daughter, fullName: `${NAMES.daughter} Carter`, initial: 'M', role: 'child', hasAccount: false, age: 11, status: 'away', statusLine: 'At Riverside Elementary · rehearsal 3:30', school: 'Riverside Elementary', grade: 'Grade 5' },
  ];
}

export const seedChildren = (): ChildInfo[] => [
  { memberId: ID.ethan, school: 'Lakeside High', grade: 'Grade 11', homeroom: '11B', teacher: 'Ms. Alvarez' },
  { memberId: ID.mia, school: 'Riverside Elementary', grade: 'Grade 5', homeroom: '5A', teacher: 'Mr. Okafor' },
];

/** Sidebar spaces (MASTER §3.1, §4): our five agent colours, plus Health, Travel, Investments, Memories. */
export const seedSpaces = (): Space[] => [
  { id: 'education', name: 'School', color: colors.agents.education, icon: 'GraduationCap', agent: 'education', route: '/agents/education', description: 'Ethan and Mia: what the schools sent, what is due, and what was accepted.' },
  { id: 'health', name: 'Health', color: colors.health, icon: 'HeartPulse', route: '/health', description: 'Appointments, prescriptions and clinic notices for everyone.' },
  { id: 'travel', name: 'Travel', color: colors.agents.calendar, icon: 'Plane', route: '/travel', description: 'Trips the family is planning, and what still needs booking.' },
  { id: 'finance', name: 'Money', color: colors.agents.finance, icon: 'Wallet', agent: 'finance', route: '/agents/finance', description: 'Only what mail can see: bills, charges and what renews.' },
  { id: 'investments', name: 'Investments', color: colors.agents.finance, icon: 'TrendingUp', agent: 'finance', route: '/agents/finance/investments', description: 'Statements and notices from the brokerage, in order.' },
  { id: 'household', name: 'Home', color: colors.agents.household, icon: 'House', agent: 'household', route: '/agents/household', description: 'Visits, repairs and errands for the house.' },
  { id: 'grocery', name: 'Groceries', color: colors.agents.grocery, icon: 'ShoppingBasket', agent: 'grocery', route: '/agents/grocery', description: 'The weekly cart, deliveries and what to order again.' },
  { id: 'calendar', name: 'Calendar', color: colors.agents.calendar, icon: 'CalendarDays', agent: 'calendar', route: '/agents/calendar', description: 'Everyone’s events, and dates spotted in notices.' },
  { id: 'memories', name: 'Memories', color: colors.dust, icon: 'Images', route: '/memories', description: 'Photos and moments the family chose to keep.' },
];

export const seedSettings = (tz: string): HouseholdSettings => ({
  name: 'The Carters',
  country: 'United States',
  timezone: tz,
  currency: 'USD',
  familyAddress: 'carters.maple@in.familyos.example',
});

export const seedWeather = (): Weather => ({ now: todayBrief.weather.value, detail: todayBrief.weather.detail });

export const seedConsents = (c: SeedCtx): Consent[] => [
  { childId: ID.ethan, verifiedBy: ID.michael, noticeDate: c.day(-90) },
  { childId: ID.mia, verifiedBy: ID.sarah, noticeDate: c.day(-90) },
];

export const seedMailboxes = (c: SeedCtx): Mailbox[] => [
  { id: 'mb_michael', address: profile.email, ownerId: ID.michael, connectedAt: c.at(-60, 9, 12), lastSync: c.past(0, 7, 55), status: 'connected' },
  { id: 'mb_sarah', address: 'sarah@example.com', ownerId: ID.sarah, connectedAt: c.at(-45, 20, 3), lastSync: c.past(0, 7, 55), status: 'connected' },
];

export const seedTokens = (c: SeedCtx): PhoneToken[] => [
  { id: 'tk_michael', device: 'Michael’s iPhone', ownerId: ID.michael, createdAt: c.at(-40, 18, 20), lastUsed: c.past(0, 9, 41) },
  { id: 'tk_sarah', device: 'Sarah’s iPhone', ownerId: ID.sarah, createdAt: c.at(-38, 21, 5), lastUsed: c.at(-2, 16, 12) },
  { id: 'tk_ipad', device: 'Kitchen iPad', ownerId: ID.sarah, createdAt: c.at(-120, 10, 0), lastUsed: c.at(-34, 8, 30), revokedAt: c.at(-30, 9, 0) },
];

export const seedWatchers = (c: SeedCtx): Watcher[] => [
  { id: 'w_inn', label: 'Adobe Court Inn · rates for the trip dates', url: 'https://adobecourt.example/rates', spaceId: 'travel', since: c.at(-6, 21, 0), lastChecked: c.past(0, 6, 0), status: 'watching' },
  { id: 'w_lakeside', label: 'Lakeside High · school calendar', url: 'https://lakesidehigh.example/calendar', spaceId: 'education', since: c.at(-50, 9, 0), lastChecked: c.past(0, 6, 0), status: 'watching' },
  { id: 'w_lunch', label: 'Riverside Elementary · lunch menu', url: 'https://riverside-elem.example/lunch', spaceId: 'education', since: c.at(-50, 9, 5), lastChecked: c.at(-1, 6, 0), status: 'watching' },
];

export const seedTelegram = (c: SeedCtx): TelegramLink => ({
  bot: '@CarterFamilyOS_bot',
  devices: [{ id: 'tg_michael', label: 'Michael’s phone', ownerId: ID.michael, linkedAt: c.at(-30, 19, 40) }],
});

export const seedToggles = (): HouseholdToggle[] => [
  { id: 'childrenNotices', label: 'Children’s notices', explain: 'Notices about Ethan and Mia are shown to both guardians. Turn off to show each notice only to the guardian it was sent to.', on: true },
  { id: 'weeklyDigest', label: 'Weekly digest', explain: 'A short summary every Sunday evening of what arrived and what is still waiting.', on: true },
  { id: 'calendarSync', label: 'Calendar sync', explain: 'Accepted dates are written to the family calendar. Nothing is written until someone accepts it.', on: true },
  { id: 'localModel', label: 'Local model', explain: 'Read notices with a model that runs on this household’s own computer instead of a hosted one. Slower, and nothing leaves the house.', on: false },
  { id: 'picturesByModel', label: 'Pictures read by your model', explain: 'Let the model read photos and screenshots you share (for example a school app screenshot). Off means pictures are kept but not read.', on: true },
  { id: 'holidaysAutoAccept', label: 'Holidays accept themselves', explain: 'School holidays from a school you added go on the calendar without asking. Everything else still waits for a person.', on: false },
  { id: 'receiptsSettleBills', label: 'Receipts settle bills', explain: 'When a receipt matches a bill exactly, mark the bill as paid. FamilyOS never pays anything itself.', on: true },
  { id: 'billReminders', label: 'Bill reminders', explain: 'A reminder the day before a bill is due. The reminder is all it does.', on: true },
];
