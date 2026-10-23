// ALL dummy copy and numbers shown by the app (AGENT.md §10), transcribed
// from the reference video. Change the currency symbol or names here once and
// every screen follows.
import type { AgentId } from '../theme/tokens';
import type {
  AgentCard,
  AgentDetail,
  FamilyMember,
  NeedsItem,
  Profile,
  SummaryMode,
  TodayBrief,
  WalkthroughStep,
} from '../services/interfaces';

export const CURRENCY = '$';
const C = CURRENCY;

export const NAMES = { me: 'Michael', partner: 'Sarah', son: 'Ethan', daughter: 'Mia', grandma: 'Linda' };
const { me, son, daughter } = NAMES;

export const profile: Profile = {
  name: me,
  initial: me[0],
  plan: 'Family plan · 5 agents',
  email: 'michael@example.com',
};

/** Video default: the summary button starts in Listen (spoken walkthrough). */
export const defaultSummaryMode: SummaryMode = 'listen';

export const family: FamilyMember[] = [
  { id: 'm1', name: me, relationship: 'You', age: 42 },
  { id: 'm2', name: NAMES.partner, relationship: 'Partner', age: 40 },
  { id: 'm3', name: son, relationship: 'Son', age: 16 },
  { id: 'm4', name: daughter, relationship: 'Daughter', age: 11 },
  { id: 'm5', name: NAMES.grandma, relationship: 'Mother', age: 68 },
];

export const agentNames: Record<AgentId, string> = {
  finance: 'Finance',
  education: 'Education',
  household: 'Household',
  grocery: 'Grocery',
  calendar: 'Calendar',
};

export const copy = {
  appName: 'FamilyOS',
  greeting: { morning: 'Good morning', afternoon: 'Good afternoon', evening: 'Good evening' },
  summaryPrefix: "Today's summary",
  allClear: 'all clear',
  calmHeadline: 'Everything is on track.',
  askPlaceholder: 'Ask FamilyOS',
  askAgent: (agent: string) => `Ask ${agent} anything`,
  chatTitle: 'Ask FamilyOS',
  chatAgentTitle: (agent: string) => `Ask ${agent}`,
  typeMessage: 'Type a message',
  close: 'Close',
  later: 'Later',
  done: 'Done',
  doneSwipe: '✓ DONE',
  laterSwipe: 'LATER ›',
  snoozed: 'Snoozed until tonight',
  more: (n: number) => `+${n} more`,
  needsTitle: (n: number) => `Needs you · ${n}`,
  todayTitle: 'Today',
  todaySection: 'TODAY',
  yourAgents: 'YOUR AGENTS',
  whatIDid: 'WHAT I DID',
  needsSection: 'NEEDS YOU',
  needsOpen: (n: number) => `${n} OPEN`,
  todaysSummary: "Today's summary",
  summaryCardCalm: 'All clear · tap to read',
  summaryCardBusy: (n: number, word: string) => `${n} ${word} · tap to read`,
  undo: 'Undo',
  undone: 'Undone',
  details: 'Details',
  askAboutThis: 'Ask about this',
  tellMeMore: (title: string) => `Tell me more about: ${title}`,
  undoneToast: 'Undone. Nothing else changed.',
  summaryModeLabel: { listen: 'Listen', read: 'Read' } as Record<SummaryMode, string>,
  summaryModeToast: {
    read: 'The summary button now opens the written summary',
    listen: 'The summary button now plays the summary aloud',
  } as Record<SummaryMode, string>,
  listening: 'Listening…',
  heardTranscript: 'What needs me today?',
  allDoneToast: 'All clear. Nice work.',
  loading: [`Waking up your agents`, 'Syncing the family calendar', `Building ${me}'s home`],
  login: {
    title: 'Welcome back',
    subtitle: 'Log in to your family pod',
    email: 'Email or mobile',
    password: 'Password',
    keep: 'Keep me logged in',
    forgot: 'Forgot password?',
    forgotToast: 'A reset link is on its way to your email',
    submit: 'Log in',
    otp: 'Log in with a one-time code',
    google: 'Continue with Google',
    otpToast: 'One-time codes arrive with the real backend',
    note: 'Prototype: any credentials work.',
  },
  profileMenu: {
    rows: ['Profile', 'Family members', 'Agents and permissions', 'Notifications', 'Privacy and data'],
    summaryButton: 'Summary button',
    settings: 'Settings',
    help: 'Help and feedback',
    switchAccount: 'Log in or switch account',
    logout: 'Log out',
  },
  settings: {
    title: 'Settings',
    demoScenario: 'Demo scenario',
    demoHint: 'Dev builds only. Long-press the date on Home to cycle.',
    reduceGraphics: 'Low-power graphics',
    reduceGraphicsHint: 'Fewer facets and particles. Turned on automatically on slow devices.',
    spoken: 'Spoken summary',
    version: 'Version',
    versionValue: '1.0.0 · demo data',
    summarySection: 'SUMMARY',
    graphicsSection: 'GRAPHICS',
    devSection: 'DEVELOPER',
    privacySection: 'PRIVACY',
    accountSection: 'ACCOUNT',
    // Carried over from the existing iPhone app's Settings → Privacy.
    privacy: [
      ['Private by default', 'What you share is yours alone unless you share it with the household. A child’s notices follow the consent their guardians set.'],
      ['What this phone keeps', 'Your sign-in, kept securely. Anything done with no signal, until it is sent. No notice text, no pictures.'],
      ['What FamilyOS never does', 'Hold a card, a password or a bank login. Pay. Act without showing you exactly what first.'],
    ] as [string, string][],
  },
  family: {
    title: 'Family members',
    section: 'YOUR FAMILY POD',
    stage: (n: number, name: string) => `Stage ${n} · ${name}`,
    age: (rel: string, age: number) => `${rel} · ${age}`,
  },
  placeholder: (title: string) => `${title} will connect to your FamilyOS account when the backend is wired up.`,
  scenarioLabels: { calm: 'Calm', insight: 'Insight', headsup: 'Heads-up', urgent: 'Urgent' },
};

/** Status label during a walkthrough, e.g. "TODAY · FINANCE · 2 OF 7". */
export const walkLabel = (agent: AgentId, i: number, n: number, filtered: boolean) =>
  filtered
    ? `${agentNames[agent].toUpperCase()} · ${i} OF ${n}`
    : `TODAY · ${agentNames[agent].toUpperCase()} · ${i} OF ${n}`;

export const todayBrief: TodayBrief = {
  commute: {
    section: 'TOMORROW MORNING',
    label: 'COMMUTE TO THE OFFICE',
    title: 'Leave by 8:10',
    detail: '32 min via Route 9, light traffic',
    alt: 'Alt: I-95 · 38 min',
  },
  weather: { label: 'WEATHER', value: '68°F', detail: 'Rain after 3 pm. Pack umbrellas for pickup.' },
  firstEvent: { label: 'FIRST EVENT', value: '9:30 am', detail: 'Dentist, 12 min from home' },
  items: [
    { id: 't1', agent: 'household', text: 'The electrician arrives at 4 pm.' },
    { id: 't2', agent: 'finance', text: `Reserve is ${C}12,450, up 4.2% this month.` },
    { id: 't3', agent: 'education', text: `${son}'s math final is tomorrow.` },
    { id: 't4', agent: 'grocery', text: `Your cart is ready: 14 items, ${C}86.40.` },
    { id: 't5', agent: 'finance', text: `The mortgage, ${C}2,150, is due Oct 28.` },
    { id: 't6', agent: 'household', text: 'Furnace service is booked for Nov 9.' },
    { id: 't7', agent: 'calendar', text: `${daughter}'s recital is Saturday at 2 pm.` },
  ],
};

/** Agent-filtered walkthroughs (long-press or tap on a satellite). */
export const agentWalkthroughs: Record<AgentId, WalkthroughStep[]> = {
  education: [
    { agent: 'education', text: `${son} and ${daughter} are on schedule.` },
    { agent: 'education', text: `${son}'s math final is tomorrow.` },
    { agent: 'education', text: `${daughter}'s science project is 90% done, due Friday.` },
    { agent: 'education', text: 'The parent-teacher conference is booked for Nov 6.' },
  ],
  finance: [
    { agent: 'finance', text: `Reserve is ${C}12,450, up 4.2% this month.` },
    { agent: 'finance', text: `The mortgage, ${C}2,150, is due Oct 28.` },
    { agent: 'finance', text: `I moved ${son}'s coaching to a lower tier. It saves ${C}120 a month.` },
  ],
  household: [
    { agent: 'household', text: 'The electrician arrives at 4 pm.' },
    { agent: 'household', text: 'Furnace service is booked for Nov 9.' },
    { agent: 'household', text: 'All home sensors are dry and steady.' },
  ],
  grocery: [
    { agent: 'grocery', text: `Your cart is ready: 14 items, ${C}86.40.` },
    { agent: 'grocery', text: 'Delivery is booked for 6:00 pm.' },
  ],
  calendar: [
    { agent: 'calendar', text: 'You have 3 events today.' },
    { agent: 'calendar', text: `Your 2 pm client call overlaps ${son}'s final.` },
    { agent: 'calendar', text: `${daughter}'s recital is Saturday at 2 pm.` },
  ],
};

/** Every item that can need the user. Scenarios pick subsets (mocks/scenarios.ts). */
export const needsItems: NeedsItem[] = [
  { id: 'n1', severity: 'urgent', agent: 'calendar', time: 'NOW', text: `Your 2 pm client call overlaps ${son}'s final.`, action: { id: 'move-call', label: 'Move call to 3:30' }, priority: 2 },
  { id: 'n2', severity: 'urgent', agent: 'finance', time: '3 MIN AGO', text: `A ${C}1,240 charge on the card ending 4417 looks unfamiliar.`, action: { id: 'review-charge', label: 'Review charge' }, priority: 1 },
  { id: 'n3', severity: 'urgent', agent: 'household', time: '1 MIN AGO', text: 'The basement water sensor just tripped.', action: { id: 'shut-valve', label: 'Shut off valve' }, priority: 3 },
  { id: 'n4', severity: 'headsup', agent: 'household', time: '3:10 PM', text: 'The electrician arrives at 4 pm.', action: { id: 'confirm', label: 'Confirm' }, priority: 1 },
  { id: 'n5', severity: 'headsup', agent: 'calendar', time: 'YESTERDAY', text: 'Dentist tomorrow at 9:30 am.', action: { id: 'add-reminder', label: 'Add reminder' }, priority: 2 },
  { id: 'n6', severity: 'headsup', agent: 'education', time: 'TODAY', text: `${daughter}'s science project is due Friday.`, action: { id: 'see-checklist', label: 'See checklist' }, priority: 3 },
  { id: 'n7', severity: 'headsup', agent: 'grocery', time: '9:40 AM', text: 'Milk and eggs are running low.', action: { id: 'add-to-cart', label: 'Add to cart' }, priority: 4 },
  { id: 'n8', severity: 'headsup', agent: 'finance', time: 'TODAY', text: `Car insurance, ${C}184, renews Nov 2.`, action: { id: 'review', label: 'Review' }, priority: 5 },
  { id: 'n9', severity: 'headsup', agent: 'education', time: 'TODAY', text: `${son}'s field trip form is due Wednesday.`, action: { id: 'sign-form', label: 'Sign form' }, priority: 6 },
  { id: 'n10', severity: 'insight', agent: 'education', time: 'TODAY', text: `${son} is ahead in math this month.`, action: { id: 'got-it', label: 'Got it' }, priority: 2 },
  { id: 'n11', severity: 'insight', agent: 'finance', time: 'TODAY', text: `You could save ${C}180 a month on subscriptions.`, action: { id: 'see-how', label: 'See how' }, priority: 1 },
  { id: 'n12', severity: 'insight', agent: 'calendar', time: 'TODAY', text: 'You have 2.5 free hours on Thursday afternoon.', action: { id: 'block-it', label: 'Block it' }, priority: 3 },
  { id: 'n13', severity: 'insight', agent: 'grocery', time: 'YESTERDAY', text: `Store-brand pasta sauce would save ${C}4.20 a week.`, action: { id: 'swap', label: 'Swap' }, priority: 4 },
];

export const dashboardCards: AgentCard[] = [
  { agent: 'finance', status: `${C}12,450 reserve · up 4.2%` },
  { agent: 'education', status: `${son} and ${daughter} on schedule` },
  { agent: 'household', status: 'Electrician at 4 pm' },
  { agent: 'calendar', status: '3 events today' },
  { agent: 'grocery', status: `Cart ready · 14 items · ${C}86.40` },
];

export const agentDetails: Record<AgentId, AgentDetail> = {
  finance: {
    agent: 'finance',
    title: 'Finance',
    subtitle: 'On track this month',
    hero: {
      kind: 'sparkline',
      label: 'Projected reserve',
      value: `${C}12,450`,
      delta: '▲ 4.2% this month',
      up: true,
      series: [10.2, 10.22, 10.25, 10.24, 10.27, 10.3, 10.29, 10.31, 10.6, 10.95, 11.05, 11.1, 11.18, 11.3, 11.45, 11.62, 11.8, 12.05, 12.2, 12.45],
    },
    stats: [
      { label: 'Invested', value: 18.4, prefix: C, suffix: 'k', decimals: 1 },
      { label: 'Est. expenses', value: 4.2, prefix: C, suffix: 'k', decimals: 1 },
      { label: 'Optimized', value: 620, prefix: C },
    ],
    timeline: [
      {
        id: 'f1',
        when: 'Today · 9:12 am',
        title: `Moved ${son}'s coaching to a lower tier`,
        description: `Saves ${C}120 a month. Classes and materials stay exactly the same.`,
        rows: [
          ['Saves', `${C}120 a month`],
          ['Takes effect', 'Nov 1'],
          ['Checked with', 'Coach Rivera'],
          ['Done by', 'Finance agent'],
        ],
        undoable: true,
      },
      {
        id: 'f2',
        when: 'Yesterday',
        title: `Invested ${C}1,500 of surplus`,
        description: `Added to your index fund. Within your ${C}2,000 auto-invest limit.`,
        rows: [
          ['Amount', `${C}1,500.00`],
          ['Fund', 'Total Market Index'],
          ['Auto-invest limit', `${C}2,000 a month`],
          ['Time', 'Oct 19, 4:02 pm'],
        ],
      },
      {
        id: 'f3',
        when: 'Oct 4',
        title: `Paid ${daughter}'s lab fees and the electric bill`,
        description: `Bundled into one payment to avoid late charges. Saved ${C}25.`,
        rows: [
          ['Lab fees', `${C}65.00`],
          ['Electric bill', `${C}142.30`],
          ['Late fees avoided', `${C}25.00`],
          ['Paid from', 'Checking'],
        ],
      },
      {
        id: 'f4',
        when: 'Oct 2',
        title: 'Caught a duplicate Instacart charge',
        description: `Refund of ${C}85 secured from the merchant.`,
        rows: [
          ['Refunded', `${C}85.00`],
          ['Status', 'Complete'],
        ],
      },
    ],
    chips: ['Show upcoming bills', `Move ${C}500 to savings`, 'How much did we save?'],
  },
  calendar: {
    agent: 'calendar',
    title: 'Calendar',
    subtitle: '3 events today',
    hero: { kind: 'bars', label: 'Today', value: '3 events', note: '1 clash needs you', bars: [0.32, 0.72, 0.55, 0.55, 0.92, 0.34, 0.14], todayIndex: 6 },
    stats: [
      { label: 'Free time', value: 2.5, suffix: ' h', decimals: 1 },
      { label: 'Clashes', value: 1 },
      { label: 'This week', value: 14 },
    ],
    timeline: [
      {
        id: 'c1',
        when: 'Today · 9:05 am',
        title: `Spotted a clash with ${son}'s final`,
        description: 'Your 2 pm client call overlaps his final. Moving it to 3:30 works for everyone.',
        rows: [
          ['Client call', '2:00 pm'],
          [`${son}'s final`, '2:00 pm'],
          ['Suggested', '3:30 pm'],
          ['Done by', 'Calendar agent'],
        ],
        undoable: true,
      },
      {
        id: 'c2',
        when: 'Yesterday',
        title: 'Moved the dentist to Thursday',
        description: 'Thursday at 9:30 am, clear of both school runs.',
        rows: [
          ['New time', 'Thu, 9:30 am'],
          ['Office', 'Lakeside Dental'],
          ['Reminder', '1 day before'],
        ],
      },
      {
        id: 'c3',
        when: 'Oct 4',
        title: `Added ${daughter}'s recital`,
        description: 'Saturday at 2 pm. Directions and parking info attached.',
        rows: [
          ['When', 'Sat, 2:00 pm'],
          ['Where', 'Riverside Hall'],
        ],
      },
      {
        id: 'c4',
        when: 'Oct 2',
        title: 'Declined a duplicate invite',
        description: 'The same meeting was sent twice, so I kept one.',
        rows: [
          ['Meeting', 'Quarterly review'],
          ['Kept', 'Tue, 10 am'],
        ],
      },
    ],
    chips: ["What's on today?", 'Move my 2 pm call', 'Find a free slot'],
  },
  grocery: {
    agent: 'grocery',
    title: 'Grocery',
    subtitle: 'Cart ready · 14 items',
    hero: {
      kind: 'sparkline',
      label: "This week's cart",
      value: `${C}86.40`,
      delta: `▼ ${C}9 vs last week`,
      up: false,
      series: [95.4, 95.1, 94.2, 92.8, 91.5, 90.9, 90.2, 89.1, 88.6, 88.9, 88.4, 87.6, 87.1, 86.9, 86.4],
    },
    stats: [
      { label: 'Items', value: 14 },
      { label: 'Saved', value: 11, prefix: C },
      { label: 'Delivery', value: 0, text: '6:00 pm' },
    ],
    timeline: [
      {
        id: 'g0',
        when: 'Today · 7:20 am',
        title: 'Built your weekly cart',
        description: 'Based on your last six orders and what is running low.',
        rows: [
          ['Items', '14'],
          ['Total', `${C}86.40`],
          ['Delivery', 'Today, 6:00 pm'],
        ],
        undoable: true,
      },
      {
        id: 'g1',
        when: 'Yesterday',
        title: `Swapped a brand to save ${C}4.20`,
        description: 'Same size and ingredients, lower price.',
        rows: [
          ['Item', 'Pasta sauce'],
          ['Saved', `${C}4.20`],
          ['Rating', '4.7 stars'],
        ],
      },
      {
        id: 'g2',
        when: 'Oct 4',
        title: 'Added milk and eggs',
        description: 'Both were running low based on your usual pace.',
        rows: [
          ['Milk', '1 gallon'],
          ['Eggs', '1 dozen'],
          ['Added', `${C}7.80`],
        ],
      },
      {
        id: 'g3',
        when: 'Oct 2',
        title: 'Flagged a duplicate charge',
        description: `Instacart refunded ${C}85 within a day.`,
        rows: [
          ['Refunded', `${C}85.00`],
          ['Status', 'Complete'],
        ],
      },
    ],
    chips: ["What's in my cart?", 'Add milk', 'When is delivery?'],
  },
  education: {
    agent: 'education',
    title: 'Education',
    subtitle: `${son} and ${daughter} on schedule`,
    hero: {
      kind: 'progress',
      label: 'This term',
      value: 'On schedule',
      note: '1 deadline this week',
      items: [
        { name: `${son} · Math`, pct: 0.92 },
        { name: `${daughter} · Science project`, pct: 0.9 },
        { name: `${son} · Reading list`, pct: 0.68 },
      ],
    },
    stats: [
      { label: 'Due this week', value: 3 },
      { label: 'Avg. grade', value: 0, text: 'A-' },
      { label: 'Conferences', value: 1 },
    ],
    timeline: [
      {
        id: 'e1',
        when: 'Today · 8:40 am',
        title: 'Booked the parent-teacher conference',
        description: 'Nov 6 at 5:30 pm, after your last meeting.',
        rows: [
          ['When', 'Nov 6, 5:30 pm'],
          ['With', 'Ms. Alvarez'],
          ['Done by', 'Education agent'],
        ],
        undoable: true,
      },
      {
        id: 'e2',
        when: 'Yesterday',
        title: `Shared a study plan for ${son}'s final`,
        description: 'Three short sessions, built from his last two quizzes.',
        rows: [
          ['Sessions', '3 × 40 min'],
          ['Focus', 'Algebra, functions'],
        ],
      },
      {
        id: 'e3',
        when: 'Oct 4',
        title: `Ordered supplies for ${daughter}'s project`,
        description: `Poster board and paint, delivered Tuesday. ${C}18.60.`,
        rows: [
          ['Cost', `${C}18.60`],
          ['Arrived', 'Oct 6'],
        ],
      },
    ],
    chips: [`How is ${son} doing?`, "What's due this week?", 'Book a tutor'],
  },
  household: {
    agent: 'household',
    title: 'Household',
    subtitle: 'Electrician at 4 pm',
    hero: { kind: 'ring', label: 'Home tasks this week', value: '4 of 6 done', note: 'Next: electrician at 4 pm', pct: 0.67 },
    stats: [
      { label: 'Open tasks', value: 2 },
      { label: 'Saved', value: 140, prefix: C },
      { label: 'Sensors', value: 0, text: 'All dry' },
    ],
    timeline: [
      {
        id: 'h1',
        when: 'Today · 10:15 am',
        title: 'Confirmed the electrician for 4 pm',
        description: 'Fixing the hallway circuit. Quote approved within your limit.',
        rows: [
          ['Visit', 'Today, 4:00 pm'],
          ['Quote', `${C}180.00`],
          ['Done by', 'Household agent'],
        ],
        undoable: true,
      },
      {
        id: 'h2',
        when: 'Yesterday',
        title: 'Scheduled furnace service',
        description: 'Nov 9, before the first cold week. Same company as last year.',
        rows: [
          ['When', 'Nov 9, 10:00 am'],
          ['Company', 'Northside Heating'],
        ],
      },
      {
        id: 'h3',
        when: 'Oct 4',
        title: 'Renewed the home warranty',
        description: `Switched to the annual plan and saved ${C}140.`,
        rows: [
          ['Plan', 'Annual'],
          ['Saved', `${C}140.00`],
        ],
      },
    ],
    chips: ['When is the electrician coming?', 'Book a cleaner', 'Any home alerts?'],
  },
};
