/* Orbit: what the household's record says, shaped for the orbits, the bento
   and the deep layers. Only fields the API returns are read; nothing is
   estimated, and a block with nothing behind it says so. */

export const AGENTS = [
  { key: 'finance', label: 'Finance', color: '#2dd4bf' },
  { key: 'education', label: 'Education', color: '#b9a5ff' },
  { key: 'household', label: 'Household', color: '#ffb547' },
  { key: 'calendar', label: 'Calendar', color: '#5cc8ff' },
  { key: 'grocery', label: 'Grocery', color: '#7ef2b1' },
];
export const AGENT = Object.fromEntries(AGENTS.map((a) => [a.key, a]));
export const EXTRA = {
  health: { key: 'health', label: 'Health', color: '#34d399' },
  memories: { key: 'memories', label: 'Memories', color: '#fbbf6a' },
  waiting: { key: 'waiting', label: 'Waiting for you', color: '#ffd60a' },
  conflicts: { key: 'conflicts', label: 'Clashes', color: '#ff6b6b' },
  todos: { key: 'todos', label: 'To-dos', color: '#93c5fd' },
  documents: { key: 'documents', label: 'Documents', color: '#cbd5e1' },
};
export function catInfo(key) { return AGENT[key] || EXTRA[key] || { key, label: key, color: '#cbd5e1' }; }

const URGENT = ['missed', 'overdue', 'undecided', 'mailbox'];
const GROCERY_WORDS = /grocer|pantry|vegetable|rice|salt|spice|milk|eggs?\b|fruit|atta|dal\b|instamart|bigbasket|zepto|blinkit/i;
const GROCERY_MERCHANTS = /instamart|bigbasket|zepto|blinkit|dunzo|jiomart|grofers|dmart/i;

/* ── dates ───────────────────────────────────────────────────── */

export function isoAdd(iso, days) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + days);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
export function localIso(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
export function daysBetween(a, b) { return Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000); }
export function fmtDay(iso, today) {
  if (!iso) return '';
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
  if (today) {
    const n = daysBetween(today, String(iso).slice(0, 10));
    if (n === 0) return 'Today';
    if (n === 1) return 'Tomorrow';
    if (n === -1) return 'Yesterday';
    if (n > 1 && n < 7) return d.toLocaleDateString('en-IN', { weekday: 'long' });
  }
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
}
export function fmtWhen(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) + ', ' + d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
}
/* A time as the notice gave it, unless it gave nothing useful. */
export function cleanTime(t) {
  if (!t) return '';
  const s = String(t).trim();
  if (/not specified|unspecified|none|n\/a/i.test(s)) return '';
  return /^\d\d:\d\d(:\d\d)?$/.test(s) ? s.slice(0, 5) : s;
}

export function money(amount, currency) {
  if (amount === null || amount === undefined) return '';
  const cur = currency || 'INR';
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: cur, maximumFractionDigits: Math.abs(amount) >= 1000 ? 0 : 2, minimumFractionDigits: 0 }).format(amount);
  } catch (e) { return cur + ' ' + amount; }
}

/* ── loading ─────────────────────────────────────────────────── */

export async function loadAll(api) {
  const soft = (p) => api(p).catch((e) => { if (e && e.status === 401) throw e; return null; });
  const [me, household] = await Promise.all([api('/me'), api('/household')]);
  const [brief, inbox, moneyRaw, calendar, errands, todos, offers, obligations, reminders, documents] = await Promise.all([
    soft('/brief?limit=40'), soft('/inbox?days=60&limit=200'), soft('/money?days=120'), soft('/calendar/upcoming?days=7'),
    soft('/errands'), soft('/todos'), soft('/offers'), soft('/obligations?status=&limit=300'), soft('/reminders?limit=200'), soft('/documents'),
  ]);
  return derive({ me, household, brief, inbox, money: moneyRaw, calendar, errands, todos, offers, obligations, reminders, documents });
}

/* ── shaping ─────────────────────────────────────────────────── */

export function derive(raw) {
  const m = { raw };
  const members = (raw.household && raw.household.members) || [];
  const names = new Map(members.map((x) => [x.id, x.display_name]));
  m.me = raw.me;
  m.household = raw.household;
  m.members = members;
  m.children = members.filter((x) => x.role === 'child');
  const childIds = new Set(m.children.map((c) => c.id));
  m.name = (id) => (id && names.get(id)) || '';
  m.today = (raw.brief && raw.brief.date) || localIso(new Date());
  const today = m.today, weekEnd = isoAdd(today, 7);

  const inbox = raw.inbox || [];
  const byArtifact = new Map(inbox.map((r) => [r.id, r]));
  m.notice = (id) => byArtifact.get(id) || null;
  const obligations = (raw.obligations || []).filter((o) => !o.superseded_at);
  const oblById = new Map((raw.obligations || []).map((o) => [o.id, o]));
  m.obligation = (id) => oblById.get(id) || null;

  /* Which orbit a dated thing belongs to: what it asks, whom it is about,
     and the kind of mail it came in. */
  const agentFor = (x) => {
    if (x.reason === 'money' || x.action === 'pay') return 'finance';
    if (x.reason === 'mailbox') return 'household';
    const row = x.artifact_id ? byArtifact.get(x.artifact_id) : null;
    const cat = row ? row.category : null;
    if (cat === 'school' || (x.subject_member_id && childIds.has(x.subject_member_id))) return 'education';
    if (cat === 'home') return 'household';
    if (cat === 'food' || cat === 'shopping') return 'grocery';
    if (cat === 'bills' || cat === 'banking' || cat === 'subscriptions' || cat === 'trading') return 'finance';
    return x.due_date ? 'calendar' : 'household';
  };
  m.agentFor = agentFor;

  const briefItems = ((raw.brief && raw.brief.items) || []).map((i) => Object.assign({}, i, {
    subject: i.subject_name || m.name(i.subject_member_id),
    agent: agentFor(i),
  }));
  m.brief = briefItems;
  m.briefCounts = (raw.brief && raw.brief.counts) || {};
  m.moneyLine = (briefItems.find((i) => i.reason === 'money') || {}).title || '';

  const errands = raw.errands || [];
  m.errands = errands;
  m.errandsActive = errands.filter((e) => ['proposed', 'approved', 'running', 'needs_you'].includes(e.status));
  m.errandsNeedYou = errands.filter((e) => e.status === 'needs_you');
  m.errandsProposed = errands.filter((e) => e.status === 'proposed');

  const money = raw.money || null;
  m.money = money;
  m.runningLow = (money && money.running_low) || [];
  m.usual = (money && money.usual) || [];
  m.todos = (raw.todos || []).filter((t) => !t.done_at);
  m.groceryTodos = m.todos.filter((t) => GROCERY_WORDS.test(t.title));
  m.offers = raw.offers || [];
  m.calendar = raw.calendar || [];
  m.documents = (raw.documents && raw.documents.documents) || [];
  m.documentChecks = (raw.documents && raw.documents.checks) || [];
  m.reminders = raw.reminders || [];
  m.loaded = {
    brief: !!raw.brief, inbox: !!raw.inbox, money: !!raw.money, calendar: !!raw.calendar, errands: !!raw.errands,
    todos: !!raw.todos, offers: !!raw.offers, obligations: !!raw.obligations, reminders: !!raw.reminders, documents: !!raw.documents,
  };

  /* ── this week, dated ─────────────────────────────────────── */
  const week = [];
  const seen = new Set();
  const addWeek = (x) => { const k = (x.title || '').toLowerCase().trim() + '|' + x.date; if (seen.has(k)) return; seen.add(k); week.push(x); };
  briefItems.forEach((i) => { if (i.due_date && i.due_date >= today && i.due_date < weekEnd && i.reason !== 'amendment') addWeek({ date: i.due_date, time: cleanTime(i.due_time), title: i.title, who: i.subject, src: 'brief', item: i }); });
  m.calendar.forEach((e) => {
    const d = localIso(new Date(e.starts_at));
    const time = e.all_day ? '' : new Date(e.starts_at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
    if (d >= today && d < weekEnd) addWeek({ date: d, time, title: e.summary, who: '', src: 'calendar', event: e, at: e.starts_at });
  });
  week.sort((a, b) => (a.date + (a.at || '')).localeCompare(b.date + (b.at || '')));
  m.week = week;
  m.todayItems = week.filter((x) => x.date === today);
  // The next thing still ahead of now.
  const now = Date.now();
  m.nextThing = week.find((x) => (x.at ? new Date(x.at).getTime() > now : x.date > today || x.date === today)) || null;

  /* ── conflicts and approvals ──────────────────────────────── */
  m.clashes = briefItems.filter((i) => i.clashes && (Array.isArray(i.clashes) ? i.clashes.length : true));
  m.overlapOffers = m.offers.filter((o) => String(o.key).startsWith('overlap:'));
  m.proposed = obligations.filter((o) => o.status === 'proposed');
  m.offersOpen = m.offers.filter((o) => !o.fyi && !String(o.key).startsWith('overlap:'));
  m.waitingCount = m.proposed.length + m.errandsProposed.length + m.offersOpen.length;

  /* ── money ─────────────────────────────────────────────────── */
  const recurring = (money && money.recurring) || [];
  const due7 = recurring.filter((r) => r.next_date && r.next_date >= today && r.next_date < weekEnd);
  m.outThisWeek = due7;
  m.nextBill = recurring.filter((r) => r.next_date && r.next_date >= today).sort((a, b) => a.next_date.localeCompare(b.next_date))[0] || null;
  m.payItems = briefItems.filter((i) => i.action === 'pay' && i.reason !== 'handled');
  m.payLink = (briefItems.find((i) => i.pay_url && i.reason !== 'handled') || {}).pay_url || null;
  const charges = ((money && money.charges) || []).filter((c) => !c.upcoming);
  m.charges = charges;
  // Weekly totals of receipts read, in the household's currency, oldest first.
  const cur = (raw.household && raw.household.currency) || 'INR';
  m.currency = cur;
  const weeks = 17, buckets = new Array(weeks).fill(0);
  charges.forEach((c) => {
    if (c.currency !== cur || !c.date) return;
    const ago = daysBetween(c.date, today);
    const w = Math.floor(ago / 7);
    if (w >= 0 && w < weeks) buckets[weeks - 1 - w] += c.amount;
  });
  m.spark = buckets;
  const month = (money && money.month) || null;
  if (month && month.by_category) {
    const same = month.by_category.filter((c) => c.currency === cur);
    m.monthTotal = same.reduce((s, c) => s + (c.total || 0), 0);
    m.monthPrev = same.reduce((s, c) => s + (c.previous || 0), 0);
    m.monthComparable = !!month.comparable;
    m.monthDriver = (same.slice().sort((a, b) => (b.delta || 0) - (a.delta || 0))[0] || {}).driver || null;
  } else { m.monthTotal = null; }

  /* ── notices by kind ──────────────────────────────────────── */
  m.medical = inbox.filter((r) => r.category === 'medical');
  m.school = inbox.filter((r) => r.category === 'school');
  m.home = inbox.filter((r) => r.category === 'home');
  const docArtifacts = new Set(m.documents.map((d) => d.artifact_id));
  // Photos the family shared, never a scanned document.
  m.photos = inbox.filter((r) => /^image\//.test(r.media_type) && !docArtifacts.has(r.id) && !/aadhaar|pan card|passport|licen[cs]e|card$/i.test(r.headline || ''));

  /* ── the five orbits ──────────────────────────────────────── */
  const live = (i) => i.reason !== 'handled' && i.reason !== 'money';
  const urgentIn = (list) => list.filter((i) => i.reason === 'missed' || i.reason === 'overdue').length;
  const fin = briefItems.filter((i) => i.agent === 'finance' && live(i));
  const edu = briefItems.filter((i) => i.agent === 'education' && live(i));
  const schoolTodo = m.school.filter((r) => r.state === 'todo');
  const homeTodo = m.home.filter((r) => r.state === 'todo');
  m.agents = {
    finance: { items: fin, badge: fin.length, urgent: urgentIn(fin), tension: urgentIn(fin) > 0 ? 1 : 0 },
    education: { items: edu, badge: edu.length + schoolTodo.length, urgent: urgentIn(edu), tension: urgentIn(edu) > 0 ? 1 : 0 },
    household: { items: m.errandsActive, badge: m.errandsActive.length + homeTodo.length + m.runningLow.length, urgent: m.errandsNeedYou.length, tension: m.errandsNeedYou.length ? 1 : 0 },
    calendar: { items: week, badge: week.length, urgent: m.clashes.length + m.overlapOffers.length, tension: m.clashes.length ? 1 : 0 },
    grocery: { items: m.runningLow, badge: m.runningLow.length + m.groceryTodos.length, urgent: 0, tension: 0 },
  };

  /* ── what the core says ───────────────────────────────────── */
  const anyRed = briefItems.some((i) => i.reason === 'missed' || i.reason === 'overdue' || i.reason === 'mailbox') || m.errandsNeedYou.length;
  const anyAmber = briefItems.some((i) => i.reason === 'undecided' || i.status === 'proposed') || m.errandsProposed.length || m.proposed.length;
  m.status = anyRed ? 'red' : anyAmber ? 'amber' : 'calm';

  /* ── orbital notifications ────────────────────────────────── */
  const notes = briefItems.filter((i) => URGENT.includes(i.reason)).map((i) => ({
    id: 'b:' + (i.obligation_id || i.artifact_id || i.mailbox_id || i.title), kind: 'brief', item: i, agent: i.agent,
    color: (AGENT[i.agent] || {}).color || '#fff', reason: i.reason,
  }));
  m.errandsNeedYou.forEach((e) => notes.unshift({ id: 'e:' + e.id, kind: 'errand', errand: e, agent: 'household', color: AGENT.household.color, reason: 'needs_you' }));
  m.notesAll = notes;
  m.notes = notes.slice(0, 8);

  /* ── children's adventures (dated school things ahead) ────── */
  const adv = [], advSeen = new Set();
  const addAdv = (o) => { const k = o.title.toLowerCase() + '|' + o.date; if (advSeen.has(k)) return; advSeen.add(k); adv.push(o); };
  briefItems.forEach((i) => { if (i.due_date && i.due_date >= today && i.subject_member_id && childIds.has(i.subject_member_id)) addAdv({ date: i.due_date, title: i.title, who: i.subject, artifact_id: i.artifact_id }); });
  obligations.forEach((o) => { if (o.status !== 'dismissed' && o.due_date && o.due_date >= today && o.subject_member_id && childIds.has(o.subject_member_id)) addAdv({ date: o.due_date, title: o.title, who: m.name(o.subject_member_id), artifact_id: o.artifact_id }); });
  adv.sort((a, b) => a.date.localeCompare(b.date));
  m.adventures = adv;
  m.adventuresDone = obligations.filter((o) => o.status === 'accepted' && o.due_date && o.due_date < today && o.subject_member_id && childIds.has(o.subject_member_id)).length;
  m.nextSchool = adv[0] || null;

  /* ── the stream: what FamilyOS actually did, and what people did ── */
  m.events = buildEvents(m, raw, agentFor, byArtifact);
  return m;
}

function headlineOf(byArtifact, id) {
  const r = id ? byArtifact.get(id) : null;
  return r ? (r.headline || r.from_label || '') : '';
}

function buildEvents(m, raw, agentFor, byArtifact) {
  const ev = [];
  const push = (e) => { if (e.at) ev.push(e); };
  const kidIds = new Set(m.children.map((c) => c.id));
  // Obligations: proposed from a notice, decided by a person, replaced by a later notice.
  (raw.obligations || []).forEach((o) => {
    const cat = agentFor(o);
    const cats = [cat, 'calendar'].filter((v, i, a) => a.indexOf(v) === i);
    if (o.subject_member_id && kidIds.has(o.subject_member_id) && !cats.includes('education')) cats.push('education');
    const from = headlineOf(byArtifact, o.artifact_id);
    const due = o.due_date ? ' for ' + fmtDay(o.due_date) : '';
    const who = m.name(o.subject_member_id);
    push({ at: o.created_at, cats, kind: 'Proposed', tone: 'blue',
      text: 'I read ' + (from ? '\u201C' + from + '\u201D' : 'a notice') + ' and proposed \u201C' + o.title + '\u201D' + due + (who ? ', for ' + who : '') + '. Nothing happens until someone accepts it.',
      artifact_id: o.artifact_id, obligation_id: o.id, date: o.due_date });
    if (o.decided_at) {
      const by = m.name(o.decided_by);
      push({ at: o.decided_at, cats, kind: o.status === 'accepted' ? 'Accepted' : 'Dismissed', tone: o.status === 'accepted' ? 'green' : 'grey',
        text: (o.status === 'accepted' ? 'Accepted' : 'Dismissed') + (by ? ' by ' + by : '') + ': \u201C' + o.title + '\u201D' + due + '.',
        artifact_id: o.artifact_id, date: o.due_date });
    }
    if (o.superseded_at) push({ at: o.superseded_at, cats, kind: 'Replaced', tone: 'amber', text: 'A later notice replaced \u201C' + o.title + '\u201D, so I stopped counting it.', artifact_id: o.superseded_by_artifact_id || o.artifact_id });
  });
  // Reminders that went out.
  const oblById = new Map((raw.obligations || []).map((o) => [o.id, o]));
  (raw.reminders || []).forEach((r) => {
    if (r.status !== 'sent' || !r.sent_at) return;
    const o = oblById.get(r.obligation_id);
    const cat = o ? agentFor(o) : 'calendar';
    const how = r.channel === 'log' ? 'I logged a reminder' : 'I sent a reminder by ' + (r.channel === 'telegram' ? 'Telegram' : r.channel);
    push({ at: r.sent_at, cats: [cat, 'calendar'], kind: 'Reminded', tone: 'blue',
      text: how + ' about \u201C' + r.title + '\u201D' + (r.reason === 'undecided' ? ', still undecided' : ', coming due') + (r.due_date ? ' (' + fmtDay(r.due_date) + ')' : '') + '.',
      artifact_id: o ? o.artifact_id : null });
  });
  // Notices handed to someone, and marked handled.
  (raw.inbox || []).forEach((r) => {
    const cat = { school: 'education', home: 'household', medical: 'health', food: 'grocery', shopping: 'grocery', bills: 'finance', banking: 'finance', subscriptions: 'finance' }[r.category] || null;
    const cats = cat ? [cat] : ['household'];
    if (r.assigned_at && r.assigned_to) push({ at: r.assigned_at, cats, kind: 'Handed over', tone: 'blue', text: (m.name(r.assigned_by) || 'Someone') + ' handed \u201C' + (r.headline || 'a notice') + '\u201D to ' + (m.name(r.assigned_to) || 'someone') + (r.assigned_note ? ': \u201C' + r.assigned_note + '\u201D' : '.'), artifact_id: r.id });
    if (r.handled_at) push({ at: r.handled_at, cats, kind: 'Handled', tone: 'green', text: (m.name(r.handled_by) || 'Someone') + ' marked \u201C' + (r.headline || 'a notice') + '\u201D handled' + (r.handled_note ? ': \u201C' + r.handled_note + '\u201D' : '.'), artifact_id: r.id });
    if (r.category === 'medical' || r.category === 'school' || r.category === 'home') push({ at: r.received_at, cats, kind: 'Read', tone: 'grey', text: 'I read \u201C' + (r.headline || 'a notice') + '\u201D from ' + r.from_label + (r.state === 'todo' ? '. It asks for something.' : '.'), artifact_id: r.id });
  });
  // Errands: who asked, who approved, each step as it was recorded.
  (raw.errands || []).forEach((e) => {
    const cats = ['household'].concat(e.service === 'myclassboard' ? ['education'] : []);
    push({ at: e.created_at, cats, kind: 'Errand', tone: 'amber', text: (m.name(e.created_by) || 'Someone') + ' asked for an errand: \u201C' + e.title + '\u201D.' + (e.status === 'proposed' ? ' It waits for a guardian to approve.' : ''), errand: e.id });
    if (e.approved_at) push({ at: e.approved_at, cats, kind: 'Approved', tone: 'green', text: 'Approved by ' + (m.name(e.approved_by) || 'a guardian') + ': \u201C' + e.title + '\u201D.', errand: e.id });
    const out = e.outcome || {};
    (out.steps || []).forEach((s, idx) => {
      const pics = [];
      if (s.artifact_id) pics.push(s.artifact_id);
      push({ at: s.at, cats, kind: 'Errand step', tone: 'grey', text: s.said, pics, errand: e.id, sub: e.title });
    });
    if (e.status === 'needs_you') push({ at: e.updated_at, cats, kind: 'Needs you', tone: 'red', text: '\u201C' + e.title + '\u201D needs a person to take over.', errand: e.id });
    if (e.ended_at && ['done', 'failed', 'stopped', 'cancelled'].includes(e.status)) push({ at: e.ended_at, cats, kind: e.status === 'done' ? 'Errand done' : 'Errand ' + e.status, tone: e.status === 'done' ? 'green' : 'grey', text: '\u201C' + e.title + '\u201D ' + (e.status === 'done' ? 'finished.' : e.status + (e.error ? ': ' + e.error : '.')), errand: e.id });
    else if (e.status === 'cancelled') push({ at: e.updated_at, cats, kind: 'Errand cancelled', tone: 'grey', text: '\u201C' + e.title + '\u201D was cancelled' + (e.error ? ': ' + e.error : '.'), errand: e.id });
  });
  // Receipts read.
  const money = raw.money || {};
  (money.charges || []).forEach((c) => {
    const cats = ['finance'];
    if (c.category === 'food' || c.category === 'shopping' || GROCERY_MERCHANTS.test(c.merchant || '')) cats.push('grocery');
    if (c.upcoming) push({ at: (c.due || c.date) + 'T09:00:00', cats, kind: 'Expected', tone: 'amber', text: c.merchant + ' says ' + money_(c) + ' will be charged' + (c.due ? ' on ' + fmtDay(c.due) : '') + '. I only read this; FamilyOS does not pay it.', artifact_id: c.artifact_id });
    else push({ at: c.date + 'T09:00:00', cats, kind: 'Receipt read', tone: 'grey', text: 'I read a receipt: ' + money_(c) + ' to ' + c.merchant + ' (' + c.category + ')' + (c.settles_due ? ', which settles the bill due ' + fmtDay(c.settles_due) : '') + '.', artifact_id: c.artifact_id });
  });
  ((money.services && money.services.timeline) || []).forEach((s) => push({ at: s.date + 'T10:00:00', cats: ['household'], kind: 'Service', tone: 'grey', text: s.merchant + ', ' + s.kind + ': ' + s.what + (s.amount ? ' (' + money_(s) + ')' : '') + '. Read from the receipt.', artifact_id: s.artifact_id }));
  // To-dos.
  (raw.todos || []).forEach((t) => {
    const cats = ['todos'].concat(GROCERY_WORDS.test(t.title) ? ['grocery'] : []);
    push({ at: t.created_at, cats, kind: 'To-do', tone: 'blue', text: (m.name(t.created_by) || 'Someone') + ' added \u201C' + t.title + '\u201D' + (t.assigned_to ? ' for ' + m.name(t.assigned_to) : '') + (t.due_date ? ', by ' + fmtDay(t.due_date) : '') + '.', todo: t.id });
    if (t.done_at) push({ at: t.done_at, cats, kind: 'Done', tone: 'green', text: (m.name(t.done_by) || 'Someone') + ' ticked off \u201C' + t.title + '\u201D.' });
  });
  // Calendar entries ahead.
  (raw.calendar || []).forEach((e) => push({ at: e.starts_at, cats: ['calendar'], kind: 'On the calendar', tone: 'blue', text: e.summary + (e.all_day ? ' (all day)' : ''), future: true }));
  ev.sort((a, b) => String(b.at).localeCompare(String(a.at)));
  return ev;
}

function money_(c) { return money(c.amount, c.currency); }

/* ── who is looking ──────────────────────────────────────────── */

export const PERSONAS = { toddler: 1, child: 2, preteen: 3, teen: 4, lateteen: 5, young: 6, adult: 7, senior: 8 };
export const STAGE_NAMES = {
  1: 'The Playful Spark', 2: 'The Adventure Pod', 3: 'The Bio-Kinetic Catalyst', 4: 'The Glitch Synth',
  5: 'The Kinetic Prism', 6: 'The Digital Oasis', 7: 'The Quantum Glass Hub', 8: 'The Warm Solaria',
};
export function segOf(stage) { return stage <= 3 ? 'kid' : stage <= 5 ? 'teen' : stage === 8 ? 'senior' : 'adult'; }

function ageOn(dob, todayIso) {
  const b = new Date(dob + 'T00:00:00'), t = new Date(todayIso + 'T00:00:00');
  let a = t.getFullYear() - b.getFullYear();
  if (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate())) a -= 1;
  return a;
}
/* From the signed-in member: a birth date decides; a child with none is read
   from the class they are in when it says (KG = 4, class 4 = 9), else 6-8. */
export function stageFor(member, todayIso) {
  if (!member) return 7;
  let age = member.date_of_birth ? ageOn(member.date_of_birth, todayIso) : null;
  if (member.role === 'child') {
    if (age === null && member.class_label) {
      const s = String(member.class_label);
      if (/pre-?kg|nursery|play/i.test(s)) age = 3;
      else if (/u?kg|lkg/i.test(s)) age = 4;
      else { const n = parseInt(s, 10); if (n >= 1 && n <= 12) age = n + 5; }
    }
    if (age === null) return 2;
    return age <= 5 ? 1 : age <= 8 ? 2 : age <= 12 ? 3 : age <= 15 ? 4 : 5;
  }
  if (age === null) return 7;
  return age <= 18 ? 5 : age <= 25 ? 6 : age >= 60 ? 8 : 7;
}
