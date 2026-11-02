// The desk store's data read from the FamilyOS backend (VITE_FAMILYOS_API=on), in the desk's own shapes so no page
// changes. Field by field this follows famos-notes/WEB_MAPPING.md §2. What the backend has no record for starts
// empty (conflicts: they need a connected calendar) or stays the web app's own (spaces, the bill-reminders switch).
// Lists a member may not read (the audit and Quarantine are a guardian's) come back empty rather than failing.
import { request } from '../../services/api';
import type {
  AgendaItem, AgentId, AuditEntry, ChildInfo, Consent, DeskData, DueKind, Errand, HouseholdToggle, Mailbox, Member, Notice,
  NoticeCategory, NoticeSource, OrderAgainItem, PhoneToken, Plan, Proposal, QuarantineItem, RecurringMerchant, Revision, Sitting,
  SpaceId, Statement, Todo, ToggleId, Watcher, When,
} from '../types';
import { dayKey, zoned } from '../format';
import { seedSpaces, seedToggles } from '../seed/people';

// ── Backend shapes (familyos/models.py), only the fields read here ──────────

interface ApiMember { id: string; display_name: string; role: Member['role']; email?: string | null; phone?: string | null; date_of_birth?: string | null; school?: string | null; class_label?: string | null; joined?: boolean; telegram_linked?: boolean; created_at: string }
interface ApiHousehold { id: string; name: string; inbound_address: string; telegram_bot?: string | null; country: string; timezone: string; currency: string; members: ApiMember[] }
interface InboxRow { id: string; channel: string; received_at: string; filename?: string | null; headline?: string | null; from_label: string; subject_member_ids: string[]; assigned_to?: string | null; attachments: number; preview: string[]; reason?: string | null; category: string; visibility: string }
interface Obligation { id: string; artifact_id: string; claim_id: string; subject_member_id?: string | null; kind: 'task' | 'calendar'; action?: string | null; title: string; due_date?: string | null; due_time?: string | null; status: 'proposed' | 'accepted' | 'dismissed'; decided_by?: string | null; decided_at?: string | null; created_at: string; superseded_at?: string | null }
interface Amendment { id: string; amends_claim_id?: string | null; amends_title?: string | null; amends_date?: string | null; status: string }
interface ApiTodo { id: string; title: string; due_date?: string | null; due_time?: string | null; calendar_event_id?: string | null; assigned_to?: string | null; created_by?: string | null; done_at?: string | null; created_at: string }
interface Money { recurring: { merchant: string; category?: string | null; cadence: string; next_amount?: number | null; last_amount?: number | null; last_date?: string | null; next_date?: string | null; manage_url?: string | null; artifact_id?: string | null }[]; running_low: { item: string; item_key: string; merchant?: string | null; last_on?: string | null; last_amount?: number | null; reorder_url?: string | null; artifact_id?: string | null }[]; usual: { item: string; item_key: string; merchant?: string | null; last_on?: string | null; last_amount?: number | null; reorder_url?: string | null }[]; charges: { artifact_id: string; amount: number }[] }
interface ApiErrand { id: string; service: string; kind: string; title: string; spec: Record<string, unknown>; params_sha256: string; status: string; created_by: string; approved_by?: string | null; approved_at?: string | null; outcome?: { steps?: { at: string; said: string; artifact_id?: string | null }[] | number } | null; error?: string | null; created_at: string }
interface ApiPlan { id: string; title: string; summary?: string | null; brief?: string | null; status: string; starts_on?: string | null; ends_on?: string | null; budget_amount?: number | null; created_by: string; itinerary?: { day: number; date?: string | null; title: string; notes?: string | null }[]; options?: { id: string; label: string; provider?: string | null; estimate?: number | null; url?: string | null; evidence?: { excerpt?: string | null } | null; watch_id?: string | null; page?: { checked_at?: string | null } | null; booked_at?: string | null }[]; todos?: { id: string }[] }
interface ApiAudit { id: number; actor_kind: string; actor_member_id?: string | null; action: string; detail?: Record<string, unknown> | null; at: string; said: string; target_type?: string | null; target_id?: string | null }
interface ApiActivity { id: number; at: string; who?: string | null; said: string; action: string; target?: { type?: string | null; id?: string | null } | null; receipt?: { observed?: string | null } | null; undo?: unknown }
interface ApiArtifact { id: string; received_at: string; quarantine_reason?: string | null; source?: { from?: string; subject?: string } | null; channel: string; category: string }
interface ApiDevice { id: string; label: string; created_at: string; last_used_at?: string | null }
interface ApiWatch { id: string; url: string; label?: string | null; last_checked_at?: string | null; paused_at?: string | null; expires_at?: string | null }
interface ApiRule { key: string; title: string; sentence: string; on: boolean }
interface ApiConsent { id: string; subject_member_id: string; guardian_member_id: string; granted_at: string; withdrawn_at?: string | null }
interface ApiMailbox { id: string; email: string; connected_at: string; last_polled_at?: string | null; disconnected_at?: string | null }
interface ApiHarvest { id: string; label: string; allow_hosts: string[]; started_at: string; expires_at: string }
interface ApiSchool { id: string; name: string; portal_url?: string | null; created_at: string }
interface ApiMe { id: string; role: Member['role'] }

// ── Words between the two models ────────────────────────────────────────────

/** Backend category (categories.py) → the desk's space. */
const SPACE: Record<string, SpaceId> = {
  school: 'education', bills: 'finance', insurance: 'finance', subscriptions: 'finance', banking: 'investments', trading: 'investments',
  food: 'grocery', shopping: 'grocery', home: 'household', government: 'household', medical: 'health', travel: 'travel',
};
/** Backend category → the desk's notice category. */
const CATEGORY: Record<string, NoticeCategory> = {
  school: 'school', bills: 'bills', insurance: 'bills', banking: 'trading', trading: 'trading', subscriptions: 'subscription', shopping: 'shopping',
  food: 'receipt', home: 'home', government: 'home', medical: 'health', travel: 'travel', promo: 'promo', newsletter: 'newsletter',
};
const AGENT_OF: Record<SpaceId, AgentId> = {
  finance: 'finance', education: 'education', household: 'household', grocery: 'grocery', calendar: 'calendar',
  health: 'household', travel: 'calendar', investments: 'finance', memories: 'calendar',
};
const WORDS: [RegExp, AgentId][] = [
  [/\b(fee|fees|bill|invoice|premium|pay|paid|payment|₹|rs\.?|inr|renewal|emi)\b/i, 'finance'],
  [/\b(school|class|exam|ptm|homework|circular|term|teacher|uniform)\b/i, 'education'],
  [/\b(grocery|groceries|milk|vegetables|order|delivery|cart|refill)\b/i, 'grocery'],
  [/\b(trip|flight|train|meeting|appointment|holiday|event|party|birthday)\b/i, 'calendar'],
];
const agentByWords = (text: string): AgentId => WORDS.find(([re]) => re.test(text))?.[1] ?? 'household';

function sourceOf(channel: string): NoticeSource {
  if (channel.startsWith('email') || channel.startsWith('gmail')) return 'email';
  if (channel.startsWith('telegram')) return 'telegram';
  if (channel.startsWith('whatsapp')) return 'whatsapp';
  if (channel === 'share') return 'phone';
  if (channel === 'harvest') return 'site';
  return 'paste';
}

/** Desk ToggleId ↔ backend rule key (rules.py). The bill-reminders switch has no rule: it stays the web app's. */
export const RULE_KEY: Partial<Record<ToggleId, string>> = {
  childrenNotices: 'childrens_notices_shared', weeklyDigest: 'weekly_digest', calendarSync: 'calendar_follows_decisions', localModel: 'local_models',
  picturesByModel: 'pictures_by_model', holidaysAutoAccept: 'holidays_accepted', receiptsSettleBills: 'receipts_close_bills',
};

/** ISO-2 ↔ the country name the desk shows (the backend keeps the code). */
export const COUNTRIES: Record<string, string> = { IN: 'India', US: 'United States', GB: 'United Kingdom', AE: 'United Arab Emirates', SG: 'Singapore', CA: 'Canada', AU: 'Australia' };

const ageOf = (dob: string | null | undefined, now: Date) => {
  if (!dob) return 0;
  const [y, m, d] = dob.split('-').map(Number);
  let age = now.getFullYear() - y;
  if (now.getMonth() + 1 < m || (now.getMonth() + 1 === m && now.getDate() < d)) age -= 1;
  return Math.max(0, age);
};

/** A backend day + "HH:MM" as the desk's When. */
function whenOf(day: string | null | undefined, time: string | null | undefined, tz: string): { due?: When; dueKind?: DueKind } {
  if (!day) return {};
  if (!time) return { due: day, dueKind: 'allDay' };
  const [h, m] = time.split(':').map(Number);
  return { due: zoned(day, h, m, tz), dueKind: 'time' };
}

const get = <T,>(path: string, fallback: T) => request<T>('GET', path).catch(() => fallback);

/** Ids the write side needs that the desk shapes do not carry. */
export interface ServerIds {
  /** proposal (obligation) id → its claim id, for amendments. */
  claimOf: Record<string, string>;
  /** claim id → the proposed amendment that changes it. */
  amendmentOf: Record<string, string>;
  /** child member id → consent id. */
  consentOf: Record<string, string>;
  /** school name → school id (portals are stored on the school). */
  schoolOf: Record<string, string>;
  /** plan booking id → plan id. */
  planOfBooking: Record<string, string>;
  /** errand id → the backend's params fingerprint (an approval echoes it). */
  paramsOf: Record<string, string>;
  /** the signed-in member's role. */
  role: Member['role'];
}

/** An empty household for the moment before the server has answered (the web app's own parts kept). */
export function emptyDeskData(): DeskData {
  return {
    settings: { name: '', country: '', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, currency: 'INR', familyAddress: '' },
    members: [], children: [], spaces: seedSpaces(), notices: [], quarantine: [], proposals: [], agenda: [], todos: [], conflicts: [], errands: [],
    plans: [], recurring: [], statements: [], orderAgain: [], revisions: [], audit: [], mailboxes: [], phoneTokens: [], watchers: [],
    toggles: seedToggles().map((t) => ({ ...t, on: false })), consents: [], telegram: { bot: '', devices: [] }, sittings: [], weather: { now: '—', detail: '' },
  };
}

export async function loadDeskData(): Promise<{ data: DeskData; actor: string; ids: ServerIds }> {
  const [me, household] = await Promise.all([request<ApiMe>('GET', '/me'), request<ApiHousehold>('GET', '/household')]);
  const [inbox, obligations, amendments, todosRaw, money, errandsRaw, plansRaw, auditRaw, activity, quarantineRaw, devices, watches, rules, consentsRaw, harvests, mailboxesRaw, schools] =
    await Promise.all([
      get<InboxRow[]>('/inbox?days=365&limit=300', []),
      get<Obligation[]>('/obligations?status=&limit=300', []),
      get<Amendment[]>('/amendments?status=&limit=200', []),
      get<ApiTodo[]>('/todos?include_done=true', []),
      get<Money | null>('/money', null),
      get<ApiErrand[]>('/errands', []),
      get<ApiPlan[]>('/plans', []),
      get<ApiAudit[]>('/audit?limit=300', []),
      get<ApiActivity[]>('/activity?limit=100', []),
      get<ApiArtifact[]>('/quarantine', []),
      get<ApiDevice[]>('/devices', []),
      get<ApiWatch[]>('/watches', []),
      get<{ rules: ApiRule[] }>('/household/rules', { rules: [] }),
      get<ApiConsent[]>('/consents', []),
      get<ApiHarvest[]>('/harvests', []),
      get<ApiMailbox[]>('/google/mailboxes', []),
      get<ApiSchool[]>('/household/schools', []),
    ]);
  const now = new Date();
  const tz = household.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const today = dayKey(now, tz);
  const ids: ServerIds = { claimOf: {}, amendmentOf: {}, consentOf: {}, schoolOf: {}, planOfBooking: {}, paramsOf: {}, role: me.role };

  const members: Member[] = household.members.map((a) => ({
    id: a.id, name: a.display_name.trim().split(/\s+/)[0] || a.display_name, fullName: a.display_name, initial: a.display_name.trim()[0]?.toUpperCase() ?? '?',
    role: a.role, hasAccount: a.role !== 'child' && !!a.joined, age: ageOf(a.date_of_birth, now),
    school: a.school ?? undefined, grade: a.class_label ?? undefined, email: a.email ?? undefined,
  }));
  const children: ChildInfo[] = household.members.filter((a) => a.role === 'child').map((a) => ({ memberId: a.id, school: a.school ?? '', grade: a.class_label ?? '', homeroom: '', teacher: '' }));

  const spaceOfNotice: Record<string, SpaceId | undefined> = {};
  const notices: Notice[] = inbox.map((r) => {
    spaceOfNotice[r.id] = SPACE[r.category];
    return {
      id: r.id, source: sourceOf(r.channel), sender: r.from_label, receivedAt: r.received_at,
      title: r.headline || r.filename || r.from_label, summary: r.preview[0] ?? r.reason ?? '',
      // The text is read when the notice is opened (desk/api/server.ts loadNoticeDetail): one call per notice.
      body: '', category: CATEGORY[r.category] ?? 'family', spaceId: SPACE[r.category], memberIds: r.subject_member_ids,
      attachments: r.attachments || undefined, handledBy: r.assigned_to ?? '',
    };
  });
  const quarantine: QuarantineItem[] = quarantineRaw.map((a) => ({ id: a.id, noticeId: a.id, heldAt: a.received_at, reason: (a.quarantine_reason ?? 'held').replace(/_/g, ' ') }));
  for (const a of quarantineRaw) {
    notices.push({
      id: a.id, source: sourceOf(a.channel), sender: a.source?.from ?? 'unknown sender', senderAddress: a.source?.from, receivedAt: a.received_at,
      title: a.source?.subject || 'Held notice', summary: '', body: '', category: CATEGORY[a.category] ?? 'family', quarantined: true,
    });
  }

  for (const am of amendments) if (am.status === 'proposed' && am.amends_claim_id) ids.amendmentOf[am.amends_claim_id] = am.id;
  const amendmentByClaim: Record<string, Amendment> = {};
  for (const am of amendments) if (am.status === 'proposed' && am.amends_claim_id) amendmentByClaim[am.amends_claim_id] = am;

  const live = obligations.filter((o) => !o.superseded_at);
  const proposals: Proposal[] = live.map((o) => {
    ids.claimOf[o.id] = o.claim_id;
    const space = spaceOfNotice[o.artifact_id];
    const w = whenOf(o.due_date, o.due_time, tz);
    const am = amendmentByClaim[o.claim_id];
    let state: Proposal['state'] = o.status;
    if (o.status === 'proposed' && am) state = 'changed';
    else if (o.status === 'proposed' && o.due_date && o.due_date < today) state = 'missed';
    return {
      id: o.id, noticeId: o.artifact_id, kind: o.action === 'pay' ? 'payment' : o.kind, agent: space ? AGENT_OF[space] : agentByWords(o.title), spaceId: space,
      title: o.title, ...w, forMemberId: o.subject_member_id ?? undefined, state, createdAt: o.created_at,
      changedFrom: am ? { due: am.amends_date ?? undefined, title: am.amends_title ?? undefined } : undefined,
      decidedAt: o.decided_at ?? undefined, decidedBy: o.decided_by ?? undefined,
    };
  });
  // On the server an accepted date is the calendar entry itself (no separate record is made on accept).
  const agenda: AgendaItem[] = live.filter((o) => o.status === 'accepted' && o.kind === 'calendar' && o.due_date).map((o) => {
    const space = spaceOfNotice[o.artifact_id];
    const w = whenOf(o.due_date, o.due_time, tz);
    return {
      id: o.id, agent: space ? AGENT_OF[space] : agentByWords(o.title), spaceId: space, kind: o.action === 'pay' ? 'bill' : 'event', title: o.title,
      when: w.due!, dueKind: w.dueKind!, memberIds: o.subject_member_id ? [o.subject_member_id] : [], createdAt: o.decided_at ?? o.created_at,
      noticeId: o.artifact_id, proposalId: o.id,
    };
  });

  const todos: Todo[] = todosRaw.map((t) => ({
    id: t.id, title: t.title, ...whenOf(t.due_date, t.due_time, tz), ownerId: t.assigned_to ?? t.created_by ?? me.id, onCalendar: !!t.calendar_event_id,
    done: !!t.done_at, doneAt: t.done_at ?? undefined, agent: agentByWords(t.title), createdAt: t.created_at,
  }));

  const errands: Errand[] = errandsRaw.map((e) => {
    ids.paramsOf[e.id] = e.params_sha256;
    const spec = e.spec as { what?: string; details?: string; when?: { date?: string; time?: string; part?: string; by?: string }; limits?: { max_amount?: number }; max_amount?: number; payment?: { mode?: string }; stop_rules?: Record<string, string> };
    const when = spec.when ? [spec.when.date, spec.when.time ?? spec.when.part, spec.when.by ? `by ${spec.when.by}` : ''].filter(Boolean).join(' ') : '';
    const status: Errand['status'] = e.status === 'proposed' ? 'proposed' : e.status === 'done' ? 'done' : ['cancelled', 'stopped', 'failed'].includes(e.status) ? 'cancelled' : 'approved';
    return {
      id: e.id, title: e.title, agent: agentByWords(`${e.title} ${e.service}`), status, what: spec.what ?? e.title, when, where: e.service.replace(/_/g, ' '),
      atMost: spec.limits?.max_amount ?? spec.max_amount ?? 0, paidBy: (spec.payment?.mode ?? '').replace(/_/g, ' '), card: '', stopsIf: Object.keys(spec.stop_rules ?? {}).join(', ').replace(/_/g, ' '),
      fingerprint: e.params_sha256, approvedFingerprint: e.approved_at ? e.params_sha256 : undefined, approvedBy: e.approved_by ?? undefined, approvedAt: e.approved_at ?? undefined,
      requestedBy: e.created_by, createdAt: e.created_at, // A finished run's outcome counts its steps; a running one lists them.
      steps: Array.isArray(e.outcome?.steps) ? e.outcome.steps.map((s) => ({ text: s.said, at: s.at })) : [],
      cancelledReason: e.status === 'cancelled' ? undefined : (e.error ?? (status === 'cancelled' ? e.status : undefined)),
    };
  });

  const plans: Plan[] = plansRaw.map((p) => {
    for (const o of p.options ?? []) ids.planOfBooking[o.id] = p.id;
    return {
      id: p.id, title: p.title, status: p.status === 'done' ? 'done' : p.status === 'dropped' || p.status === 'failed' ? 'dropped' : 'draft',
      start: p.starts_on ?? '', end: p.ends_on ?? '', budget: p.budget_amount ?? 0, authorId: p.created_by, summary: p.summary ?? p.brief ?? '',
      itinerary: (p.itinerary ?? []).map((d) => ({ day: d.day, date: d.date ?? '', title: d.title, text: d.notes ?? '' })),
      bookings: (p.options ?? []).map((o) => ({
        id: o.id, option: o.label, provider: o.provider ?? '', estCost: o.estimate ?? 0, sourceSnippet: o.evidence?.excerpt ?? '', sourceUrl: o.url ?? '',
        watch: !o.watch_id ? 'not watched' : o.page?.checked_at ? 'watching · read' : 'watching · not read yet', booked: !!o.booked_at,
      })),
      todoIds: (p.todos ?? []).map((t) => t.id), noticeIds: [],
    };
  });

  const kindOf = (category?: string | null): RecurringMerchant['kind'] => (category === 'insurance' ? 'insurance' : category === 'subscriptions' ? 'subscription' : 'bill');
  const recurring: RecurringMerchant[] = (money?.recurring ?? []).map((r) => ({
    id: `${r.artifact_id ?? 'r'}:${r.merchant}`, merchant: r.merchant, kind: kindOf(r.category), cadence: r.cadence === 'weekly' || r.cadence === 'yearly' ? r.cadence : 'monthly',
    amount: r.next_amount ?? r.last_amount ?? 0, last: r.last_date ?? '', next: r.next_date ?? '', spaceId: SPACE[r.category ?? ''] ?? 'finance', url: r.manage_url ?? '', noticeId: r.artifact_id ?? '',
  }));
  const orderAgain: OrderAgainItem[] = [
    ...(money?.running_low ?? []).map((r) => ({ id: r.item_key, item: r.item, store: r.merchant ?? '', lastDate: r.last_on ?? '', price: r.last_amount ?? 0, url: r.reorder_url ?? '', noticeId: r.artifact_id ?? '' })),
    ...(money?.usual ?? []).map((r) => ({ id: `usual:${r.item_key}`, item: r.item, store: r.merchant ?? '', lastDate: r.last_on ?? '', price: r.last_amount ?? 0, url: r.reorder_url ?? '', noticeId: '' })),
  ];
  const charged: Record<string, number> = {};
  for (const c of money?.charges ?? []) charged[c.artifact_id] = (charged[c.artifact_id] ?? 0) + c.amount;
  const statements: Statement[] = inbox.filter((r) => r.category === 'trading' || r.category === 'banking').map((r) => ({
    id: `s:${r.id}`, institution: r.from_label, kind: 'notice', title: r.headline || r.from_label, summary: r.preview[0] ?? '', date: dayKey(r.received_at, tz), amount: charged[r.id], noticeId: r.id,
  }));

  const audit: AuditEntry[] = auditRaw.map((a) => ({
    id: String(a.id), at: a.at, actor: a.actor_kind === 'member' && a.actor_member_id ? a.actor_member_id : 'FamilyOS', sentence: a.said, code: a.action,
    raw: { ...(a.detail ?? {}), target_type: a.target_type, target_id: a.target_id },
  })).reverse();
  // The Activity Ledger (activity.py) stands in for field revisions: what changed, by whom, and an undo where the server has one.
  const RECORD: Record<string, Revision['recordType']> = { obligation: 'agenda', todo: 'todo', plan: 'plan', member: 'member', errand: 'errand' };
  const revisions: Revision[] = activity.filter((a) => a.target?.type && RECORD[a.target.type]).map((a) => ({
    id: String(a.id), at: a.at, actor: a.who ?? 'FamilyOS', recordType: RECORD[a.target!.type!], recordId: a.target!.id ?? '', recordLabel: a.receipt?.observed ?? a.said,
    field: a.action, before: null, after: a.said, revertible: !!a.undo,
  })).reverse();

  const mailboxes: Mailbox[] = mailboxesRaw.map((m) => ({ id: m.id, address: m.email, ownerId: me.id, connectedAt: m.connected_at, lastSync: m.last_polled_at ?? undefined, status: m.disconnected_at ? 'disconnected' : 'connected' }));
  const phoneTokens: PhoneToken[] = devices.map((d) => ({ id: d.id, device: d.label, ownerId: me.id, createdAt: d.created_at, lastUsed: d.last_used_at ?? undefined }));
  const watchers: Watcher[] = [
    ...watches.map((w) => ({ id: w.id, label: w.label ?? w.url, url: w.url, spaceId: 'travel' as SpaceId, since: w.last_checked_at ?? now.toISOString(), lastChecked: w.last_checked_at ?? undefined, status: (w.paused_at ? 'stopped' : 'watching') as Watcher['status'] })),
    ...schools.filter((s) => s.portal_url).map((s) => ({ id: `school:${s.id}`, label: `${s.name} · portal`, url: s.portal_url!, spaceId: 'education' as SpaceId, since: s.created_at, status: 'watching' as const })),
  ];
  for (const s of schools) ids.schoolOf[s.name] = s.id;

  const byKey = Object.fromEntries(rules.rules.map((r) => [r.key, r]));
  const toggles: HouseholdToggle[] = seedToggles().map((t) => {
    const r = RULE_KEY[t.id] ? byKey[RULE_KEY[t.id]!] : undefined;
    return r ? { id: t.id, label: r.title, explain: r.sentence, on: r.on } : t;
  });
  const consents: Consent[] = consentsRaw.map((c) => {
    ids.consentOf[c.subject_member_id] = c.id;
    return { childId: c.subject_member_id, verifiedBy: c.guardian_member_id, noticeDate: dayKey(c.granted_at, tz), withdrawnAt: c.withdrawn_at ?? undefined };
  });
  const sittings: Sitting[] = harvests.map((h) => ({
    id: h.id, purpose: h.label, site: h.allow_hosts[0] ?? '', minutes: Math.round((new Date(h.expires_at).getTime() - new Date(h.started_at).getTime()) / 60000), openedAt: h.started_at, openedBy: me.id,
  }));

  return {
    actor: me.id,
    ids,
    data: {
      settings: { name: household.name, country: COUNTRIES[household.country] ?? household.country, timezone: tz, currency: household.currency, familyAddress: household.inbound_address },
      members, children, spaces: seedSpaces(), notices, quarantine, proposals, agenda, todos, conflicts: [], errands, plans, recurring, statements, orderAgain,
      revisions, audit, mailboxes, phoneTokens, watchers, toggles, consents,
      telegram: { bot: household.telegram_bot ?? '', devices: household.members.filter((a) => a.telegram_linked).map((a) => ({ id: `tg:${a.id}`, label: 'Telegram', ownerId: a.id, linkedAt: a.created_at })) },
      sittings, weather: { now: '—', detail: '' },
    },
  };
}
