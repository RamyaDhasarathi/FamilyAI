// Desktop data model (MASTER_AGENT.md §9), typed and additive: it lives beside
// the mobile mocks and never changes their shapes. One store (desk/store.ts)
// holds one copy of every record; views derive from it (desk/selectors.ts).
//
// Dates. `Instant` is an ISO string with a zone (`2026-10-28T20:00:00.000Z`).
// `Day` is a calendar date `YYYY-MM-DD` in the household's timezone. A `When`
// is either: timed things carry an Instant, all-day / end-of-day / "no time
// given" things carry a Day. Read them with desk/format.ts (`dayOf`, `fmtTime`…),
// never with `new Date(day)` (that would be UTC midnight).
//
// Money. Amounts are numbers in the household currency. Prose that contains
// an amount uses the token `¤{12450}`; render every desk string with
// `fmtText()` (or the `useDeskFormat()` hook) so changing the one currency
// setting re-formats everything.
import type { AgentId } from '../theme/tokens';

export type { AgentId };
export type SpaceId = AgentId | 'health' | 'travel' | 'investments' | 'memories';

export type Instant = string;
export type Day = string;
export type When = Instant | Day;

// ── People ─────────────────────────────────────────────────────────────

export type Role = 'guardian' | 'adult' | 'child';
export type MemberStatus = 'busy' | 'free' | 'home' | 'away';

export interface Member {
  /** Same ids as the family store (`m_michael` …), so `/family/:id` works. */
  id: string;
  name: string;
  fullName: string;
  initial: string;
  role: Role;
  /** Children are data subjects only: no sign-in of their own. */
  hasAccount: boolean;
  age: number;
  status?: MemberStatus;
  /** One line: what they are on right now. */
  statusLine?: string;
  school?: string;
  grade?: string;
  email?: string;
}

/** "The children" card (School space). */
export interface ChildInfo {
  memberId: string;
  school: string;
  grade: string;
  homeroom: string;
  teacher: string;
}

// ── Notices (everything that arrives) ─────────────────────────────────

export type NoticeSource = 'email' | 'phone' | 'telegram' | 'whatsapp' | 'paste' | 'site';
export type NoticeCategory =
  | 'school' | 'bills' | 'trading' | 'subscription' | 'shopping' | 'receipt'
  | 'promo' | 'newsletter' | 'home' | 'health' | 'travel' | 'family';

export interface Notice {
  id: string;
  source: NoticeSource;
  /** Display name; `senderAddress` when it came by email. */
  sender: string;
  senderAddress?: string;
  receivedAt: Instant;
  title: string;
  /** One line: what it wants from the family. */
  summary: string;
  /** The text FamilyOS read (fictional); proposals quote substrings of it. */
  body: string;
  category: NoticeCategory;
  spaceId?: SpaceId;
  memberIds?: string[];
  attachments?: number;
  /** Held in Quarantine (unknown sender) until a person releases it. */
  quarantined?: boolean;
  /** Who in the household can see it (absent = everyone). */
  visibleTo?: string[];
  /** "Not right?" notes from the family. */
  flags?: { at: Instant; by: string; note: string }[];
  /** Who handles it (Inbox "Handling"); '' = cleared to nobody, absent = the seed's default. */
  handledBy?: string;
}

export interface QuarantineItem {
  id: string;
  noticeId: string;
  heldAt: Instant;
  reason: string;
}

// ── Proposals and what accepting them creates ─────────────────────────

export type ProposalKind = 'task' | 'calendar' | 'reminder' | 'payment' | 'errand';
export type DueKind = 'time' | 'allDay' | 'eod' | 'notSpecified';
export type ProposalState = 'proposed' | 'accepted' | 'dismissed' | 'missed' | 'changed';

export interface Proposal {
  id: string;
  noticeId: string;
  kind: ProposalKind;
  /** The agent it belongs to once accepted (filters, colours, "Open {Agent}"). */
  agent: AgentId;
  spaceId?: SpaceId;
  title: string;
  /** Instant when dueKind is 'time', otherwise a Day; absent = no date. */
  due?: When;
  dueKind?: DueKind;
  forMemberId?: string;
  state: ProposalState;
  createdAt: Instant;
  /** Exact substring of the notice body it was read from ("Read from this notice"). */
  quote?: string;
  /** state 'changed': what the notice said before it was updated. */
  changedFrom?: { due?: When; dueKind?: DueKind; title?: string };
  /** Payment proposals: the amount (never paid by FamilyOS). */
  amount?: number;
  decidedAt?: Instant;
  decidedBy?: string;
  /** Records created on accept (Undo removes them). */
  created?: { agendaId?: string; todoId?: string; errandId?: string };
  /** State before the last decision (Undo restores it). */
  prevState?: ProposalState;
  /** What the last accept changed, so Undo can put it back exactly. */
  lastDecision?: { createdAgendaId?: string; createdTodoId?: string; moved?: { agendaId: string; when: When; end?: Instant } };
}

export type AgendaKind = 'event' | 'visit' | 'delivery' | 'bill' | 'update' | 'reminder';

/** Something on the family's day: calendar events, visits, deliveries, bills due, agent updates, reminders. */
export interface AgendaItem {
  id: string;
  agent: AgentId;
  spaceId?: SpaceId;
  kind: AgendaKind;
  title: string;
  /** Short chip text for the agent chips on Today ("Electrician 4 pm"). */
  short?: string;
  when: When;
  dueKind: DueKind;
  end?: Instant;
  memberIds?: string[];
  place?: string;
  /** Key/value rows for Details ▾. */
  details?: [string, string][];
  createdAt: Instant;
  /** kind 'reminder': the Day it reminds about (e.g. tomorrow's final). */
  remindsOf?: Day;
  noticeId?: string;
  proposalId?: string;
  done?: boolean;
}

export interface Todo {
  id: string;
  title: string;
  due?: When;
  dueKind?: DueKind;
  ownerId: string;
  onCalendar?: boolean;
  done: boolean;
  doneAt?: Instant;
  agent?: AgentId;
  spaceId?: SpaceId;
  planId?: string;
  proposalId?: string;
  noticeId?: string;
  createdAt: Instant;
}

/** "FamilyOS noticed": two records that cannot both happen. */
export interface ConflictFix {
  id: string;
  label: string;
  /** What changes: the agenda item and its new time. */
  agendaId: string;
  newWhen: When;
  newEnd?: Instant;
}

export interface Conflict {
  id: string;
  aId: string;
  bId: string;
  title: string;
  message: string;
  fixes: ConflictFix[];
  resolvedAt?: Instant;
  resolvedBy?: string;
  /** For Undo: the moved item's previous time. */
  undo?: { agendaId: string; when: When; end?: Instant };
}

// ── Errands (a booking or purchase, written down in full first) ──────

export type ErrandStatus = 'proposed' | 'approved' | 'done' | 'cancelled';

export interface ErrandStep {
  text: string;
  at: Instant;
  /** Placeholder screenshot id (no real screenshots in the mock). */
  image?: string;
}

/** The written-down fields; the fingerprint covers exactly these. */
export interface ErrandTerms {
  what: string;
  when: string;
  where: string;
  atMost: number;
  paidBy: string;
  card: string;
  stopsIf: string;
}

export interface Errand extends ErrandTerms {
  id: string;
  title: string;
  agent: AgentId;
  status: ErrandStatus;
  fingerprint: string;
  /** Fingerprint the guardian approved; approval holds only while it matches. */
  approvedFingerprint?: string;
  approvedBy?: string;
  approvedAt?: Instant;
  requestedBy: string;
  createdAt: Instant;
  steps: ErrandStep[];
  noticeId?: string;
  proposalId?: string;
  cancelledReason?: string;
}

// ── Plans (Travel) ────────────────────────────────────────────────────

export interface Booking {
  id: string;
  option: string;
  provider: string;
  estCost: number;
  sourceSnippet: string;
  sourceUrl: string;
  watch: 'watching · not read yet' | 'watching · read' | 'not watched';
  booked: boolean;
  noticeId?: string;
}

export interface Plan {
  id: string;
  title: string;
  status: 'draft' | 'done' | 'dropped';
  start: Day;
  end: Day;
  budget: number;
  authorId: string;
  summary: string;
  itinerary: { day: number; date: Day; title: string; text: string }[];
  bookings: Booking[];
  /** One store: the plan's to-dos live in `todos` with this planId (MASTER §9 rule). */
  todoIds: string[];
  noticeIds: string[];
}

// ── Money, investments, groceries ─────────────────────────────────────

export interface RecurringMerchant {
  id: string;
  merchant: string;
  kind: 'subscription' | 'bill' | 'insurance' | 'loan';
  cadence: 'weekly' | 'monthly' | 'yearly';
  amount: number;
  last: Day;
  next: Day;
  spaceId: SpaceId;
  url: string;
  noticeId: string;
}

export interface Statement {
  id: string;
  institution: string;
  kind: 'statement' | 'trade' | 'dividend' | 'notice';
  title: string;
  summary: string;
  date: Day;
  amount?: number;
  noticeId: string;
}

export interface OrderAgainItem {
  id: string;
  item: string;
  store: string;
  lastDate: Day;
  price: number;
  url: string;
  noticeId: string;
}

// ── Record history and the audit log ──────────────────────────────────

export type RecordType = 'agenda' | 'todo' | 'plan' | 'member' | 'errand';

export interface Revision {
  id: string;
  at: Instant;
  actor: string;
  recordType: RecordType;
  recordId: string;
  recordLabel: string;
  field: string;
  before: string | number | boolean | null;
  after: string | number | boolean | null;
  revertible: boolean;
  revertedAt?: Instant;
  /** Set on a revision that is itself a revert. */
  revertOf?: string;
}

export interface AuditEntry {
  id: string;
  at: Instant;
  /** A member id, or 'FamilyOS' for the assistant. */
  actor: string;
  sentence: string;
  /** Raw event code, e.g. `proposal.accepted`. */
  code: string;
  raw?: Record<string, unknown>;
}

// ── Connections and settings ──────────────────────────────────────────

export interface Mailbox {
  id: string;
  address: string;
  ownerId: string;
  connectedAt: Instant;
  lastSync?: Instant;
  status: 'connected' | 'disconnected';
}

export interface PhoneToken {
  id: string;
  device: string;
  ownerId: string;
  createdAt: Instant;
  lastUsed?: Instant;
  revokedAt?: Instant;
}

export interface Watcher {
  id: string;
  label: string;
  url: string;
  spaceId: SpaceId;
  since: Instant;
  lastChecked?: Instant;
  status: 'watching' | 'stopped';
}

export type ToggleId =
  | 'childrenNotices' | 'weeklyDigest' | 'calendarSync' | 'localModel'
  | 'picturesByModel' | 'holidaysAutoAccept' | 'receiptsSettleBills' | 'billReminders';

export interface HouseholdToggle {
  id: ToggleId;
  label: string;
  explain: string;
  on: boolean;
}

export interface Consent {
  childId: string;
  verifiedBy: string;
  noticeDate: Day;
  withdrawnAt?: Instant;
}

export interface TelegramLink {
  bot: string;
  devices: { id: string; label: string; ownerId: string; linkedAt: Instant }[];
}

/** "Collect from a site": a short sitting the family opens; no password, no stored session. */
export interface Sitting {
  id: string;
  purpose: string;
  site: string;
  minutes: number;
  openedAt: Instant;
  openedBy: string;
}

export interface Space {
  id: SpaceId;
  name: string;
  /** CSS colour (an agent token where one exists). */
  color: string;
  /** lucide-react icon name. */
  icon: string;
  agent?: AgentId;
  route: string;
  description: string;
}

export interface HouseholdSettings {
  name: string;
  country: string;
  /** IANA zone; defaults to the browser's own zone at load. */
  timezone: string;
  /** ISO 4217; the one setting that switches every amount (USD default, INR works). */
  currency: string;
  familyAddress: string;
}

export interface Weather {
  now: string;
  detail: string;
}

/** Everything the desk store holds (exportAll() writes exactly this). */
export interface DeskData {
  settings: HouseholdSettings;
  members: Member[];
  children: ChildInfo[];
  spaces: Space[];
  notices: Notice[];
  quarantine: QuarantineItem[];
  proposals: Proposal[];
  agenda: AgendaItem[];
  todos: Todo[];
  conflicts: Conflict[];
  errands: Errand[];
  plans: Plan[];
  recurring: RecurringMerchant[];
  statements: Statement[];
  orderAgain: OrderAgainItem[];
  revisions: Revision[];
  audit: AuditEntry[];
  mailboxes: Mailbox[];
  phoneTokens: PhoneToken[];
  watchers: Watcher[];
  toggles: HouseholdToggle[];
  consents: Consent[];
  telegram: TelegramLink;
  sittings: Sitting[];
  weather: Weather;
}
