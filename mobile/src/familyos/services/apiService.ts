// FamilyOSService over the FamilyOS backend (/v1). The screens keep their
// five agents; each backend record is placed under one by its category (the
// inbox's), else by its words. Copy that has no backend counterpart (agent
// titles, chat chips) stays in mocks/data.ts.
import type { AgentId, Severity } from '../theme/tokens';
import { AGENT_IDS } from '../theme/tokens';
import { agentDetails } from '../mocks/data';
import { suggestionsFor } from '../mocks/chatReplies';
import type {
  AgentCard,
  AgentDetail,
  ChatMessage,
  FamilyOSService,
  NeedsItem,
  Profile,
  ResolveResult,
  TimelineEntry,
  TodayBrief,
  TodayItem,
  WalkthroughStep,
} from './interfaces';
import { ApiError, clearToken, request, saveToken } from './api';

// ── Backend shapes (familyos/models.py), only the fields read here ──────────

export interface ApiMember {
  id: string;
  household_id: string;
  display_name: string;
  role: 'guardian' | 'adult' | 'child';
  email?: string | null;
  phone?: string | null;
  date_of_birth?: string | null;
  school?: string | null;
  class_label?: string | null;
  created_at: string;
}

export interface ApiHousehold {
  id: string;
  name: string;
  currency: string;
  members: ApiMember[];
}

interface BriefItem {
  reason: string;
  rank: number;
  title: string;
  why: string;
  when?: string | null;
  due_date?: string | null;
  status?: string | null;
  obligation_id?: string | null;
  amendment_id?: string | null;
  artifact_id?: string | null;
  subject_name?: string | null;
}

interface Brief {
  display_name: string;
  items: BriefItem[];
  context?: { weather?: string | null } | null;
  next_thing?: { title: string; due_date: string; days_away: number; when: string } | null;
}

interface InboxRow {
  id: string;
  received_at: string;
  headline?: string | null;
  from_label: string;
  preview: string[];
  next_date?: string | null;
  open: number;
  state: 'todo' | 'done' | 'info';
  category: string;
}

interface Todo {
  id: string;
  title: string;
  due_date?: string | null;
  done_at?: string | null;
}

interface Money {
  charges: { artifact_id: string; merchant: string; amount: number; currency: string; date: string; title: string }[];
  recurring: { merchant: string; next_date: string; next_amount: number; currency: string }[];
  month: { charges: number; previous_charges: number; by_category: { category?: string | null; total: number; currency: string }[] };
  running_low: unknown[];
}

interface ChatTurn {
  say: string;
}

// ── Placing records under the five agents ───────────────────────────────────

const CATEGORY_AGENT: Record<string, AgentId> = {
  school: 'education',
  bills: 'finance',
  banking: 'finance',
  insurance: 'finance',
  subscriptions: 'finance',
  trading: 'finance',
  food: 'grocery',
  shopping: 'grocery',
  home: 'household',
  medical: 'household',
  government: 'household',
  travel: 'calendar',
};

const WORDS: [RegExp, AgentId][] = [
  [/\b(fee|fees|bill|invoice|premium|pay|paid|payment|₹|rs\.?|inr|renewal|emi)\b/i, 'finance'],
  [/\b(school|class|exam|ptm|homework|circular|term|teacher|uniform)\b/i, 'education'],
  [/\b(grocery|groceries|milk|vegetables|order|delivery|cart|refill)\b/i, 'grocery'],
  [/\b(trip|flight|train|meeting|appointment|holiday|event|party|birthday)\b/i, 'calendar'],
];

function agentFor(artifactId: string | null | undefined, text: string, categories: Map<string, string>): AgentId {
  const category = artifactId ? categories.get(artifactId) : undefined;
  if (category && CATEGORY_AGENT[category]) return CATEGORY_AGENT[category];
  for (const [re, agent] of WORDS) if (re.test(text)) return agent;
  return 'household';
}

const URGENT = new Set(['missed', 'overdue', 'mailbox']);
const INSIGHT = new Set(['handled']);

function severityFor(reason: string): Exclude<Severity, 'positive'> {
  if (URGENT.has(reason)) return 'urgent';
  if (INSIGHT.has(reason)) return 'insight';
  return 'headsup';
}

// ── Formatting ──────────────────────────────────────────────────────────────

const SYMBOL: Record<string, string> = { INR: '₹', USD: '$', AED: 'AED ', GBP: '£', EUR: '€' };

function money(amount: number, currency: string): string {
  const sym = SYMBOL[currency] ?? `${currency} `;
  return `${sym}${Math.round(amount).toLocaleString('en-IN')}`;
}

function shortDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function ago(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'TODAY';
  if (days === 1) return 'YESTERDAY';
  if (days < 7) return `${days} DAYS AGO`;
  return shortDate(iso).toUpperCase();
}

const firstName = (name: string) => name.trim().split(/\s+/)[0] || name;

// ── One snapshot of the record, shared by the boot-time calls ───────────────

interface Snapshot {
  me: ApiMember;
  household: ApiHousehold;
  brief: Brief;
  inbox: InboxRow[];
  todos: Todo[];
  money: Money | null;
  categories: Map<string, string>;
  at: number;
}

const FRESH_MS = 20_000;
let snap: Promise<Snapshot> | null = null;
let snapAt = 0;

function snapshot(force = false): Promise<Snapshot> {
  if (!force && snap && Date.now() - snapAt < FRESH_MS) return snap;
  snapAt = Date.now();
  snap = (async () => {
    const [me, household, brief, inbox, todos, moneyView] = await Promise.all([
      request<ApiMember>('GET', '/me'),
      request<ApiHousehold>('GET', '/household'),
      request<Brief>('GET', '/brief?limit=20'),
      request<InboxRow[]>('GET', '/inbox?days=365&limit=200'),
      request<Todo[]>('GET', '/todos'),
      // Money is derived from receipts; a household without any still has a home screen.
      request<Money>('GET', '/money').catch(() => null),
    ]);
    const categories = new Map(inbox.map((r) => [r.id, r.category]));
    return { me, household, brief, inbox, todos, money: moneyView, categories, at: Date.now() };
  })();
  snap.catch(() => {
    snap = null;
  });
  return snap;
}

function needsFrom(s: Snapshot): NeedsItem[] {
  return s.brief.items.map((b) => {
    const proposed = !!b.obligation_id && b.status === 'proposed';
    const text = b.when ? `${b.title} · ${b.when}` : b.title;
    return {
      id: b.obligation_id ? `o:${b.obligation_id}` : `b:${b.rank}:${b.artifact_id ?? b.amendment_id ?? ''}`,
      severity: severityFor(b.reason),
      agent: agentFor(b.artifact_id, `${b.title} ${b.why}`, s.categories),
      time: b.due_date ? shortDate(b.due_date).toUpperCase() : b.reason.toUpperCase(),
      text,
      action: proposed ? { id: 'accept', label: 'Accept' } : { id: 'got-it', label: 'Got it' },
      priority: b.rank,
    };
  });
}

function todayFrom(s: Snapshot): TodayItem[] {
  const fromBrief = s.brief.items.slice(0, 6).map((b, i) => ({
    id: `t${i}`,
    agent: agentFor(b.artifact_id, `${b.title} ${b.why}`, s.categories),
    text: b.when ? `${b.title}, ${b.when}.` : `${b.title}.`,
  }));
  const fromTodos = s.todos
    .filter((t) => !t.done_at)
    .slice(0, Math.max(0, 7 - fromBrief.length))
    .map((t, i) => ({
      id: `td${i}`,
      agent: agentFor(null, t.title, s.categories),
      text: t.due_date ? `To-do: ${t.title}, by ${shortDate(t.due_date)}.` : `To-do: ${t.title}.`,
    }));
  return [...fromBrief, ...fromTodos];
}

function rowsFor(agent: AgentId, s: Snapshot): InboxRow[] {
  return s.inbox.filter((r) => agentFor(r.id, `${r.headline ?? ''} ${r.preview.join(' ')}`, s.categories) === agent);
}

function statusFor(agent: AgentId, s: Snapshot): string {
  const rows = rowsFor(agent, s);
  const open = rows.filter((r) => r.state === 'todo').length;
  if (agent === 'finance' && s.money) {
    const spent = s.money.month.by_category.reduce((n, c) => n + c.total, 0);
    const cur = s.money.month.by_category[0]?.currency ?? s.household.currency;
    return spent > 0 ? `${money(spent, cur)} this month · ${open} open` : `${open} bills open`;
  }
  if (agent === 'household') {
    const todos = s.todos.filter((t) => !t.done_at).length;
    return `${todos} to-dos · ${open} open`;
  }
  if (agent === 'calendar') {
    const next = s.brief.next_thing;
    return next ? `Next: ${next.title} · ${next.when}` : `${rows.length} dated notices`;
  }
  if (agent === 'grocery') {
    const low = s.money?.running_low.length ?? 0;
    return low ? `${low} running low` : `${rows.length} orders seen`;
  }
  return open ? `${open} things open from school` : `${rows.length} notices · nothing open`;
}

function timelineFor(agent: AgentId, s: Snapshot): TimelineEntry[] {
  return rowsFor(agent, s)
    .slice(0, 12)
    .map((r) => ({
      id: r.id,
      when: ago(r.received_at),
      title: r.headline || r.from_label,
      description: r.preview[0] ?? `From ${r.from_label}`,
      rows: [
        ['From', r.from_label],
        ['Status', r.state === 'todo' ? `${r.open} open` : r.state === 'done' ? 'Done' : 'For your information'],
        ...(r.next_date ? ([['Next date', shortDate(r.next_date)]] as [string, string][]) : []),
      ],
    }));
}

function detailFor(agent: AgentId, s: Snapshot): AgentDetail {
  const base = agentDetails[agent];
  const rows = rowsFor(agent, s);
  const open = rows.filter((r) => r.state === 'todo').length;
  const done = rows.filter((r) => r.state === 'done').length;
  const pct = rows.length ? Math.round((done / rows.length) * 100) : 100;
  let hero: AgentDetail['hero'] = {
    kind: 'ring',
    label: 'HANDLED',
    value: `${done} of ${rows.length}`,
    note: open ? `${open} still open` : 'Nothing open',
    pct,
  };
  if (agent === 'finance' && s.money && s.money.charges.length) {
    // The last eight weeks of charges, oldest first.
    const weeks = Array.from({ length: 8 }, () => 0);
    for (const c of s.money.charges) {
      const w = Math.floor((Date.now() - new Date(c.date).getTime()) / (7 * 86_400_000));
      if (w >= 0 && w < 8) weeks[7 - w] += c.amount;
    }
    const cur = s.money.charges[0].currency;
    const now = weeks[7];
    const before = weeks[6];
    hero = {
      kind: 'sparkline',
      label: 'SPENT THIS WEEK',
      value: money(now, cur),
      delta: before ? `${Math.round(((now - before) / before) * 100)}% vs last week` : 'first week on record',
      up: now >= before,
      series: weeks.some((w) => w > 0) ? weeks : [0, 0, 0, 0, 0, 0, 0, 1],
    };
  }
  return {
    ...base,
    hero,
    stats: [
      { label: 'Notices', value: rows.length },
      { label: 'Open', value: open },
      { label: 'Done', value: done },
    ],
    timeline: timelineFor(agent, s),
  };
}

// ── The service ─────────────────────────────────────────────────────────────

const histories: Record<string, { role: 'user' | 'assistant'; content: string }[]> = {};
let msgId = 0;
const nextId = () => `m${Date.now()}-${msgId++}`;

const ok = (message: string): ResolveResult => ({ ok: true, message });

export const apiService: FamilyOSService = {
  async getProfile(): Promise<Profile> {
    const s = await snapshot();
    const n = s.household.members.length;
    return {
      name: s.me.display_name,
      initial: s.me.display_name.trim()[0]?.toUpperCase() ?? '?',
      plan: `${s.household.name} · ${n} ${n === 1 ? 'member' : 'members'}`,
      email: s.me.email ?? '',
    };
  },

  async getHomeSummary() {
    const s = await snapshot();
    const dashboard: AgentCard[] = AGENT_IDS.map((agent) => ({ agent, status: statusFor(agent, s) }));
    return { greetingName: firstName(s.me.display_name), dashboard };
  },

  async getTodayItems(): Promise<TodayBrief> {
    const s = await snapshot();
    const next = s.brief.next_thing;
    return {
      weather: {
        label: 'WEATHER',
        value: s.brief.context?.weather ? '' : '—',
        detail: s.brief.context?.weather ?? 'Weather is off for this household.',
      },
      firstEvent: next
        ? { label: 'NEXT DATE', value: next.when, detail: next.title }
        : { label: 'NEXT DATE', value: '—', detail: 'Nothing dated coming up.' },
      items: todayFrom(s),
    };
  },

  // The scenario switcher is a demo device; the backend has one truth.
  async getNeedsYou() {
    const s = await snapshot(true);
    return needsFrom(s);
  },

  async resolveItem(id, actionId) {
    if (actionId === 'accept' && id.startsWith('o:')) {
      await request('POST', `/obligations/${id.slice(2)}/decision`, { status: 'accepted' });
      snap = null;
      return ok('Accepted');
    }
    return ok('Done');
  },

  // No snooze on the backend yet: the card leaves the list for this session.
  async snoozeItem() {
    return ok('Hidden until you reopen the app');
  },

  async getWalkthrough(agent?: AgentId): Promise<WalkthroughStep[]> {
    const s = await snapshot();
    const items = todayFrom(s);
    const steps = (agent ? items.filter((t) => t.agent === agent) : items).map((t) => ({ agent: t.agent, text: t.text }));
    if (steps.length) return steps;
    return [{ agent: agent ?? 'calendar', text: agent ? `${statusFor(agent, s)}.` : 'Nothing needs you today.' }];
  },

  async getAgentDetail(agentId) {
    return detailFor(agentId, await snapshot());
  },

  async undoAction() {
    return ok('Nothing to undo on the server');
  },

  async sendChat(threadId, text) {
    const history = (histories[threadId] ??= []);
    let say: string;
    try {
      const turn = await request<ChatTurn>('POST', '/chat', { message: text, history: history.slice(-10) });
      say = turn.say;
    } catch (e) {
      say = e instanceof Error ? e.message : 'The assistant did not answer.';
    }
    history.push({ role: 'user', content: text }, { role: 'assistant', content: say });
    return { id: nextId(), role: 'assistant', text: say } satisfies ChatMessage;
  },

  async getChatGreeting(threadId) {
    const s = await snapshot();
    const name = firstName(s.me.display_name);
    const text =
      threadId === 'home'
        ? `Hi ${name}. Ask me about your family's notices, dates, bills and to-dos.`
        : `Hi ${name}. ${statusFor(threadId as AgentId, s)}. What would you like to know?`;
    return { id: nextId(), role: 'assistant', text };
  },

  async getChatSuggestions(threadId) {
    return threadId === 'home' ? suggestionsFor('home') : agentDetails[threadId as AgentId].chips;
  },

  async setSummaryMode() {
    return ok('Saved');
  },

  async logIn(email, password) {
    // The backend signs people in by mailed link. Until mail is set up, the
    // development sign-in (FAMILYOS_DEV_SIGN_IN) runs that same link-and-
    // redeem path from the address alone. A session token pasted into the
    // password field (the backend's start "fos_") is used as it is.
    const pasted = password.trim();
    try {
      await clearToken();
      if (pasted.startsWith('fos_')) {
        await saveToken(pasted);
      } else {
        // Keyboards add spaces after a dot or capitalise; an address has neither.
        const address = email.replace(/\s+/g, '').toLowerCase();
        if (!address) return { ok: false, message: 'Enter the email your household knows you by.' };
        const r = await request<{ token: string }>('POST', '/sign-in/dev', { email: address });
        await saveToken(r.token);
      }
      snap = null;
      await snapshot(true);
      return ok('Welcome back');
    } catch (e) {
      await clearToken();
      if (e instanceof ApiError && e.status === 404) {
        return { ok: false, message: "This server doesn't allow signing in by email alone (FAMILYOS_DEV_SIGN_IN)." };
      }
      if (e instanceof ApiError && e.status === 422) return { ok: false, message: "That doesn't look like an email address." };
      return { ok: false, message: e instanceof Error ? e.message : 'Could not sign in.' };
    }
  },

  async logOut() {
    // End this session on the server too, then forget it here.
    await request('POST', '/signout').catch(() => undefined);
    await clearToken();
    snap = null;
    return ok('Logged out');
  },
};
