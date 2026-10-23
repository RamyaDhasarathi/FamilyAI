/* FamilyOS console.
 *
 * Served by the API it talks to, so a request is same-origin and the member's
 * bearer token goes straight on it: no CORS rule, no second host.
 *
 * The one idea this console is built around: a claim shows the words it was
 * read from, and where they sit in the original. Claims carry a page, a
 * character span and a box per line, so selecting a claim draws those boxes
 * over the rendered page. A claim the grounder could not place says so, and
 * never became an obligation.
 */
'use strict';

const PDFJS_VERSION = '3.11.174';
const PDFJS_BASE = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/' + PDFJS_VERSION;

const root = document.getElementById('root');
const store = {
  token: null,
  me: null,
  household: null,
  mailboxes: [],
  quarantineCount: 0,
  amendmentCount: 0,
};

/* ── plumbing ─────────────────────────────────────────────────── */

function readToken() {
  try { return localStorage.getItem('familyos.token'); } catch (e) { return null; }
}
function writeToken(value) {
  try {
    if (value) localStorage.setItem('familyos.token', value);
    else localStorage.removeItem('familyos.token');
  } catch (e) { /* private window: the session simply does not outlive the tab */ }
}

class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.detail || body.error)) || ('HTTP ' + status));
    this.status = status;
    this.body = body || {};
  }
}

/* Every request shows itself. A thin bar along the top of the page while any
   call is in flight (after 150ms, so a fast one never flickers), and the
   button that was just pressed goes busy until the call it caused settles.
   Both are automatic: no handler has to remember. */
let inFlight = 0, barTimer = null;
function netbar(on) {
  let bar = document.querySelector('.netbar');
  if (on) {
    if (barTimer || (bar && bar.classList.contains('on'))) return;
    barTimer = setTimeout(() => { barTimer = null; if (!bar) { bar = document.createElement('div'); bar.className = 'netbar'; document.body.appendChild(bar); } bar.classList.add('on'); }, 150);
  } else {
    if (barTimer) { clearTimeout(barTimer); barTimer = null; }
    if (bar) bar.classList.remove('on');
  }
}
let pressed = null, pressedAt = 0;
document.addEventListener('click', (ev) => {
  const b = ev.target && ev.target.closest ? ev.target.closest('button, a.btn') : null;
  if (b) { pressed = b; pressedAt = Date.now(); }
}, true);
document.addEventListener('submit', (ev) => { if (ev.submitter) { pressed = ev.submitter; pressedAt = Date.now(); } }, true);
document.addEventListener('click', (ev) => {
  const card = ev.target && ev.target.closest ? ev.target.closest('.ov-card[data-href]') : null;
  if (card && !ev.target.closest('a, button')) go(card.dataset.href.replace(/^#/, ''));
});
function busy(el) {
  if (!el || el.getAttribute('aria-busy') === 'true') return () => {};
  const wasDisabled = el.disabled;
  el.setAttribute('aria-busy', 'true'); el.disabled = true;
  return () => { if (!document.body.contains(el)) return; el.removeAttribute('aria-busy'); if (!wasDisabled) el.disabled = false; };
}

async function api(path, options) {
  const opts = options || {};
  const headers = Object.assign({}, opts.headers);
  if (store.token) headers.Authorization = 'Bearer ' + store.token;
  let body = opts.body;
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.json);
  }
  // The button pressed in the last half-second is the one this call answers.
  const cause = pressed && Date.now() - pressedAt < 600 && (opts.method || 'GET') !== 'GET' ? pressed : null;
  const release = cause ? busy(cause) : () => {};
  inFlight += 1; netbar(true);
  let res;
  try {
    res = await fetch('/v1' + path, { method: opts.method || 'GET', headers, body });
  } finally {
    inFlight -= 1; if (inFlight <= 0) { inFlight = 0; netbar(false); }
    release();
  }
  if (res.status === 204) return null;
  const raw = opts.blob ? null : await res.text();
  if (!res.ok) {
    let parsed = null;
    try { parsed = raw ? JSON.parse(raw) : null; } catch (e) { parsed = { detail: raw }; }
    if (res.status === 401 && store.token) { forget(); }
    throw new ApiError(res.status, parsed);
  }
  if (opts.blob) return res.blob();
  if (opts.text) return raw || '';
  return raw ? JSON.parse(raw) : null;
}

function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

let flashTimer = null;
function flash(message, bad) {
  const old = document.querySelector('.flash');
  if (old) old.remove();
  if (flashTimer) clearTimeout(flashTimer);
  const el = document.createElement('div');
  el.className = 'flash' + (bad ? ' bad' : '');
  el.setAttribute('role', 'status');
  el.textContent = message;
  document.body.appendChild(el);
  flashTimer = setTimeout(() => el.remove(), 5200);
}

function fail(err) {
  const extra = err.body && err.body.member_ids ? ' (' + err.body.member_ids.length + ' child without consent)' : '';
  flash(err.message + extra, true);
}

const DAY = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
function date(iso) {
  if (!iso) return '';
  const d = new Date(iso.length <= 10 ? iso + 'T00:00:00' : iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString(undefined, DAY);
}
function ago(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  if (mins < 1440) return Math.round(mins / 60) + 'h ago';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}
function bytes(n) {
  if (!n && n !== 0) return '';
  if (n < 1024) return n + ' B';
  if (n < 1048576) return Math.round(n / 1024) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
}
function money(value, currency) {
  if (value === null || value === undefined) return '';
  const symbol = { INR: '₹', USD: '$', GBP: '£', EUR: '€', SGD: 'S$', AED: 'AED ' }[currency];
  const n = Number(value);
  const shown = Number.isInteger(n) ? String(n) : n.toFixed(2);
  return symbol ? symbol + shown : shown + (currency ? ' ' + currency : '');
}
function initial(name) { return (name || '?').trim().charAt(0).toUpperCase(); }

function memberName(id) {
  if (!id || !store.household) return '';
  const m = (store.household.members || []).find((x) => x.id === id);
  return m ? m.display_name : '';
}
function membersByRole(roles) {
  if (!store.household) return [];
  return (store.household.members || []).filter((m) => roles.indexOf(m.role) !== -1);
}

/* ── theme ────────────────────────────────────────────────────── */
/* Dark by default. The choice is per browser and never leaves it: it is a
   convenience, not household data, so it has no business in the database. */

const THEME_KEY = 'familyos.theme';

function theme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function setTheme(next) {
  if (next === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
  else document.documentElement.removeAttribute('data-theme');
  // May throw in a private window, and the theme still applied, so this is
  // the last thing done and its failure changes nothing on screen.
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* this session only */ }
}

/* ── routing ──────────────────────────────────────────────────── */

const ROUTES = [
  { path: /^\/(today|home)$/, view: pulseView, nav: 'home' },   // #/home is the old name, kept for links in the wild
  { path: /^\/family$/, view: familyView, nav: 'family' },
  { path: /^\/life$/, view: lifeView, nav: 'life' },
  { path: /^\/space\/([a-z]+)$/, view: spaceView, nav: 'space' },
  { path: /^\/memories$/, view: memoriesView, nav: 'memories' },
  { path: /^\/chat$/, view: chatView, nav: 'chat' },
  { path: /^\/notices\/([0-9a-f-]{36})$/i, view: noticeView },
  { path: /^\/notices$/, view: noticesView, nav: 'notices' },
  { path: /^\/waiting$/, view: todayView, nav: 'today' },
  { path: /^\/money$/, view: moneyView, nav: 'money' },
  { path: /^\/plans\/([0-9a-f-]{36})$/i, view: planView, nav: 'plans' },
  { path: /^\/plans$/, view: plansView, nav: 'plans' },
  { path: /^\/quarantine$/, view: quarantineView, nav: 'quarantine' },
  { path: /^\/revisions$/, view: amendmentsView, nav: 'revisions' },
  { path: /^\/collect$/, view: collectView, nav: 'collect' },
  { path: /^\/household$/, view: householdView, nav: 'household' },
  { path: /^\/sign-in$/, view: signInView, nav: 'household' },
  { path: /^\/errands$/, view: errandsView, nav: 'errands' },
  { path: /^\/errands\/([0-9a-f-]{36})$/i, view: errandView, nav: 'errands' },
  { path: /^\/audit$/, view: auditView, nav: 'audit' },
];

/* The Google callback comes back to #/household?mailbox=connected, so a path
   has to survive having a query on it. */
function here() {
  const raw = location.hash.replace(/^#/, '').split('?')[0];
  return raw || '/today';
}
function hashQuery() {
  return new URLSearchParams(location.hash.replace(/^#/, '').split('?')[1] || '');
}
function go(path) { location.hash = path; }

async function render() {
  if (!store.token) { gateView(); return; }
  const path = here();
  const match = ROUTES.map((r) => ({ r, m: path.match(r.path) })).find((x) => x.m);
  const route = match ? match.r : ROUTES[0];
  const args = match ? match.m.slice(1) : [];

  root.className = '';
  const navKey = route.nav === 'space' ? 'space:' + (args[0] || '') : route.nav;
  root.innerHTML = '<div class="shell">' + chrome(navKey)
    + '<main><div class="skel" style="height:28px;width:260px;margin-bottom:14px"></div>'
    + '<div class="skel" style="height:120px"></div></main>'
    + '<aside class="context" data-context></aside></div>'
    + (route.view === chatView ? '' : askBar());
  wireChrome();
  wireAsk();
  const main = root.querySelector('main');
  try {
    await route.view(main, args);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return;
    main.innerHTML = '<div class="card pad"><h2>That did not load</h2><p class="muted" style="margin-top:8px">'
      + esc(err.message) + '</p></div>';
  }
}

/* ── chrome ───────────────────────────────────────────────────── */


/* ── icons: a small outline set, drawn inline so colour follows the text ── */
const ICON_PATHS = {
  invest: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8.5-8 9.5C7.5 20.5 4 17 4 12V6z"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5"/><path d="M4 19h16"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  'arrow-up': '<path d="M12 19V5M5 12l7-7 7 7"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  more: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  today: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  family: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  life: '<circle cx="12" cy="12" r="10"/><path d="M16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88z"/>',
  memories: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  school: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
  travel: '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
  money: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  health: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z"/><path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>',
  attach: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  open: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m2 7 10 7 10-7"/>',
  phone: '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M11 18h2"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  upload: '<path d="M12 16V4M6 10l6-6 6 6"/><path d="M4 20h16"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  cart: '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>',
  sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
};
function icon(name, size) {
  return '<svg class="i" width="' + (size || 18) + '" height="' + (size || 18) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICON_PATHS[name] || '') + '</svg>';
}
/* The sidebar: Today, Family, Life, Memories; then the spaces of a family's
   life, each with its hue; Settings at the foot. Never the architecture:
   nothing here is called a quarantine, a revision or an agent. On a phone
   the four a parent opens most are a bar along the bottom. */
const TABS = ['home', 'family', 'life', 'money'];
const SPACES = {
  // Home has no page of its own: its notices and its ledger live on Life.
  home: { label: 'Home', glyph: '⌂', hue: 'home', categories: ['home', 'food', 'shopping', 'government', 'unknown'], onLife: true },
  school: { label: 'School', glyph: '⚑', hue: 'school', categories: ['school'] },
  health: { label: 'Health', glyph: '❤', hue: 'health', categories: ['medical', 'insurance'] },
  travel: { label: 'Travel', glyph: '✈', hue: 'travel', categories: ['travel'] },
  money: { label: 'Money', glyph: '₹', hue: 'money', categories: ['bills', 'banking', 'subscriptions'] },
  invest: { label: 'Investments', glyph: '⇗', hue: 'invest', categories: ['trading'] },
};
function spaceOf(category) {
  for (const [key, sp] of Object.entries(SPACES)) if (sp.categories.includes(category)) return key;
  return 'home';
}
/* A notice's space: its category, or, when the sender gave none away -- a
   circular shared from a phone -- the child it names puts it in School. */
function spaceOfNotice(n) {
  if ((!n.category || n.category === 'unknown') && (n.subject_member_ids || []).some((id) => childIds().includes(id))) return 'school';
  return spaceOf(n.category);
}

function chrome(active) {
  const link = (id, name, label, extra, hue) =>
    '<a href="#/' + id + '"' + (active === id ? ' aria-current="page"' : '') + (TABS.includes(id) ? ' data-tab' : '') + '>'
    + '<span class="g"' + (hue ? ' style="color:var(--' + hue + ')"' : '') + '>' + icon(name) + '</span>'
    + '<span class="l">' + label + '</span>' + (extra || '') + '</a>';
  const badge = store.quarantineCount ? '<span class="count">' + store.quarantineCount + '</span>' : '';
  const settingsBadge = '';
  const dark = theme() === 'dark';
  const ms = members();
  return '<aside class="side">'
    + '<div class="brand"><span class="mark">' + icon('home', 16) + '</span><b>FamilyOS</b></div>'
    + '<nav class="nav">'
    + link('home', 'today', 'Today')
    + link('life', 'family', 'Family')
    + link('memories', 'memories', 'Memories')
    + '<span class="group"></span>'
    + Object.entries(SPACES).filter(([, sp]) => !sp.onLife).map(([key, sp]) => key === 'money'
      ? link('money', 'money', sp.label, '', sp.hue)
      : link('space/' + key, key, sp.label, '', sp.hue).replace('href="#/space/' + key + '"', 'href="#/space/' + key + '"' + (active === 'space:' + key ? ' aria-current="page"' : ''))).join('')
    + '<span class="group"></span>'
    + link('notices', 'mail', 'Inbox')
    + link('today', 'bell', 'Waiting on you')
    + link('chat', 'sparkle', 'Ask')
    + link('errands', 'cart', 'Errands')
    + (store.me && store.me.role === 'guardian'
      ? '<span class="group"></span>'
        + link('quarantine', 'shield', 'Quarantine', badge)
        + link('revisions', 'refresh', 'Revisions')
        + link('collect', 'download', 'Collect')
        + link('audit', 'list', 'Audit')
      : '')
    + '<span class="group"></span>'
    + '<a href="#" data-open-search><span class="g">' + icon('search') + '</span><span class="l">Search</span><span class="kbd" style="margin-left:auto">⌘K</span></a>'
    + link('household', 'settings', 'Settings', settingsBadge)
    + '<button class="more" data-more' + (TABS.includes(active) ? '' : ' aria-current="page"') + ' aria-expanded="false">'
    + '<span class="g" aria-hidden="true">' + icon('more') + '</span><span class="l">More</span></button>'
    + '</nav>'
    + '<a class="homecard" href="#/family"><span class="sky"></span><b>' + esc(store.household ? store.household.name : 'Our home') + '</b><span>' + ms.length + ' of you · a calmer week, together.</span></a>'
    + '<div class="who"><span class="avatar">' + esc(initial(store.me && store.me.display_name)) + '</span>'
    + '<span class="name">' + esc(store.me ? store.me.display_name : '') + '</span>'
    + '<button class="icon-btn" data-theme-toggle title="' + (dark ? 'Switch to light' : 'Switch to dark') + '" aria-label="' + (dark ? 'Switch to light' : 'Switch to dark') + '">' + icon(dark ? 'sun' : 'moon', 16) + '</button>'
    + '<button class="icon-btn" data-signout title="Sign out" aria-label="Sign out">' + icon('logout', 16) + '</button></div>'
    + '</aside>';
}

/* ── the context panel: navigate less, expand context instead ─────── */
let contextOpen = false;
function openContext(title, fill) {
  const shell = root.querySelector('.shell'); const panel = root.querySelector('[data-context]');
  if (!shell || !panel) return;
  panel.innerHTML = '<div class="ctx-head"><span class="t">' + esc(title || '') + '</span>'
    + '<a class="ib" data-ctx-full href="#" title="Open as a page" aria-label="Open as a page">' + icon('open') + '</a>'
    + '<button class="ib" data-ctx-close aria-label="Close">' + icon('x') + '</button></div>'
    + '<div class="ctx-body"><div class="skel" style="height:80px"></div></div>'
  shell.classList.add('has-context'); contextOpen = true;
  panel.querySelector('[data-ctx-close]').addEventListener('click', closeContext);
  const body = panel.querySelector('.ctx-body');
  const full = panel.querySelector('[data-ctx-full]');
  Promise.resolve(fill(body, full)).catch((err) => { body.innerHTML = '<p class="muted">' + esc(err.message) + '</p>'; });
}
function closeContext() {
  const shell = root.querySelector('.shell'); const panel = root.querySelector('[data-context]');
  if (shell) shell.classList.remove('has-context');
  if (panel) setTimeout(() => { if (!contextOpen) panel.innerHTML = ''; }, 240);
  contextOpen = false;
}
document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && contextOpen) closeContext(); });
/* A notice opened from a card expands beside the page rather than replacing it. */
document.addEventListener('click', (ev) => {
  const a = ev.target && ev.target.closest ? ev.target.closest('a[href^="#/notices/"]') : null;
  if (!a || ev.metaKey || ev.ctrlKey || window.innerWidth <= 880 || !root.querySelector('[data-context]')) return;
  if (a.closest('[data-context]')) return;
  const id = a.getAttribute('href').split('/')[2];
  if (!id || id.length !== 36) return;
  ev.preventDefault();
  openContext('Notice', async (body, full) => {
    full.href = '#/notices/' + id;
    const main = document.createElement('main'); body.innerHTML = ''; body.appendChild(main);
    await noticeView(main, [id]);
  });
});

/* ── Ask FamilyOS: the command surface, everywhere ───────────────── */
const ASK_SUGGESTIONS = [
  ['sun', "What's everyone doing tomorrow?"], ['travel', 'Plan our weekend'], ['money', 'What do we pay every month?'],
  ['school', 'What school work is pending?'], ['home', 'Plan dinner tonight'], ['calendar', 'When are we all free?'],
];
function askBar() {
  return '<div class="askbar" data-askbar role="button" tabindex="0"><span class="star">\u2726</span>'
    + '<span class="ph">Ask FamilyOS anything\u2026</span><span class="kbd">\u2318K</span>'
    + '<button class="ib" data-ask-attach title="Add a notice or a photo" aria-label="Add a notice or a photo">' + icon('attach') + '</button>'
    + '<button class="ib" data-ask-mic title="Say it" aria-label="Say it">' + icon('mic') + '</button></div>';
}
/* Say it: the browser's own speech recognition, where it has one. */
function listen(onText) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { flash('This browser cannot listen; type it instead.', true); return; }
  const r = new SR(); r.lang = 'en-IN'; r.interimResults = false;
  r.onresult = (ev) => { const t = ev.results[0][0].transcript; if (t) onText(t); };
  r.onerror = () => flash('Could not hear that.', true);
  r.start();
}
/* ⌘K: find, or ask. Typing finds pages, people, notices, plans and
   documents by their words; Enter opens the first hit, or, when nothing
   matches or the words end in a question mark, asks FamilyOS. */
const FIND_PAGES = [['Today', '#/today', 'today'], ['Family', '#/family', 'family'], ['Life', '#/life', 'life'], ['Memories', '#/memories', 'memories'],
  ['Inbox', '#/notices', 'mail'], ['Waiting on you', '#/waiting', 'bell'], ['Ask', '#/chat', 'sparkle'], ['Plans', '#/plans', 'calendar'],
  ['Errands', '#/errands', 'cart'], ['Money', '#/money', 'money'], ['Settings', '#/household', 'settings'], ['Quarantine', '#/quarantine', 'shield'],
  ['Revisions', '#/revisions', 'refresh'], ['Collect', '#/collect', 'download'], ['Audit', '#/audit', 'list']];
let _findCache = { at: 0, notices: [], plans: [], documents: [] };
async function findIndex() {
  if (Date.now() - _findCache.at < 60000) return _findCache;
  const [notices, plans, documents] = await Promise.all([
    api('/inbox?days=365&limit=400').catch(() => []), api('/plans').catch(() => []), api('/documents').then((d) => d.documents || []).catch(() => [])]);
  _findCache = { at: Date.now(), notices, plans, documents };
  return _findCache;
}
function findHits(q, idx) {
  const words = q.toLowerCase().split(/\s+/).filter((w) => w.length >= 2);
  if (!words.length) return [];
  const has = (hay) => { const h = (hay || '').toLowerCase(); return words.every((w) => h.includes(w)); };
  const hits = [];
  FIND_PAGES.forEach(([label, href, ic]) => { if (has(label)) hits.push({ kind: 'page', title: label, sub: 'page', href, icon: ic }); });
  Object.entries(SPACES).forEach(([key, sp]) => { if (has(sp.label)) hits.push({ kind: 'page', title: sp.label, sub: 'space', href: key === 'money' ? '#/money' : sp.onLife ? '#/life' : '#/space/' + key, icon: key }); });
  members().forEach((m) => { if (has(m.display_name)) hits.push({ kind: 'person', title: m.display_name, sub: m.role, person: m.id, icon: 'family' }); });
  idx.plans.filter((pl) => pl.status !== 'dropped' && has(pl.title)).forEach((pl) => hits.push({ kind: 'plan', title: pl.title, sub: 'plan', href: '#/plans/' + pl.id, icon: 'calendar' }));
  idx.documents.filter((d) => has([d.title, d.holder_name, d.label].join(' '))).forEach((d) => hits.push({ kind: 'document', title: d.title, sub: [d.holder_name, d.label].filter(Boolean).join(' · '), href: '#/notices/' + d.artifact_id, icon: 'doc' }));
  idx.notices.filter((n) => has([n.headline, n.from_label, ...(n.preview || [])].join(' '))).slice(0, 8)
    .forEach((n) => hits.push({ kind: 'notice', title: n.headline || 'Notice', sub: n.from_label + ' · ' + ago(n.received_at), href: '#/notices/' + n.id, icon: (CHANNEL[n.channel] || {}).icon || 'doc' }));
  return hits.slice(0, 10);
}

function openPalette(prefill) {
  if (document.querySelector('.palette')) return;
  const el = document.createElement('div'); el.className = 'palette';
  el.innerHTML = '<div class="box"><form data-palette><span class="star" style="color:var(--primary);display:grid;place-items:center">' + icon('search', 18) + '</span>'
    + '<input type="text" name="q" placeholder="Find a notice, a person, a page — or ask anything…" autocomplete="off" maxlength="1000"></form>'
    + '<div class="sugg" data-sugg-list>' + ASK_SUGGESTIONS.map(([g, t]) => '<button type="button" data-sugg="' + esc(t) + '"><span class="g">' + icon(g, 15) + '</span>' + esc(t) + '</button>').join('') + '</div>'
    + '<div class="sugg" data-hits hidden></div>'
    + '<div class="foot">Type to find · Enter opens the first match, or asks · Esc closes. It sees only what you can see, and changes nothing until you confirm.</div></div>';
  document.body.appendChild(el);
  const input = el.querySelector('input'); if (prefill) input.value = prefill; input.focus();
  el.querySelector('form').insertAdjacentHTML('beforeend', '<button type="button" class="ib" data-pal-mic aria-label="Say it">' + icon('mic') + '</button>');
  el.querySelector('[data-pal-mic]').addEventListener('click', () => listen((t) => { input.value = t; input.focus(); input.dispatchEvent(new Event('input')); }));
  const close = () => el.remove();
  const hitsBox = el.querySelector('[data-hits]'); const suggBox = el.querySelector('[data-sugg-list]');
  let hits = [];
  const open = (h) => { close(); if (h.person) { openPerson(h.person); } else if (h.href) { location.hash = h.href; } };
  const paint = () => {
    const q = input.value.trim();
    if (q.length < 2) { hitsBox.hidden = true; suggBox.hidden = false; hits = []; return; }
    suggBox.hidden = true; hitsBox.hidden = false;
    hitsBox.innerHTML = hits.map((h, i) => '<button type="button" data-hit="' + i + '"><span class="g">' + icon(h.icon, 15) + '</span><span class="grow" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(h.title) + '</span><span class="muted" style="white-space:nowrap">' + esc(h.sub) + '</span></button>').join('')
      + '<button type="button" data-ask-it><span class="g">' + icon('sparkle', 15) + '</span>Ask FamilyOS: “' + esc(q) + '”</button>';
    hitsBox.querySelectorAll('[data-hit]').forEach((b) => b.addEventListener('click', () => open(hits[+b.dataset.hit])));
    hitsBox.querySelector('[data-ask-it]').addEventListener('click', () => { close(); ask(q); });
  };
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => { const idx = await findIndex(); hits = findHits(input.value.trim(), idx); paint(); }, 120);
  });
  el.addEventListener('click', (ev) => { if (ev.target === el) close(); });
  el.querySelector('form').addEventListener('submit', (ev) => {
    ev.preventDefault(); const q = input.value.trim(); if (!q) return;
    if (hits.length && !/\?\s*$/.test(q)) { open(hits[0]); return; }
    close(); ask(q);
  });
  el.querySelectorAll('[data-sugg]').forEach((b) => b.addEventListener('click', () => { close(); ask(b.dataset.sugg); }));
  const onKey = (ev) => { if (ev.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); } };
  document.addEventListener('keydown', onKey);
  if (prefill) input.dispatchEvent(new Event('input'));
}
/* Asking takes you to the answer. A plan becomes a plan page; spending
   becomes the Money view; everything else is the conversation. */
/* Open Ask with a question already asked. The question rides in the hash,
   so it survives a browser that refuses session storage (a private window,
   a home-screen web app) and a page that is already on Ask. */
function openAsk(text) {
  const target = '/chat?q=' + encodeURIComponent(text);
  if (location.hash === '#' + target) { render().catch(() => {}); return; }
  go(target);
}

function ask(text) {
  if (/spend|spending|pay every|bills?\b|subscriptions?/i.test(text) && !/plan|book|order/i.test(text)) { go('/money'); return; }
  openAsk(text);
}
function wireAsk() {
  const sr = root.querySelector('[data-open-search]');
  if (sr) sr.addEventListener('click', (ev) => { ev.preventDefault(); openPalette(); });
  const bar = root.querySelector('[data-askbar]');
  if (bar) {
    bar.querySelector('[data-ask-attach]').addEventListener('click', (ev) => { ev.stopPropagation(); go('/notices'); });
    bar.querySelector('[data-ask-mic]').addEventListener('click', (ev) => { ev.stopPropagation(); listen((t) => openPalette(t)); });
    bar.addEventListener('click', () => openPalette()); bar.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openPalette(); } }); }
}
document.addEventListener('keydown', (ev) => {
  if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k' && store.token) { ev.preventDefault(); openPalette(); }
});

function wireChrome() {
  const more = root.querySelector('[data-more]');
  if (more) more.addEventListener('click', () => {
    const side = root.querySelector('.side');
    const open = side.classList.toggle('open');
    more.setAttribute('aria-expanded', open ? 'true' : 'false');
    more.querySelector('.l').textContent = open ? 'Close' : 'More';
  });
  const btn = root.querySelector('[data-signout]');
  if (btn) btn.addEventListener('click', () => { signOut().catch(() => forget()); });
  const swap = root.querySelector('[data-theme-toggle]');
  if (swap) swap.addEventListener('click', async () => {
    setTheme(theme() === 'dark' ? 'light' : 'dark');
    // Re-rendered rather than just restyled: a rendered PDF page is drawn to a
    // canvas, so its backdrop does not follow a CSS variable on its own.
    await render();
  });
}

function forget() {
  store.token = null;
  store.me = null;
  store.household = null;
  writeToken(null);
  gateView();
}

async function signOut() {
  // End the token on the server first. Clearing localStorage alone only
  // forgets it in this browser: it would keep working for anyone holding it.
  try {
    if (store.token) await api('/signout', { method: 'POST' });
  } catch (e) { /* already gone, or the server cannot be reached */ }
  forget();
}

/* ── sign in ──────────────────────────────────────────────────── */

function gateView(notice, opts) {
  root.className = '';
  // opts.newEmail: Google verified this address and no household uses it, so
  // the gate opens on Start a household with it filled in rather than on a
  // sign-in that has nothing to sign into.
  const newEmail = (opts && opts.newEmail) || '';
  const founding = (opts && opts.founding) || '';
  root.innerHTML = '<div class="gate">'
    + '<div><div class="mark">FamilyOS</div>'
    + '<p class="lede" style="margin-top:10px">School notices, bills and forms turned into things that get done &mdash; '
    + 'without losing track of where each fact came from, or who is allowed to see it.</p></div>'
    + '<div class="tabs"><button data-tab="in" aria-pressed="' + String(!newEmail) + '">Sign in</button>'
    + '<button data-tab="new" aria-pressed="' + String(!!newEmail) + '">Start a household</button></div>'
    + '<div class="card pad" data-panel="in"' + (newEmail ? ' hidden' : '') + '>'
    + '<button class="btn" data-google style="width:100%;justify-content:center">Continue with Google</button>'
    + '<p class="muted" style="margin:10px 0 14px;line-height:1.5">Signing in asks Google for your address '
    + 'and nothing else. Reading your mail is a separate choice, later, that you can decline.</p>'
    + '<div class="row" style="gap:10px"><span class="rule"></span>'
    + '<span class="muted" style="flex-shrink:0">or</span><span class="rule"></span></div>'
    + '<form class="stack" data-form="link" style="margin-top:14px">'
    + '<label>Your email<input type="email" name="email" placeholder="you@example.com" required '
    + 'autocomplete="email"></label>'
    + '<p class="muted">We send a link that signs you in. No password to remember, and nothing to copy.</p>'
    + '<button class="btn" type="submit">Email me a link</button>'
    + '<p class="sub" data-linksent hidden></p>'
    + '</form>'
    + '<details style="margin-top:14px"><summary class="muted" style="cursor:pointer">I have a token</summary>'
    + '<form class="stack" data-form="in" style="margin-top:10px">'
    + '<label>Sign-in token<input type="password" name="token" placeholder="fos_&hellip;" autocomplete="off" required></label>'
    + '<button class="btn ghost" type="submit">Sign in</button></form></details>'
    + '</div>'
    + '<div class="card pad" data-panel="new"' + (newEmail ? '' : ' hidden') + '>'
    + (newEmail
      ? '<p class="sub" style="margin-bottom:14px;line-height:1.5">Google confirmed <b>' + esc(newEmail) + '</b>. '
        + 'No household uses it yet &mdash; start one and you will be its first guardian.</p>'
      : '')
    + '<form class="stack" data-form="new">'
    + '<label>Household name<input type="text" name="name" placeholder="The Iyer family" required maxlength="100"' + (newEmail ? ' autofocus' : '') + '></label>'
    + '<label>Your name<input type="text" name="display_name" placeholder="Amma" required maxlength="100"></label>'
    + '<label>Your email<input type="email" name="email" placeholder="you@example.com" required value="' + esc(newEmail) + '"></label>'
    + '<p class="muted">Creates the household and makes you its first guardian.</p>'
    + '<button class="btn" type="submit">Create household</button></form></div>'
    + '</div>';

  if (notice) flash(notice, true);

  root.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const want = btn.dataset.tab;
      root.querySelectorAll('[data-tab]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === want)));
      root.querySelectorAll('[data-panel]').forEach((p) => { p.hidden = p.dataset.panel !== want; });
    });
  });

  const google = root.querySelector('[data-google]');
  if (google) google.addEventListener('click', async () => {
    try {
      const where = await api('/sign-in/google');
      location.href = where.url;
    } catch (err) {
      // Most often: this deployment has no Google client configured.
      fail(err);
    }
  });

  root.querySelector('[data-form="link"]').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const email = new FormData(ev.target).get('email').trim();
    if (!email) return;
    const said = root.querySelector('[data-linksent]');
    try {
      await api('/sign-in/request', { method: 'POST', json: { email } });
    } catch (e) { /* the answer is the same either way, on purpose */ }
    // Said whether or not the address belongs to a family: which addresses do
    // is not a stranger's to learn by watching this form.
    said.textContent = 'If ' + email + ' can sign in, a link is on its way. '
      + 'It works once and lasts 15 minutes.';
    said.hidden = false;
  });

  root.querySelector('[data-form="in"]').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const token = new FormData(ev.target).get('token').trim();
    if (!token) return;
    store.token = token;
    try {
      await boot();
    } catch (err) {
      store.token = null;
      flash('That token was not accepted.', true);
    }
  });

  root.querySelector('[data-form="new"]').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const form = new FormData(ev.target);
    try {
      const made = await api('/households', { method: 'POST', json: {
        name: form.get('name').trim(),
        guardian: { display_name: form.get('display_name').trim(), email: form.get('email').trim() },
        founding: founding,
      } });
      store.token = made.credentials.token;
      await boot();
    } catch (err) { fail(err); }
  });
}

/* A link arrives as ?link=lnk_... on the console's own URL. Spend it, keep the
   session it returns, and take the link back out of the address bar so it is
   not sitting in history or a screenshot. */
/* Google sends the browser back to /app/#token=... -- the fragment never
   reaches a server, and it is taken out of the address bar at once. */
function takeTokenFromFragment() {
  return takeFromFragment('token');
}

/* Google also sends back a verified address that has no household yet, the
   same way: in the fragment, read once, then gone. */
/* Several values in the fragment at once (#found=...&email=...), read once
   and gone together. */
function takeAllFromFragment() {
  if (!location.hash || location.hash.length < 2) return {};
  const out = {};
  location.hash.slice(1).split('&').forEach((pair) => {
    const i = pair.indexOf('=');
    if (i > 0) out[pair.slice(0, i)] = decodeURIComponent(pair.slice(i + 1));
  });
  history.replaceState(null, '', location.pathname + location.search);
  return out;
}

function takeFromFragment(name) {
  const match = location.hash.match(new RegExp('^#' + name + '=([^&]+)'));
  if (!match) return null;
  const value = decodeURIComponent(match[1]);
  history.replaceState(null, '', location.pathname + location.search);
  return value;
}

async function redeemLinkFromUrl() {
  const params = new URLSearchParams(location.search);
  const link = params.get('link');
  if (!link) return false;
  params.delete('link');
  const clean = location.pathname + (params.toString() ? '?' + params : '') + location.hash;
  try {
    const signed = await api('/sign-in/redeem', { method: 'POST', json: { link } });
    store.token = signed.token;
    history.replaceState(null, '', clean);
    await boot();
    return true;
  } catch (err) {
    history.replaceState(null, '', clean);
    store.token = null;
    writeToken(null);
    gateView('That link has expired or has already been used. Ask for another.');
    return true;
  }
}

async function boot() {
  const me = await api('/me');
  store.me = me;
  store.token = store.token;
  writeToken(store.token);
  store.household = await api('/household');
  if (me.role === 'guardian') {
    try {
      const q = await api('/quarantine');
      store.quarantineCount = q.length;
    } catch (e) { store.quarantineCount = 0; }
  }
  try {
    store.amendmentCount = (await api('/amendments?status=proposed')).length;
  } catch (e) { store.amendmentCount = 0; }
  await render();
}

/* ── home ─────────────────────────────────────────────────────── */
/* The front door. Left: what needs a decision, worst first, then what was
   spotted and not yet decided, then what arrived. Right: what is coming, the
   bills, the people. A first visit shows a hero that connects a mailbox, and
   the moment one is connected the page reads it in front of the person,
   counting notices and action points as they appear -- because a brief that
   says "nothing yet" on day one is the surest way to never be opened again. */

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function dayKey(iso) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const d = new Date(iso + 'T00:00:00');
  const diff = Math.round((d - today) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  if (diff < 0) return diff === -1 ? 'Yesterday' : Math.abs(diff) + ' days ago';
  if (diff < 7) return d.toLocaleDateString(undefined, { weekday: 'long' });
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}
function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  return { top: d.toLocaleDateString(undefined, { weekday: 'short' }), bottom: d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) };
}

async function homeView(main) {
  main.classList.remove('chat-main');
  const q = hashQuery();
  const [brief, proposed, accepted, notices, billers, mailboxes, week] = await Promise.all([
    api('/brief?limit=8'),
    api('/obligations?status=proposed&limit=100'),
    api('/obligations?status=accepted&limit=100'),
    api('/artifacts?limit=8'),
    api('/billers').catch(() => []),
    api('/google/mailboxes').catch(() => []),
    api('/inbox?days=7&limit=40').catch(() => []),
  ]);
  store.mailboxes = mailboxes;
  const connected = mailboxes.filter((m) => !m.disconnected_at);
  const importing = connected.find((m) => !m.backfill_done);
  const justConnected = q.get('mailbox') === 'connected';
  if (q.get('mailbox') === 'failed') flash('Google did not finish connecting the mailbox. Try again.', true);
  if (q.get('mailbox') === 'cancelled') flash('Connecting the mailbox was cancelled.');
  // No mailbox yet: the hero stays until one is connected, because the
  // household address and forwarding are work and a mailbox is not.
  const fresh = connected.length === 0;

  main.innerHTML = '<div class="home">'
    + '<div class="stack" style="gap:18px">'
    + homeHead(brief)
    + ((justConnected || importing) ? importPanel(importing || connected[connected.length - 1]) : (fresh ? setupHero() : ''))
    + urgentStrip(brief)
    + spottedSection(proposed)
    + '</div>'
    + '<aside class="stack" style="gap:14px">'
    + comingUpCard(accepted, proposed)
    + billsCard(billers)
    + peopleCard(week)
    + guardianCard()
    + '</aside></div>'
    + assignDialog();
  wireHome(main);
  wireAssignDialog(main);
  wireAssignButtons(main);
  loadRecurringCard(main);
  loadTodosCard(main);
  loadSuggestionsCard(main);
  if (justConnected || importing) {
    const account = importing || connected[connected.length - 1];
    if (account) runImport(main, account);
  }
}

function homeHead(b) {
  return '<div class="home-head"><div>'
    + '<h1>' + esc(greeting()) + ', ' + esc(b.display_name) + '</h1>'
    + '<div class="sub">' + esc(date(b.date))
    + (b.counts ? '  ·  ' + (b.counts.missed + b.counts.overdue + b.counts.today + b.counts.undecided) + ' things need someone' : '')
    + '</div></div>'
    + '<div class="row" style="gap:8px"><button class="btn ghost sm" data-add>Add a notice</button></div></div>';
}

function setupHero() {
  const h = store.household || {};
  return '<section class="hero">'
    + '<h2>' + (store.household && store.household.members && store.household.members.length > 1
      ? 'Connect your mailbox and the rest reads itself.' : 'Let it read your mail, and the first week fills itself.') + '</h2>'
    + '<p>Connect Gmail and FamilyOS reads the last 30 days of school, clinic and bill mail — only mail that looks '
    + 'like a notice, nothing else — and turns the dates into things to decide. It takes about a minute, and '
    + 'you watch it happen.</p>'
    + '<div class="actions">'
    + '<button class="btn big" data-connect-gmail>Connect Gmail</button>'
    + (h.telegram_bot ? '<button class="btn ghost" data-tglink>Link Telegram</button>' : '')
    + '<button class="btn ghost" data-add>Paste a message</button>'
    + '</div>'
    + (h.inbound_address
      ? '<p style="margin-top:14px;font-size:12px">Or give the school this address: <code class="addr" style="display:inline;padding:3px 7px">'
        + esc(h.inbound_address) + '</code></p>' : '')
    + '</section>';
}

function importPanel(account) {
  return '<section class="card import" data-import data-account="' + esc(account ? account.id : '') + '">'
    + '<div class="row" style="gap:10px"><span class="glyph blue" aria-hidden="true">◔</span>'
    + '<div class="grow"><div class="status" data-import-status">Reading ' + esc(account ? account.email : 'your mailbox') + '…</div>'
    + '<div class="detail" data-import-detail>Only mail that looks like a notice. Nothing is sent, nothing is changed.</div></div></div>'
    + '<div class="prog busy"><i data-import-bar style="width:6%"></i></div>'
    + '<div class="counts">'
    + '<div><b data-c-read>0</b><span>messages read</span></div>'
    + '<div><b data-c-new>0</b><span>notices kept</span></div>'
    + '<div><b data-c-points>0</b><span>action points</span></div>'
    + '</div>'
    + '<div class="found" data-found></div>'
    + '</section>';
}

async function runImport(main, account) {
  const panel = main.querySelector('[data-import]');
  if (!panel) return;
  const el = (sel) => panel.querySelector(sel);
  const say = (status, detail) => {
    if (el('[data-import-status]')) el('[data-import-status]').textContent = status;
    if (detail !== undefined && el('[data-import-detail]')) el('[data-import-detail]').textContent = detail;
  };
  const bar = (pct) => { if (el('[data-import-bar]')) el('[data-import-bar]').style.width = pct + '%'; };
  let read = 0, kept = 0, pages = 0;
  try {
    for (let i = 0; i < 60; i++) {
      const r = await api('/google/mailboxes/' + account.id + '/sync', { method: 'POST' });
      pages += 1;
      read += (r.stored || 0) + (r.duplicates || 0) + (r.refused || 0);
      kept += r.stored || 0;
      el('[data-c-read]').textContent = read;
      el('[data-c-new]').textContent = kept;
      bar(Math.min(80, 10 + pages * 8));
      say('Reading ' + account.email + '…', read + ' messages so far, ' + kept + ' kept as notices.');
      if (!r.backfilling) break;
    }
  } catch (err) {
    say('Could not read the mailbox', err.message);
    panel.querySelector('.prog').classList.remove('busy');
    return;
  }
  say('Mailbox read. Finding the dates…', kept + ' notices are being read for dates and amounts. This takes a moment.');
  bar(85);
  // Extraction runs in the background job worker; watch the action points
  // arrive rather than guess when they are done.
  const seen = new Set();
  let last = -1, steady = 0;
  for (let t = 0; t < 30; t++) {
    await sleep(2500);
    let props = [];
    try { props = await api('/obligations?status=proposed&limit=100'); } catch (e) { break; }
    el('[data-c-points]').textContent = props.length;
    const found = el('[data-found]');
    props.slice(0, 6).forEach((o) => {
      if (seen.has(o.id)) return;
      seen.add(o.id);
      const div = document.createElement('div');
      div.innerHTML = spotRow(o, false);
      found.appendChild(div.firstChild);
    });
    bar(Math.min(98, 85 + t));
    if (props.length === last) steady += 1; else steady = 0;
    last = props.length;
    if (steady >= 4) break;
  }
  bar(100);
  panel.querySelector('.prog').classList.remove('busy');
  say('Done. ' + last + ' action point' + (last === 1 ? '' : 's') + ' to decide.',
    'They are below, and in Waiting on you. Anything you accept goes on the calendar and gets a reminder.');
  history.replaceState(null, '', location.pathname + '#/today');
  await sleep(1400);
  await render();
}

const REASON_LABEL = { handled: 'Handled',
  missed: 'Missed', overdue: 'Overdue', today: 'Today', undecided: 'Undecided', soon: 'Coming up',
  amendment: 'Changed', quarantine: 'Held', mailbox: 'Mailbox', unbilled: 'No bill', school_year: 'New year', birthday: 'Birthday', majority: 'Of age', money: 'Money', prepare: 'Prepare',
};
const REASON_TONE = { handled: 'green', missed: 'red', overdue: 'red', today: 'amber', undecided: 'amber', amendment: 'rust', quarantine: 'rust', mailbox: 'red', unbilled: 'rust', soon: 'blue' };

/* What cannot wait: everything the brief ranks above an undecided date.
   Undecided dates have their own section, so they are not repeated here. */
/* Only what needs a person today or is already late. The money line, a
   closed hand-over and a missing bill are facts for the ledger and the
   Family page, not calls to act. */
const NOT_TODAY = { undecided: 1, soon: 1, money: 1, handled: 1, unbilled: 1 };
function urgentStrip(b) {
  const items = b.items.filter((i) => !NOT_TODAY[i.reason]);
  if (!items.length) return '';
  return '<div class="section-title"><h2>Needs someone</h2><span class="muted">worst first</span></div>'
    + '<div class="ov">' + items.map(overviewCard).join('') + '</div>';
}

/* This week, one card per notice: who sent it, what it asks, whose it is,
   who is handling it. The digest a family reads on Sunday night. */
/* The front page shows a notice only when it means something to a person:
   something open in it, somebody handling it, a child it names, or a thing
   done in the last day. Everything else -- receipts, alerts, a test
   reminder, a photo -- is in the Inbox and on the ledger, not here. */
function worthALook(r) {
  if (r.state === 'todo' || !!r.assigned_to || (r.subject_member_ids || []).length > 0) return true;
  if (r.handled_at && Date.now() - new Date(r.handled_at).getTime() < 86400000) return true;
  return false;
}

function digestSection(all) {
  const week = all.filter(worthALook);
  const hidden = all.length - week.length;
  const ledgerNote = hidden ? '<p class="muted" style="margin:6px 2px 0;font-size:12.5px">' + hidden + ' more with nothing to decide '
    + (hidden === 1 ? 'is' : 'are') + ' in the <a href="#/notices">Inbox</a>; receipts and alerts on <a href="#/money">Money</a>.</p>' : '';
  if (!week.length) {
    return '<div class="section-title"><h2>This week</h2></div>'
      + '<div class="card pad"><p class="muted" style="line-height:1.55">Nothing arrived in the last seven days. '
      + 'Forward a notice, paste one, or connect a mailbox and it reads itself.</p></div>' + ledgerNote;
  }
  const kids = new Set();
  week.forEach((r) => (r.subject_member_ids || []).forEach((k) => kids.add(k)));
  return '<div class="section-title"><h2>This week</h2><span class="muted">' + week.length + ' notice' + (week.length === 1 ? '' : 's')
    + (kids.size ? ' \u00B7 ' + Array.from(kids).map(memberName).filter(Boolean).join(', ') : '') + '</span></div>'
    + '<div class="dg">' + week.slice(0, 6).map(digestCard).join('') + '</div>' + ledgerNote
    + (week.length > 6 ? '<a class="btn ghost sm" href="#/notices" style="align-self:flex-start">All ' + week.length + ' in the inbox</a>' : '');
}

function digestCard(r) {
  const ch = CHANNEL[r.channel] || CHANNEL.upload;
  const kids = (r.subject_member_ids || []).map(memberName).filter(Boolean);
  const who = memberName(r.assigned_to);
  return '<div class="dg-card" data-row="' + esc(r.id) + '">'
    + '<div class="kicker"><span class="glyph ' + ch.tone + '" style="width:22px;height:22px;font-size:11px">' + icon(ch.icon || 'doc', 15) + '</span>'
    + '<b>' + esc(r.from_label) + '</b><span>' + esc(ago(r.received_at)) + '</span>'
    + kids.map((n) => '<span class="tag kid">' + esc(n) + '</span>').join('') + '</div>'
    + '<a class="t title" href="#/notices/' + esc(r.id) + '">' + esc(r.headline || 'Notice') + '</a>'
    + (r.preview.length ? '<ul class="pv">' + r.preview.map((t) => '<li>' + esc(t) + '</li>').join('') + (r.dates > r.preview.length ? '<li class="muted">and ' + (r.dates - r.preview.length) + ' more</li>' : '') + '</ul>'
      : '<p class="muted">Nothing to decide in it.</p>')
    + '<div class="foot">'
    + (r.state === 'todo' ? '<span class="tag amber">' + r.open + ' to decide</span>' : r.state === 'done' ? '<span class="tag green">decided</span>' : '<span class="tag">for information</span>')
    + '<span class="grow"></span>'
    + (who ? '<button class="assignee" data-assign="' + esc(r.id) + '" data-current="' + esc(r.assigned_to) + '"><span class="avatar">' + esc(initial(who)) + '</span>' + esc(who) + '</button>'
      : '<button class="btn ghost sm" data-assign="' + esc(r.id) + '">Hand to\u2026</button>')
    + '</div></div>';
}

function overviewSection(b) {
  if (!b.items.length) {
    return '<div class="section-title"><h2>Your overview</h2></div>'
      + '<div class="card pad"><p class="muted" style="line-height:1.55">Nothing needs anyone today.'
      + (b.next_thing ? ' Next: <b style="color:var(--ink)">' + esc(b.next_thing.title) + '</b>, ' + esc(b.next_thing.when) + '.' : '')
      + '</p></div>';
  }
  return '<div class="section-title"><h2>Your overview</h2><span class="muted">worst first'
    + (b.more ? ' · and ' + b.more + ' more' : '') + '</span></div>'
    + '<div class="ov">' + b.items.map(overviewCard).join('') + '</div>';
}

function overviewCard(i) {
  const href = i.artifact_id ? '#/notices/' + i.artifact_id : (i.reason === 'mailbox' ? '#/household' : i.reason === 'quarantine' ? '#/quarantine' : '#/waiting');
  const who = i.subject_name || memberName(i.subject_member_id);
  return '<div class="ov-card' + (i.reason === 'missed' || i.reason === 'overdue' ? ' missed' : '') + '" data-href="' + href + '">'
    + '<span class="kicker"><span class="tag ' + (REASON_TONE[i.reason] || '') + '">' + esc(REASON_LABEL[i.reason] || i.reason) + '</span>'
    + (i.when ? '<span>' + esc(i.when) + '</span>' : '')
    + (who ? '<span class="tag kid">' + esc(who) + '</span>' : '') + '</span>'
    + '<a class="t" href="' + href + '" style="color:inherit;text-decoration:none">' + esc(i.title) + '</a>'
    + '<span class="why">' + esc(i.why) + (i.clashes && i.clashes.length ? ' · clashes with ' + esc(i.clashes[0]) : '')
    + (i.leave_by ? ' · leave by ' + esc(i.leave_by) + ' (' + esc(String(i.travel_minutes)) + ' min from home)' : '') + '</span>'
    + (i.pay_url ? '<span class="row wrap" style="gap:6px;margin-top:8px">' + payLinks(i.pay_url) + '</span>' : '')
    + '</div>';
}

function spottedSection(proposed) {
  const rows = proposed.slice().sort((a, b) => (a.due_date || '9999') < (b.due_date || '9999') ? -1 : 1);
  return '<div class="section-title"><h2>Dates spotted</h2><span class="muted">'
    + (rows.length ? rows.length + ' to decide · accept puts it on the calendar' : 'nothing waiting') + '</span></div>'
    + (rows.length
      ? '<div class="stack" style="gap:7px" data-spots>' + rows.slice(0, 8).map((o) => spotRow(o, true)).join('')
        + (rows.length > 8 ? '<a class="btn ghost sm" href="#/today" style="align-self:flex-start">All ' + rows.length + '</a>' : '') + '</div>'
      : '<div class="card pad"><p class="muted">When a notice is read, every date it asks about appears here for a yes or a no.</p></div>');
}

function spotRow(o, withActs) {
  const d = o.due_date ? shortDate(o.due_date) : null;
  const who = memberName(o.subject_member_id);
  return '<div class="spot" data-spot="' + esc(o.id) + '">'
    + '<span class="when">' + (d ? '<b>' + esc(d.bottom) + '</b><span>' + esc(d.top) + (o.due_time ? ' · ' + esc(o.due_time) : '') + '</span>' : '<b>—</b><span>no date</span>') + '</span>'
    + '<span class="grow"><a class="t" href="#/notices/' + esc(o.artifact_id) + '" style="color:inherit;text-decoration:none">' + esc(o.title) + '</a>'
    + '<div class="s">' + esc(o.action) + (who ? ' · ' + esc(who) : '') + (o.optional ? ' · optional' : '')
    + (o.pay_url ? ' · ' + payLinks(o.pay_url, 'plain') : '') + '</div></span>'
    + (withActs ? '<span class="acts"><button class="yes" data-decide="accepted" title="Accept">' + icon('check', 14) + '</button>'
      + '<button class="no" data-decide="dismissed" title="Dismiss">' + icon('x', 14) + '</button></span>' : '')
    + '</div>';
}

function recentSection(notices) {
  if (!notices.length) return '';
  return '<div class="section-title"><h2>Arrived</h2><a class="muted" href="#/notices" style="text-decoration:none">all notices</a></div>'
    + '<div class="card list">' + notices.slice(0, 5).map(noticeRow).join('') + '</div>';
}

function comingUpCard(accepted, proposed) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const horizon = new Date(today); horizon.setDate(horizon.getDate() + 14);
  const all = accepted.map((o) => Object.assign({ soft: false }, o)).concat(proposed.map((o) => Object.assign({ soft: true }, o)))
    .filter((o) => o.due_date && new Date(o.due_date + 'T00:00:00') >= today && new Date(o.due_date + 'T00:00:00') <= horizon)
    .sort((a, b) => (a.due_date + (a.due_time || '')) < (b.due_date + (b.due_time || '')) ? -1 : 1);
  let html = '<section class="card rail-card"><h2>Coming up</h2>';
  if (!all.length) html += '<p class="muted">Nothing in the next two weeks. Accept a date and it appears here.</p>';
  let lastDay = null;
  all.slice(0, 10).forEach((o) => {
    const k = dayKey(o.due_date);
    if (k !== lastDay) { html += '<div class="day-label">' + esc(k) + '</div>'; lastDay = k; }
    const who = memberName(o.subject_member_id);
    html += '<a class="up" href="#/notices/' + esc(o.artifact_id) + '"><span class="tm">' + esc(o.due_time || 'all day') + '</span>'
      + '<span class="t' + (o.soft ? ' soft' : '') + '">' + (who ? esc(who) + ': ' : '') + esc(o.title) + (o.soft ? ' <span class="muted">(undecided)</span>' : '') + '</span></a>';
  });
  return html + '</section>';
}

function billsCard(billers) {
  let html = '<section class="card rail-card"><h2>Bills</h2>';
  if (!billers.length) {
    return html + '<p class="muted">Add a biller on the Household page and the brief says when a bill is late.</p></section>';
  }
  const today = new Date(); today.setHours(0, 0, 0, 0);
  billers.forEach((b) => {
    let expected = null, late = 0;
    if (b.last_seen_at) {
      expected = new Date(b.last_seen_at); expected.setDate(expected.getDate() + b.every_days);
      late = Math.round((today - expected) / 86400000);
    }
    html += '<div class="bill"><span class="grow"><div class="t">' + esc(b.provider) + '</div>'
      + '<div class="s">' + esc(b.label) + ' · every ' + b.every_days + ' days</div></span>'
      + '<span class="amt' + (late > b.grace_days ? ' late' : '') + '">'
      + (expected ? (late > b.grace_days ? late + 'd late' : date(expected.toISOString().slice(0, 10))) : 'not seen yet') + '</span></div>';
  });
  return html + '</section>';
}

/* Who is handling what: open notices per member, and the ones nobody has
   taken. Whom a notice is about is the kid tag on the row; this is the
   other question. */
function peopleCard(rows) {
  const members = (store.household && store.household.members || []).filter((m) => m.role !== 'child');
  const counts = {};
  let unassigned = 0;
  rows.filter((r) => r.state === 'todo').forEach((r) => {
    if (r.assigned_to) counts[r.assigned_to] = (counts[r.assigned_to] || 0) + 1; else unassigned += 1;
  });
  let html = '<section class="card rail-card"><div class="row wrap" style="gap:8px"><h2>Handling</h2><span class="muted">open notices</span></div>';
  members.forEach((m) => {
    html += '<div class="person"><span class="avatar" style="width:26px;height:26px;font-size:11px">' + esc(initial(m.display_name)) + '</span>'
      + '<span class="n">' + esc(m.display_name) + '</span><span class="c">' + (counts[m.id] || 0) + '</span></div>';
  });
  html += '<div class="person"><span class="avatar" style="width:26px;height:26px;font-size:11px;background:var(--sunk);color:var(--ink-3)">?</span>'
    + '<span class="n" style="color:var(--ink-3)">Nobody yet</span><span class="c">' + unassigned + '</span></div>';
  return html + '</section>';
}

function guardianCard() {
  if (!store.me || store.me.role !== 'guardian') return '';
  if (!store.quarantineCount) return '';
  return '<a class="card rail-card lift" href="#/quarantine" style="text-decoration:none;color:inherit">'
    + '<h2>Held for you</h2><p style="font-size:13px">' + store.quarantineCount + ' message' + (store.quarantineCount === 1 ? '' : 's')
    + ' arrived from someone the household does not know. Nothing in them is read until you look.</p></a>';
}

function wireHome(main) {
  main.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => go('/notices')));
  const gmail = main.querySelector('[data-connect-gmail]');
  if (gmail) gmail.addEventListener('click', async () => {
    gmail.disabled = true;
    try {
      const auth = await api('/google/mailboxes/authorize', { method: 'POST' });
      location.href = auth.url;
    } catch (err) {
      gmail.disabled = false;
      flash(err.status === 503 || err.status === 501 ? 'Gmail is not switched on for this deployment yet.' : err.message, true);
    }
  });
  const tg = main.querySelector('[data-tglink]');
  if (tg) tg.addEventListener('click', async () => {
    try { telegramLink(main, await api('/telegram/link', { method: 'POST' })); } catch (err) { fail(err); }
  });
  wireSpots(main);
}

/* ── notices ──────────────────────────────────────────────────── */

const CHANNEL = {
  upload: { glyph: '↑', icon: 'upload', tone: '', label: 'Added here' },
  email: { glyph: '✉', icon: 'mail', tone: 'blue', label: 'Email' },
  email_attachment: { glyph: '▣', icon: 'attach', tone: 'amber', label: 'Attachment' },
  gmail: { glyph: '✉', icon: 'mail', tone: 'blue', label: 'Email' },
  gmail_attachment: { glyph: '▣', icon: 'attach', tone: 'amber', label: 'Attachment' },
  telegram: { glyph: '➤', icon: 'send', tone: 'blue', label: 'Telegram' },
  telegram_media: { glyph: '▣', icon: 'attach', tone: 'amber', label: 'Telegram' },
  whatsapp: { glyph: '➤', icon: 'send', tone: 'blue', label: 'WhatsApp' },
  whatsapp_media: { glyph: '▣', icon: 'attach', tone: 'amber', label: 'WhatsApp' },
  share: { glyph: '⬆', icon: 'phone', tone: 'blue', label: 'From your phone' },
  harvest: { glyph: '⬆', icon: 'doc', tone: '', label: 'Collected' },
  errand: { glyph: '✓', icon: 'sparkle', tone: '', label: 'A step FamilyOS took' },
};
function channelLabel(ch) { return (CHANNEL[ch] || {}).label || String(ch || '').replace('_', ' '); }

const CATEGORY = {
  school: 'School', medical: 'Medical', government: 'Government', bills: 'Bill', banking: 'Bank', trading: 'Trading',
  insurance: 'Insurance', subscriptions: 'Subscription', shopping: 'Shopping', food: 'Food', home: 'Home',
  travel: 'Travel', promo: 'Promo', newsletter: 'Newsletter', developer: 'Dev',
};
// Folded away unless asked for: bank alerts are lines in Money, not notices.
const QUIET = { promo: 1, newsletter: 1, developer: 1, banking: 1 };

async function noticesView(main) {
  const [rows, proposed, mailboxes] = await Promise.all([
    api('/inbox?days=120&limit=200'),
    api('/obligations?status=proposed&limit=200'),
    // Only so Ways in can say whether a mailbox is connected.
    api('/google/mailboxes').catch(() => []),
  ]);
  store.mailboxes = mailboxes;
  const counts = { todo: 0, done: 0, info: 0 };
  rows.forEach((r) => { counts[r.state] = (counts[r.state] || 0) + 1; });
  const want = store.inboxFilter || 'todo';
  const cats = {};
  rows.forEach((r) => { cats[r.category] = (cats[r.category] || 0) + 1; });
  const catKeys = Object.keys(CATEGORY).filter((k) => cats[k]);
  const quiet = rows.filter((r) => QUIET[r.category]).length;
  if (store.inboxCategory && !cats[store.inboxCategory]) store.inboxCategory = '';

  main.innerHTML = '<div class="head"><div><h1>Inbox</h1>'
    + '<p>Everything that arrived, kept exactly as it came. To do until every date on it is decided.</p></div>'
    + '<div class="row" style="gap:8px"><button class="btn ghost" data-reportgap>Something missing?</button>'
    + '<button class="btn" data-add>Add a notice</button></div></div>'
    + '<div class="home">'
    + '<div class="stack" style="gap:12px">'
    + '<div class="pills" data-pills>'
    + ['todo', 'done', 'info', 'all'].map((k) => '<button class="pill" data-filter="' + k + '" aria-pressed="' + (want === k) + '">'
      + ({ todo: 'To do', done: 'Done', info: 'Nothing asked', all: 'All' })[k]
      + ' <span class="n">' + (k === 'all' ? rows.length : counts[k]) + '</span></button>').join('')
    + '</div>'
    + (catKeys.length > 1 ? '<div class="pills cats" data-cats>'
      + '<button class="pill sm" data-cat="" aria-pressed="' + !store.inboxCategory + '">Everything</button>'
      + catKeys.map((k) => '<button class="pill sm' + (QUIET[k] ? ' quiet' : '') + '" data-cat="' + k + '" aria-pressed="' + (store.inboxCategory === k) + '">'
        + CATEGORY[k] + ' <span class="n">' + cats[k] + '</span></button>').join('')
      + '</div>' : '')
    + '<div class="card list" data-list></div>'
    + '<p class="muted quiet-note" data-quiet></p>'
    + inboundCard()
    + '</div>'
    + '<aside class="stack" style="gap:14px">'
    + spottedRail(proposed)
    + peopleCard(rows)
    + '</aside></div>'
    + uploadDialog()
    + handleDialog()
    + gapDialog()
    + assignDialog();

  const list = main.querySelector('[data-list]');
  const paint = () => {
    const f = store.inboxFilter || 'todo';
    const c = store.inboxCategory || '';
    // Promotions and newsletters stay out of the way until asked for by name.
    const shown = rows.filter((r) => (f === 'all' || r.state === f) && (c ? r.category === c : !QUIET[r.category]));
    list.innerHTML = shown.length ? shown.map(inboxRow).join('')
      : '<div class="empty">' + ({ todo: 'Nothing to do. Every date that arrived has been decided.',
        done: 'Nothing decided yet.', info: 'Nothing here asked for anything.', all: 'Nothing yet. Forward a notice, or paste one.' })[f] + '</div>';
    const foot = main.querySelector('[data-quiet]');
    if (foot) foot.textContent = !c && quiet ? quiet + ' promotion' + (quiet > 1 ? 's' : '') + ' and newsletter' + (quiet > 1 ? 's' : '') + ' kept out of the way. Pick Promo or Newsletter above to see them.' : '';
    wireAssignButtons(main);
  };
  paint();
  main.querySelectorAll('[data-filter]').forEach((b) => b.addEventListener('click', () => {
    store.inboxFilter = b.dataset.filter;
    main.querySelectorAll('[data-filter]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    paint();
  }));
  main.querySelectorAll('[data-cat]').forEach((b) => b.addEventListener('click', () => {
    store.inboxCategory = b.dataset.cat;
    main.querySelectorAll('[data-cat]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    paint();
  }));

  const dlg = main.querySelector('dialog[data-upload]') || main.querySelector('dialog');
  wireUpload(dlg);
  wireWays(main, dlg);
  wireGaps(main);
  wireHandle(main);
  wireSpots(main);
  wireAssignDialog(main);
}

function inboxRow(r) {
  const ch = CHANNEL[r.channel] || CHANNEL.upload;
  const kids = (r.subject_member_ids || []).map(memberName).filter(Boolean);
  const who = memberName(r.assigned_to);
  const nextDay = r.next_date ? dayKey(r.next_date) : null;
  return '<div class="inbox-row" data-row="' + esc(r.id) + '">'
    + '<span class="glyph ' + ch.tone + '" aria-hidden="true">' + icon(ch.icon || 'doc', 15) + '</span>'
    + '<a class="grow body" href="#/notices/' + esc(r.id) + '">'
    + '<span class="meta"><b>' + esc(r.from_label) + '</b><span>' + esc(ago(r.received_at)) + '</span>'
    + (CATEGORY[r.category] ? '<span class="tag line cat ' + esc(r.category) + '">' + CATEGORY[r.category] + '</span>' : '')
    + kids.map((n) => '<span class="tag kid">' + esc(n) + '</span>').join('')
    + (r.attachments ? '<span class="muted">' + r.attachments + ' attachment' + (r.attachments > 1 ? 's' : '') + '</span>' : '')
    + '</span>'
    + '<span class="title">' + esc(r.headline || 'Notice') + '</span>'
    + (r.preview.length ? '<span class="sub">' + esc(r.preview.slice(0, 2).join(' · ')) + (r.dates > 2 ? ' · +' + (r.dates - 2) : '') + '</span>' : '')
    + (r.assigned_note ? '<span class="note">“' + esc(r.assigned_note) + '”</span>' : '')
    + '</a>'
    + '<span class="rside">'
    + (nextDay ? '<span class="next">' + esc(nextDay) + '</span>' : '')
    + (r.handled_at ? '<span class="tag green" title="' + esc(r.handled_note || '') + '">handled' + (memberName(r.handled_by) ? ' by ' + esc(memberName(r.handled_by)) : '') + '</span>'
      : r.state === 'todo' ? '<span class="tag amber">' + r.open + ' to decide</span>' : r.state === 'done' ? '<span class="tag green">done</span>'
      : (r.reason && /password/i.test(r.reason) ? '<span class="tag rust" title="' + esc(r.reason) + '">\uD83D\uDD12 locked PDF</span>'
        : r.reason && /promotion/i.test(r.reason) ? '<span class="tag" title="' + esc(r.reason) + '">no task proposed</span>' : ''))
    + (who
      ? '<button class="assignee" data-assign="' + esc(r.id) + '" data-current="' + esc(r.assigned_to) + '" title="Handled by ' + esc(who) + '"><span class="avatar">' + esc(initial(who)) + '</span>' + esc(who) + '</button>'
      : '<button class="btn ghost sm assign-btn" data-assign="' + esc(r.id) + '">Assign</button>')
    + '</span>'
    + '</div>';
}

/* the dates rail, shared by Home and the Inbox */
function spottedRail(proposed) {
  const rows = proposed.slice().sort((a, b) => (a.due_date || '9999') < (b.due_date || '9999') ? -1 : 1);
  return '<section class="card rail-card"><div class="row wrap" style="gap:8px"><h2>Dates spotted</h2>'
    + '<span class="muted">' + (rows.length ? rows.length + ' to decide' : 'none') + '</span></div>'
    + (rows.length ? '<div class="stack" style="gap:6px" data-spots>' + rows.slice(0, 8).map((o) => spotRow(o, true)).join('') + '</div>'
      : '<p class="muted">Every date a notice asks about appears here for a yes or a no.</p>')
    + '</section>';
}

function wireSpots(main) {
  main.querySelectorAll('[data-decide]').forEach((b) => b.addEventListener('click', async () => {
    const row = b.closest('[data-spot]');
    const id = row.dataset.spot, status = b.dataset.decide;
    row.querySelectorAll('button').forEach((x) => { x.disabled = true; });
    try {
      await api('/obligations/' + id + '/decision', { method: 'POST', json: { status } });
      row.classList.add('gone');
      flash(status === 'accepted' ? 'On the calendar. You will be reminded.' : 'Dismissed.');
      setTimeout(() => render().catch(() => {}), 260);
    } catch (err) { fail(err); row.querySelectorAll('button').forEach((x) => { x.disabled = false; }); }
  }));
}

/* ── assigning ────────────────────────────────────────────────── */
/* Who is handling a notice, with a note. A dialog rather than a dropdown
   because the note is the point: "can you let them know who is on pickup?"
   is what makes a hand-over land. */

function assignDialog() {
  const adults = membersByRole(['guardian', 'adult']);
  return '<dialog class="card" data-assign-dialog style="max-width:420px;padding:20px;border:1px solid var(--line)">'
    + '<form class="stack" data-form="assign">'
    + '<h2>Hand this to someone</h2>'
    + '<p class="muted" data-assign-title style="line-height:1.5"></p>'
    + '<label>Who<select name="member_id">'
    + adults.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.display_name) + (store.me && m.id === store.me.id ? ' (me)' : '') + '</option>').join('')
    + '<option value="">Nobody — take it back</option>'
    + '</select></label>'
    + '<label>A note<textarea name="note" rows="3" maxlength="500" placeholder="Can you let them know who will be on pickup?"></textarea></label>'
    + '<p class="muted" data-assign-hint style="line-height:1.45">They are told right away, on Telegram if they have linked it, otherwise by email. '
    + 'This changes nothing about who can see the notice.</p>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn ghost" type="button" data-close>Cancel</button>'
    + '<button class="btn" type="submit">Hand over</button></div></form></dialog>';
}

function wireAssignDialog(main) {
  const dlg = main.querySelector('[data-assign-dialog]');
  if (!dlg) return;
  dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());
  dlg.querySelector('form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const id = dlg.dataset.artifact;
    const body = { member_id: f.get('member_id') || null, note: (f.get('note') || '').trim() || null };
    const button = ev.target.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      await api('/artifacts/' + id + '/assign', { method: 'POST', json: body });
      dlg.close();
      flash(body.member_id ? 'Handed over. They have been told.' : 'Taken back.');
      await render();
    } catch (err) {
      if (err.status === 409 && body.member_id) {
        // The one refusal: they cannot see it. Offer the fix, do not do it quietly.
        const ok = window.confirm(err.message + '\n\nShare it with the household and hand it over?');
        if (ok) {
          try {
            await api('/artifacts/' + id, { method: 'PATCH', json: { visibility: 'shared' } });
            await api('/artifacts/' + id + '/assign', { method: 'POST', json: body });
            dlg.close();
            flash('Shared with the household and handed over.');
            await render();
            return;
          } catch (err2) { fail(err2); }
        }
      } else { fail(err); }
    } finally { button.disabled = false; }
  });
}

function openAssign(main, artifactId, current, title) {
  const dlg = main.querySelector('[data-assign-dialog]');
  if (!dlg) return;
  dlg.dataset.artifact = artifactId;
  dlg.querySelector('[data-assign-title]').textContent = title || '';
  const sel = dlg.querySelector('[name="member_id"]');
  sel.value = current || (store.me ? store.me.id : '');
  dlg.querySelector('[name="note"]').value = '';
  dlg.showModal();
  dlg.querySelector('[name="note"]').focus();
}

function wireAssignButtons(main) {
  main.querySelectorAll('[data-assign]').forEach((b) => b.addEventListener('click', (ev) => {
    ev.preventDefault();
    const row = b.closest('[data-row]');
    const title = row ? (row.querySelector('.title') || {}).textContent : '';
    openAssign(main, b.dataset.assign, b.dataset.current || '', title);
  }));
}

function wireWays(main, dlg) {
  main.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(b.dataset.copy);
      flash('Copied.');
    } catch (e) { flash('Could not reach the clipboard.', true); }
  }));
  // Every one of them: there is a button in the head and another inside the
  // Ways in card, and querySelector only ever found the first. On a page with
  // no upload dialog it goes to the page that has one.
  main.querySelectorAll('[data-add]').forEach((add) => add.addEventListener(
    'click', () => (dlg ? dlg.showModal() : go('/notices'))));
  const how = main.querySelector('[data-shortcut]');
  if (how) how.addEventListener('click', () => shortcutHelp(main));
  const tg = main.querySelector('[data-tglink]');
  if (tg) tg.addEventListener('click', async () => {
    tg.disabled = true;
    try {
      telegramLink(main, await api('/telegram/link', { method: 'POST' }));
    } catch (e) {
      flash(e.message || 'Could not make a link.', true);
    } finally { tg.disabled = false; }
  });
}

function telegramLink(main, link) {
  // Shown rather than mailed: the member is signed in here, and the phone with
  // Telegram on it is usually the one they are reading this on. One tap on the
  // same device, or copy it across.
  const el = document.createElement('dialog');
  el.className = 'card pad';
  el.style.cssText = 'max-width:440px;padding:20px;border:1px solid var(--line)';
  el.innerHTML = '<div class="stack">'
    + '<h2>Link your Telegram</h2>'
    + '<p class="muted" style="line-height:1.55">Open this on the phone that has Telegram and press '
    + '<b>Start</b>. The bot will say who it linked to.</p>'
    + '<div class="row wrap" style="gap:8px">'
    + '<a class="btn" href="' + esc(link.url) + '" target="_blank" rel="noopener">Open in Telegram</a>'
    + '<button class="btn ghost sm" data-copy="' + esc(link.url) + '">Copy the link</button></div>'
    + '<p class="muted" style="line-height:1.5">It works once and stops working in '
    + esc(String(link.expires_in_minutes)) + ' minutes. Asking again replaces it, so a link somebody '
    + 'screenshotted is already dead.</p>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn" data-close-tg>Close</button></div>'
    + '</div>';
  main.appendChild(el);
  el.querySelector('[data-close-tg]').addEventListener('click', () => el.close());
  el.querySelector('[data-copy]').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(link.url);
      flash('Copied.');
    } catch (e) { flash('Could not reach the clipboard.', true); }
  });
  el.addEventListener('close', () => el.remove());
  el.showModal();
}

function shortcutHelp(main) {
  const existing = main.querySelector('dialog[data-help]');
  if (existing) { existing.showModal(); return; }
  const host = location.origin;
  const el = document.createElement('dialog');
  el.setAttribute('data-help', '');
  el.className = 'card';
  el.style.cssText = 'max-width:480px;padding:20px;border:1px solid var(--line)';
  el.innerHTML = '<div class="stack">'
    + '<h2>Share straight from your phone</h2>'
    + '<p class="muted" style="line-height:1.55"><b>iPhone.</b> Shortcuts \u2192 new shortcut \u2192 \u24D8 \u2192 '
    + 'turn on <b>Show in Share Sheet</b>. Add one action, <b>Get Contents of URL</b>:</p>'
    + '<pre class="recipe">URL      ' + esc(host) + '/v1/artifacts\n'
    + 'Method   POST\n'
    + 'Headers  Authorization : Bearer &lt;your token&gt;\n'
    + 'Body     Form\n'
    + '           file = Shortcut Input</pre>'
    + '<p class="muted" style="line-height:1.55">It then appears in WhatsApp\u2019s share sheet. The token sits in '
    + 'the shortcut in plain text, so if the phone is lost use <b>Sign out everywhere</b> on the Household page.</p>'
    + '<p class="muted" style="line-height:1.55"><b>Android.</b> The same request from Tasker or MacroDroid, which '
    + 'can also fire on a notification \u2014 the only way to catch something nobody opened. iPhones cannot do that.</p>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn" data-close-help>Close</button></div>'
    + '</div>';
  main.appendChild(el);
  el.querySelector('[data-close-help]').addEventListener('click', () => el.close());
  el.showModal();
}

function inboundCard() {
  const h = store.household || {};
  const ways = [
    {
      key: 'paste',
      live: true,
      glyph: '\u270E', icon: 'pen',
      tone: '',
      title: 'Paste or upload',
      what: 'Copy a WhatsApp message and paste it, or add a photo, screenshot or PDF.',
      value: '',
      hint: 'Copied text reads better than a screenshot of it.',
    },
    {
      key: 'whatsapp',
      live: !!h.whatsapp_number,
      glyph: '\u2709', icon: 'phone',
      tone: 'green',
      title: 'Forward on WhatsApp',
      what: 'Long-press the message, Forward, and pick this number. Several at once is fine.',
      value: h.whatsapp_number || '',
      hint: h.whatsapp_number
        ? 'Only numbers saved against a member are accepted.'
        : 'Not set up yet \u2014 needs a WhatsApp business number. Paste works meanwhile.',
    },
    {
      key: 'telegram',
      live: !!h.telegram_bot,
      glyph: '\u27A4', icon: 'send',
      tone: 'blue',
      title: 'Forward on Telegram',
      what: 'Link your account once, then forward anything to the bot. Files up to 20MB.',
      value: h.telegram_bot ? '@' + h.telegram_bot : '',
      hint: !h.telegram_bot
        ? 'Not set up yet \u2014 needs a bot token. WhatsApp and paste work meanwhile.'
        : ((store.me && store.me.telegram_linked)
          ? 'Linked. In a group, mention the bot or reply to it \u2014 it does not read the rest of the group.'
          : 'Reminders here need no approved template, so they arrive whatever time they are due.'),
    },
    {
      key: 'email',
      live: !!h.inbound_address,
      glyph: '\u2192', icon: 'mail',
      tone: 'blue',
      title: 'Forward by email',
      what: 'Forward a circular from any mailbox to the family address above.',
      value: '',
      hint: 'Four taps from inside any app \u2014 including the group chats no API can read.',
    },
    {
      key: 'gmail',
      live: ((store.mailboxes || []).some((m) => !m.needs_reconnect)),
      glyph: '\u25D4', icon: 'mail',
      tone: 'blue',
      title: 'Connect your Gmail',
      what: 'Read-only, and only mail that looks like a school notice. Nothing is sent or changed.',
      value: '',
      hint: ((store.mailboxes || []).some((m) => m.needs_reconnect))
        ? 'A connected mailbox has stopped being readable \u2014 reconnect it on the Household page.'
        : 'Removes the step where somebody has to notice a notice and forward it.',
    },
    {
      key: 'phone',
      live: true,
      glyph: '\u2191',
      tone: 'amber',
      title: 'From your phone',
      what: 'Share straight from WhatsApp or the school app, without opening this.',
      value: '',
      hint: 'iPhone: a Shortcut in the share sheet. Android: Tasker can also catch notifications nobody opened.',
    },
  ];

  // The household address comes out of the list and sits above it. It is not
  // one way in among four: it is the address a family writes on a school form,
  // and the only one that works without an app, a login or our permission.
  const addr = h.inbound_address || '';
  return '<section class="card pad stack" style="gap:12px">'
    + (addr
      ? '<div class="stack" style="gap:8px;padding:14px 15px;background:var(--sunk);'
        + 'border:1px solid var(--line-soft);border-radius:9px">'
        + '<div class="row wrap" style="gap:8px"><span style="font-size:13px;font-weight:600">'
        + 'Your family address</span><span class="muted">give this to the school</span></div>'
        + '<div class="row wrap" style="gap:8px"><code class="addr" style="font-size:13px">' + esc(addr) + '</code>'
        + '<button class="btn sm" data-copy="' + esc(addr) + '">Copy</button>'
        + (store.me && store.me.role === 'guardian'
          ? '<button class="btn ghost sm" data-renameaddr>'
            + (h.handle ? 'Change' : 'Choose a name') + '</button>' : '') + '</div>'
        + (h.handle ? '' : '<p class="muted" style="line-height:1.5">That is the generated address. '
          + 'Pick a name a person can say down a phone before you give it to a school \u2014 the generated '
          + 'one keeps working either way.</p>')
        + '<p class="muted" style="line-height:1.5">Anything sent here reaches the household. Mail from a member '
        + 'whose provider vouched for it is read; <b>anything from a stranger waits in quarantine</b> until a '
        + 'guardian looks, so the address is safe to hand out.</p></div>'
      : '')
    + '<div class="row wrap" style="gap:8px;padding:10px 2px 2px"><span style="font-size:13px;font-weight:600">Where we live</span>'
    + '<span class="muted" data-locale-text>' + esc(h.country || 'IN') + ' · ' + esc(h.timezone || 'Asia/Kolkata') + ' · ' + esc(h.currency || 'INR') + '</span>'
    + (store.me && store.me.role === 'guardian' ? '<button class="btn ghost sm" data-locale>Change</button>' : '') + '</div>'
    + '<form class="row wrap" data-locale-form hidden style="gap:8px;align-items:flex-end">'
    + '<label style="font-size:12px">Country<br><input name="country" value="' + esc(h.country || 'IN') + '" maxlength="2" style="width:64px;text-transform:uppercase"></label>'
    + '<label style="font-size:12px">Time zone<br><input name="timezone" value="' + esc(h.timezone || 'Asia/Kolkata') + '" list="tzlist" style="width:170px"></label>'
    + '<datalist id="tzlist"><option value="Asia/Kolkata"><option value="Asia/Dubai"><option value="Asia/Singapore"><option value="Europe/London"><option value="America/New_York"></datalist>'
    + '<label style="font-size:12px">Currency<br><input name="currency" value="' + esc(h.currency || 'INR') + '" maxlength="3" style="width:64px;text-transform:uppercase"></label>'
    + '<button class="btn sm" type="submit">Save</button><span class="muted" data-locale-note>The country sets the school year and the payment rails; the zone times the digest and the calendar; totals are said in the currency.</span></form>'
    + '<div data-places></div>'
    + '<div data-schools></div>'
    + '<div class="row wrap" style="gap:8px"><h2>Other ways in</h2>'
    + '<span class="muted">school notices arrive however they arrive</span></div>'
    + '<div class="ways">'
    + ways.map((w) =>
      '<div class="way' + (w.live ? '' : ' off') + '">'
      + '<div class="row" style="gap:9px;align-items:flex-start">'
      + '<span class="glyph ' + (w.live ? w.tone : '') + '" style="width:28px;height:28px" aria-hidden="true">'
      + icon(w.icon || 'doc', 14) + '</span>'
      + '<span class="grow"><span class="row wrap" style="gap:6px">'
      + '<span style="font-size:13px;font-weight:600">' + esc(w.title) + '</span>'
      + (w.live ? '' : '<span class="tag">not set up</span>') + '</span>'
      + '<span class="sub">' + esc(w.what) + '</span></span></div>'
      + (w.value
        ? '<div class="row" style="gap:7px"><code class="addr">' + esc(w.value) + '</code>'
          + '<button class="btn ghost sm" data-copy="' + esc(w.value) + '">Copy</button></div>'
        : '')
      + (w.key === 'paste'
        ? '<button class="btn sm" data-add style="align-self:flex-start">Add a notice</button>' : '')
      + (w.key === 'phone'
        ? '<button class="btn ghost sm" data-shortcut style="align-self:flex-start">How</button>' : '')
      + (w.key === 'gmail'
        ? '<a class="btn ghost sm" href="#/household" style="align-self:flex-start">Set up</a>' : '')
      + (w.key === 'telegram' && w.live
        ? '<button class="btn' + (store.me && store.me.telegram_linked ? ' ghost' : '') + ' sm" '
          + 'data-tglink style="align-self:flex-start">'
          + (store.me && store.me.telegram_linked ? 'Link another device' : 'Link my Telegram')
          + '</button>' : '')
      + '<p class="muted" style="line-height:1.45">' + esc(w.hint) + '</p>'
      + '</div>').join('')
    + '</div></section>';
}

function noticeRow(a) {
  const ch = CHANNEL[a.channel] || CHANNEL.upload;
  const subjects = (a.subject_member_ids || []).map(memberName).filter(Boolean);
  return '<a class="item" href="#/notices/' + esc(a.id) + '">'
    + '<span class="glyph ' + ch.tone + '" aria-hidden="true">' + icon(ch.icon || 'doc', 15) + '</span>'
    + '<span class="grow"><span class="row wrap" style="gap:8px">'
    + '<span class="title">' + esc(a.filename || a.source.subject || a.channel) + '</span>'
    + '<span class="tag ' + (a.visibility === 'shared' ? 'line' : 'solid') + '">' + esc(a.visibility) + '</span>'
    + subjects.map((n) => '<span class="tag kid">' + esc(n) + '</span>').join('')
    + '</span>'
    + '<span class="sub">' + esc(noticeSub(a)) + '</span></span>'
    + '<span class="muted" style="flex-shrink:0">' + esc(bytes(a.size_bytes)) + '</span>'
    + '<span class="muted" style="width:82px;text-align:right;flex-shrink:0">' + esc(ago(a.received_at)) + '</span>'
    + '</a>';
}

function noticeSub(a) {
  const bits = [];
  if (a.source && a.source.from) bits.push('from ' + a.source.from);
  if (a.submitted_by) bits.push('by ' + (memberName(a.submitted_by) || 'a member'));
  bits.push(a.media_type);
  if (a.children && a.children.length) bits.push(a.children.length + ' attachment' + (a.children.length > 1 ? 's' : ''));
  return bits.join('  ·  ');
}

function uploadDialog() {
  const kids = membersByRole(['child', 'adult', 'guardian']);
  return '<dialog class="card" data-upload style="max-width:440px;padding:20px;border:1px solid var(--line)">'
    + '<form class="stack" data-form="upload">'
    + '<h2>Add a notice</h2>'
    + '<div class="tabs"><button type="button" data-how="paste" aria-pressed="true">Paste a message</button>'
    + '<button type="button" data-how="file" aria-pressed="false">Upload a file</button></div>'
    + '<label data-pane="paste">Paste it here'
    + '<textarea name="text" rows="7" placeholder="Long-press the WhatsApp message, Copy, then paste here."></textarea>'
    + '</label>'
    + '<p class="muted" data-pane="paste">A screenshot works too, but copied text reads better than OCR of it.</p>'
    + '<label data-pane="file" hidden>File<input type="file" name="file"></label>'
    + '<label>Who can see it<select name="visibility">'
    + '<option value="private">Private to me</option><option value="shared">Shared with the household</option>'
    + '</select></label>'
    + '<label>Who it is about<select name="subject" >'
    + '<option value="">Nobody in particular</option>'
    + kids.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.display_name) + ' (' + esc(m.role) + ')</option>').join('')
    + '</select></label>'
    + '<p class="muted">Naming a child needs an active consent record for them.</p>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn ghost" type="button" data-close>Cancel</button>'
    + '<button class="btn" type="submit">Upload</button></div>'
    + '</form></dialog>';
}

function wireUpload(dlg) {
  dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());

  let how = 'paste';
  dlg.querySelectorAll('[data-how]').forEach((tab) => {
    tab.addEventListener('click', () => {
      how = tab.dataset.how;
      dlg.querySelectorAll('[data-how]').forEach((t) => t.setAttribute('aria-pressed', String(t === tab)));
      dlg.querySelectorAll('[data-pane]').forEach((p) => { p.hidden = p.dataset.pane !== how; });
    });
  });

  dlg.querySelector('form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const f = new FormData(form);

    let file;
    if (how === 'paste') {
      const text = (f.get('text') || '').trim();
      if (!text) { flash('Paste the message first.', true); return; }
      // A pasted message is a notice like any other: same bytes-in, same
      // hash, same dedup. Two parents pasting the same message store once.
      const stamp = new Date().toISOString().slice(0, 16).replace('T', ' ');
      file = new File([text], 'pasted ' + stamp + '.txt', { type: 'text/plain' });
    } else {
      file = f.get('file');
      if (!file || !file.size) { flash('Pick a file first.', true); return; }
    }

    const body = new FormData();
    body.append('file', file);
    body.append('visibility', f.get('visibility'));
    if (f.get('subject')) body.append('subject_member_ids', f.get('subject'));
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      const out = await api('/artifacts', { method: 'POST', body });
      dlg.close();
      flash(out.duplicate ? 'You had already sent those exact bytes — showing the first one.' : 'Stored. Reading it now.');
      go('/notices/' + out.artifact.id);
      await render();
    } catch (err) {
      fail(err);
    } finally {
      button.disabled = false;
    }
  });
}

/* ── one notice: the review card ──────────────────────────────── */

async function noticeView(main, args) {
  const id = args[0];
  const artifact = await api('/artifacts/' + id);
  let extraction = null;
  try {
    extraction = await api('/artifacts/' + id + '/extraction');
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 404) throw err;
  }

  // Is this a notice at all, or a record of something that happened? A
  // receipt, an alert, a promotion: nothing to reply to, nobody it is
  // about. Only a notice that asks something gets the reply and the
  // "which child, which school" question.
  {
    const cl = (extraction && extraction.extraction && extraction.extraction.claims) || [];
    const asks = cl.some((c) => ['event', 'deadline', 'form', 'amendment', 'instruction', 'payment'].includes(c.kind) && c.kind !== 'payment' || (c.kind === 'payment' && c.date && c.date >= todayISO()));
    const actionable = !!(extraction && extraction.extraction && extraction.extraction.actionable);
    artifact.noticeLike = !TRANSACTIONAL[artifact.category] && (actionable || asks || !extraction);
  }
  main.innerHTML = noticeHeader(artifact)
    + '<div class="split">'
    + '<div class="viewer" data-viewer></div>'
    + '<div class="stack" data-side></div>'
    + '</div>';

  main.insertAdjacentHTML('beforeend', assignDialog());
  renderSide(main.querySelector('[data-side]'), artifact, extraction, id);
  wireNoticeHeader(main, artifact, id);
  wireAssignDialog(main);
  wireAssignButtons(main);
  renderOriginal(main.querySelector('[data-viewer]'), artifact).catch((err) => {
    main.querySelector('[data-viewer]').innerHTML =
      '<header><b>Original</b></header><div class="stage"><p class="note">Could not load the original: '
      + esc(err.message) + '</p></div>';
  });
}

function noticeHeader(a) {
  const auth = a.source && a.source.sender_authenticated;
  const claimsFrom = a.source && a.source.from;
  return '<div class="head"><div>'
    + '<p class="muted" style="margin-bottom:6px"><a href="#/notices" style="color:var(--ink-3);text-decoration:none">Inbox</a> \u00B7 '
    + esc(channelLabel(a.channel)) + '</p>'
    + '<h1>' + esc(a.filename || (a.source && a.source.subject) || 'Notice') + '</h1>'
    + '<p class="row wrap" style="gap:8px;margin-top:9px">'
    + '<span class="tag ' + ((CHANNEL[a.channel] || {}).tone || '') + '">' + esc(channelLabel(a.channel)) + '</span>'
    + '<span class="tag line">' + (a.visibility === 'shared' ? 'shared with the family' : 'only you') + '</span>'
    + (a.status === 'quarantined' ? '<span class="tag rust">quarantined</span>' : '')
    + (claimsFrom ? '<span class="muted">from <b style="color:var(--ink);font-weight:500">' + esc(claimsFrom) + '</b></span>' : '')
    + (a.submitted_by ? '<span class="muted">' + esc(memberName(a.submitted_by)) + '</span>' : '')
    + '<span class="muted">' + esc(date(a.received_at)) + '</span>'
    + (a.source && a.source.from && a.channel !== 'whatsapp' && a.channel !== 'whatsapp_media'
        ? '<span class="tag ' + (auth ? 'green' : 'red') + '">' + (auth ? 'sender authenticated' : 'sender not authenticated') + '</span>'
        : '')
    + (a.source && a.source.forwarded
        ? '<span class="tag amber" title="Relayed by someone, not issued by the school">second-hand</span>'
        : '')
    + '</p>'
    + (a.handled_at
      ? '<p class="handoff done"><span class="avatar">\u2713</span>'
        + '<span><b>' + esc(memberName(a.handled_by) || 'Someone') + '</b> handled this on ' + esc(date(a.handled_at))
        + (a.handled_note ? ' \u2014 \u201C' + esc(a.handled_note) + '\u201D' : '') + '</span></p>'
      : a.assigned_to
      ? '<p class="handoff"><span class="avatar">' + esc(initial(memberName(a.assigned_to))) + '</span>'
        + '<span><b>' + esc(memberName(a.assigned_to)) + '</b> is handling this'
        + (a.assigned_by && a.assigned_by !== a.assigned_to ? ', from ' + esc(memberName(a.assigned_by)) : '')
        + (a.assigned_note ? ' \u2014 \u201C' + esc(a.assigned_note) + '\u201D' : '') + '</span></p>'
      : '')
    + '</div>'
    + '<div class="row wrap" style="gap:8px">'
    + (a.handled_at
      ? '<button class="btn ghost" data-reopen="' + esc(a.id) + '">Not done after all</button>'
      : '<button class="btn" data-handled="' + esc(a.id) + '">Done</button>')
    + '<button class="btn ghost" data-assign="' + esc(a.id) + '" data-current="' + esc(a.assigned_to || '') + '">'
    + (a.assigned_to ? 'Reassign' : 'Hand to someone') + '</button>'
    + (a.submitted_by === (store.me || {}).id && !a.parent_id
        ? '<button class="btn ghost" data-vis>Make ' + (a.visibility === 'shared' ? 'private' : 'shared') + '</button>' : '')
    + '<button class="btn ghost" data-reread>Read again</button>'
    + '<button class="btn ghost" data-download>Download original</button>'
    + '</div>'
    + (['gmail', 'gmail_attachment', 'email', 'telegram'].includes(a.channel) && store.me && store.me.role !== 'child' && a.noticeLike
      ? '<div class="stack" data-reply style="gap:8px;margin-top:12px;padding:12px 14px;background:var(--sunk);border:1px solid var(--line-soft);border-radius:9px">'
        + '<div class="row wrap" style="gap:8px"><span style="font-size:13px;font-weight:600">Reply to the sender</span>'
        + '<span class="muted">drafted from the notice and what you decided; nothing goes until you send it</span></div>'
        + '<div class="row wrap" style="gap:6px"><button class="btn ghost sm" data-reply-stance="yes">Yes, we will</button>'
        + '<button class="btn ghost sm" data-reply-stance="no">No, we won\u2019t</button>'
        + '<input type="text" data-reply-note placeholder="a note to carry, optional" maxlength="300" style="flex:1;min-width:180px">'
        + '<button class="btn sm" data-reply-draft>Draft</button></div>'
        + '<div data-reply-box hidden class="stack" style="gap:6px"><div class="muted" data-reply-to></div>'
        + '<input type="text" data-reply-subject style="width:100%">'
        + '<textarea data-reply-text rows="5" style="width:100%"></textarea>'
        + '<div class="row wrap" style="gap:8px"><button class="btn" data-reply-send>Send</button><span class="muted" data-reply-note-out></span></div></div>'
        + '</div>' : '')
    + '</div>';
}

function wireReply(main, id) {
  const box = main.querySelector('[data-reply]'); if (!box) return;
  let stance = null;
  box.querySelectorAll('[data-reply-stance]').forEach((b) => b.addEventListener('click', () => {
    stance = b.dataset.replyStance; box.querySelectorAll('[data-reply-stance]').forEach((x) => x.classList.toggle('on', x === b));
  }));
  const out = box.querySelector('[data-reply-note-out]');
  box.querySelector('[data-reply-draft]').addEventListener('click', async () => {
    const btn = box.querySelector('[data-reply-draft]'); btn.disabled = true; btn.textContent = 'Drafting\u2026';
    try {
      const d = await api('/artifacts/' + id + '/reply/draft', { method: 'POST', json: { stance, note: box.querySelector('[data-reply-note]').value.trim() || null } });
      box.querySelector('[data-reply-to]').textContent = 'To ' + d.to + ' by ' + (d.channel === 'email' ? 'mail' : 'Telegram');
      box.querySelector('[data-reply-subject]').value = d.subject; box.querySelector('[data-reply-subject]').hidden = d.channel !== 'email';
      box.querySelector('[data-reply-text]').value = d.text; box.querySelector('[data-reply-box]').hidden = false; out.textContent = '';
    } catch (err) { out.textContent = (err && err.message) || 'Could not draft.'; box.querySelector('[data-reply-box]').hidden = false; }
    btn.disabled = false; btn.textContent = 'Draft';
  });
  box.querySelector('[data-reply-send]').addEventListener('click', async () => {
    const btn = box.querySelector('[data-reply-send]'); btn.disabled = true;
    try {
      const r = await api('/artifacts/' + id + '/reply', { method: 'POST', json: { text: box.querySelector('[data-reply-text]').value, subject: box.querySelector('[data-reply-subject]').value || null } });
      out.textContent = 'Sent to ' + r.to + '.'; btn.textContent = 'Sent';
    } catch (err) { out.textContent = (err && err.message) || 'Could not send.'; btn.disabled = false; }
  });
}

function wireNoticeHeader(main, artifact, id) {
  wireReply(main, id);
  const handled = main.querySelector('[data-handled]');
  if (handled) handled.addEventListener('click', () => openHandled(main, artifact));
  const reopen = main.querySelector('[data-reopen]');
  if (reopen) reopen.addEventListener('click', async () => {
    reopen.disabled = true;
    try { await api('/artifacts/' + artifact.id + '/handled', { method: 'DELETE' }); flash('Reopened.'); render(); }
    catch (err) { reopen.disabled = false; flash(err.message, true); }
  });
  const vis = main.querySelector('[data-vis]');
  if (vis) {
    vis.addEventListener('click', async () => {
      try {
        await api('/artifacts/' + id, { method: 'PATCH', json: { visibility: artifact.visibility === 'shared' ? 'private' : 'shared' } });
        flash('Visibility changed.');
        await render();
      } catch (err) { fail(err); }
    });
  }
  main.querySelector('[data-reread]').addEventListener('click', async (ev) => {
    ev.target.disabled = true;
    try {
      await api('/artifacts/' + id + '/extract', { method: 'POST' });
      flash('Queued. It will re-read in the background.');
      setTimeout(() => { render().catch(() => {}); }, 1600);
    } catch (err) { fail(err); ev.target.disabled = false; }
  });
  main.querySelector('[data-download]').addEventListener('click', async () => {
    try {
      const blob = await api('/artifacts/' + id + '/original', { blob: true });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = artifact.filename || (id + '.bin');
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (err) { fail(err); }
  });
}

/* the claims panel */

const KIND_TONE = {
  event: 'blue', deadline: 'amber', payment: 'green',
  form: 'amber', amendment: 'rust', instruction: '', info: '',
};

function renderSide(side, artifact, extraction, id) {
  const x = extraction && extraction.extraction;
  const claims = x ? x.claims : [];
  const grounded = claims.filter((c) => c.location && c.location.match);

  let metaCard = '';
  if (x) {
    metaCard = '<div class="card pad stack" style="gap:8px">'
      + '<div class="row wrap" style="gap:8px"><h2>Read from this notice</h2>'
      + '<span class="muted">' + claims.length + ' claim' + (claims.length === 1 ? '' : 's')
      + ' · ' + grounded.length + ' grounded</span></div>'
      + '<div class="row wrap" style="gap:6px">'
      + '<span class="tag line mono">' + esc(x.model || x.extractor) + '</span>'
      + '<span class="tag line mono">' + esc(x.prompt_version) + '</span>'
      + '<span class="muted">' + esc(x.page_count) + ' page' + (x.page_count === 1 ? '' : 's')
      + (x.ocr_pages ? ' · ' + x.ocr_pages + ' by OCR' : '') + '</span>'
      + (x.actionable ? '' : '<span class="tag">asks nothing of you</span>')
      + '</div>'
      + (x.non_actionable_reason ? '<p class="muted">' + esc(x.non_actionable_reason) + '</p>' : '')
      + (artifact.source && artifact.source.forwarded
        ? '<p class="muted" style="padding:9px 11px;background:var(--amber-tint);border-radius:6px;line-height:1.5">'
          + 'Forwarded, so this is somebody\u2019s retelling rather than the school\u2019s own notice. '
          + 'These claims are held a little less confidently until the original turns up.</p>'
        : '')
      + '</div>';
  } else {
    const status = extraction ? extraction.job_status : null;
    const err = extraction ? extraction.job_error : null;
    metaCard = '<div class="card pad stack" style="gap:8px"><h2>Read from this notice</h2>'
      + '<p class="muted">' + esc(
        err ? 'The reader failed: ' + err
          : status ? 'The reader is ' + status + '.'
            : artifact.status === 'quarantined'
              ? 'Quarantined mail is not read until a guardian accepts it.'
              : 'Nothing has been read from this yet.'
      ) + '</p></div>';
  }

  side.innerHTML = whoCard(artifact)
    + metaCard
    + (claims.length ? '<div class="stack" data-claims style="gap:9px"></div>' : '')
    + '<div class="card pad stack" data-obligations style="gap:10px"></div>';
  wireWho(side, artifact, id);

  if (claims.length) {
    const box = side.querySelector('[data-claims]');
    box.innerHTML = claims.map((c, i) => claimCard(c, i)).join('');
    box.querySelectorAll('.claim').forEach((btn) => {
      btn.addEventListener('click', () => selectClaim(Number(btn.dataset.i), claims));
    });
    selectClaim(0, claims);
  }

  renderObligations(side.querySelector('[data-obligations]'), id, [id, ...((artifact && artifact.children) || [])]);
}

/* Whom the notice is about. Worked out where it can be -- a class on the
   notice, a school in its text, the group it came from, or the one school
   the children share. Where it cannot, the question is asked as the parent
   would answer it: which school sent this? One tap, and if the notice came
   from a group, the group is remembered as that school's so it is never
   asked again. */
/* Senders whose mail is a record of something that happened, not a notice
   to answer: no reply is drafted and no child or school is asked for. */
const TRANSACTIONAL = { food: 1, shopping: 1, trading: 1, banking: 1, subscriptions: 1, bills: 1, promo: 1, newsletter: 1, developer: 1 };

function whoCard(a) {
  const kids = (store.household && store.household.members || []).filter((m) => m.role === 'child');
  if (!kids.length) return '';
  if (!a.noticeLike && !(a.subject_member_ids || []).length) return '';
  const schools = [...new Set(kids.map((m) => (m.school || '').trim()).filter(Boolean))];
  const about = (a.subject_member_ids || []).map(memberName).filter(Boolean);
  const canRemember = !!a.source_key;
  let body;
  if (about.length) {
    body = '<div class="row wrap" style="gap:6px">'
      + about.map((n) => '<span class="tag kid">' + esc(n) + '</span>').join('')
      + '<button class="btn ghost sm" data-who-change>Not right?</button></div>';
  } else {
    body = '<p class="muted" style="line-height:1.5">Nothing on this notice says which child it is for'
      + (schools.length > 1 ? ', and your children are at different schools.' : '.') + '</p>';
  }
  const chooser = '<div class="stack" data-who-chooser' + (about.length ? ' hidden' : '') + ' style="gap:8px">'
    + (schools.length > 1
      ? '<p style="font-size:13px;font-weight:600">Which school sent this?</p>'
        + '<div class="row wrap" style="gap:6px">'
        + schools.map((s) => '<button class="btn sm" data-who-school="' + esc(s) + '">' + esc(s) + '</button>').join('')
        + '</div>'
        + (canRemember
          ? '<p class="muted" style="line-height:1.45">It came from a group. Picking a school remembers the group as that '
            + 'school’s, so the next notice from it is attributed on arrival.</p>'
          : a.channel === 'share'
            ? '<p class="muted" style="line-height:1.45">Shared from your phone, so there is no sender to remember. '
              + 'Pick the school once for this notice.</p>'
            : '<p class="muted" style="line-height:1.45">Pasted, so there is no group to remember. Forward from inside the '
              + 'group on Telegram and the next one answers itself.</p>')
      : '')
    + '<p style="font-size:13px;font-weight:600">' + (schools.length > 1 ? 'Or one child' : 'Which child?') + '</p>'
    + '<div class="row wrap" style="gap:6px">'
    + kids.map((m) => '<button class="btn ghost sm" data-who-kid="' + esc(m.id) + '">' + esc(m.display_name) + '</button>').join('')
    + '<button class="btn ghost sm" data-who-kid="">Nobody in particular</button></div>'
    + '</div>';
  return '<div class="card pad stack" data-who style="gap:8px">'
    + '<div class="row wrap" style="gap:8px"><h2>About</h2>'
    + '<span class="muted">' + (about.length ? 'worked out, or set by a parent' : 'not known yet') + '</span></div>'
    + body + chooser + '</div>';
}

function wireWho(side, a, id) {
  const card = side.querySelector('[data-who]');
  if (!card) return;
  const change = card.querySelector('[data-who-change]');
  if (change) change.addEventListener('click', () => { card.querySelector('[data-who-chooser]').hidden = false; });

  const setSubjects = async (ids, remembered) => {
    try {
      const out = await api('/artifacts/' + id + '/subjects', { method: 'PUT', json: ids });
      const nowShared = a.visibility === 'private' && out && out.visibility === 'shared';
      flash(remembered ? 'Set, and remembered: anything from that group is ' + remembered + '’s now.'
        + (nowShared ? ' Shared with the household.' : '')
        : ids.length ? (nowShared ? 'Set, and shared with the household: a child’s notice is every adult’s.' : 'Set.') : 'Cleared.');
      await render();
    } catch (err) { fail(err); }
  };

  card.querySelectorAll('[data-who-school]').forEach((b) => b.addEventListener('click', async () => {
    const school = b.dataset.whoSchool;
    const kids = (store.household.members || []).filter((m) => m.role === 'child' && (m.school || '').trim() === school);
    let remembered = null;
    if (a.source_key && store.me && store.me.role === 'guardian') {
      try {
        await api('/household/source-schools', { method: 'PUT', json: { source_key: a.source_key, school } });
        remembered = school;
      } catch (err) { fail(err); }
    }
    await setSubjects(kids.map((m) => m.id), remembered);
  }));
  card.querySelectorAll('[data-who-kid]').forEach((b) => b.addEventListener('click', () => {
    setSubjects(b.dataset.whoKid ? [b.dataset.whoKid] : [], null);
  }));
}

function claimCard(c, i) {
  const loc = c.location || {};
  const placed = !!loc.match;
  const needs = (c.requires || []).map((r) => '<span class="need">' + esc(r.replace(/_/g, ' ')) + '</span>').join('');
  const when = c.date
    ? date(c.date) + (c.end_date && c.end_date !== c.date ? ' – ' + date(c.end_date) : '')
    : (c.date_text || '');
  const amount = money(c.amount, c.currency);
  return '<button class="claim' + (placed ? '' : ' ungrounded') + '" type="button" data-i="' + i
    + '" aria-pressed="false" aria-label="Claim ' + (i + 1) + ': ' + esc(c.title) + '">'
    + '<span class="row" style="align-items:flex-start;gap:10px">'
    + '<span class="n" aria-hidden="true">' + (i + 1) + '</span>'
    + '<span class="grow stack" style="gap:6px">'
    + '<span class="row wrap" style="gap:7px">'
    + '<span class="tag ' + (KIND_TONE[c.kind] || '') + '">' + esc(c.kind) + '</span>'
    + '<span style="font-size:14px;font-weight:600">' + esc(c.title) + '</span></span>'
    + '<span class="row wrap" style="gap:9px;font-size:12px;color:var(--ink-2)">'
    + (when ? '<span style="font-weight:500;color:var(--ink)">' + esc(when) + (c.uncertain ? ' (uncertain)' : '') + '</span>' : '')
    + (amount ? '<span style="font-weight:600;color:var(--ink)">' + esc(amount) + '</span>' : '')
    + (c.applies_to ? '<span class="tag line" style="text-transform:none;letter-spacing:0">' + esc(c.applies_to) + '</span>' : '')
    + (c.subject_name ? '<span class="tag kid">' + esc(c.subject_name) + '</span>' : '')
    + (c.optional ? '<span class="tag line" style="text-transform:none;letter-spacing:0">optional</span>' : '')
    + '</span>'
    + (needs ? '<span class="needs">' + needs + '</span>' : '')
    + '<span class="quote">&ldquo;' + esc(c.quote) + '&rdquo;</span>'
    + '<span class="foot">'
    + '<span class="tag ' + (loc.match === 'exact' ? 'green' : loc.match ? '' : 'red') + '">'
    + esc(loc.match || 'not found in the text') + '</span>'
    + (placed ? '<span>page ' + esc(loc.page) + ' · chars ' + esc(loc.span_start) + '–' + esc(loc.span_end) + '</span>' : '')
    + '<span class="grow"></span><span class="mono">' + Number(c.confidence).toFixed(2) + '</span>'
    + '</span></span></span></button>';
}

let viewerState = { pages: [], boxesFor: null };

function selectClaim(index, claims) {
  root.querySelectorAll('.claim').forEach((b) => {
    b.setAttribute('aria-pressed', String(Number(b.dataset.i) === index));
  });
  drawBoxes(claims[index]);
}

function drawBoxes(claim) {
  root.querySelectorAll('.box').forEach((b) => b.remove());
  const loc = claim && claim.location;
  if (!loc || !loc.match || !loc.boxes || !loc.boxes.length) return;
  const wrap = viewerState.pages[loc.page];
  if (!wrap) return;
  const scale = Number(wrap.dataset.scale) || 1;
  loc.boxes.forEach((b) => {
    const el = document.createElement('div');
    el.className = 'box';
    el.style.left = (b[0] * scale) + 'px';
    el.style.top = (b[1] * scale) + 'px';
    el.style.width = Math.max(2, (b[2] - b[0]) * scale) + 'px';
    el.style.height = Math.max(2, (b[3] - b[1]) * scale) + 'px';
    wrap.appendChild(el);
  });
  wrap.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

/* the original, rendered so boxes can sit on it */

async function renderOriginal(viewer, artifact) {
  viewerState = { pages: [], boxesFor: null };
  const kind = /pdf/.test(artifact.media_type) ? 'PDF' : /^image\//.test(artifact.media_type) ? 'Image' : /rfc822/.test(artifact.media_type) ? 'Email' : /text/.test(artifact.media_type) ? 'Text' : artifact.media_type;
  viewer.innerHTML = '<header><b>Original</b>'
    + '<span>' + esc(kind) + ' \u00B7 ' + esc(bytes(artifact.size_bytes)) + '</span>'
    + '<span class="grow"></span>'
    + '<span class="mono muted" title="' + esc(artifact.media_type) + ' \u00B7 sha256 ' + esc(String(artifact.sha256)) + '">sha256 ' + esc(String(artifact.sha256).slice(0, 10)) + '\u2026</span></header>'
    + '<div class="stage"><p class="note">Fetching&hellip;</p></div>';
  const stage = viewer.querySelector('.stage');
  // A phone's HEIC is shown through its JPEG rendition at full size, so the
  // reader's boxes still land; everything else is the original itself.
  const blob = await api('/artifacts/' + artifact.id + (artifact.media_type === 'image/heic' ? '/picture?full=1' : '/original'), { blob: true });

  if (artifact.media_type.startsWith('image/')) {
    const url = URL.createObjectURL(blob);
    stage.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'page-wrap';
    const img = document.createElement('img');
    img.alt = 'The original notice';
    img.src = url;
    wrap.appendChild(img);
    stage.appendChild(wrap);
    await new Promise((res) => { img.onload = res; img.onerror = res; });
    // Boxes for an image are in its own pixels, so the factor is how much the
    // browser had to shrink it to fit.
    wrap.dataset.scale = String(img.naturalWidth ? img.clientWidth / img.naturalWidth : 1);
    viewerState.pages[1] = wrap;
    return;
  }

  if (artifact.media_type === 'application/pdf') {
    try {
      await renderPdf(stage, await blob.arrayBuffer());
      return;
    } catch (err) {
      stage.innerHTML = '<p class="note">The page renderer could not load, so the words cannot be '
        + 'highlighted here. Each claim still shows the text it was read from.</p>';
      const obj = document.createElement('object');
      obj.type = 'application/pdf';
      obj.data = URL.createObjectURL(blob);
      stage.appendChild(obj);
      return;
    }
  }

  if (artifact.media_type.startsWith('text/') || artifact.media_type === 'message/rfc822') {
    // A mail is shown as its words, not its headers; the raw message is a tap away.
    let words = null;
    if (artifact.media_type === 'message/rfc822') { try { words = await api('/artifacts/' + artifact.id + '/text', { text: true }); } catch (err) { words = null; } }
    const raw = await blob.text();
    const box = (t, mono) => '<pre style="margin:0;width:100%;max-height:620px;overflow:auto;background:var(--card);'
      + 'padding:18px;border-radius:6px;font:400 ' + (mono ? '12px/1.6 var(--mono)' : '14px/1.65 inherit') + ';white-space:pre-wrap">' + esc(t.slice(0, 200000)) + '</pre>';
    if (words !== null && typeof words === 'string') {
      stage.innerHTML = box(words, false) + '<p class="muted" style="margin:8px 0 0"><button class="btn ghost sm" data-raw>Show the raw message</button></p>';
      stage.querySelector('[data-raw]').addEventListener('click', () => { stage.innerHTML = box(raw, true); });
    } else {
      stage.innerHTML = box(raw, artifact.media_type === 'message/rfc822');
    }
    return;
  }

  stage.innerHTML = '<p class="note">' + esc(artifact.media_type)
    + ' cannot be shown here. Use &ldquo;Download original&rdquo; — every read is audited either way.</p>';
}

let pdfjsLoading = null;
function loadPdfjs() {
  if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
  if (pdfjsLoading) return pdfjsLoading;
  pdfjsLoading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = PDFJS_BASE + '/pdf.min.js';
    s.onload = () => {
      if (!window.pdfjsLib) { reject(new Error('pdf.js did not register')); return; }
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_BASE + '/pdf.worker.min.js';
      resolve(window.pdfjsLib);
    };
    s.onerror = () => reject(new Error('pdf.js could not be fetched'));
    document.head.appendChild(s);
  });
  return pdfjsLoading;
}

async function renderPdf(stage, buffer) {
  const lib = await loadPdfjs();
  const pdf = await lib.getDocument({ data: buffer }).promise;
  stage.innerHTML = '';
  const width = Math.min(stage.clientWidth - 40, 900);
  for (let n = 1; n <= pdf.numPages; n += 1) {
    const page = await pdf.getPage(n);
    const base = page.getViewport({ scale: 1 });
    // PyMuPDF gives box coordinates in PDF points from the top left, which is
    // the same origin the canvas uses, so one factor maps both.
    const scale = width / base.width;
    const viewport = page.getViewport({ scale });
    const wrap = document.createElement('div');
    wrap.className = 'page-wrap';
    wrap.dataset.scale = String(scale);
    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = Math.floor(viewport.width) + 'px';
    canvas.style.height = Math.floor(viewport.height) + 'px';
    wrap.appendChild(canvas);
    stage.appendChild(wrap);
    viewerState.pages[n] = wrap;
    await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
  }
  const selected = root.querySelector('.claim[aria-pressed="true"]');
  if (selected) selected.click();
}

/* ── obligations ──────────────────────────────────────────────── */

const ACTION = {
  sign: { glyph: '✎', icon: 'pen', tone: 'amber' },
  pay: { glyph: '₹', icon: 'money', tone: 'green' },
  attend: { glyph: '⚑', icon: 'calendar', tone: 'blue' },
  submit: { glyph: '↗', icon: 'send', tone: 'amber' },
  prepare: { glyph: '▣', icon: 'cart', tone: '' },
  note: { glyph: '○', icon: 'info', tone: '' },
};

async function renderObligations(box, artifactId, familyIds) {
  const all = await api('/obligations?status=&limit=200');
  // A notice and its attachments are one notice: the PDF's dates show on the mail's page.
  const ids = new Set(familyIds || (artifactId ? [artifactId] : []));
  const mine = artifactId ? all.filter((o) => ids.has(o.artifact_id)) : all;
  box.innerHTML = '<div class="row wrap" style="gap:8px"><h2>Proposed for the family</h2>'
    + '<span class="muted">nothing is accepted until someone says so</span></div>'
    + (mine.length ? '<div class="stack" style="gap:7px" data-obs></div>'
      : '<p class="muted">Nothing proposed from this notice.</p>');
  if (mine.length) wireObligationRows(box.querySelector('[data-obs]'), mine);
}

/* A UPI intent on an iPhone opens whichever app claimed the upi:// scheme --
   there is no chooser -- so beside the plain link, one that names Google Pay
   by its own scheme (gpay://upi/pay?..., per Google's iOS guide). */
function payLinks(url, cls) {
  if (!url) return '';
  const a = (href, label) => '<a class="' + (cls || 'btn sm') + '" href="' + esc(href) + '" target="_blank" rel="noopener" style="text-decoration:none">' + label + '</a>';
  if (/^upi:\/\/pay\?/i.test(url)) return a(url, 'Pay \u2197') + ' ' + a('gpay://upi/pay?' + url.split('?')[1], 'Google Pay');
  return a(url, 'Pay \u2197');
}

function obligationRow(o, withLink) {
  const act = ACTION[o.action] || ACTION.note;
  const done = o.status !== 'proposed';
  const gone = !!o.superseded_at;
  const bits = [o.kind, o.due_date ? 'Due ' + fmtDate(o.due_date).replace(/,.*$/, '') + (o.due_time ? ' ' + o.due_time : '') : 'No date',
    o.subject_member_id ? 'for ' + memberName(o.subject_member_id) : null,
    o.action === 'pay' ? (o.pay_url ? 'Pay opens the biller\u2019s own page, you pay there' : 'a reminder, nothing here pays') : null].filter(Boolean);
  return '<div class="row card" style="gap:12px;padding:12px 14px;background:'
    + (done ? 'var(--sunk)' : 'var(--card)') + ';opacity:' + (o.status === 'dismissed' ? '0.5' : '1') + '">'
    + '<span class="glyph ' + (done ? 'green' : act.tone) + '" aria-hidden="true">'
    + (o.status === 'accepted' ? icon('check', 15) : icon(act.icon || 'info', 15)) + '</span>'
    + '<span class="grow"><span class="row wrap" style="gap:7px">'
    + '<span style="font-size:13.5px;font-weight:600' + (gone ? ';text-decoration:line-through' : '') + '">'
    + esc(o.title) + '</span>'
    + (gone ? '<a class="tag amber" href="#/notices/' + esc(o.superseded_by_artifact_id)
      + '" style="text-decoration:none">superseded \u2014 see the notice this came from</a>' : '')
    + (o.optional ? '<span class="tag line" style="text-transform:none;letter-spacing:0">optional</span>' : '')
    + (done ? '<span class="tag ' + (o.status === 'accepted' ? 'green' : '') + '">' + esc(o.status) + '</span>' : '')
    + '</span><span class="sub">' + esc(bits.join(' \u00B7 '))
    + (withLink ? ' \u00B7 <a href="#/notices/' + esc(o.artifact_id) + '">the notice</a>' : '')
    + '</span></span>'
    + (o.pay_url && o.status !== 'dismissed' && !gone ? payLinks(o.pay_url) : '')
    + '<span class="acts">' + (o.status === 'proposed'
      ? '<button class="btn sm" data-accept="' + esc(o.id) + '">Accept</button>'
        + '<button class="icon-btn" data-dismiss="' + esc(o.id) + '" aria-label="Dismiss" title="Dismiss">' + icon('x', 15) + '</button>'
      : '<button class="btn ghost sm" data-accept="' + esc(o.id) + '" '
        + (o.status === 'accepted' ? 'disabled' : '') + '>Accept</button>') + '</span>'
    + '</div>';
}

function wireObligationRows(container, rows, withLink) {
  container.innerHTML = rows.map((o) => obligationRow(o, withLink)).join('');
  const decide = async (id, status) => {
    try {
      await api('/obligations/' + id + '/decision', { method: 'POST', json: { status } });
      flash(status === 'accepted' ? 'Accepted.' : 'Dismissed.');
      await render();
    } catch (err) { fail(err); }
  };
  container.querySelectorAll('[data-accept]').forEach((b) =>
    b.addEventListener('click', () => decide(b.dataset.accept, 'accepted')));
  container.querySelectorAll('[data-dismiss]').forEach((b) =>
    b.addEventListener('click', () => decide(b.dataset.dismiss, 'dismissed')));
}

/* ── the brief ────────────────────────────────────────────────── */
/* Worst first, and never more than a few lines: a brief that lists everything
   is the list it was meant to replace. The server decides what matters and in
   what order; this only draws it. */

const REASON = {
  missed: { tone: 'red', label: 'missed', glyph: '!', icon: 'bell' },
  mailbox: { tone: 'red', label: 'not being read', glyph: '\u2709', icon: 'mail' },
  overdue: { tone: 'red', label: 'overdue', glyph: '!', icon: 'bell' },
  today: { tone: 'amber', label: 'today', glyph: '\u25CF', icon: 'clock' },
  undecided: { tone: 'amber', label: 'undecided', glyph: '?', icon: 'info' },
  soon: { tone: 'blue', label: 'soon', glyph: '\u2192', icon: 'calendar' },
  amendment: { tone: 'rust', label: 'may have changed', glyph: '\u21BB', icon: 'refresh' },
  quarantine: { tone: 'rust', label: 'needs vouching', glyph: '\u29B8', icon: 'shield' },
  assigned: { tone: 'blue', label: 'assigned', glyph: '\u00B7', icon: 'send' },
};

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  return hour < 18 ? 'Good afternoon' : 'Good evening';
}

/* Each line goes where the thing is actually dealt with. */
function briefHref(i) {
  if (i.reason === 'mailbox') return '#/household';
  if (i.reason === 'amendment') return '#/revisions';
  if (i.reason === 'quarantine') return '#/quarantine';
  return i.artifact_id ? '#/notices/' + i.artifact_id : '#/waiting';
}

function briefRow(i) {
  const r = REASON[i.reason] || { tone: '', label: i.reason, glyph: '\u00B7', icon: 'info' };
  return '<a class="brief-row row" href="' + briefHref(i) + '" style="gap:10px;align-items:flex-start">'
    + '<span class="glyph ' + r.tone + '" style="width:28px;height:28px;flex-shrink:0"'
    + ' aria-hidden="true">' + icon(r.icon || 'info', 14) + '</span>'
    + '<span class="grow"><span class="row wrap" style="gap:6px">'
    + '<span style="font-size:13.5px;font-weight:600">' + esc(i.title) + '</span>'
    + '<span class="tag ' + r.tone + '">' + esc(r.label) + '</span>'
    + (i.optional ? '<span class="tag line">optional</span>' : '')
    + (i.subject_name ? '<span class="tag kid">' + esc(i.subject_name) + '</span>' : '')
    // A pending revision means the date shown may not be the date that holds.
    + (i.contested && i.reason !== 'amendment'
      ? '<span class="tag rust" title="A later notice looks like it changes this">may have changed</span>' : '')
    // Something already in a calendar this member can see overlaps it. Nobody
    // reads two calendars side by side at 7am, which is when it matters.
    + ((i.clashes && i.clashes.length)
      ? '<span class="tag amber" title="' + esc(i.clashes.join(', ')) + '">clashes</span>' : '')
    + '</span>'
    + '<span class="sub">' + esc(i.why) + (i.when ? ' \u00B7 ' + esc(i.when) : '') + '</span>'
    + ((i.clashes && i.clashes.length)
      ? '<span class="sub" style="opacity:.9">already on at that time: <b>'
        + i.clashes.map(esc).join('</b>, <b>') + '</b></span>' : '')
    + '</span></a>';
}

function briefCard(b) {
  return '<section class="card pad stack brief" style="gap:13px">'
    + '<div class="row wrap" style="gap:10px">'
    + '<h1 style="margin:0">' + esc(greeting()) + ', ' + esc(b.display_name) + '</h1>'
    + '<span class="rule"></span>'
    + '<span class="muted" style="flex-shrink:0">' + esc(date(b.date)) + '</span></div>'
    + (b.items.length
      ? '<div class="stack" style="gap:9px">' + b.items.map(briefRow).join('') + '</div>'
        + (b.more ? '<span class="muted">and ' + b.more + ' more below</span>' : '')
      : '<p class="muted">Nothing needs anyone today. A dated thing appears here before its day, and anything '
        + 'nobody has decided appears sooner than that.</p>'
        // Without this, a family who has just forwarded a circular about
        // December sees a blank screen and concludes nothing happened.
        + (b.next_thing
          ? '<div class="row" style="gap:10px;padding:10px 12px;background:var(--sunk);'
            + 'border:1px solid var(--line-soft);border-radius:7px;align-items:flex-start">'
            + '<span class="grow"><span class="sub">Next, ' + esc(b.next_thing.when) + '</span>'
            + '<span style="font-size:13px;font-weight:600">' + esc(b.next_thing.title) + '</span></span>'
            + '<a class="btn ghost sm" href="#/today">See everything</a></div>'
          : ''))
    + '</section>';
}

/* ── today ────────────────────────────────────────────────────── */

async function todayView(main) {
  const [brief, proposed, upcoming, inboxRows] = await Promise.all([
    api('/brief?limit=3'),
    api('/obligations?status=proposed&limit=200'),
    api('/reminders?limit=200'),
    api('/inbox?days=120&limit=400').catch(() => []),
  ]);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const week = new Date(today); week.setDate(week.getDate() + 7);

  const investIds = new Set((inboxRows || []).filter((n) => spaceOfNotice(n) === 'invest').map((n) => n.id));
  const bucket = { Overdue: [], 'This week': [], Later: [], 'No date': [], Investments: [] };
  proposed.forEach((o) => {
    // E-votes, ballots and AGMs: asked, optional, and not the family's week.
    if (investIds.has(o.artifact_id)) { bucket.Investments.push(o); return; }
    if (!o.due_date) { bucket['No date'].push(o); return; }
    const d = new Date(o.due_date + 'T00:00:00');
    if (d < today) bucket.Overdue.push(o);
    else if (d <= week) bucket['This week'].push(o);
    else bucket.Later.push(o);
  });

  main.classList.remove('chat-main');
  const TONE = { Overdue: 'red', 'This week': 'amber', Later: '', 'No date': '', Investments: 'cat invest' };
  main.innerHTML = briefCard(brief)
    + '<div class="head"><div><h1>Waiting on you</h1>'
    + '<p>Proposed from notices you can see. Nothing here has been agreed to yet, and nothing here pays.</p></div>'
    + '<a class="btn ghost" href="#/notices">All notices</a></div>'
    + '<div class="split"><div>'
    + (proposed.length ? '<div class="stack" style="gap:20px" data-groups></div>'
      : '<div class="card"><div class="empty">Nothing is waiting on you. Anything a notice asks for shows up here first as a proposal.</div></div>')
    + '</div><aside class="stack" data-side></aside></div>';

  renderUpcoming(main.querySelector('[data-side]'), upcoming);
  if (!proposed.length) return;
  const groups = main.querySelector('[data-groups]');
  Object.keys(bucket).forEach((label) => {
    if (!bucket[label].length) return;
    const sec = document.createElement('section');
    sec.className = 'stack';
    sec.style.gap = '8px';
    sec.innerHTML = '<div class="row"><span class="tag ' + TONE[label] + '">' + esc(label)
      + '</span><span class="rule"></span></div><div data-rows class="stack" style="gap:7px"></div>';
    groups.appendChild(sec);
    wireObligationRows(sec.querySelector('[data-rows]'), bucket[label], true);
  });
  loadTodosCard(main, '[data-side]');
  loadSuggestionsCard(main, '[data-side]');
}

function renderUpcoming(side, reminders) {
  const pending = reminders.filter((r) => r.status === 'pending');
  const sent = reminders.filter((r) => r.status === 'sent');
  side.innerHTML = '<div class="card pad stack" style="gap:11px">'
    + '<div class="row wrap" style="gap:8px"><h2>You will be told</h2>'
    + '<span class="muted">' + pending.length + ' to come</span></div>'
    + (pending.length
      ? '<div class="stack" style="gap:8px">' + pending.slice(0, 8).map(reminderRow).join('') + '</div>'
      : '<p class="muted">Nothing queued. A dated task is reminded about before its day.</p>')
    + (sent.length ? '<p class="muted" style="padding-top:4px;border-top:1px solid var(--line-soft)">'
      + sent.length + ' already sent.</p>' : '')
    + '</div>'
    + '<div class="card pad stack" style="gap:7px">'
    + '<span style="font-size:12.5px;font-weight:600">Who gets told</span>'
    + '<span class="muted" style="line-height:1.55">A shared notice reminds the adults and guardians. A private one '
    + 'reminds only the member who sent it. Children are never told: a task names a child because it is '
    + '<em>about</em> them.</span></div>';
}

function reminderRow(r) {
  const nudge = r.reason === 'undecided';
  return '<div class="row" style="gap:10px;align-items:flex-start">'
    + '<span class="lead" aria-hidden="true">' + (r.lead_days === 0 ? 'day' : r.lead_days + 'd') + '</span>'
    + '<span class="grow"><span style="font-size:12.5px;font-weight:500;display:block">' + esc(r.title) + '</span>'
    + '<span class="muted">' + (nudge ? 'nudge \u2014 still undecided' : 'due ' + esc(date(r.due_date)))
    + '  \u00B7  ' + esc(ago(r.send_after).replace(' ago', ' from now').replace('just now', 'now')) + '</span></span>'
    + '</div>';
}

/* ── quarantine ───────────────────────────────────────────────── */

async function quarantineView(main) {
  const items = await api('/quarantine');
  store.quarantineCount = items.length;
  main.innerHTML = '<div class="head"><div><div class="row" style="gap:10px"><h1>Quarantine</h1>'
    + '<span class="tag rust">guardians only</span></div>'
    + '<p style="max-width:760px">Mail whose sender we could not place, or whose provider would not vouch for the address it '
    + 'claims. It is kept, encrypted, and nothing has read it. Say who it belongs to and it joins the household; '
    + 'reject it and the bytes go.</p></div></div>'
    + (items.length ? '<div class="stack" data-items></div>'
      : '<div class="card"><div class="empty">Nothing is waiting. Mail from a member whose provider authenticated it is accepted straight away.</div></div>');
  if (!items.length) return;

  const box = main.querySelector('[data-items]');
  const people = membersByRole(['guardian', 'adult']);
  box.innerHTML = items.map((q) => {
    const src = q.source || {};
    return '<article class="card pad stack" data-q="' + esc(q.id) + '" style="gap:14px">'
      + '<div class="row wrap" style="gap:13px;align-items:flex-start">'
      + '<span class="glyph ' + (q.quarantine_reason === 'unknown_sender' ? 'rust' : 'amber') + '" aria-hidden="true">!</span>'
      + '<span class="grow"><span class="row wrap" style="gap:9px">'
      + '<span style="font-size:15px;font-weight:600">' + esc(src.subject || q.filename || 'No subject') + '</span>'
      + '<span class="tag ' + (q.quarantine_reason === 'unknown_sender' ? 'rust' : 'red') + '">'
      + esc(String(q.quarantine_reason || '').replace(/_/g, ' ')) + '</span></span>'
      + '<span class="sub">from <b class="mono" style="color:var(--ink);font-weight:500">' + esc(src.from || 'unknown')
      + '</b>  ·  ' + esc(date(q.received_at)) + '  ·  ' + esc(bytes(q.size_bytes))
      + '  ·  ' + (q.children || []).length + ' attachment' + ((q.children || []).length === 1 ? '' : 's')
      + '</span></span></div>'
      + '<div class="row wrap" style="gap:10px;padding:10px 13px;background:var(--sunk);border:1px solid var(--line-soft);border-radius:8px">'
      + '<span class="mono" style="font-size:11px;font-weight:500">sender authenticated</span>'
      + '<span class="mono" style="font-size:11px;color:var(--ink-2)">' + (src.sender_authenticated ? 'yes' : 'no')
      + '</span><span class="rule"></span>'
      + '<span class="mono" style="font-size:11px;color:var(--ink-2)">message-id ' + esc(src.message_id || '—') + '</span>'
      + '</div>'
      + '<div class="row wrap" style="gap:10px">'
      + '<span class="muted">If you know this sender, say whose it is:</span>'
      + '<span class="row wrap" style="gap:6px" data-owners>'
      + people.map((m) => '<button class="pill" data-owner="' + esc(m.id) + '" aria-pressed="false">'
        + esc(m.display_name) + '</button>').join('')
      + '</span><span class="grow"></span>'
      + '<select data-visibility style="width:auto"><option value="private">Private to them</option>'
      + '<option value="shared">Shared with the household</option></select>'
      + '<button class="btn ghost" data-reject>Reject and delete</button>'
      + '<button class="btn" data-accept disabled>Accept</button>'
      + '</div></article>';
  }).join('');

  box.querySelectorAll('[data-q]').forEach((card) => {
    const id = card.dataset.q;
    let owner = null;
    const accept = card.querySelector('[data-accept]');
    card.querySelectorAll('[data-owner]').forEach((b) => {
      b.addEventListener('click', () => {
        owner = b.dataset.owner;
        card.querySelectorAll('[data-owner]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
        accept.disabled = false;
        accept.textContent = 'Accept for ' + memberName(owner);
      });
    });
    accept.addEventListener('click', async () => {
      if (!owner) return;
      accept.disabled = true;
      try {
        await api('/quarantine/' + id + '/accept', {
          method: 'POST',
          json: { member_id: owner, visibility: card.querySelector('[data-visibility]').value },
        });
        flash('Accepted. It will be read now.');
        await render();
      } catch (err) { fail(err); accept.disabled = false; }
    });
    card.querySelector('[data-reject]').addEventListener('click', async () => {
      if (!confirm('Reject this? The stored bytes are deleted and this cannot be undone.')) return;
      try {
        await api('/quarantine/' + id + '/reject', { method: 'POST' });
        flash('Rejected and deleted.');
        await render();
      } catch (err) { fail(err); }
    });
  });
}

/* -- revisions -------------------------------------------------- */

async function amendmentsView(main) {
  const proposed = await api('/amendments?status=proposed&limit=200');
  const all = await api('/amendments?status=&limit=200');
  const settled = all.filter((a) => a.status !== 'proposed');
  store.amendmentCount = proposed.length;

  main.innerHTML = '<div class="head"><div><h1>Revisions</h1>'
    + '<p style="max-width:780px">A notice that looks like it changes an earlier one. Matching two notices by their '
    + 'words is a guess, so nothing is applied until you say so. Until then <b>both still remind you</b>, and the '
    + 'reminder for the older one says a later notice may have changed it.</p></div></div>'
    + (proposed.length ? '<div class="stack" data-proposed></div>'
      : '<div class="card"><div class="empty">Nothing is waiting. When a notice revises an earlier one, the link to '
        + 'confirm shows up here.</div></div>')
    + (settled.length ? '<h2 style="margin:26px 0 12px">Already decided</h2><div class="card list" data-settled></div>' : '');

  if (proposed.length) {
    const box = main.querySelector('[data-proposed]');
    box.innerHTML = proposed.map(amendmentCard).join('');
    box.querySelectorAll('[data-decide]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const status = btn.dataset.decide;
        if (status === 'confirmed'
          && !confirm('Confirm that this replaces the earlier notice?\n\nThe earlier notice’s tasks are superseded '
            + 'and stop reminding. If the two are not actually the same thing, nobody will be reminded about the '
            + 'earlier one again.')) return;
        btn.disabled = true;
        try {
          const out = await api('/amendments/' + btn.dataset.id + '/decision', { method: 'POST', json: { status } });
          flash(status === 'confirmed'
            ? 'Linked. ' + out.obligations_superseded + ' task'
              + (out.obligations_superseded === 1 ? '' : 's') + ' superseded.'
            : 'Left as two separate notices.');
          await render();
        } catch (err) { fail(err); btn.disabled = false; }
      });
    });
  }

  if (settled.length) {
    main.querySelector('[data-settled]').innerHTML = settled.map((a) =>
      '<div class="item" style="cursor:default">'
      + '<span class="tag ' + (a.status === 'confirmed' ? 'green' : '') + '">' + esc(a.status) + '</span>'
      + '<span class="grow"><span class="title">' + esc(a.claim_title) + '</span>'
      + '<span class="sub">' + (a.status === 'confirmed' ? 'replaced' : 'kept separate from') + ' “'
      + esc(a.amends_title) + '”  ·  ' + esc(memberName(a.decided_by) || 'a member')
      + '  ·  ' + esc(ago(a.decided_at)) + '</span></span></div>').join('');
  }
}

function amendmentCard(a) {
  const pct = Math.round(Number(a.score) * 100);
  return '<article class="card pad stack" style="gap:16px">'
    + '<div class="row wrap" style="gap:10px">'
    + '<span class="glyph amber" aria-hidden="true">⇄</span>'
    + '<span class="grow"><span style="font-size:15px;font-weight:600">This looks like a revision</span>'
    + '<span class="sub">matched on ' + esc(a.matched_on) + '</span></span>'
    + '<span class="tag ' + (pct >= 70 ? 'green' : 'amber') + '">' + pct + '% match</span>'
    + '</div>'
    + '<div class="revision">'
    + '<div class="side"><div class="label">The newer notice says</div>'
    + '<a class="ref" href="#/notices/' + esc(a.artifact_id) + '">' + esc(a.claim_title) + '</a>'
    + (a.change ? '<p class="change">“' + esc(a.change) + '”</p>' : '')
    + '</div>'
    + '<div class="arrow" aria-hidden="true">replaces</div>'
    + '<div class="side old"><div class="label">The earlier notice</div>'
    + '<a class="ref" href="#/notices/' + esc(a.amends_artifact_id) + '">' + esc(a.amends_title) + '</a>'
    + (a.amends_date ? '<p class="change">was ' + esc(date(a.amends_date)) + '</p>' : '')
    + '</div></div>'
    + '<div class="row wrap" style="gap:10px">'
    + '<span class="muted" style="max-width:520px;line-height:1.5">Confirming supersedes the earlier notice’s '
    + 'tasks and stops their reminders. Rejecting leaves both standing.</span>'
    + '<span class="grow"></span>'
    + '<button class="btn ghost" data-decide="rejected" data-id="' + esc(a.id) + '">Not the same thing</button>'
    + '<button class="btn" data-decide="confirmed" data-id="' + esc(a.id) + '">Confirm the revision</button>'
    + '</div></article>';
}


/* ── household ────────────────────────────────────────────────── */

/* ── connected mailboxes, export, and what did not arrive ─────── */

function watchesCard(watches) {
  const SHOWN = 5;
  const live = watches.filter((w) => !w.paused_at);
  const rowsOf = (list) => list.map((w) => {
    let state = '<span class="tag" style="white-space:nowrap">not checked yet</span>';
    if (w.last_error) state = '<span class="tag amber" style="white-space:nowrap">could not read</span>';
    else if (w.last_found === true) state = '<span class="tag green">found</span>';
    else if (w.last_found === false) state = '<span class="tag" style="white-space:nowrap">not there</span>';
    return '<div class="row" style="gap:10px;padding:9px 11px;background:var(--sunk);'
      + 'border:1px solid var(--line-soft);border-radius:7px">'
      + '<span class="grow"><span style="font-size:12.5px;font-weight:600">' + esc(w.label) + '</span>'
      + '<span class="sub">looking for \u201c' + esc(w.look_for) + '\u201d on ' + esc(host(w.url))
      + '  \u00b7  every ' + esc(String(w.every_hours)) + 'h'
      + (w.last_checked_at ? '  \u00b7  checked ' + esc(ago(w.last_checked_at)) : '  \u00b7  not checked yet')
      + (w.last_error ? '  \u00b7  ' + esc(w.last_error) : '') + '</span>'
      + (w.last_excerpt ? '<span class="sub" style="opacity:.85">\u201c' + esc(w.last_excerpt.slice(0, 160)) + '\u2026\u201d</span>' : '')
      + '</span>' + state
      + '<button class="btn ghost sm" data-unwatch="' + esc(w.id) + '">Stop</button>'
      + '</div>';
  }).join('');
  const rows = rowsOf(live.slice(0, SHOWN))
    + (live.length > SHOWN
      ? '<details class="stack" style="gap:10px"><summary class="muted" style="cursor:pointer;font-size:12.5px">'
        + (live.length - SHOWN) + ' more</summary>' + rowsOf(live.slice(SHOWN)) + '</details>'
      : '');

  return '<div class="card pad stack" style="gap:10px">'
    + '<div class="row wrap" style="gap:8px"><h2>Pages you are watching</h2>'
    + '<span class="muted">' + (live.length ? live.length + ' · ' : '') + 'read-only</span></div>'
    + '<p class="muted" style="line-height:1.55">FamilyOS reads a public page on a schedule and tells you when the '
    + 'answer changes. It <b>never signs in</b>, holds no password for the site, and does nothing on your behalf \u2014 '
    + 'it reads the page and writes to you.</p>'
    + (rows || '<p class="muted">Nothing being watched.</p>')
    + '<button class="btn sm" data-addwatch style="align-self:flex-start">Watch a page</button>'
    + '</div>';
}

function host(url) {
  try { return new URL(url).hostname; } catch (e) { return url; }
}

function handleDialog() {
  const h = store.household || {};
  return '<dialog data-addrdialog class="card" style="max-width:420px;padding:20px;border:1px solid var(--line)">'
    + '<div class="stack" style="gap:12px"><h2>Name the family address</h2>'
    + '<p class="muted" style="line-height:1.5">This is what a school writes down. Letters, numbers, dots and '
    + 'hyphens. The generated address never stops working, so nothing you have already given out breaks.</p>'
    + '<label class="stack" style="gap:4px"><span class="sub">Address</span>'
    + '<input data-handle type="text" placeholder="the.sharmas" value="' + esc(h.handle || '') + '"></label>'
    + '<p class="sub" data-handlehint></p>'
    + '<div class="row" style="gap:8px;justify-content:flex-end">'
    + '<button type="button" class="btn ghost sm" data-addrcancel>Cancel</button>'
    + '<button type="button" class="btn sm" data-addrsave>Use this</button></div></div></dialog>';
}

function wireHandle(main) {
  const dialog = main.querySelector('[data-addrdialog]');
  const placesBox = main.querySelector('[data-places]');
  if (placesBox) wirePlaces(placesBox);
  const schoolsBox = main.querySelector('[data-schools]');
  if (schoolsBox) {
    api('/household/schools').then((schools) => {
      if (!schools.length) return;
      const hm = (t) => (t ? String(t).slice(0, 5) : '');
      const guardian = store.me && store.me.role === 'guardian';
      schoolsBox.innerHTML = '<div class="stack" style="gap:6px;padding:8px 2px 4px"><span style="font-size:13px;font-weight:600">Schools</span>'
        + schools.map((sc) => '<div class="stack" style="gap:4px" data-school-row="' + esc(sc.id) + '"><div class="row wrap" style="gap:8px"><b>' + esc(sc.name) + '</b><span class="muted">' + esc(sc.children.join(', ') || 'no child attached')
          + (sc.sources.length ? ' · ' + sc.sources.length + ' group' + (sc.sources.length > 1 ? 's' : '') + ' mapped' : '') + '</span>'
          + (sc.portal_url ? '<a class="muted" href="' + esc(sc.portal_url) + '" target="_blank" rel="noopener">portal</a>' : '')
          + (guardian ? '<button class="btn ghost sm" data-school-edit="' + esc(sc.id) + '">' + (sc.starts_at || sc.portal_url ? 'edit' : 'add timings') + '</button>' : '') + '</div>'
          + (sc.starts_at ? '<span class="muted" style="font-size:12.5px">school day ' + hm(sc.starts_at) + (sc.ends_at ? ' to ' + hm(sc.ends_at) : '') + '</span>' : '')
          + '</div>').join('') + '</div>';
      schoolsBox.querySelectorAll('[data-school-edit]').forEach((b) => b.addEventListener('click', () => {
        const sc = schools.find((x) => x.id === b.dataset.schoolEdit); if (!sc) return;
        const row = schoolsBox.querySelector('[data-school-row="' + sc.id + '"]');
        const form = document.createElement('form'); form.className = 'stack'; form.style.gap = '6px'; form.style.marginTop = '4px';
        form.innerHTML = '<div class="row wrap" style="gap:10px"><label class="stack" style="gap:2px"><span class="muted" style="font-size:12px">School starts</span><input type="time" name="starts_at" value="' + esc(hm(sc.starts_at)) + '"></label>'
          + '<label class="stack" style="gap:2px"><span class="muted" style="font-size:12px">Ends</span><input type="time" name="ends_at" value="' + esc(hm(sc.ends_at)) + '"></label>'
          + '<label class="stack grow" style="gap:2px"><span class="muted" style="font-size:12px">Portal</span><input type="url" name="portal_url" placeholder="https://" value="' + esc(sc.portal_url || '') + '"></label></div>'
          + '<div class="row" style="gap:8px"><button class="btn sm" type="submit">Save</button><button class="btn ghost sm" type="button" data-cancel>Cancel</button>'
          + '<span class="muted" style="font-size:12px">A start time gives a leave-by on Today and, on a school morning, a word when the drive is markedly slower than usual.</span></div>';
        row.appendChild(form); b.hidden = true;
        form.querySelector('[data-cancel]').addEventListener('click', () => { form.remove(); b.hidden = false; });
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const f = new FormData(form);
          const body = { starts_at: String(f.get('starts_at')) || null, ends_at: String(f.get('ends_at')) || null, portal_url: String(f.get('portal_url')).trim() || null };
          try { await api('/household/schools/' + sc.id, { method: 'PUT', json: body }); render(); }
          catch (err) { form.querySelector('[type="submit"]').textContent = (err && err.message) || 'Failed'; }
        });
      }));
    }).catch(() => {});
  }
  const localeBtn = main.querySelector('[data-locale]'); const localeForm = main.querySelector('[data-locale-form]');
  if (localeBtn && localeForm) {
    localeBtn.addEventListener('click', () => { localeForm.hidden = !localeForm.hidden; });
    localeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = new FormData(localeForm); const note = localeForm.querySelector('[data-locale-note]');
      try {
        const h = await api('/household/locale', { method: 'PUT', json: { country: String(f.get('country')).trim().toUpperCase(), timezone: String(f.get('timezone')).trim(), currency: String(f.get('currency')).trim().toUpperCase() } });
        store.household = h; main.querySelector('[data-locale-text]').textContent = h.country + ' · ' + h.timezone + ' · ' + h.currency; localeForm.hidden = true;
      } catch (err) { note.textContent = (err && err.message) || 'That did not save.'; }
    });
  }
  const open = main.querySelector('[data-renameaddr]');
  if (!dialog || !open) return;
  open.addEventListener('click', () => dialog.showModal());
  main.querySelector('[data-addrcancel]').addEventListener('click', () => dialog.close());

  const field = main.querySelector('[data-handle]');
  const hint = main.querySelector('[data-handlehint]');
  let timer = null;
  field.addEventListener('input', () => {
    clearTimeout(timer);
    const value = field.value.trim().toLowerCase();
    hint.textContent = '';
    if (value.length < 3) return;
    timer = setTimeout(async () => {
      try {
        const r = await api('/household/handle/available?handle=' + encodeURIComponent(value));
        hint.textContent = r.available ? value + '@ is free' : value + '@ is taken';
      } catch (err) { hint.textContent = (err && err.detail) ? err.detail : 'that will not work'; }
    }, 300);
  });

  main.querySelector('[data-addrsave]').addEventListener('click', async () => {
    try {
      await api('/household/handle', { method: 'PUT', json: { handle: field.value.trim().toLowerCase() } });
      dialog.close();
      flash('That is your family address now.');
      await render();
    } catch (err) { fail(err); }
  });
}

function watchDialog() {
  // The dialog element itself carries no layout class: .stack sets
  // display:flex, which would override the browser's dialog:not([open])
  // rule and leave it permanently on the page.
  return '<dialog data-watchdialog class="card" style="max-width:440px;padding:20px;border:1px solid var(--line)">'
    + '<div class="stack" style="gap:12px"><h2>Watch a page</h2>'
    + '<p class="muted" style="line-height:1.5">Only public pages, over https. Anything that needs a sign-in is '
    + 'refused \u2014 this reader holds no credentials at all.</p>'
    + '<label class="stack" style="gap:4px"><span class="sub">Page address</span>'
    + '<input data-wurl type="url" placeholder="https://\u2026" required></label>'
    + '<label class="stack" style="gap:4px"><span class="sub">Words to look for</span>'
    + '<input data-wlook type="text" placeholder="in stock" required></label>'
    + '<label class="stack" style="gap:4px"><span class="sub">Call it</span>'
    + '<input data-wlabel type="text" placeholder="Cool Air 1.5T AC" required></label>'
    + '<label class="stack" style="gap:4px"><span class="sub">Check every</span>'
    + '<select data-wevery><option value="1">hour</option><option value="6">6 hours</option>'
    + '<option value="24" selected>day</option><option value="168">week</option></select></label>'
    + '<div class="row" style="gap:8px;justify-content:flex-end">'
    + '<button type="button" class="btn ghost sm" data-wcancel>Cancel</button>'
    + '<button type="button" class="btn sm" data-wsave>Start watching</button></div></div></dialog>';
}

function wireWatches(main) {
  const dialog = main.querySelector('[data-watchdialog]');
  const open = main.querySelector('[data-addwatch]');
  if (open && dialog) open.addEventListener('click', () => dialog.showModal());
  const cancel = main.querySelector('[data-wcancel]');
  if (cancel) cancel.addEventListener('click', () => dialog.close());

  const save = main.querySelector('[data-wsave]');
  if (save) save.addEventListener('click', async () => {
    const body = {
      url: main.querySelector('[data-wurl]').value.trim(),
      look_for: main.querySelector('[data-wlook]').value.trim(),
      label: main.querySelector('[data-wlabel]').value.trim(),
      every_hours: Number(main.querySelector('[data-wevery]').value),
    };
    if (!body.url || !body.look_for || !body.label) { flash('Fill all three.'); return; }
    try {
      await api('/watches', { method: 'POST', json: body });
      dialog.close();
      flash('Watching. You will hear when it changes.');
      await render();
    } catch (err) { fail(err); }
  });

  main.querySelectorAll('[data-unwatch]').forEach((b) => b.addEventListener('click', async () => {
    try {
      await api('/watches/' + b.dataset.unwatch, { method: 'DELETE' });
      flash('Stopped.');
      await render();
    } catch (err) { fail(err); }
  }));
}

function mailboxesCard(mailboxes) {
  const rows = mailboxes.map((m) => '<div class="row" style="gap:10px;padding:9px 11px;background:var(--sunk);'
    + 'border:1px solid var(--line-soft);border-radius:7px">'
    + '<span class="grow"><span style="font-size:12.5px;font-weight:600">' + esc(m.email) + '</span>'
    + '<span class="sub">' + (m.needs_reconnect
      ? 'Not being read — Google will not refresh this any more.'
      : 'connected ' + esc(ago(m.connected_at))
        + (m.last_polled_at ? '  ·  last read ' + esc(ago(m.last_polled_at)) : '  ·  not read yet')
        + (m.backfill_done ? '' : '  ·  still catching up')
        // The brief says a mailbox has gone quiet; this is where it says why.
        + (m.last_error ? '  ·  ' + esc(m.last_error) : '')) + '</span></span>'
    + (m.needs_reconnect ? '<span class="tag red">reconnect</span>'
      : m.last_error ? '<span class="tag amber">stalled</span>'
      : '<span class="tag green">reading</span>')
    + '<button class="btn ghost sm" data-disconnect="' + esc(m.id) + '">Disconnect</button>'
    + '</div>').join('');

  return '<div class="card pad stack" style="gap:10px">'
    + '<div class="row wrap" style="gap:8px"><h2>Connected mailboxes</h2>'
    + '<span class="muted">read-only</span></div>'
    + '<p class="muted" style="line-height:1.55">FamilyOS asks for one permission, <b>gmail.readonly</b>, and reads '
    + 'only mail that looks like a school notice. It cannot send, change or label anything. The token is sealed with '
    + 'your household key, so erasing the household also ends this.</p>'
    + (rows || '<p class="muted">Nothing connected. Forwarding keeps working either way.</p>')
    + '<button class="btn sm" data-connectmail style="align-self:flex-start">Connect a Gmail account</button>'
    + '<p class="muted" style="line-height:1.45">While FamilyOS is in testing with Google, a connection lasts seven '
    + 'days and then asks to be reconnected. Your brief says so when it happens, rather than quietly reading nothing.</p>'
    + '</div>';
}

function exportCard() {
  return '<div class="card pad stack" style="gap:9px">'
    + '<h3>Take everything with you</h3>'
    + '<p class="muted" style="line-height:1.55">Every notice you can see, exactly as it arrived, with a page for each '
    + 'one saying what was read out of it and the words it came from — plus the same contents as JSON. Built for '
    + 'the download and never stored.</p>'
    + '<button class="btn ghost" data-export>Download everything</button>'
    + '</div>';
}

const WHERE_LABEL = {
  email: 'Email we did not match',
  whatsapp_group: 'A WhatsApp group',
  whatsapp_direct: 'A WhatsApp message',
  school_portal: 'The school portal',
  school_app: 'The school app',
  other_app: 'Another app',
  sms: 'A text message',
  paper: 'On paper',
  word_of_mouth: 'Somebody told us',
  unknown: 'We are not sure',
};

function gapsCard(summary, gaps) {
  const rate = summary.capture_rate === null || summary.capture_rate === undefined
    ? '—' : Math.round(summary.capture_rate * 100) + '%';
  const bars = summary.missed_by_where.map((w) =>
    '<div class="row" style="gap:10px;align-items:flex-start">'
    + '<span class="lead" aria-hidden="true">' + w.count + '</span>'
    + '<span class="grow"><span style="font-size:12.5px;font-weight:600">'
    + esc(WHERE_LABEL[w.lived_where] || w.lived_where) + '</span>'
    + '<span class="sub">' + esc(w.means)
    + (w.with_a_date ? '  ·  ' + w.with_a_date + ' asked for something by a date' : '')
    + (w.arrived_later ? '  ·  ' + w.arrived_later + ' turned up later' : '') + '</span></span></div>').join('');

  return '<div class="card pad stack" style="gap:11px">'
    + '<div class="row wrap" style="gap:8px"><h2>What did not arrive</h2>'
    + '<span class="muted">' + summary.captured + ' in, ' + summary.missed_reported + ' missed</span></div>'
    + '<p class="muted" style="line-height:1.55">Capture <b style="color:var(--ink)">' + rate + '</b>. '
    + esc(summary.caveat) + '</p>'
    + (bars ? '<div class="stack" style="gap:9px">' + bars + '</div>'
      : '<p class="muted">Nothing reported missing. If something never reaches here, say so — where it '
        + 'actually lived is what decides what gets built next.</p>')
    + '<button class="btn ghost sm" data-reportgap style="align-self:flex-start">Report a missed notice</button>'
    + (gaps.length
      ? '<details><summary class="muted" style="cursor:pointer;font-size:12px">' + gaps.length
        + ' report' + (gaps.length === 1 ? '' : 's') + '</summary><div class="stack" style="gap:6px;padding-top:9px">'
        + gaps.map((g) => '<div class="row" style="gap:8px">'
          + '<span class="grow"><span style="font-size:12.5px">' + esc(g.title) + '</span>'
          + '<span class="sub">' + esc(WHERE_LABEL[g.lived_where] || g.lived_where)
          + '  ·  ' + esc(memberName(g.reported_by) || 'a member')
          + '  ·  ' + esc(ago(g.created_at)) + '</span></span>'
          + (g.arrived_as ? '<span class="tag green">turned up</span>' : '') + '</div>').join('')
        + '</div></details>'
      : '')
    + '</div>';
}

function gapDialog() {
  const options = Object.keys(WHERE_LABEL)
    .map((k) => '<option value="' + k + '">' + esc(WHERE_LABEL[k]) + '</option>').join('');
  return '<dialog class="card" data-gap style="max-width:460px;padding:20px;border:1px solid var(--line)">'
    + '<form class="stack" data-form="gap"><h2>Something never reached here</h2>'
    + '<p class="muted" style="line-height:1.55">This is counted, not read: it never becomes a task or a date, '
    + 'because what you type here is from memory and FamilyOS only records what it can point at in a document. '
    + 'Where it lived is the useful part.</p>'
    + '<label>What was it?<input type="text" name="title" required maxlength="300" '
    + 'placeholder="The swimming letter"></label>'
    + '<label>Where did it actually live?<select name="lived_where">' + options + '</select></label>'
    + '<label>Was it emailed as well?<select name="also_emailed">'
    + '<option value="">Not sure</option><option value="no">No</option><option value="yes">Yes</option>'
    + '</select></label>'
    + '<label class="row" style="gap:8px;align-items:center"><input type="checkbox" name="had_date" '
    + 'style="width:auto">It asked for something by a date</label>'
    + '<label>When did you find out? (optional)<input type="date" name="noticed_on"></label>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn ghost" type="button" data-close-gap>Cancel</button>'
    + '<button class="btn" type="submit">Report it</button></div></form></dialog>';
}

async function download(path, fallbackName) {
  flash('Building it…');
  const blob = await api(path, { blob: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoked straight away: the whole household is in that blob.
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  flash('Downloaded.');
}

function wireConnections(main) {
  const connect = main.querySelector('[data-connectmail]');
  if (connect) connect.addEventListener('click', async () => {
    try {
      const begun = await api('/google/mailboxes/authorize', { method: 'POST' });
      // Same tab: Google sends them back to the callback, which returns here.
      location.href = begun.url;
    } catch (err) { fail(err); }
  });

  main.querySelectorAll('[data-disconnect]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Stop reading this mailbox? The stored token is overwritten and Google is told.')) return;
    try {
      await api('/google/mailboxes/' + b.dataset.disconnect + '/disconnect', { method: 'POST' });
      flash('Disconnected.');
      await render();
    } catch (err) { fail(err); }
  }));

  const exp = main.querySelector('[data-export]');
  if (exp) exp.addEventListener('click', async () => {
    try {
      await download('/export', 'familyos-export.zip');
    } catch (err) { fail(err); }
  });
}

function wireGaps(main) {
  const dlg = main.querySelector('dialog[data-gap]');
  if (!dlg) return;
  main.querySelectorAll('[data-reportgap]').forEach((b) =>
    b.addEventListener('click', () => dlg.showModal()));
  dlg.querySelector('[data-close-gap]').addEventListener('click', () => dlg.close());
  dlg.querySelector('form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const also = f.get('also_emailed');
    const body = {
      title: f.get('title'),
      lived_where: f.get('lived_where'),
      had_date: f.get('had_date') === 'on',
    };
    if (also) body.also_emailed = also === 'yes';
    if (f.get('noticed_on')) body.noticed_on = f.get('noticed_on');
    try {
      await api('/intake-gaps', { method: 'POST', json: body });
      dlg.close();
      ev.target.reset();
      flash('Logged. Where it lived is what decides what gets built next.');
      await render();
    } catch (err) { fail(err); }
  });
}

/* ── household ────────────────────────────────────────────────── */

/* ── collect: an assisted harvest ──────────────────────────────── */

async function collectView(main) {
  const open = (await api('/harvests').catch(() => []))[0];
  if (!open) { main.innerHTML = collectStart(); wireCollectStart(main); return; }

  const candidates = await api('/harvests/' + open.id + '/candidates').catch(() => []);
  main.innerHTML = '<div class="head"><div><h1>' + esc(open.label) + '</h1>'
    + '<p>You sign in yourself. FamilyOS never sees your password, and keeps nothing '
    + 'when you are done but the pages you pick.</p></div>'
    + '<button class="btn ghost" data-finish="' + esc(open.id) + '">Finish</button></div>'
    + (open.live_url
      ? '<section class="card pad stack" style="gap:10px"><div class="row wrap" style="gap:8px">'
        + '<h2>The browser</h2><span class="muted">' + esc(open.allow_hosts.join(', ')) + ' only</span></div>'
        + '<iframe src="' + esc(open.live_url) + '" title="The browser for this sitting" '
        + 'style="width:100%;height:460px;border:1px solid var(--line);border-radius:8px;background:#000"></iframe>'
        + '<p class="muted">Sign in and move around. Every page is checked against the site above before '
        + 'it can be collected.</p></section>'
      : (open.ws_url && /^http:\/\/127\.0\.0\.1/.test(open.ws_url)
        ? '<section class="card pad stack" style="gap:8px"><h2>A window opened on the Mac running FamilyOS</h2>'
          + '<p class="muted">Sign in there, in that window, then press Finish here. It is the family\u2019s own browser: '
          + 'its own address, nothing rented. Only ' + esc(open.allow_hosts.join(', ')) + ' is kept.</p></section>'
        : '<section class="card pad stack" style="gap:8px"><h2>No browser on this deployment</h2>')
        + '<p class="muted">Pages have to be handed in some other way. The sitting still keeps only what '
        + 'you pick.</p></section>')
    + '<div style="height:12px"></div>'
    + candidatesCard(open, candidates);

  wireCollect(main, open);
}

function collectStart() {
  return '<div class="head"><div><h1>Collect from a site</h1>'
    + '<p>For a site that has no other way in \u2014 a school portal, a utility account. '
    + 'One sitting: you sign in, pages are collected for you to read, and nothing is kept '
    + 'afterwards but what you pick.</p></div></div>'
    + '<section class="card pad stack" style="gap:12px;max-width:520px">'
    + '<label class="stack" style="gap:4px"><span class="sub">What is this for</span>'
    + '<input data-hlabel type="text" placeholder="School portal circulars"></label>'
    + '<label class="stack" style="gap:4px"><span class="sub">The site</span>'
    + '<input data-hhost type="text" placeholder="portal.school.edu.in"></label>'
    + '<label class="stack" style="gap:4px"><span class="sub">How long you need</span>'
    + '<select data-hmins><option value="30">30 minutes</option>'
    + '<option value="90" selected>an hour and a half</option>'
    + '<option value="240">four hours</option></select></label>'
    + '<p class="muted" style="line-height:1.5">FamilyOS takes no password and stores no session. '
    + 'When the sitting ends the browser is gone.</p>'
    + '<button class="btn" data-hstart style="align-self:flex-start">Open the sitting</button></section>';
}

function candidatesCard(open, candidates) {
  if (!candidates.length) {
    return '<section class="card pad stack" style="gap:8px"><h2>Nothing collected yet</h2>'
      + '<p class="muted">Pages you visit are offered here for you to read and choose from.</p></section>';
  }
  // Grouped by the first path segment: keeping "everything under /circulars"
  // in one tap is realistic, and ticking three hundred boxes is not.
  const groups = {};
  candidates.forEach((c) => {
    let key = 'elsewhere';
    try { key = (new URL(c.url).pathname.split('/').filter(Boolean)[0]) || 'top level'; } catch (e) { /* keep */ }
    (groups[key] = groups[key] || []).push(c);
  });

  return '<section class="card pad stack" style="gap:12px">'
    + '<div class="row wrap" style="gap:8px"><h2>' + candidates.length + ' collected</h2>'
    + '<span class="muted">nothing here is in your notices yet</span></div>'
    + Object.keys(groups).sort().map((key) =>
      '<div class="stack" style="gap:7px">'
      + '<div class="row wrap" style="gap:8px"><span style="font-size:12.5px;font-weight:600">/'
      + esc(key) + '</span><span class="muted">' + groups[key].length + '</span>'
      + '<span class="grow"></span>'
      + '<button class="btn ghost sm" data-keepgroup="' + esc(key) + '">Keep all</button>'
      + '<button class="btn ghost sm" data-dropgroup="' + esc(key) + '">Discard all</button></div>'
      + groups[key].map((c) =>
        '<div class="row" style="gap:10px;padding:9px 11px;background:var(--sunk);'
        + 'border:1px solid var(--line-soft);border-radius:7px;align-items:flex-start" data-group="' + esc(key) + '">'
        + '<span class="grow"><span style="font-size:12.5px;font-weight:600">' + esc(c.title || c.url) + '</span>'
        + '<span class="sub mono" style="font-size:11px">' + esc(c.url) + '</span>'
        + '<span class="sub" style="opacity:.9">' + esc((c.text || '').slice(0, 180)) + '\u2026</span></span>'
        + '<button class="btn sm" data-keep="' + esc(c.id) + '">Keep</button>'
        + '<button class="btn ghost sm" data-drop="' + esc(c.id) + '">Discard</button></div>').join('')
      + '</div>').join('')
    + '</section>';
}

function wireCollectStart(main) {
  const go = main.querySelector('[data-hstart]');
  if (!go) return;
  go.addEventListener('click', async () => {
    const label = main.querySelector('[data-hlabel]').value.trim();
    const host = main.querySelector('[data-hhost]').value.trim().toLowerCase().replace(/^https?:\/\//, '').split('/')[0];
    if (!label || !host) { flash('Name it, and say which site.'); return; }
    try {
      await api('/harvests', { method: 'POST', json: {
        label, allow_hosts: [host], minutes: Number(main.querySelector('[data-hmins]').value) } });
      await render();
    } catch (err) { fail(err); }
  });
}

function wireCollect(main, open) {
  const act = async (fn) => { try { await fn(); await render(); } catch (err) { fail(err); } };

  main.querySelectorAll('[data-keep]').forEach((b) => b.addEventListener('click', () =>
    act(() => api('/harvest-candidates/' + b.dataset.keep + '/keep', { method: 'POST' }))));
  main.querySelectorAll('[data-drop]').forEach((b) => b.addEventListener('click', () =>
    act(() => api('/harvest-candidates/' + b.dataset.drop, { method: 'DELETE' }))));

  const group = (attr, run) => main.querySelectorAll('[' + attr + ']').forEach((b) =>
    b.addEventListener('click', () => act(async () => {
      const rows = main.querySelectorAll('[data-group="' + b.dataset[attr === 'data-keepgroup' ? 'keepgroup' : 'dropgroup'] + '"]');
      for (const row of rows) {
        const id = (row.querySelector('[data-keep]') || {}).dataset;
        if (id && id.keep) await run(id.keep);
      }
    })));
  group('data-keepgroup', (id) => api('/harvest-candidates/' + id + '/keep', { method: 'POST' }));
  group('data-dropgroup', (id) => api('/harvest-candidates/' + id, { method: 'DELETE' }));

  const finish = main.querySelector('[data-finish]');
  if (finish) finish.addEventListener('click', () => act(async () => {
    if (!confirm('End the sitting? Anything you have not kept goes now.')) return;
    await api('/harvests/' + finish.dataset.finish + '/finish', { method: 'POST' });
  }));
}

async function householdView(main) {
  const [household, consents, mySessions, mailboxes, summary, gaps, watches, signedIn, sitesOffered, openSitting] = await Promise.all([
    api('/household'), api('/consents'), api('/sessions'),
    api('/google/mailboxes'), api('/intake-gaps/summary'), api('/intake-gaps'),
    // Off on some deployments; the card simply does not appear then.
    api('/watches').catch(() => []),
    api('/signed-in').catch(() => []), api('/sites').catch(() => []), api('/sign-ins/open').catch(() => null),
  ]);
  store.household = household;
  store.mailboxes = mailboxes;
  const isGuardian = store.me.role === 'guardian';
  const children = (household.members || []).filter((m) => m.role === 'child');
  const active = (id) => consents.find((c) => c.subject_member_id === id && !c.withdrawn_at);

  main.innerHTML = '<div class="head"><div><h1>' + esc(household.name) + '</h1>'
    + '<p>Guardians manage the household and consent for the children. Children are not accounts and do not sign in.</p></div>'
    + (isGuardian ? '<button class="btn" data-addmember>Add a member</button>' : '') + '</div>'
    + '<div class="split"><div class="stack">'
    + '<div class="card list" data-members></div>'
    + '<div class="card pad stack" data-consent></div>'
    + rulesCard()
    + documentsCard()
    + weeklyDigestCard()
    + signedInCard(signedIn, sitesOffered, openSitting)
    + sessionsCard(mySessions)
    + exportCard()
    + (isGuardian ? dangerCard(household) : '')
    + '</div><div class="stack">'
    + mailboxesCard(mailboxes)
    + telegramCard(household)
    + phoneCard()
    + watchesCard(watches)
    + gapsCard(summary, gaps)
    + '</div></div>'
    + memberDialog()
    + watchDialog()
    + gapDialog();

  wireDigest(main);
  wireRules(main);
  wireDocuments(main);
  wirePhone(main);
  wireSignedIn(main);
  wireTelegram(main);
  main.querySelector('[data-members]').innerHTML = (household.members || []).map((m) => {
    const tone = m.role === 'guardian' ? 'blue' : m.role === 'child' ? 'green' : '';
    const c = active(m.id);
    return '<div class="item" style="cursor:default">'
      + '<span class="glyph ' + tone + '">' + esc(initial(m.display_name)) + '</span>'
      + '<span class="grow"><span class="row wrap" style="gap:8px"><span class="title">' + esc(m.display_name) + '</span>'
      + '<span class="tag ' + tone + '">' + esc(m.role) + '</span>'
      + (m.id === store.me.id ? '<span class="tag line">you</span>' : '') + '</span>'
      + '<span class="sub">' + esc(m.email || 'no account — a data subject only')
      + (m.date_of_birth ? '  ·  born ' + esc(date(m.date_of_birth)) + ' (' + ageOf(m.date_of_birth) + ')' : '')
      + (store.me && (store.me.role === 'guardian' || store.me.id === m.id) ? ' <button class="btn ghost sm" data-birthday="' + esc(m.id) + '" data-dob="' + esc(m.date_of_birth || '') + '">' + (m.date_of_birth ? 'change' : 'birthday') + '</button>' : '')
      // The key circulars are addressed by. Without it, a notice that says
      // "Grade 4" or just "Dear Parents" attaches to nobody.
      + (m.role === 'child'
        ? '  ·  ' + (m.school || m.class_label
          ? esc([m.school, m.class_label ? 'class ' + m.class_label : ''].filter(Boolean).join(', '))
          : 'no school set — circulars cannot find this child')
        : '')
      + '</span></span>'
      + (m.role === 'child'
        ? (c ? '<span class="tag kid">consented</span>' : '<span class="tag red">no consent</span>') : '')
      + (m.role === 'child' && isGuardian
        ? '<button class="btn ghost sm" data-school="' + esc(m.id) + '" data-schoolnow="' + esc(m.school || '')
          + '" data-classnow="' + esc(m.class_label || '') + '">' + (m.school || m.class_label ? 'School' : 'Set school') + '</button>' : '')
      + (m.role === 'child' && isGuardian
        ? '<button class="btn danger sm" data-erase="' + esc(m.id) + '">Erase</button>' : '')
      + (m.role !== 'child' && (isGuardian || m.id === store.me.id)
        ? '<button class="btn ghost sm" data-signoutall="' + esc(m.id) + '">Sign out everywhere</button>' : '')
      + '</div>';
  }).join('');

  const cbox = main.querySelector('[data-consent]');
  cbox.innerHTML = '<div class="row wrap" style="gap:9px"><h2>Consent for the children</h2>'
    + '<span class="muted">DPDP Act 2023, s.9 · kept as evidence even after it ends</span></div>'
    + (children.length ? '<div class="stack" style="gap:8px" data-crows></div>'
      : '<p class="muted">No children in this household yet.</p>')
    + '<p class="muted" style="padding:11px 13px;background:var(--red-tint);border-radius:7px;color:var(--red-ink);line-height:1.55">'
    + 'Withdrawing consent starts an erasure in the same transaction. Every notice naming that child goes, along with '
    + 'anything read from it. The consent record itself stays, as proof it existed and ended.</p>';

  if (children.length) {
    cbox.querySelector('[data-crows]').innerHTML = children.map((m) => {
      const c = active(m.id);
      return '<div class="row card" style="gap:12px;padding:11px 13px;background:var(--sunk)">'
        + '<span class="glyph green" style="width:30px;height:30px;border-radius:15px">' + esc(initial(m.display_name)) + '</span>'
        + '<span class="grow"><span style="font-size:13.5px;font-weight:600">' + esc(m.display_name) + '</span>'
        + '<span class="sub">' + (c
          ? 'by ' + esc(memberName(c.guardian_member_id) || 'a guardian') + '  ·  verified as '
            + esc(c.verification_method) + '  ·  notice ' + esc(c.notice_version) + '  ·  ' + esc(date(c.granted_at))
          : 'Nothing may name this child until a guardian consents.') + '</span></span>'
        + (c ? '<span class="tag green">active</span>' : '')
        + (isGuardian
          ? (c ? '<button class="btn danger sm" data-withdraw="' + esc(c.id) + '">Withdraw</button>'
            : '<button class="btn sm" data-grant="' + esc(m.id) + '">Record consent</button>') : '')
        + '</div>';
    }).join('');
  }

  wireHousehold(main, household);
  wireConnections(main);
  wireWatches(main);
  wireGaps(main);

  // The Google callback returns to #/household?mailbox=..., which is the only
  // place the result of leaving the app can be reported.
  const said = hashQuery().get('mailbox');
  if (said) {
    history.replaceState(null, '', '#/household');
    if (said === 'connected') flash('Mailbox connected. School mail in it will start arriving.');
    else if (said === 'cancelled') flash('Not connected \u2014 nothing was shared.');
    else flash('That did not connect. Nothing was stored; try again.', true);
  }
}

/* Sites the member is signed in to, for FamilyOS to act on -- a booking on
   a site with no API. The sign-in is theirs, in a browser they watch; what
   is kept is sealed, and nothing of it is shown here but the name and the
   dates. */
function signedInCard(signedIn, offered, openSitting) {
  const rows = (signedIn || []).map((x) => '<div class="row" style="gap:10px;padding:9px 11px;background:var(--sunk);border:1px solid var(--line-soft);border-radius:7px">'
    + '<span class="grow"><b style="font-size:12.5px">' + esc(x.label) + '</b><span class="sub">signed in ' + esc(ago(x.created_at)) + ' · until ' + esc(fmtDate(String(x.expires_at).slice(0, 10)))
    + (x.uses ? ' · used ' + x.uses + '×' : ' · not used yet') + '</span></span>'
    + '<button class="btn ghost sm" data-signout-site="' + esc(x.id) + '">Sign out</button></div>').join('');
  const have = new Set((signedIn || []).map((x) => x.service));
  const offers = (offered || []).map((o) => '<button class="btn sm' + (have.has(o.service) ? ' ghost' : '') + '" data-signin-site="' + esc(o.service) + '">'
    + (have.has(o.service) ? 'Sign in again to ' : 'Sign in to ') + esc(o.label) + '</button>').join('');
  return '<section class="card pad stack" data-signedin style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Signed-in sites</h2>'
    + '<span class="muted">for bookings on sites with no API</span></div>'
    + '<p class="muted" style="font-size:13px;line-height:1.5;margin:0">You sign in yourself, in a browser you watch. FamilyOS never sees the password or the OTP. '
    + 'What the browser holds for that site is sealed under the household key and opened only for a task you approved; sign out here and it is gone.</p>'
    + (openSitting ? '<a class="btn" href="#/sign-in" style="align-self:flex-start;text-decoration:none">A sign-in to ' + esc(openSitting.label) + ' is open →</a>' : '')
    + (rows ? '<div class="stack" style="gap:8px">' + rows + '</div>' : '<p class="muted" style="font-size:12.5px">Nothing signed in.</p>')
    + '<div class="row wrap" style="gap:8px">' + offers + '</div></section>';
}

function wireSignedIn(main) {
  const box = main.querySelector('[data-signedin]');
  if (!box) return;
  box.querySelectorAll('[data-signin-site]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/sign-ins', { method: 'POST', json: { service: b.dataset.signinSite } }); go('/sign-in'); }
    catch (err) { fail(err); }
  }));
  box.querySelectorAll('[data-signout-site]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/signed-in/' + b.dataset.signoutSite, { method: 'DELETE' }); flash('Signed out. The session is gone.'); await render(); }
    catch (err) { fail(err); }
  }));
}

/* ── errands: a booking or purchase on a signed-in site ───────────────── */
const ERRAND_STATUS = { proposed: 'waiting for approval', approved: 'approved', running: 'running', needs_you: 'needs you', done: 'done', stopped: 'stopped', failed: 'failed', cancelled: 'cancelled' };
const ERRAND_TONE = { proposed: 'amber', approved: 'blue', running: 'blue', needs_you: 'amber', done: 'green', stopped: 'red', failed: 'red', cancelled: '' };

function errandLine(e) {
  const sp = e.spec || {};
  return '<a class="card pad lift" href="#/errands/' + esc(e.id) + '" style="text-decoration:none;color:inherit">'
    + '<div class="row wrap" style="gap:8px;justify-content:space-between"><h2 style="margin:0">' + esc(e.title) + '</h2>'
    + '<span class="tag ' + (ERRAND_TONE[e.status] || '') + '">' + esc(ERRAND_STATUS[e.status] || e.status) + '</span></div>'
    + '<p class="muted" style="margin:6px 0 0">' + esc((sp.where && sp.where.service) || e.service) + (sp.when && sp.when.date ? ' · ' + esc(fmtDate(sp.when.date)) + (sp.when.part !== 'any' ? ' ' + esc(sp.when.part) : '') : '')
    + (sp.limits ? ' · at most ' + esc(money(sp.limits.max_amount, sp.limits.currency)) : '') + '</p></a>';
}

async function errandsView(main) {
  main.classList.remove('chat-main');
  const list = await api('/errands').catch(() => []);
  main.innerHTML = '<div class="head"><div><h1>Errands</h1>'
    + '<p>A booking or a purchase on a site you are signed in to, written down in full before anything happens \u2014 what, when, the most it may cost, how it is paid \u2014 and approved by a guardian against exactly that. '
    + 'Paid after the service, or by a UPI request on your own phone. FamilyOS holds no card.</p></div>'
    + '<a class="btn" href="#/chat" style="text-decoration:none">Ask for one</a></div>'
    + (list.length ? '<div class="stack" style="gap:10px">' + list.map(errandLine).join('') + '</div>'
      : '<section class="card pad"><p class="muted">Nothing yet. In Ask, say something like “book a kitchen deep clean on Urban Company Saturday morning, under ₹3,000”.</p></section>');
}

async function errandView(main, args) {
  main.classList.remove('chat-main');
  const e = await api('/errands/' + args[0]);
  const sp = e.spec || {};
  const isGuardian = store.me && store.me.role === 'guardian';
  const row = (k, v) => '<div class="row" style="gap:12px;align-items:flex-start"><span class="muted" style="width:120px;flex-shrink:0">' + k + '</span><span>' + v + '</span></div>';
  const stops = Object.entries(sp.stop_rules || {}).map(([k, v]) => '<span class="tag ' + (v === 'stop' ? 'red' : 'amber') + '" style="text-transform:none;letter-spacing:0">' + esc(k.replace(/_/g, ' ')) + ' → ' + esc(v === 'needs_you' ? 'needs you' : v) + '</span>').join(' ');
  main.innerHTML = '<div class="head"><div><p class="muted" style="margin-bottom:6px"><a href="#/errands" style="color:var(--ink-3);text-decoration:none">Errands</a></p>'
    + '<h1>' + esc(e.title) + '</h1>'
    + '<p class="row wrap" style="gap:8px;margin-top:8px"><span class="tag ' + (ERRAND_TONE[e.status] || '') + '">' + esc(ERRAND_STATUS[e.status] || e.status) + '</span>'
    + '<span class="muted">' + esc(e.kind) + ' on ' + esc((sp.where && sp.where.service) || e.service) + ' · asked by ' + esc(memberName(e.created_by) || 'someone') + '</span>'
    + (e.approved_by ? '<span class="muted">· approved by ' + esc(memberName(e.approved_by) || 'a guardian') + '</span>' : '') + '</p></div>'
    + '<div class="row" style="gap:8px">'
    + (e.status === 'proposed' && isGuardian ? '<button class="btn" data-approve>Approve exactly this</button>' : '')
    + (['proposed', 'approved', 'needs_you'].includes(e.status) ? '<button class="btn ghost" data-cancel>Cancel</button>' : '')
    + '</div></div>'
    + '<div class="home"><div class="stack" style="gap:16px">'
    + '<section class="card pad stack" style="gap:10px"><h2>What was written down</h2>'
    + row('What', '<b>' + esc(sp.what || '') + '</b>' + (sp.details ? '<br><span class="muted">' + esc(sp.details) + '</span>' : ''))
    + row('When', sp.when && sp.when.date ? esc(fmtDate(sp.when.date)) + (sp.when.time ? ' at ' + esc(sp.when.time) : sp.when.part !== 'any' ? ', ' + esc(sp.when.part) : '') : 'any time' + (sp.when && sp.when.by ? ', by ' + esc(fmtDate(sp.when.by)) : ''))
    + row('Where', esc((sp.where && sp.where.address) || 'the saved home address') + ' · ' + esc(((sp.where && sp.where.hosts) || []).join(', ')))
    + row('At most', '<b>' + esc(money(sp.limits ? sp.limits.max_amount : 0, sp.limits ? sp.limits.currency : 'INR')) + '</b>, one of it')
    + row('Paid', sp.payment && sp.payment.mode === 'upi_request' ? 'by a UPI request you approve on your phone' : 'after the service, from the invoice that lands in the Inbox')
    + row('Card', 'none — FamilyOS holds no card, PIN or password')
    + row('Stops if', '<span class="row wrap" style="gap:6px">' + stops + '</span>')
    + '<p class="muted" style="font-size:12px">Fingerprint <span class="mono">' + esc(e.params_sha256.slice(0, 16)) + '…</span>. Approval is of exactly this; if anything about it changes, the approval no longer applies.</p>'
    + '</section>'
    + (e.status === 'approved' ? '<section class="card pad"><h2>Approved</h2><p class="muted">Starting in a fresh browser with your sealed ' + esc(e.service) + ' session. Steps appear below as they happen.</p></section>' : '')
    + (e.status === 'running' ? '<section class="card pad"><h2 class="row" style="gap:10px"><span class="dots"><i></i><i></i><i></i></span> Running</h2><p class="muted">Every step is written here with a picture. If it cannot tell what to do next, it stops and hands you the browser.</p></section>' : '')
    + (e.status === 'needs_you' ? '<section class="card pad stack" style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Your turn</h2><span class="muted" data-live-status>connecting\u2026</span>'
        + '<button class="btn" data-finish style="margin-left:auto">Finished \u2014 it\u2019s booked</button></div>'
        + '<p class="muted">' + esc((e.outcome && e.outcome.steps && e.outcome.steps.length) ? e.outcome.steps[e.outcome.steps.length - 1].said : 'Finish from here.') + '</p>'
        + '<div class="live" data-live tabindex="0"><canvas></canvas><textarea class="live-keys" aria-label="Type into the page" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false"></textarea></div></section>' : '')
    + ((e.outcome && e.outcome.slots && e.outcome.slots.length) ? '<section class="card pad"><h2>Slots seen</h2><p class="row wrap" style="gap:6px;margin-top:8px">' + e.outcome.slots.map((t) => '<span class="tag line" style="text-transform:none;letter-spacing:0">' + esc(t) + '</span>').join('') + '</p>' + (e.outcome.total ? '<p class="muted" style="margin-top:8px">Total on the page: ' + esc(money(e.outcome.total, 'INR')) + '</p>' : '') + '</section>' : '')
    + (e.error ? '<section class="card pad"><h2>What went wrong</h2><p class="muted" style="color:var(--red)">' + esc(e.error) + '</p></section>' : '')
    + ((e.outcome && e.outcome.steps && e.outcome.steps.length) ? '<section class="card pad stack" style="gap:10px"><h2>The run</h2>' + e.outcome.steps.map((st, i) => '<div class="stack" style="gap:6px"><div class="row" style="gap:10px;align-items:flex-start"><span class="muted" style="width:28px;flex-shrink:0">' + (i + 1) + '</span><span>' + esc(st.said || '') + '<br><span class="muted" style="font-size:11.5px">' + esc(st.at ? ago(st.at) : '') + '</span></span></div>'
      + (st.artifact_id ? '<img alt="step ' + (i + 1) + '" data-shot="' + esc(st.artifact_id) + '" style="width:100%;max-width:640px;border:1px solid var(--line);border-radius:8px;margin-left:38px">' : '') + '</div>').join('') + '</section>' : '')
    + '</div><aside class="stack" style="gap:14px">'
    + '<section class="card rail-card"><h2>How it runs</h2><p class="muted">In a fresh browser holding your sealed ' + esc((sp.where && sp.where.service) || e.service) + ' session, for the length of the run only. Every page it reaches is checked against the site’s own hosts. A screenshot is kept at each step. If a rule stops it, it stops and says why; if it needs you, you get the browser.</p></section>'
    + '</aside></div>';
  const approve = main.querySelector('[data-approve]');
  if (approve) approve.addEventListener('click', async () => {
    try { await api('/errands/' + e.id + '/approve', { method: 'POST', json: { params_sha256: e.params_sha256 } }); flash('Approved exactly this.'); render(); }
    catch (err) { fail(err); }
  });
  const cancel = main.querySelector('[data-cancel]');
  if (cancel) cancel.addEventListener('click', async () => {
    try { await api('/errands/' + e.id + '/cancel', { method: 'POST' }); flash('Cancelled.'); render(); } catch (err) { fail(err); }
  });
  const finish = main.querySelector('[data-finish]');
  if (finish) finish.addEventListener('click', async () => {
    try { await api('/errands/' + e.id + '/finish', { method: 'POST' }); flash('Done. The browser is released.'); render(); } catch (err) { fail(err); }
  });
  // The pictures: fetched with the token, since an <img> cannot carry one.
  main.querySelectorAll('img[data-shot]').forEach(async (img) => {
    try { const blob = await api('/artifacts/' + img.dataset.shot + '/original', { blob: true }); img.src = URL.createObjectURL(blob); } catch (err) { img.remove(); }
  });
  if (e.status === 'needs_you') liveView(main.querySelector('[data-live]'), main.querySelector('[data-live-status]'), e.id, '/errands/');
  if (e.status === 'approved' || e.status === 'running') {
    const here = location.hash;
    const poll = async () => {
      if (location.hash !== here) return;
      let now = null; try { now = await api('/errands/' + e.id); } catch (err) { /* next time */ }
      if (now && (now.status !== e.status || (now.outcome && now.outcome.steps || []).length !== (e.outcome && e.outcome.steps || []).length)) { render(); return; }
      setTimeout(poll, 3000);
    };
    setTimeout(poll, 3000);
  }
}

/* The live view: the page as a picture, over the browser's own debugging
   socket -- a screencast one way, clicks and keys the other. Nothing of the
   page passes through the server; the member's browser talks to the
   sitting's browser directly, and the socket is closed when they leave. */
function liveView(box, status, sittingId, base) {
  const canvas = box.querySelector('canvas');
  const keys = box.querySelector('.live-keys');
  const ctx = canvas.getContext('2d');
  const here = location.hash;
  let ws = null, nextId = 1, session = null, size = { w: 1280, h: 800 };
  const img = new Image();
  const say = (t) => { if (status) status.textContent = t; };
  const waiting = {};
  const send = (method, params, sid) => {
    if (!ws || ws.readyState !== 1) return 0;
    const m = { id: nextId++, method, params: params || {} };
    if (sid || session) m.sessionId = sid || session;
    ws.send(JSON.stringify(m));
    return m.id;
  };
  const ask = (method, params, sid) => new Promise((resolve) => { const id = send(method, params, sid); if (id) waiting[id] = resolve; else resolve(null); });
  const stop = () => { if (ws) { try { ws.close(); } catch (e) { /* gone */ } ws = null; } };
  const alive = () => location.hash === here && document.body.contains(box);
  const tick = setInterval(() => { if (!alive()) { clearInterval(tick); stop(); } }, 1000);

  const scale = (ev) => {
    const r = canvas.getBoundingClientRect();
    return { x: Math.round((ev.clientX - r.left) * (size.w / r.width)), y: Math.round((ev.clientY - r.top) * (size.h / r.height)) };
  };
  const mouse = (type, ev, extra) => {
    const p = scale(ev);
    send('Input.dispatchMouseEvent', Object.assign({ type, x: p.x, y: p.y, button: 'left', clickCount: 1, modifiers: 0 }, extra || {}));
  };
  canvas.addEventListener('mousedown', (ev) => { ev.preventDefault(); keys.focus(); mouse('mousePressed', ev); });
  canvas.addEventListener('mouseup', (ev) => { ev.preventDefault(); mouse('mouseReleased', ev); });
  canvas.addEventListener('mousemove', (ev) => { if (ev.buttons) mouse('mouseMoved', ev); });
  canvas.addEventListener('wheel', (ev) => { ev.preventDefault(); mouse('mouseWheel', ev, { deltaX: ev.deltaX, deltaY: ev.deltaY, button: 'none' }); }, { passive: false });
  canvas.addEventListener('touchstart', (ev) => { const t = ev.touches[0]; if (t) { keys.focus(); mouse('mousePressed', t); } }, { passive: true });
  canvas.addEventListener('touchend', (ev) => { const t = ev.changedTouches[0]; if (t) mouse('mouseReleased', t); }, { passive: true });
  const CODES = { Enter: 13, Backspace: 8, Tab: 9, Escape: 27, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, Delete: 46 };
  keys.addEventListener('keydown', (ev) => {
    if (!(ev.key in CODES)) return;
    ev.preventDefault();
    const base = { key: ev.key, code: ev.code, windowsVirtualKeyCode: CODES[ev.key], nativeVirtualKeyCode: CODES[ev.key] };
    send('Input.dispatchKeyEvent', Object.assign({ type: 'keyDown' }, base, ev.key === 'Enter' ? { text: '\r', unmodifiedText: '\r' } : {}));
    send('Input.dispatchKeyEvent', Object.assign({ type: 'keyUp' }, base));
  });
  keys.addEventListener('input', () => { const text = keys.value; keys.value = ''; if (text) send('Input.insertText', { text }); });
  keys.addEventListener('paste', (ev) => { const t = (ev.clipboardData || window.clipboardData).getData('text'); if (t) { ev.preventDefault(); send('Input.insertText', { text: t }); } });

  img.onload = () => { if (canvas.width !== img.width || canvas.height !== img.height) { canvas.width = img.width; canvas.height = img.height; } ctx.drawImage(img, 0, 0); };
  // Through this server, on a one-time ticket: an https page may not open a
  // plain socket, and a phone cannot reach the browser's at all.
  api((base || '/sign-ins/') + sittingId + '/live-ticket', { method: 'POST' }).then((t) => {
    try { ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + t.path); } catch (e) { say('could not reach the browser'); return; }
    wire();
  }).catch((err) => say(err.message));
  function wire() {
  ws.onopen = async () => {
    say('finding the page…');
    const targets = await ask('Target.getTargets');
    const page = ((targets && targets.targetInfos) || []).find((t) => t.type === 'page' && !/^(devtools|chrome):/.test(t.url));
    if (!page) { say('no page is open in the browser'); return; }
    const att = await ask('Target.attachToTarget', { targetId: page.targetId, flatten: true });
    session = att && att.sessionId;
    if (!session) { say('could not attach to the page'); return; }
    await ask('Page.enable');
    send('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: 1280, maxHeight: 800, everyNthFrame: 1 });
    say('live');
  };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.id && waiting[m.id]) { const r = waiting[m.id]; delete waiting[m.id]; r(m.result || null); return; }
    if (m.method === 'Page.screencastFrame') {
      const md = m.params.metadata || {};
      if (md.deviceWidth && md.deviceHeight) size = { w: md.deviceWidth, h: md.deviceHeight };
      img.src = 'data:image/jpeg;base64,' + m.params.data;
      send('Page.screencastFrameAck', { sessionId: m.params.sessionId }, m.sessionId);
    }
  };
  ws.onerror = () => say('the browser’s socket refused the connection');
  ws.onclose = () => { if (alive()) say('the browser closed the connection'); };
  }
}

/* The sign-in sitting: the site's own page in a browser the member drives,
   and one button for when they are in. */
async function signInView(main) {
  main.classList.remove('chat-main');
  const open = await api('/sign-ins/open').catch(() => null);
  if (!open) {
    main.innerHTML = '<div class="head"><div><h1>No sign-in open</h1><p>Start one from the Household page.</p></div></div>';
    return;
  }
  main.innerHTML = '<div class="head"><div><p class="muted" style="margin-bottom:6px"><a href="#/household" style="color:var(--ink-3);text-decoration:none">Household</a></p>'
    + '<h1>Sign in to ' + esc(open.label) + '</h1><p>' + esc(open.how) + ' FamilyOS sees none of it. When you are in, press the button below.</p></div>'
    + '<div class="row" style="gap:8px"><button class="btn" data-seal="' + esc(open.id) + '">I’m signed in</button>'
    + '<button class="btn ghost" data-abandon="' + esc(open.id) + '">Cancel</button></div></div>'
    + (open.ws_url || open.live_url
      ? '<section class="card pad stack" style="gap:10px"><div class="row wrap" style="gap:8px"><h2>The browser</h2>'
        + '<span class="muted">' + esc(open.hosts.join(', ')) + ' · closes in ' + Math.max(0, Math.round((new Date(open.expires_at).getTime() - Date.now()) / 60000)) + ' min</span>'
        + '<span class="muted" data-live-status style="margin-left:auto">connecting…</span>'
        + (open.live_url ? '<a class="muted" href="' + esc(open.live_url) + '" target="_blank" rel="noopener">inspector ↗</a>' : '') + '</div>'
        + '<div class="live" data-live tabindex="0"><canvas></canvas><textarea class="live-keys" aria-label="Type into the page" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false"></textarea></div>'
        + '<p class="muted">Click and type as you would on the site. It is the real page, in a browser on this deployment; nothing of it passes through FamilyOS.</p></section>'
      : '<section class="card pad"><h2>No browser on this deployment</h2><p class="muted">Set FAMILYOS_STEEL_URL to a Steel browser and try again.</p></section>');
  if (open.ws_url) liveView(main.querySelector('[data-live]'), main.querySelector('[data-live-status]'), open.id);
  main.querySelector('[data-seal]').addEventListener('click', async (ev) => {
    try {
      const out = await api('/sign-ins/' + ev.currentTarget.dataset.seal + '/seal', { method: 'POST' });
      flash('Signed in to ' + out.label + '. The session is sealed; the browser is gone.');
      go('/household');
    } catch (err) { fail(err); }
  });
  main.querySelector('[data-abandon]').addEventListener('click', async (ev) => {
    try { await api('/sign-ins/' + ev.currentTarget.dataset.abandon, { method: 'DELETE' }); go('/household'); }
    catch (err) { fail(err); }
  });
}

/// Telegram on the Settings page: the bot, whether this member is linked,
/// and the one-time link that binds a phone. The same button the Notices
/// page offers in its ways-in card; people look for it here.
function telegramCard(h) {
  if (!h.telegram_bot) return '';
  const linked = !!(store.me && store.me.telegram_linked);
  return '<div class="card pad stack" data-telegram>'
    + '<div class="row wrap" style="justify-content:space-between;gap:8px"><h2 style="margin:0">Telegram</h2>'
    + '<span class="tag ' + (linked ? 'green' : 'line') + '">' + (linked ? 'linked' : 'not linked') + '</span></div>'
    + '<p class="muted">The household\'s bot is <b>@' + esc(h.telegram_bot) + '</b>. Linked, it brings notices in from the groups it is in, '
    + 'answers a question ending in “?”, and carries reminders and replies.</p>'
    + '<button class="btn' + (linked ? ' ghost' : '') + ' sm" data-tglink style="align-self:flex-start">'
    + (linked ? 'Link another device' : 'Link my Telegram') + '</button>'
    + '</div>';
}

function wireTelegram(main) {
  const tg = main.querySelector('[data-telegram] [data-tglink]');
  if (!tg) return;
  tg.addEventListener('click', async () => {
    tg.disabled = true;
    try { telegramLink(main, await api('/telegram/link', { method: 'POST' })); }
    catch (e) { flash(e.message || 'Could not make a link.', true); }
    finally { tg.disabled = false; }
  });
}

function sessionsCard(sessions) {
  return '<div class="card pad stack" style="gap:10px">'
    + '<div class="row wrap" style="gap:8px"><h2>Your sign-ins</h2>'
    + '<span class="muted">' + sessions.length + ' live</span></div>'
    + '<p class="muted" style="line-height:1.55">A token lasts 30 days and slides forward while you use it. '
    + 'Signing out ends the one you are on; other devices stay signed in.</p>'
    + sessions.map((s) =>
      '<div class="row" style="gap:10px;padding:9px 11px;background:var(--sunk);border:1px solid var(--line-soft);border-radius:7px">'
      + '<span class="grow"><span style="font-size:12.5px;font-weight:600">'
      + (s.kind === 'device' ? esc(s.label || 'A phone') + ' \u00B7 shortcut' : s.current ? 'This device' : 'Another device') + '</span>'
      + '<span class="sub">started ' + esc(ago(s.created_at))
      + (s.last_used_at ? '  \u00B7  last used ' + esc(ago(s.last_used_at)) : '')
      + (s.expires_at ? '  \u00B7  ends ' + esc(date(s.expires_at)) : '') + '</span></span>'
      + (s.current ? '<span class="tag green">current</span>' : '') + '</div>').join('')
    + '</div>';
}

function dangerCard(household) {
  return '<div class="card pad stack" style="gap:9px;border-color:var(--red-line)">'
    + '<h3 style="color:var(--red)">Erase everything</h3>'
    + '<p class="muted" style="line-height:1.55">Sign-in and intake stop at once. The household key is destroyed first, so '
    + 'every copy of your originals — backups included — is unreadable before a single file is deleted.</p>'
    + '<button class="btn danger" data-erasehousehold data-name="' + esc(household.name) + '">Erase the household…</button>'
    + '</div>';
}

function memberDialog() {
  return '<dialog class="card" style="max-width:420px;padding:20px;border:1px solid var(--line)">'
    + '<form class="stack" data-form="member"><h2>Add a member</h2>'
    + '<label>Name<input type="text" name="display_name" required maxlength="100"></label>'
    + '<label>Role<select name="role"><option value="adult">Adult — signs in, sees what is shared</option>'
    + '<option value="guardian">Guardian — can consent and manage</option>'
    + '<option value="child">Child — a data subject, no account</option></select></label>'
    + '<label data-emailwrap>Email<input type="email" name="email"></label>'
    + '<label data-dobwrap>Date of birth (optional)<input type="date" name="date_of_birth"></label>'
    + '<div data-schoolwrap hidden class="stack" style="gap:10px">'
    + '<label>School<input type="text" name="school" maxlength="100" placeholder="DPS Bangalore"></label>'
    + '<label>Class<input type="text" name="class_label" maxlength="40" placeholder="4, IX-B, KG II"></label>'
    + '<p class="muted" style="line-height:1.45">Circulars are addressed by class, not by name. With these, '
    + '"Dear Parents of Grade 4" finds this child on its own.</p></div>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn ghost" type="button" data-close>Cancel</button>'
    + '<button class="btn" type="submit">Add</button></div></form></dialog>';
}

/* The family's places -- home, the office, each school -- each picked by a
   map search: type an address, a landmark or paste a Google Maps link, pick
   the place the map suggests, and its exact point is kept. Only the words
   typed leave the house, to the public map. */
function placeSearch(box, { initial, placeholder, onPick, onClear }) {
  box.innerHTML = '<div class="stack" style="gap:4px;position:relative"><div class="row" style="gap:6px"><input class="grow" data-place-q placeholder="' + esc(placeholder || 'Address, landmark, or a Google Maps link') + '" value="' + esc(initial || '') + '" autocomplete="off" style="min-width:240px">'
    + (onClear ? '<button class="btn ghost sm" type="button" data-place-clear>Clear</button>' : '') + '<button class="btn ghost sm" type="button" data-place-cancel>Cancel</button></div>'
    + '<div class="muted" style="font-size:12px" data-place-hint>Type at least three letters, or paste a Google Maps link.</div><div class="stack" data-place-list style="gap:2px"></div></div>';
  const q = box.querySelector('[data-place-q]'); const list = box.querySelector('[data-place-list]'); const hint = box.querySelector('[data-place-hint]');
  let timer = null; let last = '';
  const search = async () => {
    const text = q.value.trim(); if (text === last) return; last = text;
    if (text.length < 3) { list.innerHTML = ''; return; }
    hint.textContent = 'Looking on the map…';
    try {
      const found = await api('/places/search?q=' + encodeURIComponent(text));
      if (q.value.trim() !== text) return;
      list.innerHTML = found.length ? found.map((f, i) => '<button class="btn ghost sm" type="button" data-place-pick="' + i + '" style="justify-content:flex-start;text-align:left">' + esc(f.label) + ' <span class="muted" style="font-size:11px">' + f.lat.toFixed(4) + ', ' + f.lon.toFixed(4) + '</span></button>').join('') : '';
      hint.textContent = found.length ? 'Pick the one you mean.' : 'The map did not find that. Try the street or a landmark nearby, or paste a Google Maps link.';
      list.querySelectorAll('[data-place-pick]').forEach((b) => b.addEventListener('click', () => onPick(found[Number(b.dataset.placePick)])));
    } catch (err) { hint.textContent = (err && err.message) || 'The map could not be reached.'; }
  };
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 450); });
  q.addEventListener('paste', () => { clearTimeout(timer); timer = setTimeout(search, 50); });
  box.querySelector('[data-place-cancel]').addEventListener('click', () => box.remove());
  const clr = box.querySelector('[data-place-clear]'); if (clr) clr.addEventListener('click', onClear);
  q.focus();
}

function wirePlaces(placesBox) {
  const guardian = store.me && store.me.role === 'guardian';
  Promise.all([api('/household/rules'), api('/household/schools').catch(() => [])]).then(([rules, schools]) => {
    const rule = (k) => (rules.rules || []).find((x) => x.key === k) || {};
    const rows = [
      { key: 'home', title: 'Home', label: rule('home_place').text, set: rule('home_place').on, why: 'the weather, leave-by times and the school run start here' },
      { key: 'work', title: 'Office', label: rule('work_place').text, set: rule('work_place').on, why: 'the commute sits beside the school run on Today' },
    ].concat(schools.map((sc) => ({ key: 'school:' + sc.id, title: sc.name, label: sc.address, set: sc.lat != null, why: 'the school run from home', school: sc })));
    placesBox.innerHTML = '<div class="stack" style="gap:6px;padding:8px 2px 4px"><div class="row wrap" style="gap:8px;align-items:baseline"><span style="font-size:13px;font-weight:600">Places</span><span class="muted" style="font-size:12px">picked on a map search; only the words typed leave the house</span></div>'
      + rows.map((r) => '<div class="row wrap" style="gap:8px" data-place-row="' + esc(r.key) + '"><b style="min-width:70px">' + esc(r.title) + '</b>'
        + '<span class="muted">' + (r.label ? esc(r.label) + (r.set ? '' : ' <span class="tag">not on the map</span>') : 'not set · ' + esc(r.why)) + '</span>'
        + (guardian ? '<button class="btn ghost sm" data-place-edit="' + esc(r.key) + '">' + (r.label ? 'change' : 'set') + '</button>' : '') + '</div>').join('') + '</div>';
    placesBox.querySelectorAll('[data-place-edit]').forEach((b) => b.addEventListener('click', () => {
      const r = rows.find((x) => x.key === b.dataset.placeEdit); const row = placesBox.querySelector('[data-place-row="' + r.key + '"]');
      if (row.querySelector('[data-place-q]')) return;
      const box = document.createElement('div'); box.style.flexBasis = '100%'; row.appendChild(box);
      const save = async (body, path) => { try { await api(path, { method: 'PUT', json: body }); render(); } catch (err) { box.querySelector('[data-place-hint]').textContent = (err && err.message) || 'That did not save.'; } };
      const path = r.school ? '/household/schools/' + r.school.id : '/household/places/' + r.key;
      placeSearch(box, {
        initial: r.label, placeholder: r.school ? 'The school\'s address, or a Google Maps link' : r.key === 'home' ? 'Your address, a landmark, or a Google Maps link' : 'The office address, or a Google Maps link',
        onPick: (f) => save(r.school ? { address: f.label, lat: f.lat, lon: f.lon } : { label: f.label, lat: f.lat, lon: f.lon }, path),
        onClear: r.label ? () => save(r.school ? { address: null, lat: null, lon: null } : { label: null, lat: null, lon: null }, path) : null,
      });
    }));
  }).catch(() => {});
}

/* The birthday button on a member's row: a date, saved on the spot. */
function wireBirthdays(main) {
  main.querySelectorAll('[data-birthday]').forEach((b) => b.addEventListener('click', () => {
    // Inline in the member's sub-line: a compact date box and a Save that keeps its word on one line.
    const wrap = document.createElement('span'); wrap.style.cssText = 'display:inline-flex;gap:6px;align-items:center;vertical-align:middle';
    wrap.innerHTML = '<input type="date" value="' + esc(b.dataset.dob) + '" max="' + todayISO() + '" aria-label="Date of birth" style="width:150px;padding:4px 8px;font-size:13px;min-height:0">'
      + '<button class="btn sm" type="button" style="white-space:nowrap">Save</button>';
    b.replaceWith(wrap); wrap.querySelector('input').focus();
    wrap.querySelector('button').addEventListener('click', async () => {
      try { await api('/members/' + b.dataset.birthday + '/birthday', { method: 'PATCH', json: { date_of_birth: wrap.querySelector('input').value || null } }); store.household = await api('/household'); go('/household'); }
      catch (err) { wrap.querySelector('button').textContent = (err && err.message) || 'Failed'; }
    });
  }));
}

function wireHousehold(main, household) {
  wireBirthdays(main);
  const dlg = main.querySelector('dialog');
  const add = main.querySelector('[data-addmember]');
  if (add) add.addEventListener('click', () => dlg.showModal());
  dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());
  const roleSel = dlg.querySelector('[name="role"]');
  roleSel.addEventListener('change', () => {
    const child = roleSel.value === 'child';
    dlg.querySelector('[data-emailwrap]').hidden = child;
    dlg.querySelector('[name="email"]').required = !child;
    dlg.querySelector('[data-dobwrap]').hidden = false;
    dlg.querySelector('[data-schoolwrap]').hidden = !child;
  });
  dlg.querySelector('[name="email"]').required = true;

  dlg.querySelector('form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const body = { display_name: f.get('display_name'), role: f.get('role') };
    if (body.role !== 'child') body.email = f.get('email');
    if (f.get('date_of_birth')) body.date_of_birth = f.get('date_of_birth');
    if (body.role === 'child') {
      if ((f.get('school') || '').trim()) body.school = f.get('school').trim();
      if ((f.get('class_label') || '').trim()) body.class_label = f.get('class_label').trim();
    }
    try {
      const made = await api('/household/members', { method: 'POST', json: body });
      dlg.close();
      if (made.token) {
        flash('Added. Their token: ' + made.token);
        window.prompt('This token is shown once. Copy it and give it to them:', made.token);
      } else {
        flash('Added. Children do not sign in.');
      }
      await render();
    } catch (err) { fail(err); }
  });

  // Two prompts rather than a form: it is set once a year, and the same two
  // words a parent would say down the phone.
  main.querySelectorAll('[data-school]').forEach((b) => b.addEventListener('click', async () => {
    const school = window.prompt('Which school? (blank to clear)', b.dataset.schoolnow || '');
    if (school === null) return;
    const cls = window.prompt('Which class? As the school writes it: 4, IX-B, KG II. (blank to clear)', b.dataset.classnow || '');
    if (cls === null) return;
    try {
      await api('/members/' + b.dataset.school + '/school', { method: 'PATCH', json: {
        school: school.trim() || null, class_label: cls.trim() || null } });
      flash(school.trim() || cls.trim() ? 'Set. Circulars for that class will find them now.' : 'Cleared.');
      await render();
    } catch (err) { fail(err); }
  }));

  main.querySelectorAll('[data-grant]').forEach((b) => b.addEventListener('click', async () => {
    const notice = window.prompt('Which consent notice version are you recording against?', new Date().toISOString().slice(0, 7));
    if (!notice) return;
    try {
      await api('/consents', {
        method: 'POST',
        json: {
          subject_member_id: b.dataset.grant,
          purpose: 'household_records',
          notice_version: notice,
          verification_method: 'account_holder',
        },
      });
      flash('Consent recorded.');
      await render();
    } catch (err) { fail(err); }
  }));

  main.querySelectorAll('[data-withdraw]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Withdraw consent? Every notice naming this child, and everything read from it, is erased. This cannot be undone.')) return;
    try {
      const e = await api('/consents/' + b.dataset.withdraw + '/withdraw', { method: 'POST' });
      flash('Withdrawn. Erasure ' + e.id.slice(0, 8) + ' is ' + e.status + '.');
      await render();
    } catch (err) { fail(err); }
  }));

  main.querySelectorAll('[data-signoutall]').forEach((b) => b.addEventListener('click', async () => {
    const mine = b.dataset.signoutall === store.me.id;
    if (!confirm(mine
      ? 'Sign out on every device, including this one?'
      : 'End every sign-in this member has? They will need a new token to get back in.')) return;
    try {
      const out = await api('/members/' + b.dataset.signoutall + '/signout', { method: 'POST' });
      flash(out.ended + ' sign-in' + (out.ended === 1 ? '' : 's') + ' ended.');
      if (mine) { forget(); return; }
      await render();
    } catch (err) { fail(err); }
  }));

  main.querySelectorAll('[data-erase]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Erase this child’s data and remove them from the household? This cannot be undone.')) return;
    try {
      const e = await api('/members/' + b.dataset.erase + '/erase', { method: 'POST' });
      flash('Erasure ' + e.id.slice(0, 8) + ' is ' + e.status + '.');
      await render();
    } catch (err) { fail(err); }
  }));

  const nuke = main.querySelector('[data-erasehousehold]');
  if (nuke) {
    nuke.addEventListener('click', async () => {
      const typed = window.prompt('This erases everything, for everyone, and cannot be undone.\n\nType the household name exactly to confirm:');
      if (typed === null) return;
      try {
        const e = await api('/household/erase', { method: 'POST', json: { confirm_name: typed } });
        flash('Erasure ' + e.id.slice(0, 8) + ' started. Every token is now invalid.');
        setTimeout(forget, 2500);
      } catch (err) { fail(err); }
    });
  }
}

/* ── audit ────────────────────────────────────────────────────── */

async function auditView(main) {
  const events = await api('/audit?limit=200');
  main.innerHTML = '<div class="head"><div><div class="row" style="gap:10px"><h1>Audit</h1>'
    + '<span class="tag">append-only</span></div>'
    + '<p>Who did what to which record. The table refuses UPDATE and DELETE; only a household erasure may purge it. '
    + 'Entries carry ids, counts, sizes and hashes — never filenames, subjects or text.</p></div></div>'
    + (events.length ? '<div class="card list" data-rows></div>'
      : '<div class="card"><div class="empty">No events yet.</div></div>');
  if (!events.length) return;

  const rows = main.querySelector('[data-rows]');
  let day = '';
  rows.innerHTML = events.map((e) => {
    const detail = Object.keys(e.detail || {}).map((k) => k + ' ' + JSON.stringify(e.detail[k])).join('   ');
    const d = date(e.at);
    const head = d !== day ? '<div class="muted" style="padding:10px 14px 4px;font-size:12px;font-weight:600">' + esc(d) + '</div>' : '';
    day = d;
    return head + '<div class="item" style="cursor:default;align-items:flex-start" data-audit-row>'
      + '<span class="muted" style="width:72px;flex-shrink:0">' + esc(new Date(e.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })) + '</span>'
      + '<span class="grow"><span style="font-size:14px">' + esc(e.said || e.action) + '</span>'
      + '<span class="sub mono" style="font-size:11px" hidden data-audit-raw>' + esc(e.action) + (detail ? '   ' + esc(detail) : '') + '</span></span>'
      + '<span class="tag line" style="flex-shrink:0">' + esc(e.who || e.actor_kind) + '</span>'
      + '</div>';
  }).join('');
  // The technical row behind each sentence, for when the sentence is not enough.
  const toggle = document.createElement('div'); toggle.className = 'row'; toggle.style.cssText = 'gap:8px;padding:8px 14px';
  toggle.innerHTML = '<button class="btn ghost sm" data-audit-toggle>Show the raw rows</button>';
  rows.before(toggle);
  toggle.querySelector('[data-audit-toggle]').addEventListener('click', (ev) => {
    const on = ev.target.textContent.startsWith('Show');
    rows.querySelectorAll('[data-audit-raw]').forEach((el) => { el.hidden = !on; });
    ev.target.textContent = on ? 'Hide the raw rows' : 'Show the raw rows';
  });
}

/* ── start ────────────────────────────────────────────────────── */

window.addEventListener('hashchange', () => { render().catch(() => {}); });

(async () => {
  const fromGoogle = takeTokenFromFragment();
  if (fromGoogle) {
    store.token = fromGoogle;
    try { await boot(); return; } catch (e) { store.token = null; writeToken(null); }
  }
  const said = new URLSearchParams(location.search).get('signin');
  // Google verified an address nobody here uses. The person just chose this
  // account, so it wins over any stored session: show them the way in.
  const fresh = said === 'new' ? takeAllFromFragment() : {};
  const newEmail = fresh.email || null;
  if (newEmail) {
    history.replaceState(null, '', location.pathname);
    gateView(null, { newEmail, founding: fresh.found || '' });
    return;
  }
  // A link in the address bar wins over whatever session is stored: the person
  // clicking it has just said which account they mean.
  if (await redeemLinkFromUrl()) return;
  store.token = readToken();
  if (store.token) {
    boot().catch(() => { store.token = null; writeToken(null); gateView(); });
  } else {
    gateView(said === 'failed' ? 'That Google account cannot sign in here.'
      : said === 'cancelled' ? 'Signing in with Google was cancelled.' : null);
  }
})();


/* ---------------------------------------------------------------------------
   Money: as far as mail can see it. Derived from the claims already read.
   --------------------------------------------------------------------------- */

const CADENCE = { monthly: 'monthly', yearly: 'yearly', weekly: 'weekly', stated: 'recurring' };

function fmtDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

async function loadRecurringCard(main, selector) {
  const aside = main.querySelector(selector || 'aside');
  if (!aside) return;
  let data;
  try { data = await api('/money?days=120'); } catch (e) { return; }
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const low = (data.running_low || []).slice(0, 4);
  const lowKeys = new Set(low.map((r) => r.item_key));
  const usual = (data.usual || []).filter((u) => !lowKeys.has(u.item_key)).slice(0, 5);
  if (low.length || usual.length) {
    const lowCard = document.createElement('section');
    lowCard.className = 'card rail-card';
    const line = (r, sub) => '<div class="row" style="justify-content:space-between;gap:10px;align-items:flex-start">'
      + '<span><b>' + esc(r.item) + '</b><br><span class="muted">' + sub + '</span></span>'
      + (r.reorder_url ? '<a class="btn ghost sm" href="' + esc(r.reorder_url) + '" target="_blank" rel="noopener">Order \u2197</a>' : '<span class="muted">' + esc(r.merchant) + '</span>') + '</div>';
    lowCard.innerHTML = '<div class="row wrap" style="gap:8px"><h2>Order again</h2><span class="muted">from your receipts</span></div>'
      + (low.length ? '<p class="muted" style="font-size:11.5px;margin:0 0 4px">Running low</p><div class="stack" style="gap:8px">'
        + low.map((r) => line(r, 'every ~' + r.every_days + ' days \u00B7 last ' + esc(fmtDate(r.last_on)) + (r.status === 'overdue' ? ' \u00B7 <span class="tag amber">due</span>' : ''))).join('') + '</div>' : '')
      + (usual.length ? '<p class="muted" style="font-size:11.5px;margin:' + (low.length ? '12px' : '0') + ' 0 4px">The usual</p><div class="stack" style="gap:8px">'
        + usual.map((r) => line(r, esc(r.merchant) + ' \u00B7 ' + r.times + '\u00D7 \u00B7 last ' + esc(fmtDate(r.last_on)) + (r.last_amount ? ' \u00B7 ' + esc(money(r.last_amount, r.currency)) : ''))).join('') + '</div>' : '')
      + '<p class="muted" style="font-size:11.5px;margin-top:10px">Links open the shop\u2019s own search. Nothing is ordered from here.</p>';
    aside.insertBefore(lowCard, aside.firstChild);
  }
  const soon = data.recurring.filter((r) => new Date(r.next_date + 'T00:00:00') >= today).slice(0, 4);
  if (!soon.length) return;
  const card = document.createElement('section');
  card.className = 'card rail-card';
  card.innerHTML = '<div class="row wrap" style="gap:8px"><h2>Recurring</h2>'
    + '<a class="muted" href="#/money">all</a></div>'
    + '<div class="stack" style="gap:8px">'
    + soon.map((r) => '<div class="row" style="justify-content:space-between;gap:10px">'
      + '<span><b>' + esc(r.merchant) + '</b> <span class="muted">' + esc(CADENCE[r.cadence]) + '</span></span>'
      + '<span style="text-align:right"><b>' + esc(money(r.next_amount, r.currency)) + '</b>'
      + '<br><span class="muted">' + esc(fmtDate(r.next_date)) + '</span></span></div>').join('')
    + '</div>';
  const bills = Array.from(aside.querySelectorAll('h2')).find((h) => h.textContent === 'Bills');
  const anchor = bills ? bills.closest('section') : null;
  if (anchor) anchor.after(card); else aside.appendChild(card);
}

const CAT_HUE = { school: 'school', medical: 'health', insurance: 'health', travel: 'travel', home: 'home', food: 'home', shopping: 'home',
  bills: 'money', banking: 'money', trading: 'invest', subscriptions: 'money', government: 'money' };
function catPill(cat) { return '<span class="tag cat ' + esc(cat || '') + '">' + esc(CATEGORY[cat] || cat || '') + '</span>'; }
function merchantTile(name, cat) {
  const hue = CAT_HUE[cat] || 'home';
  return '<span class="mtile h-' + hue + '">' + esc(initial(name)) + '</span>';
}

async function moneyView(main) {
  main.classList.remove('chat-main');
  const data = await api('/money?days=120');
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const inr = (rows) => rows.filter((r) => r.currency === 'INR');
  const other = (rows) => rows.filter((r) => r.currency !== 'INR');
  const total = inr(data.month.by_category).reduce((a, r) => a + r.total, 0);
  const upcoming = data.recurring.filter((r) => new Date(r.next_date + 'T00:00:00') >= today);
  const soon = upcoming.filter((r) => (new Date(r.next_date + 'T00:00:00') - today) / 86400000 <= 7);
  const subs = data.recurring.filter((r) => r.category === 'subscriptions' && r.currency === 'INR').reduce((a, r) => a + r.next_amount, 0);
  const maxCat = Math.max(1, ...inr(data.month.by_category).map((r) => r.total));
  const rrow = (r) => {
    const past = new Date(r.next_date + 'T00:00:00') < today;
    return '<div class="mrow' + (past ? ' past' : '') + '">' + merchantTile(r.merchant, r.category)
      + '<span class="grow"><a class="t" href="#/notices/' + esc(r.artifact_id) + '">' + esc(r.merchant) + '</a> ' + catPill(r.category)
      + '<div class="s">' + esc(CADENCE[r.cadence]) + (r.times > 1 ? ' · ' + r.times + ' times' : '') + (r.last_date ? ' · last ' + esc(fmtDate(r.last_date).replace(/,.*$/, '')) + (r.last_amount ? ' ' + esc(money(r.last_amount, r.currency)) : '') : '') + (r.total && r.times > 1 ? ' · ' + esc(money(Math.round(r.total), r.currency)) + ' so far' : '') + '</div></span>'
      + '<span class="when"><b>' + esc(money(r.next_amount, r.currency)) + '</b><span>' + (past ? 'was due ' : 'next ') + esc(fmtDate(r.next_date).replace(/,.*$/, '')) + '</span></span>'
      + (r.manage_url ? '<a class="ib" href="' + esc(r.manage_url) + '" target="_blank" rel="noopener" title="Manage">' + icon('open', 15) + '</a>' : '<span style="width:34px"></span>')
      + '</div>';
  };
  main.innerHTML = '<div class="head"><div><h1>Money</h1>'
    + '<p>As far as mail can see it: every receipt and bill the household’s mail carried, read as it came. '
    + 'What never produced a receipt — UPI, cards, cash — is in the bank statements, which stay locked.</p></div></div>'
    + '<div class="stats">'
    + '<div class="stat"><span class="ic money">' + icon('money', 18) + '</span><span><b>' + esc(money(Math.round(total), 'INR')) + '</b><span>last 30 days · ' + data.month.charges + ' charges</span></span></div>'
    + '<div class="stat"><span class="ic home">' + icon('calendar', 18) + '</span><span><b>' + soon.length + '</b><span>' + (soon.length === 1 ? 'bill due this week' : 'bills due this week') + '</span></span></div>'
    + '<div class="stat"><span class="ic travel">' + icon('clock', 18) + '</span><span><b>' + esc(money(Math.round(subs), 'INR')) + '</b><span>subscriptions, next round</span></span></div>'
    + '<div class="stat"><span class="ic school">' + icon('cart', 18) + '</span><span><b>' + (data.running_low || []).filter((r) => r.status !== 'fine').length + '</b><span>running low</span></span></div>'
    + '</div>'
    + '<div class="home"><div class="stack" style="gap:16px">'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Recurring</h2><span class="muted">' + data.recurring.length + ' merchants that charge again</span></div>'
    + (data.recurring.length ? '<div class="mlist">' + data.recurring.map(rrow).join('') + '</div>'
      : '<p class="muted">Nothing recurring yet. A second receipt from the same merchant, or one that says it renews, lands here.</p>') + '</section>'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Last 30 days</h2><span class="muted">' + data.month.charges + ' charges · <b>' + esc(money(Math.round(total), 'INR')) + '</b>'
    + (other(data.month.by_category).length ? ' + ' + other(data.month.by_category).map((r) => esc(money(r.total, r.currency))).join(' + ') : '') + (data.month.comparable ? ' · against the 30 before' : '') + '</span></div>'
    + '<div class="split" style="margin-top:4px"><div class="stack" style="gap:8px">'
    + inr(data.month.by_category).map((r) => '<div class="bar"><span class="l">' + catPill(r.category) + '</span>'
      + '<span class="track"><span class="fill ' + (CAT_HUE[r.category] || 'home') + '" style="width:' + Math.max(3, Math.round(100 * r.total / maxCat)) + '%"></span></span>'
      + '<span class="v"><b>' + esc(money(Math.round(r.total), r.currency)) + '</b>' + (r.previous && data.month.comparable ? '<span class="muted">' + (r.delta >= 0 ? '+' : '−') + esc(money(Math.round(Math.abs(r.delta)), r.currency)) + ' vs before' + (r.driver && Math.abs(r.delta) >= 500 ? ' · ' + esc(r.driver) : '') + '</span>' : '') + '</span></div>').join('')
    + other(data.month.by_category).map((r) => '<div class="bar"><span class="l">' + catPill(r.category) + '</span><span class="track"></span><span class="v"><b>' + esc(money(r.total, r.currency)) + '</b></span></div>').join('')
    + '</div><div class="stack" style="gap:2px">'
    + data.month.by_merchant.slice(0, 10).map((r) => '<div class="mrow slim">' + merchantTile(r.merchant, '') + '<span class="grow"><span class="t">' + esc(r.merchant) + '</span>' + (r.times > 1 ? '<div class="s">' + r.times + ' times</div>' : '') + '</span><b>' + esc(money(Math.round(r.total * 100) / 100, r.currency)) + '</b></div>').join('')
    + '</div></div></section>'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Running low and the usual</h2><span class="muted">what the household buys at a rhythm, and orders again and again \u00B7 one tap to the shop\u2019s search</span></div>'
    + (((data.running_low || []).length || (data.usual || []).length) ? '<div class="mlist">'
      + (data.running_low || []).map((r) => '<div class="mrow">' + merchantTile(r.item, 'food') + '<span class="grow"><span class="t">' + esc(r.item) + '</span>' + (r.status === 'overdue' ? ' <span class="tag amber">due</span>' : ' <span class="tag">due ' + esc(fmtDate(r.expected_on).replace(/,.*$/, '')) + '</span>') + '<div class="s">' + esc(r.merchant) + ' · every ~' + r.every_days + ' days · bought ' + r.times + ' times · last ' + esc(fmtDate(r.last_on).replace(/,.*$/, '')) + '</div></span>' + (r.reorder_url ? '<a class="btn ghost sm" href="' + esc(r.reorder_url) + '" target="_blank" rel="noopener">Reorder</a>' : '') + '</div>').join('')
      + (data.usual || []).map((r) => '<div class="mrow">' + merchantTile(r.item, r.kind === 'meal' ? 'food' : 'shopping') + '<span class="grow"><span class="t">' + esc(r.item) + '</span> <span class="tag ' + (r.kind === 'meal' ? 'amber' : '') + '">' + (r.kind === 'meal' ? 'meal' : 'grocery') + '</span><div class="s">' + esc(r.merchant) + ' · ' + r.times + ' times · last ' + esc(fmtDate(r.last_on).replace(/,.*$/, '')) + (r.last_amount ? ' · ' + esc(money(r.last_amount, r.currency)) : '') + '</div></span>' + (r.reorder_url ? '<a class="btn ghost sm" href="' + esc(r.reorder_url) + '" target="_blank" rel="noopener">Order</a>' : '') + '</div>').join('')
      + '</div>' : '<p class="muted">Nothing yet. The same item on two receipts a steady gap apart is a rhythm; it shows here before it runs out. Anything on two receipts shows here.</p>') + '</section>'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Home services</h2><span class="muted">when each was last done</span></div>'
    + (data.services.last_done.length
      ? '<div class="pills" style="margin:4px 0 12px">' + data.services.last_done.map((e) => '<span class="pill sm">' + esc(e.kind) + ' <span class="n">' + esc(fmtDate(e.date).replace(/,.*$/, '')) + '</span></span>').join('') + '</div>'
        + '<div class="mlist">' + data.services.timeline.map((e) => '<div class="mrow slim">' + merchantTile(e.merchant, 'home') + '<span class="grow"><a class="t" href="#/notices/' + esc(e.artifact_id) + '">' + esc(e.what) + '</a><div class="s">' + esc(e.merchant) + ' · ' + esc(fmtDate(e.date)) + '</div></span><b>' + esc(money(e.amount, e.currency)) + '</b></div>').join('') + '</div>'
      : '<p class="muted">Invoices from a plumber, an electrician or an appliance service land here, grouped by what was done.</p>') + '</section>'
    + '<details class="card pad"><summary style="cursor:pointer;font-weight:600;font-size:15px">All charges <span class="muted" style="font-weight:400;font-size:12.5px">' + data.charges.length + ' in ' + data.days + ' days</span></summary>'
    + '<div class="mlist" style="margin-top:10px">' + data.charges.map((c) => '<div class="mrow slim">' + merchantTile(c.merchant, c.category) + '<span class="grow"><a class="t" href="#/notices/' + esc(c.message_id) + '">' + esc(c.merchant) + '</a><div class="s">' + esc(c.title) + ' · ' + esc(fmtDate(c.date).replace(/,.*$/, '')) + (c.upcoming ? ' · due ' + esc(fmtDate(c.due).replace(/,.*$/, '')) : '') + (c.settles_due ? ' · settles the bill due ' + esc(fmtDate(c.settles_due).replace(/,.*$/, '')) : '') + '</div></span><b>' + esc(money(c.amount, c.currency)) + '</b></div>').join('') + '</div></details>'
    + '</div><aside class="stack" style="gap:14px">'
    + '<section class="card rail-card"><h2>Due soon</h2>' + (soon.length ? '<div class="stack" style="gap:8px">' + soon.map((r) => '<a class="row" href="#/notices/' + esc(r.artifact_id) + '" style="gap:10px;text-decoration:none;color:inherit"><span class="grow" style="font-size:13.5px">' + esc(r.merchant) + '</span><span class="muted" style="white-space:nowrap">' + esc(fmtDate(r.next_date).replace(/,.*$/, '')) + '</span><b>' + esc(money(r.next_amount, r.currency)) + '</b></a>').join('') + '</div>' : '<p class="muted">Nothing due this week.</p>') + '</section>'
    + '<section class="card rail-card"><h2>What this is</h2><p class="muted">Each line is one claim the reader found on a receipt, linked to the notice it came from. '
    + 'Nothing is typed in, nothing is paid, and nothing here is stored: it follows every re-read.</p>'
    + '<p class="muted">Recurring means the same merchant charged again at a steady gap, or the receipt itself says it renews.</p></section>'
    + '</aside></div>';
}


/* ---------------------------------------------------------------------------
   Ask: the one window. The model sees what you see and proposes; you confirm;
   the ordinary endpoint does it. The thread lives in this browser only.
   --------------------------------------------------------------------------- */

const CHAT_KEY = 'familyos.chat';

function readThread() {
  try { return JSON.parse(sessionStorage.getItem(CHAT_KEY) || '[]'); } catch (e) { return []; }
}
function writeThread(thread) {
  try { sessionStorage.setItem(CHAT_KEY, JSON.stringify(thread.slice(-40))); } catch (e) { /* fine */ }
}

async function chatView(main) {
  main.classList.add('chat-main');
  main.innerHTML = '<div class="chat-page">'
    + '<div class="chat-top"><div><h1>Ask</h1>'
    + '<p>Anything the household has received, or what should happen next. Answers point at the notice they came from; '
    + 'anything that would change something is shown as a card and happens only when you confirm.</p></div>'
    + '<button class="btn ghost sm" data-clear>Clear</button></div>'
    + '<div class="chat-thread" data-thread></div>'
    + '<div class="chat-dock">'
    + '<div class="chips" data-chips>'
    + ['What needs someone this week?', 'What do we pay every month?', 'When did the plumber last come?', 'What is still undecided?']
      .map((q) => '<button class="chip" data-try>' + esc(q) + '</button>').join('')
    + '</div>'
    + '<form class="chat-composer" data-composer>'
    + '<textarea name="message" rows="1" maxlength="1000" placeholder="Ask, or say what should happen…" required></textarea>'
    + '<button class="send" type="submit" aria-label="Send">' + icon('arrow-up', 18) + '</button></form>'
    + '<p class="chat-foot">The assistant sees only what you can see. It never sends, pays or changes anything on its own.</p>'
    + '</div></div>';
  const threadEl = main.querySelector('[data-thread]');
  const form = main.querySelector('[data-composer]');
  const box = form.querySelector('textarea');
  const chips = main.querySelector('[data-chips]');
  let thread = readThread();
  const grow = () => { box.style.height = 'auto'; box.style.height = Math.min(box.scrollHeight, 160) + 'px'; };
  const paint = (smooth) => {
    threadEl.innerHTML = thread.length ? thread.map(chatBubble).join('')
      : '<div class="chat-hello"><div class="orb" aria-hidden="true">' + icon('sparkle', 22) + '</div>'
        + '<h2>Good ' + dayPart() + ', ' + esc((store.me && store.me.display_name) || '') + '.</h2>'
        + '<p>The household’s mail, the dates spotted, the to-dos and what you pay for are all in front of me. Ask away, or try one below.</p></div>';
    chips.hidden = thread.length > 0;
    wireProposals(main, thread, paint);
    threadEl.scrollTo({ top: threadEl.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  };
  paint(false);
  // A question handed over from another page: in the hash (openAsk), or left
  // in session storage by an older page. Asked once; the hash is cleaned so
  // a reload does not ask it again.
  let pending = hashQuery().get('q') || '';
  if (pending) history.replaceState(null, '', '#/chat');
  else { try { pending = sessionStorage.getItem('familyos.ask') || ''; if (pending) sessionStorage.removeItem('familyos.ask'); } catch (e) { /* nothing pending */ } }
  if (pending) setTimeout(() => send(pending), 60);
  const send = async (text) => {
    text = (text || '').trim();
    if (!text) return;
    thread.push({ role: 'user', content: text });
    thread.push({ role: 'assistant', pending: true });
    writeThread(thread); paint(true);
    box.value = ''; grow(); box.disabled = true;
    try {
      const history = thread.filter((t) => !t.pending && t.content).slice(-13, -1).map((t) => ({ role: t.role, content: t.content }));
      let frame = 0;
      const turn = await chatStream({ message: text, history }, (said) => {
        thread[thread.length - 1].content = said.replace(/\s*\[[A-Za-z]+\d*\]/g, '');
        if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(true); });
      });
      thread.pop();
      thread.push({ role: 'assistant', content: turn.say, grounded: turn.grounded, note: turn.note || null, citations: turn.citations, proposals: turn.proposals });
    } catch (err) {
      thread.pop();
      thread.push({ role: 'assistant', content: (err && err.message) || 'Something went wrong.', error: true });
    }
    box.disabled = false; box.focus();
    writeThread(thread); paint(true);
  };
  form.addEventListener('submit', (ev) => { ev.preventDefault(); send(box.value); });
  box.addEventListener('input', grow);
  box.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); send(box.value); } });
  main.querySelectorAll('[data-try]').forEach((b) => b.addEventListener('click', () => send(b.textContent)));
  main.querySelector('[data-clear]').addEventListener('click', () => { thread = []; writeThread(thread); paint(false); });
  box.focus();
}

function dayPart() {
  const h = new Date().getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}

/* The answer as it is written: newline-delimited events from /chat/stream,
   each say delta painted into the pending bubble, then the finished turn with
   its citations and proposals. A server without the route, or a failure before
   the first word, falls back to the whole turn. */
async function chatStream(payload, onDelta) {
  const headers = { 'Content-Type': 'application/json' };
  if (store.token) headers.Authorization = 'Bearer ' + store.token;
  let res;
  try { res = await fetch('/v1/chat/stream', { method: 'POST', headers, body: JSON.stringify(payload) }); } catch (e) { res = null; }
  if (!res || !res.ok || !res.body) return api('/chat', { method: 'POST', json: payload });
  const reader = res.body.getReader(); const decoder = new TextDecoder();
  let buf = '', turn = null, said = '';
  for (;;) {
    const { value, done } = await reader.read();
    buf += done ? decoder.decode() : decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
      if (!line) continue;
      let ev; try { ev = JSON.parse(line); } catch (e) { continue; }
      if (ev.type === 'say') { said += ev.delta; onDelta(said); }
      else if (ev.type === 'turn') turn = ev;
      else if (ev.type === 'error') throw new ApiError(502, { detail: ev.detail });
    }
    if (done) break;
  }
  if (!turn) throw new ApiError(502, { detail: 'The answer stopped before it was finished.' });
  return turn;
}

function chatBubble(t) {
  if (t.role === 'user') return '<div class="bubble me">' + esc(t.content) + '</div>';
  if (t.pending) return '<div class="bubble them pending">' + (t.content ? esc(t.content) + '<span class="caret" aria-hidden="true">▍</span>' : '…') + '</div>';
  let text = esc(t.content || '');
  (t.citations || []).forEach((c) => {
    const href = c.artifact_id ? '#/notices/' + esc(c.artifact_id) : (c.kind === 'todo' ? '#/chat' : '#/money');
    text = text.split('[' + c.ref + ']').join('<a class="cite" href="' + href + '" title="' + esc(c.text) + '">' + esc(c.ref) + '</a>');
  });
  return '<div class="bubble them' + (t.error ? ' bad' : '') + '">' + text
    + (t.note ? '<div style="font-size:12px;margin-top:6px;padding:6px 9px;border-radius:8px;background:var(--amber-tint);color:var(--amber-ink)">' + esc(t.note) + '</div>' : '')
    + (t.grounded === false && !t.error && !t.note && !(t.proposals || []).length ? '<div class="muted" style="font-size:11.5px;margin-top:6px">Not pointing at any notice — treat as conversation, not fact.</div>' : '')
    + (t.proposals || []).map((p, i) => proposalCard(p, i)).join('')
    + '</div>';
}

function proposalCard(p, i) {
  const done = p.done ? '<span class="tag green">done</span>' : '';
  let body;
  if (p.kind === 'assign') body = 'Hand <b>' + esc(p.headline || 'the notice') + '</b> to <b>' + esc(p.member_name || '?') + '</b>' + (p.note ? ' — “' + esc(p.note) + '”' : '');
  else if (p.kind === 'todo') body = 'To-do: <b>' + esc(p.title || '') + '</b>' + (p.due_date ? ' by ' + esc(fmtDate(p.due_date)) + (p.due_time ? ' ' + esc(String(p.due_time).slice(0, 5)) : '') : '') + (p.member_name ? ' — ' + esc(p.member_name) + '’s' : '') + (p.note ? ' — “' + esc(p.note) + '”' : '');
  else if (p.kind === 'handled') body = 'Mark <b>' + esc(p.headline || 'the notice') + '</b> handled' + (p.note ? ' \u2014 \u201C' + esc(p.note) + '\u201D' : '');
  else if (p.kind === 'plan') body = 'Plan <b>' + esc(p.title || 'this') + '</b> \u2014 itinerary, candidate bookings as pages to open, and the legwork as to-dos. Nothing is booked.';
  else if (p.kind === 'errand') body = (p.look ? 'Look on <b>' : 'Errand on <b>') + esc(p.label || p.service) + '</b>: <b>' + esc(p.what || p.title) + '</b>' + (p.due_date ? ' \u2014 ' + esc(fmtDate(p.due_date)) + (p.due_time ? ' ' + esc(String(p.due_time).slice(0, 5)) : (p.part && p.part !== 'any' ? ' ' + esc(p.part) : '')) : '')
    + (p.look ? '. Reads the slots and the price in your signed-in session; buys nothing, so it runs at once.' : (p.max_amount ? ' \u2014 at most ' + esc(money(p.max_amount, p.currency)) : '') + '. Written down in full for a guardian to approve; paid after the service, or by a UPI request on your phone.');
  else body = (p.status === 'accepted' ? 'Accept' : 'Dismiss') + ' <b>' + esc(p.title || 'the date') + '</b>';
  return '<div class="proposal' + (p.ok ? '' : ' off') + '" data-proposal="' + i + '">'
    + '<span>' + body + (p.why ? '<br><span class="muted">' + esc(p.why) + '</span>' : '') + '</span>'
    + (p.ok && !p.done ? '<button class="btn sm" data-confirm>Confirm</button>' : done) + '</div>';
}

function wireProposals(main, thread, paint) {
  main.querySelectorAll('[data-confirm]').forEach((b) => b.addEventListener('click', async () => {
    const card = b.closest('[data-proposal]');
    const bubble = card.closest('.bubble');
    const turn = thread.filter((t) => t.role === 'assistant' && !t.pending)[Array.from(main.querySelectorAll('.bubble.them:not(.pending)')).indexOf(bubble)];
    const p = turn && turn.proposals[Number(card.dataset.proposal)];
    if (!p) return;
    b.disabled = true;
    try {
      if (p.kind === 'assign') await api('/artifacts/' + p.artifact_id + '/assign', { method: 'POST', json: { member_id: p.member_id, note: p.note } });
      else if (p.kind === 'todo') await api('/todos', { method: 'POST', json: { title: p.title, due_date: p.due_date, due_time: p.due_time, assigned_to: p.member_id, note: p.note } });
      else if (p.kind === 'handled') await api('/artifacts/' + p.artifact_id + '/handled', { method: 'POST', json: { note: p.note } });
      else if (p.kind === 'plan') { b.textContent = 'Planning\u2026'; const made = await api('/plans', { method: 'POST', json: { brief: p.brief, shape: p.shape || 'trip' } }); p.done = true; writeThread(thread); go('/plans/' + made.id); return; }
      else if (p.kind === 'errand') { const made = await api('/errands', { method: 'POST', json: { service: p.service, kind: p.look ? 'look' : 'booking', title: p.title || p.what, spec: { what: p.what || p.title, details: p.details, when: { date: p.due_date, time: p.due_time ? String(p.due_time).slice(0, 5) : null, part: p.part || 'any' }, max_amount: p.max_amount, currency: p.currency || 'INR', payment: 'pay_after_service' } } }); p.done = true; writeThread(thread); go('/errands/' + made.id); return; }
      else await api('/obligations/' + p.obligation_id + '/decision', { method: 'POST', json: { status: p.status } });
      p.done = true;
      flash(p.kind === 'assign' ? 'Handed over.' : p.kind === 'todo' ? 'Added.' : p.kind === 'handled' ? 'Handled.' : p.kind === 'plan' ? 'Planned.' : 'Decided.');
      const todos = await api('/todos').catch(() => null);
      if (todos) { const box = main.querySelector('[data-todos]'); if (box) { box.innerHTML = todosCardBody(todos); wireTodos(main); } }
    } catch (err) {
      b.disabled = false;
      flash((err && err.message) || 'That did not go through.', true);
      return;
    }
    writeThread(thread); paint();
  }));
}

/* to-dos: the family's own, shared, with a tick */
function todosRail(todos) {
  const shown = todos.slice(0, 8);
  return '<div class="row" style="gap:8px"><h2 style="margin:0">To do</h2><span class="muted" style="margin-left:auto">' + (todos.length ? todos.length + ' open' : 'none open') + '</span></div>'
    + (shown.length ? '<div class="stack" style="gap:2px">' + shown.map((t) => '<label class="todo"><input type="checkbox" data-todo="' + esc(t.id) + '">'
      + '<span class="row" style="gap:8px;flex-grow:1;min-width:0"><span class="grow" style="font-size:13.5px">' + esc(t.title) + '</span>'
      + (t.due_date ? '<span class="muted" style="white-space:nowrap;color:var(--primary)">' + esc(fmtDate(t.due_date).replace(/,.*$/, '')) + '</span>' : '') + '</span></label>').join('') + '</div>'
      : '<p class="muted">Say “add a to-do” in Ask, or add one in Life.</p>')
    + (todos.length > 8 ? '<a class="muted" href="#/life" style="align-self:flex-end">View all \u2192</a>' : '');
}

function todosCardBody(todos) {
  return '<div class="row wrap" style="gap:8px"><h2>To-dos</h2><span class="muted">' + (todos.length ? todos.length + ' open' : 'none open') + '</span></div>'
    + (todos.length ? '<div class="stack" style="gap:6px">' + todos.map((t) => '<label class="todo"><input type="checkbox" data-todo="' + esc(t.id) + '">'
      + '<span><span>' + esc(t.title) + '</span>'
      + '<span class="muted">' + [t.due_date ? 'by ' + fmtDate(t.due_date) + (t.due_time ? ' ' + t.due_time.slice(0, 5) : '') : '', memberName(t.assigned_to) || '', t.calendar_event_id ? 'on your calendar' : ''].filter(Boolean).join(' · ') + '</span></span></label>').join('') + '</div>'
      : '<p class="muted">Say “add a to-do” in the chat, or add one here.</p>')
    + '<form class="row" style="gap:6px;margin-top:10px" data-todo-form><input type="text" name="title" placeholder="A to-do" maxlength="200" required style="flex:1">'
    + '<button class="btn ghost sm" type="submit">Add</button></form>';
}

function paintTodos(box, todos) {
  box.innerHTML = box.dataset.todos === 'rail' ? todosRail(todos.filter((t) => !t.done_at)) : todosCardBody(todos);
}
function wireTodos(main) {
  main.querySelectorAll('[data-todo]').forEach((cb) => cb.addEventListener('change', async () => {
    try { await api('/todos/' + cb.dataset.todo, { method: 'PATCH', json: { done: cb.checked } }); } catch (err) { cb.checked = !cb.checked; flash(err.message, true); return; }
    const todos = await api('/todos').catch(() => null);
    const box = main.querySelector('[data-todos]');
    if (todos && box) { paintTodos(box, todos); wireTodos(main); }
  }));
  const form = main.querySelector('[data-todo-form]');
  if (form) form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const title = new FormData(form).get('title').trim();
    if (!title) return;
    try { await api('/todos', { method: 'POST', json: { title } }); } catch (err) { flash(err.message, true); return; }
    const todos = await api('/todos').catch(() => null);
    const box = main.querySelector('[data-todos]');
    if (todos && box) { paintTodos(box, todos); wireTodos(main); }
  });
}

async function loadTodosCard(main, selector) {
  const aside = main.querySelector(selector || 'aside');
  if (!aside) return;
  let todos;
  try { todos = await api('/todos'); } catch (e) { return; }
  const card = document.createElement('section');
  card.className = 'card rail-card';
  card.setAttribute('data-todos', '');
  card.innerHTML = todosCardBody(todos);
  aside.insertBefore(card, aside.firstChild);
  wireTodos(main);
}


/* "Mark handled": the answer to a hand-over, with a word back for whoever asked. */
function openHandled(main, artifact) {
  let dlg = main.querySelector('dialog[data-handled-dialog]');
  if (!dlg) {
    main.insertAdjacentHTML('beforeend', '<dialog class="dialog" data-handled-dialog><form method="dialog" class="stack" data-handled-form>'
      + '<h2>Mark as handled</h2><p class="muted" data-handled-what></p>'
      + '<label>A word back<textarea name="note" rows="3" maxlength="500" placeholder="Paid, ref 4471. / Sent the form on Tuesday."></textarea></label>'
      + '<div class="row" style="justify-content:flex-end;gap:8px"><button class="btn ghost" value="cancel" formnovalidate>Cancel</button>'
      + '<button class="btn" value="ok">Handled</button></div></form></dialog>');
    dlg = main.querySelector('dialog[data-handled-dialog]');
    dlg.querySelector('[data-handled-form]').addEventListener('submit', async (ev) => {
      if (ev.submitter && ev.submitter.value === 'cancel') return;
      ev.preventDefault();
      const note = new FormData(ev.target).get('note').trim();
      try {
        await api('/artifacts/' + dlg.dataset.artifact + '/handled', { method: 'POST', json: { note: note || null } });
        dlg.close(); flash('Handled.'); render();
      } catch (err) { flash(err.message, true); }
    });
  }
  dlg.dataset.artifact = artifact.id;
  const who = artifact.assigned_by && artifact.assigned_by !== (store.me || {}).id ? memberName(artifact.assigned_by) : null;
  dlg.querySelector('[data-handled-what]').textContent = (artifact.filename || (artifact.source && artifact.source.subject) || 'This notice')
    + (who ? ' — ' + who + ' will be told.' : '');
  dlg.querySelector('textarea').value = '';
  dlg.showModal();
}


/* The Sunday digest: the week ahead, where the family already is. */
/* The household's rules: sentences with switches, and what the household has
   taught by a tap. Not a builder; a family flips a switch once, at most. */
function rulesCard() {
  return '<section class="card pad stack" data-rules style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Rules</h2>'
    + '<span class="muted">what this household has decided</span></div>'
    + '<div class="stack" data-rules-list style="gap:10px"><p class="muted">…</p></div>'
    + '<div data-rules-learned></div></section>';
}

function wireRules(main) {
  const box = main.querySelector('[data-rules]');
  if (!box) return;
  const isGuardian = store.me && store.me.role === 'guardian';
  const paint = (r) => {
    box.querySelector('[data-rules-list]').innerHTML = r.rules.map((x) =>
      '<div class="stack" style="gap:4px;padding:8px 0;border-top:1px solid var(--line)">'
      + '<div class="row wrap" style="gap:8px"><strong style="font-size:13px">' + esc(x.title) + '</strong>'
      + '<span class="tag ' + (x.on ? 'kid' : '') + '">' + (x.fixed ? esc(x.why_fixed || 'built in') : x.on ? 'on' : 'off') + '</span>'
      + (x.kind === 'place'
        ? '<a class="muted" href="#/notices" style="margin-left:auto;font-size:12px">' + (x.text ? 'change' : 'set') + ' on the Household card</a>'
        : isGuardian && x.kind === 'text'
        ? '<input class="pill sm" style="margin-left:auto;min-width:180px" data-rule-text="' + esc(x.key) + '" value="' + esc(x.text || '') + '" placeholder="Town or city" aria-label="' + esc(x.title) + '">'
        : isGuardian && !x.fixed && x.options
        ? '<select class="pill sm" style="margin-left:auto" data-rule-who="' + esc(x.key) + '"><option value=""' + (x.member_id ? '' : ' selected') + '>Nobody</option>'
          + x.options.map((o) => '<option value="' + esc(o.id) + '"' + (o.id === x.member_id ? ' selected' : '') + '>' + esc(o.name) + '</option>').join('') + '</select>'
        : isGuardian && !x.fixed
        ? '<button class="btn ghost sm" style="margin-left:auto" data-rule-key="' + esc(x.key) + '" data-rule-on="' + (x.on ? '1' : '') + '">'
          + (x.on ? 'Turn off' : 'Turn on') + '</button>'
        : '')
      + '</div><p class="muted" style="font-size:13px;line-height:1.45;margin:0">' + esc(x.sentence) + '</p></div>').join('');
    box.querySelector('[data-rules-learned]').innerHTML = r.learned.length
      ? '<p style="font-size:13px;font-weight:600;margin:6px 0 4px">Taught by a tap</p>'
        + r.learned.map((l) => '<p class="muted" style="font-size:13px;margin:0 0 4px">' + esc(l.label) + ' ' + esc(l.says) + '</p>').join('')
      : '<p class="muted" style="font-size:12px">Nothing taught yet. When a notice asks “which school sent this?”, answering remembers the group.</p>';
    box.querySelectorAll('[data-rule-who]').forEach((sel) => sel.addEventListener('change', async () => {
      const patch = {}; patch[sel.dataset.ruleWho] = sel.value || null;
      try { paint(await api('/household/rules', { method: 'PUT', json: patch })); flash(sel.value ? 'From now on.' : 'Nobody, from now on.'); }
      catch (err) { fail(err); }
    }));
    box.querySelectorAll('[data-rule-text]').forEach((inp) => inp.addEventListener('change', async () => {
      const patch = {}; patch[inp.dataset.ruleText] = inp.value.trim() || null;
      try { paint(await api('/household/rules', { method: 'PUT', json: patch })); flash(inp.value.trim() ? 'Home is set.' : 'Home cleared.'); }
      catch (err) { fail(err); }
    }));
    box.querySelectorAll('[data-rule-key]').forEach((b) => b.addEventListener('click', async () => {
      b.disabled = true;
      const patch = {}; patch[b.dataset.ruleKey] = !b.dataset.ruleOn;
      try {
        paint(await api('/household/rules', { method: 'PUT', json: patch }));
        flash(b.dataset.ruleOn ? 'Off from now.' : 'On from now.');
      } catch (err) { fail(err); b.disabled = false; }
    }));
  };
  api('/household/rules').then(paint).catch((err) => { box.querySelector('[data-rules-list]').innerHTML = '<p class="muted">' + esc(err.message) + '</p>'; });
}

function weeklyDigestCard() {
  return '<section class="card pad" data-digest><div class="row wrap" style="gap:8px"><h2>Weekly digest</h2>'
    + '<span class="muted" data-digest-when>…</span></div>'
    + '<p class="muted" style="font-size:13px;margin:6px 0 10px">The week ahead, as it would be sent. Whether it goes on Sunday is a rule above.</p>'
    + '<pre class="digest-preview" data-digest-body hidden></pre>'
    + '<div class="row" style="gap:8px"><button class="btn ghost sm" data-digest-preview>Preview mine</button>'
    + '<button class="btn sm" data-digest-send>Send me this week’s now</button></div></section>';
}

function wireDigest(main) {
  const box = main.querySelector('[data-digest]');
  if (!box) return;
  const when = box.querySelector('[data-digest-when]');
  const body = box.querySelector('[data-digest-body]');
  api('/digest').then((d) => { const t = d.sends_on.replace(/^Weekly digest is on: /, ''); when.textContent = t.charAt(0).toUpperCase() + t.slice(1); body.textContent = d.subject + '\n\n' + d.body; })
    .catch(() => { when.textContent = ''; });
  box.querySelector('[data-digest-preview]').addEventListener('click', () => { body.hidden = !body.hidden; });
  box.querySelector('[data-digest-send]').addEventListener('click', async (ev) => {
    ev.target.disabled = true;
    try {
      const r = await api('/digest/send', { method: 'POST' });
      flash(r.sent ? 'Sent over ' + r.channel + '.' : (r.why || 'Nothing could carry it — link Telegram or add an email.'), !r.sent);
    } catch (err) { flash(err.message, true); }
    ev.target.disabled = false;
  });
}


/* ---------------------------------------------------------------------------
   Plans: the open-ended ask. Written with the household in view; booked by
   the household, in the provider's own app.
   --------------------------------------------------------------------------- */

const OPTION_KIND = { flight: 'Flight', stay: 'Stay', transport: 'Getting around', activity: 'Things to do', insurance: 'Insurance', visa: 'Visa', grocery: 'Groceries' };

async function plansView(main) {
  main.classList.remove('chat-main');
  const plans = await api('/plans');
  main.innerHTML = '<div class="head"><div><h1>Plans</h1>'
    + '<p>Open-ended things \u2014 a trip, a week of meals, a move \u2014 planned with this household\u2019s dates and budget in view. '
    + 'Candidate bookings are pages to open; the legwork is to-dos; the confirmation lands in the Inbox. Nothing here books or pays.</p></div>'
    + '<button class="btn" data-newplan>Plan something</button></div>'
    + '<div class="stack" style="gap:10px" data-plans>'
    + (plans.length ? plans.map(planCard).join('') : '<div class="card empty">Nothing planned yet. Try “plan a week in Switzerland in the Diwali break, under ₹4 lakh”.</div>')
    + '</div>'
    + '<dialog class="dialog" data-plan-dialog><form method="dialog" class="stack" data-plan-form>'
    + '<h2>Plan something</h2><p class="muted">Say where, when, who and roughly how much. The plan uses what the household already knows — the dates spoken for, the ages, what goes out every month.</p>'
    + '<div class="pills" style="margin-bottom:8px"><label class="pill"><input type="radio" name="shape" value="trip" checked> A trip</label>'
    + '<label class="pill"><input type="radio" name="shape" value="meals"> This week\u2019s meals</label>'
    + '<label class="pill"><input type="radio" name="shape" value="other"> Something else</label></div>'
    + '<label>The ask<textarea name="brief" rows="4" maxlength="2000" placeholder="A week in Switzerland in the Diwali break, two adults and two kids, under ₹4 lakh." required></textarea></label>'
    + '<div class="row" style="justify-content:flex-end;gap:8px"><button class="btn ghost" value="cancel" formnovalidate>Cancel</button><button class="btn" value="ok" data-plan-go>Write the plan</button></div></form></dialog>';
  const dlg = main.querySelector('[data-plan-dialog]');
  main.querySelector('[data-newplan]').addEventListener('click', () => dlg.showModal());
  dlg.querySelector('[data-plan-form]').addEventListener('submit', async (ev) => {
    if (ev.submitter && ev.submitter.value === 'cancel') return;
    ev.preventDefault();
    const brief = new FormData(ev.target).get('brief').trim();
    if (!brief) return;
    const btn = dlg.querySelector('[data-plan-go]'); btn.disabled = true; btn.textContent = 'Asking…';
    const shape = new FormData(ev.target).get('shape') || 'trip';
    try { const made = await api('/plans', { method: 'POST', json: { brief, shape } }); dlg.close(); go('/plans/' + made.id); }
    catch (err) { btn.disabled = false; btn.textContent = 'Write the plan'; flash(err.message, true); }
  });
}

function planCard(pl) {
  const when = pl.starts_on ? fmtDate(pl.starts_on).replace(/,.*$/, '') + (pl.ends_on ? ' \u2013 ' + fmtDate(pl.ends_on).replace(/,.*$/, '') : '') : 'dates open';
  const open = (pl.todos || []).filter((t) => !t.done_at).length;
  const hue = pl.shape === 'meals' ? 'home' : 'travel';
  return '<a class="card pad lift ptile" href="#/plans/' + esc(pl.id) + '">'
    + '<span class="ic h-' + hue + '">' + icon(pl.shape === 'meals' ? 'cart' : 'travel', 20) + '</span>'
    + '<span class="grow"><span class="row wrap" style="gap:8px"><b style="font-size:15px">' + esc(pl.title) + '</b>'
    + '<span class="tag ' + (pl.status === 'active' ? 'green' : pl.status === 'failed' ? 'red' : pl.status === 'writing' ? 'amber' : '') + '">' + esc(pl.status === 'writing' ? 'writing\u2026' : pl.status) + '</span></span>'
    + '<span class="muted" style="display:block;margin-top:4px">' + esc(when) + (pl.budget_amount ? ' \u00B7 ' + esc(money(pl.budget_amount, pl.budget_currency)) : '') + '</span>'
    + '<span class="row wrap" style="gap:6px;margin-top:8px"><span class="tag line">' + (pl.options || []).length + ' to book</span><span class="tag line">' + open + ' to do</span></span></span></a>';
}

/* A plan still being written, or one that failed: the ask, the clock, a way to ask again.
   Removed by mistake in the redesign (840dfef) while planView still called it; restored 11 Oct 2026. */
function planWritingView(main, pl) {
  const started = new Date(pl.created_at).getTime();
  const failed = pl.status === 'failed';
  main.innerHTML = '<div class="head"><div>'
    + '<p class="muted" style="margin-bottom:6px"><a href="#/plans" style="color:var(--ink-3);text-decoration:none">Plans</a></p>'
    + '<h1>' + (failed ? 'The plan could not be written' : 'Writing the plan\u2026') + '</h1></div></div>'
    + '<section class="card pad stack" style="gap:12px;max-width:720px">'
    + '<p class="muted" style="font-size:12px">The ask</p><p style="line-height:1.6">\u201c' + esc(pl.brief) + '\u201d</p>'
    + (failed
      ? '<p class="muted" style="color:var(--red)">' + esc(pl.error || 'No reason was recorded.') + '</p>'
        + '<div class="row" style="gap:8px"><button class="btn" data-plan-again>Ask again</button>'
        + '<a class="btn ghost" href="#/plans">Back to plans</a></div>'
      : '<p class="row" style="gap:10px;color:var(--ink-2)"><span class="dots"><i></i><i></i><i></i></span>'
        + '<span>Reading the household\u2019s dates and what goes out every month, then the candidate pages. '
        + 'About a minute \u2014 <span data-elapsed>0</span>s so far.</span></p>'
        + '<p class="muted" style="font-size:12px">You can leave this page; the plan will be in the list when it is done.</p>')
    + '</section>';
  const again = main.querySelector('[data-plan-again]');
  if (again) again.addEventListener('click', async () => {
    again.disabled = true;
    try { const made = await api('/plans', { method: 'POST', json: { brief: pl.brief, shape: pl.shape || 'trip' } }); go('/plans/' + made.id); }
    catch (err) { again.disabled = false; flash(err.message, true); }
  });
  if (failed) return;
  const here = location.hash;
  const tick = () => { const el = main.querySelector('[data-elapsed]'); if (el) el.textContent = String(Math.max(0, Math.round((Date.now() - started) / 1000))); };
  const timer = setInterval(() => { if (location.hash !== here || !document.body.contains(main)) { clearInterval(timer); return; } tick(); }, 1000);
  const poll = async () => {
    if (location.hash !== here || !document.body.contains(main)) return;
    let now = null;
    try { now = await api('/plans/' + pl.id); } catch (e) { /* try again next time */ }
    if (now && now.status !== 'writing') { clearInterval(timer); render(); return; }
    setTimeout(poll, 3000);
  };
  setTimeout(poll, 3000);
}

async function planView(main, args) {
  main.classList.remove('chat-main');
  const pl = await api('/plans/' + args[0]);
  if (pl.status === 'writing' || pl.status === 'failed') { planWritingView(main, pl); return; }
  const when = pl.starts_on ? fmtDate(pl.starts_on) + (pl.ends_on ? ' – ' + fmtDate(pl.ends_on) : '') : 'dates open';
  const kinds = [...new Set(pl.options.map((o) => o.kind))];
  main.innerHTML = '<div class="head"><div>'
    + '<p class="muted" style="margin-bottom:6px"><a href="#/plans" style="color:var(--ink-3);text-decoration:none">Plans</a></p>'
    + '<h1>' + esc(pl.title) + '</h1>'
    + '<p class="row wrap" style="gap:8px;margin-top:8px"><span class="tag ' + (pl.status === 'active' ? 'green' : 'line') + '">' + esc(pl.status) + '</span>'
    + '<span class="muted">' + esc(when) + '</span>' + (pl.budget_amount ? '<span class="muted">· budget ' + esc(money(pl.budget_amount, pl.budget_currency)) + '</span>' : '')
    + '<span class="muted">· by ' + esc(memberName(pl.created_by) || 'someone') + '</span></p></div>'
    + '<div class="row" style="gap:8px">'
    + (pl.status !== 'done' ? '<button class="btn ghost" data-status="done">Mark done</button>' : '')
    + (pl.status !== 'dropped' ? '<button class="btn ghost" data-status="dropped">Drop</button>' : '')
    + '</div></div>'
    + '<div class="home"><div class="stack" style="gap:16px">'
    + (pl.summary ? '<section class="card pad"><p style="line-height:1.6">' + esc(pl.summary) + '</p>'
      + '<p class="muted" style="font-size:12px;margin-top:8px">Written from the brief: “' + esc(pl.brief) + '”. Prices are the pages’ own words when last read, not quotes.</p></section>' : '')
    + '<section class="card pad"><h2>' + (pl.shape === 'meals' ? 'The week' : 'Itinerary') + '</h2><div class="stack" style="gap:8px;margin-top:8px">'
    + pl.itinerary.map((d) => '<div class="row" style="gap:12px;align-items:flex-start"><span class="muted" style="width:70px;flex-shrink:0">Day ' + d.day + (d.date ? '<br><span style="font-size:11.5px">' + esc(fmtDate(d.date)) + '</span>' : '') + '</span>'
      + '<span><b>' + esc(d.title) + '</b>' + (d.notes ? '<br><span class="muted">' + esc(d.notes) + '</span>' : '') + '</span></div>').join('')
    + '</div></section>'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>' + (pl.shape === 'meals' ? 'Groceries to order' : 'Bookings to make') + '</h2><span class="muted">' + (pl.shape === 'meals' ? 'one tap on the shop you already use' : 'you open, you pay — in the provider’s own app') + '</span></div>'
    + kinds.map((k) => '<h3 class="muted" style="margin-top:14px">' + esc(OPTION_KIND[k] || k) + '</h3>'
      + '<div class="stack" style="gap:8px">' + pl.options.filter((o) => o.kind === k).map((o) => optionRow(pl, o)).join('') + '</div>').join('')
    + (pl.options.length ? '' : '<p class="muted">No candidate pages were found for this plan.</p>')
    + '</section>'
    + '</div><aside class="stack" style="gap:14px">'
    + '<section class="card rail-card" data-todos>' + todosCardBody(pl.todos.filter((t) => !t.done_at).map((t) => ({ ...t, assigned_to: t.assigned_to }))) + '</section>'
    + '<section class="card rail-card"><h2>When something is booked</h2><p class="muted">Tick “Booked” on the option. The confirmation email arrives in the Inbox like any other notice, its dates become things to decide, and the page stops being watched.</p></section>'
    + '</aside></div>';
  main.querySelectorAll('[data-status]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/plans/' + pl.id, { method: 'PATCH', json: { status: b.dataset.status } }); render(); } catch (err) { flash(err.message, true); }
  }));
  main.querySelectorAll('[data-choose]').forEach((b) => b.addEventListener('click', async () => {
    b.disabled = true;
    try { await api('/plans/' + pl.id + '/choose', { method: 'POST', json: { option_id: b.dataset.choose, booked: b.dataset.booked === '1' } }); flash(b.dataset.booked === '1' ? 'Booked. Watch for the confirmation in the Inbox.' : 'Chosen.'); render(); }
    catch (err) { b.disabled = false; flash(err.message, true); }
  }));
  wireTodos(main);
}

function optionRow(pl, o) {
  const page = o.page;
  const said = page && page.checked_at
    ? (page.error ? '<span class="tag amber">could not read</span> <span class="muted">' + esc(page.error) + '</span>'
      : (page.found ? '<span class="tag green">page read ' + esc(ago(page.checked_at)) + '</span> <span class="muted">“' + esc((page.excerpt || '').slice(0, 160)) + '…”</span>'
        : '<span class="tag">read ' + esc(ago(page.checked_at)) + ' · “' + esc(o.look_for || '') + '” not on the page</span>'))
    : (o.watch_id ? '<span class="tag">watching · not read yet</span>' : '');
  return '<div class="option' + (o.chosen ? ' chosen' : '') + '">'
    + '<div class="grow"><b>' + esc(o.label) + '</b> <span class="muted">· ' + esc(o.provider) + '</span>'
    + (o.estimate ? ' <span class="muted">· est. ' + esc(money(o.estimate, o.currency)) + '</span>' : '')
    + (o.note ? '<br><span class="muted">' + esc(o.note) + '</span>' : '')
    + (o.evidence ? '<br><span class="evidence"><a href="' + esc(o.evidence.url) + '" target="_blank" rel="noopener">' + esc(o.evidence.title || host(o.evidence.url)) + '</a>'
      + ' <span class="muted">read ' + esc(ago(o.evidence.read_at)) + '</span>' + (o.evidence.excerpt ? '<br><span class="muted">\u201C' + esc(o.evidence.excerpt.slice(0, 220)) + (o.evidence.excerpt.length > 220 ? '\u2026' : '') + '\u201D</span>' : '') + '</span>' : '')
    + (said ? '<br>' + said : '') + '</div>'
    + '<div class="row" style="gap:6px;flex-shrink:0">'
    + '<a class="btn ghost sm" href="' + esc(o.url) + '" target="_blank" rel="noopener">' + (o.kind === 'grocery' ? 'Add to cart ↗' : 'Open to book ↗') + '</a>'
    + (o.booked_at ? '<span class="tag green">booked</span>'
      : '<button class="btn sm' + (o.chosen ? '' : ' ghost') + '" data-choose="' + esc(o.id) + '" data-booked="1">' + (o.kind === 'grocery' ? 'Bought' : 'Booked') + '</button>')
    + '</div></div>';
}


/* From your phone: the share sheet and Shortcuts, with a token the phone holds. */
function docRow(d) {
  const tone = { ok: 'green', expiring: 'amber', expired: 'red', undated: '' }[d.status] || '';
  const word = { ok: 'valid', expiring: d.days_left != null ? 'renew, ' + d.days_left + ' days left' : 'renew soon', expired: 'expired', undated: 'no expiry read' }[d.status] || d.status;
  return '<a class="mrow slim" href="#/notices/' + esc(d.artifact_id) + '" style="text-decoration:none;color:inherit">'
    + '<span class="mtile h-' + (d.kind === 'insurance' ? 'health' : d.kind === 'passport' || d.kind === 'visa' ? 'travel' : 'home') + '">' + icon(d.kind === 'passport' || d.kind === 'visa' ? 'travel' : d.kind === 'insurance' ? 'health' : 'doc', 15) + '</span>'
    + '<span class="grow" style="min-width:0"><span class="t">' + esc(d.title) + '</span>'
    + '<div class="s">' + esc([d.holder_name, d.issuer, d.identifier_tail ? '\u2026' + d.identifier_tail : null].filter(Boolean).join(' \u00B7 ') || d.label) + '</div></span>'
    + '<span class="when"><b>' + (d.expires_on ? esc(fmtDate(d.expires_on).replace(/,.*$/, '')) : '\u2014') + '</b><span class="tag ' + tone + '">' + esc(word) + '</span></span></a>';
}

function documentsCard() {
  return '<section class="card pad stack" data-documents style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Documents</h2>'
    + '<span class="muted">passports, policies, the car \u00B7 last four of a number only</span></div>'
    + '<div data-documents-list><p class="muted">\u2026</p></div></section>';
}

async function wireDocuments(main) {
  const box = main.querySelector('[data-documents-list]');
  if (!box) return;
  let data;
  try { data = await api('/documents'); } catch (err) { box.innerHTML = '<p class="muted">' + esc(err.message) + '</p>'; return; }
  box.innerHTML = (data.checks || []).map((c) => '<div class="insight" style="margin-bottom:10px"><div class="k"><span class="star">' + icon('sparkle', 14) + '</span> FamilyOS noticed</div>'
      + '<h3>' + esc(c.title) + '</h3><p>' + esc(c.why) + '</p><div class="acts"><a class="btn ghost sm" href="#/notices/' + esc(c.artifact_id) + '" style="text-decoration:none">Show me</a></div></div>').join('')
    + ((data.documents || []).length ? '<div class="mlist">' + data.documents.map(docRow).join('') + '</div>'
      : '<p class="muted" style="line-height:1.55">Share a passport\u2019s photo page, a policy PDF, the RC or the PUC from the phone and it is kept here with its dates. '
        + 'A renewal is proposed before it runs out, and a trip\u2019s dates are checked against the passports that would travel.</p>');
}

function phoneCard() {
  return '<div class="card pad stack" style="gap:10px" data-phone>'
    + '<div class="row wrap" style="gap:8px"><h2>From your phone</h2><span class="muted">share sheet · shortcuts</span></div>'
    + '<p class="muted" style="line-height:1.55">“Send to FamilyOS” in any app’s share sheet, and automations that send a bank SMS or a school email on their own. '
    + 'Each phone gets its own token: shown once, never expires, revoked here. What it sends is yours and private until you share it.</p>'
    + '<div class="stack" style="gap:6px" data-devices></div>'
    + '<form class="row" style="gap:6px" data-device-form><input type="text" name="label" placeholder="Arun’s iPhone" maxlength="80" required style="flex:1">'
    + '<button class="btn sm" type="submit">New phone token</button></form>'
    + '<div class="card" style="padding:12px;background:var(--sunk)" data-device-issued hidden></div>'
    + '<details><summary class="muted" style="cursor:pointer">How to set up the shortcut (iPhone, 2 minutes)</summary>'
    + '<ol class="muted" style="line-height:1.6;padding-left:18px;margin-top:8px">'
    + '<li>Shortcuts app → <b>+</b> → name it <b>Send to FamilyOS</b>.</li>'
    + '<li>Tap <b>ⓘ</b> → turn on <b>Show in Share Sheet</b>. In the <i>Receive</i> action pick Text, URLs, Images, PDFs, Files.</li>'
    + '<li>Add the action <b>Get Contents of URL</b>: URL = the address below; Method <b>POST</b>; Headers: <code>Authorization</code> = <code>Bearer &lt;your token&gt;</code>; Request Body <b>Form</b>, one field <code>item</code> = <i>Shortcut Input</i>, with the field\u2019s type set to <b>File</b> (tap the field, choose File), so a photo or a PDF travels as the file and not as its name. '
    + 'If the File field will not take Shortcut Input, set Request Body to <b>File</b> instead, with <i>Shortcut Input</i> as the file, and put the tag in a header <code>X-Tag</code> = <i>Chosen Item</i>.</li>'
    + '<li>To tag as you share: add <b>Choose from List</b> <i>before</i> Get Contents of URL with the children\u2019s names and \u201CNobody\u201D, and add a second form field <code>tag</code> = <i>Chosen Item</i>. One share, already tagged.</li>'
    + '<li>Add <b>Show Notification</b> after it, with its text set to <i>Contents of URL</i> \u2192 <i>message</i>, so each share says what happened (\u201CSaved to your Inbox\u201D, \u201CTagged: Varali\u201D).</li>'
    + '<li>Done. In WhatsApp: press and hold a message → Share → <b>Send to FamilyOS</b>. Type a child’s name and share that too, and the notice is theirs.</li>'
    + '<li>Bank SMS, hands-free: Shortcuts → Automation → <b>Message</b> → <i>Message Contains</i> “debited” → Run Immediately → the same Get Contents of URL with field <code>text</code> = <i>Shortcut Input</i>.</li>'
    + '</ol><p class="muted">Address: <code data-share-url>…</code></p></details>'
    + '</div>';
}

async function wirePhone(main) {
  const box = main.querySelector('[data-phone]');
  if (!box) return;
  const list = box.querySelector('[data-devices]');
  const issued = box.querySelector('[data-device-issued]');
  const paint = async () => {
    const devices = await api('/devices').catch(() => []);
    list.innerHTML = devices.length ? devices.map((d) => '<div class="row" style="gap:10px;padding:8px 11px;background:var(--sunk);border:1px solid var(--line-soft);border-radius:7px">'
      + '<span class="grow"><b style="font-size:12.5px">' + esc(d.label || 'A phone') + '</b><span class="sub">' + (d.last_used_at ? 'last used ' + esc(ago(d.last_used_at)) : 'not used yet') + ' · added ' + esc(ago(d.created_at)) + '</span></span>'
      + '<button class="btn ghost sm" data-revoke="' + esc(d.id) + '">Revoke</button></div>').join('')
      : '<p class="muted" style="font-size:12.5px">No phone tokens yet.</p>';
    list.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', async () => {
      b.disabled = true;
      try { await api('/devices/' + b.dataset.revoke, { method: 'DELETE' }); flash('Revoked. The shortcut on that phone stops working.'); paint(); }
      catch (err) { b.disabled = false; flash(err.message, true); }
    }));
  };
  paint();
  box.querySelector('[data-device-form]').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const label = new FormData(ev.target).get('label').trim();
    if (!label) return;
    try {
      const out = await api('/devices', { method: 'POST', json: { label } });
      issued.hidden = false;
      issued.innerHTML = '<p style="font-size:12.5px;margin-bottom:6px"><b>' + esc(out.device.label) + '</b> — copy this token into the shortcut now. It is not shown again.</p>'
        + '<div class="row" style="gap:6px"><code style="flex:1;word-break:break-all;font-size:12px">' + esc(out.token) + '</code><button class="btn sm" data-copy-token>Copy</button></div>'
        + '<p class="muted" style="font-size:12px;margin-top:6px">Address: <code>' + esc(out.share_url) + '</code></p>';
      issued.querySelector('[data-copy-token]').addEventListener('click', () => { navigator.clipboard.writeText(out.token).then(() => flash('Copied.')); });
      box.querySelector('[data-share-url]').textContent = out.share_url;
      ev.target.reset(); paint();
    } catch (err) { flash(err.message, true); }
  });
  box.querySelector('[data-share-url]').textContent = location.origin + '/v1/inbound/share';
}


/* Offers: what FamilyOS could start doing, or is about to, in the family's own
   names. Accept flips the switch or opens Ask with the question; Not now is
   remembered. Each says what it will do and what it will not. */
async function loadOffersCard(host) {
  if (!host) return;
  let items;
  try { items = await api('/offers'); } catch (e) { return; }
  if (!items.length) return;
  const card = document.createElement('section');
  card.className = 'card'; card.style.marginTop = '16px';
  const paint = () => {
    card.innerHTML = '<div class="row wrap" style="gap:8px"><h2>Offers</h2><span class="muted">from what the record shows · switch on, or not now</span></div>'
      + '<div class="stack" style="gap:12px;margin-top:10px">' + items.map((x) => '<div class="suggest" data-key="' + esc(x.key) + '" style="align-items:flex-start">'
        + '<div style="min-width:0"><b>' + esc(x.title) + '</b><br><span class="muted">' + esc(x.body) + '</span><br><span class="muted" style="font-style:italic">' + esc(x.limit) + '</span></div>'
        + '<div class="row" style="gap:4px;flex-shrink:0">'
        + (x.fyi ? '<button class="btn ghost sm" data-dismiss>Noted</button>'
                 : '<button class="btn sm" data-accept>' + esc(x.accept_label || 'Yes') + '</button><button class="btn ghost sm" data-dismiss>Not now</button>')
        + '</div></div>').join('')
      + '</div>';
    card.querySelectorAll('[data-accept]').forEach((b) => b.addEventListener('click', async () => {
      const key = b.closest('[data-key]').dataset.key; b.disabled = true;
      try {
        const out = await api('/offers/' + encodeURIComponent(key) + '/accept', { method: 'POST' });
        items = items.filter((x) => x.key !== key); items.length ? paint() : card.remove();
        if (out.ask) openAsk(out.ask);
        else flash(out.done);
      } catch (err) { b.disabled = false; flash(err.message, true); }
    }));
    card.querySelectorAll('[data-dismiss]').forEach((b) => b.addEventListener('click', async () => {
      const key = b.closest('[data-key]').dataset.key;
      try { await api('/offers/' + encodeURIComponent(key) + '/dismiss', { method: 'POST' }); items = items.filter((x) => x.key !== key); items.length ? paint() : card.remove(); }
      catch (err) { flash(err.message, true); }
    }));
  };
  paint();
  host.appendChild(card);
}

/* Suggested: what the calendar implies. Add makes a to-do; the cross is remembered. */
async function loadSuggestionsCard(main, selector) {
  const aside = main.querySelector(selector || 'aside');
  if (!aside) return;
  let items;
  try { items = await api('/suggestions'); } catch (e) { return; }
  if (!items.length) return;
  const card = document.createElement('section');
  card.className = 'card rail-card';
  const paint = () => {
    card.innerHTML = '<div class="row wrap" style="gap:8px"><h2>Worth doing</h2><span class="muted">implied by what’s coming</span></div>'
      + '<div class="stack" style="gap:8px">' + items.map((x) => '<div class="suggest" data-key="' + esc(x.key) + '">'
        + '<div><b>' + esc(x.title) + '</b><br><span class="muted">by ' + esc(fmtDate(x.due_date)) + ' · ' + esc(x.why) + '</span>'
        + (x.link ? ' <a class="muted" href="' + esc(x.link) + '" target="_blank" rel="noopener">options ↗</a>' : '') + '</div>'
        + '<div class="row" style="gap:4px;flex-shrink:0"><button class="btn sm" data-accept>Add</button><button class="btn ghost sm" data-dismiss aria-label="Not needed">' + icon('x', 14) + '</button></div></div>').join('')
      + '</div>';
    card.querySelectorAll('[data-accept]').forEach((b) => b.addEventListener('click', async () => {
      const key = b.closest('[data-key]').dataset.key; b.disabled = true;
      try { await api('/suggestions/' + encodeURIComponent(key) + '/accept', { method: 'POST', json: {} }); flash('Added to to-dos.'); items = items.filter((x) => x.key !== key); items.length ? paint() : card.remove();
        const todos = await api('/todos').catch(() => null); const box = main.querySelector('[data-todos]'); if (todos && box) { box.innerHTML = todosCardBody(todos); wireTodos(main); } }
      catch (err) { b.disabled = false; flash(err.message, true); }
    }));
    card.querySelectorAll('[data-dismiss]').forEach((b) => b.addEventListener('click', async () => {
      const key = b.closest('[data-key]').dataset.key;
      try { await api('/suggestions/' + encodeURIComponent(key) + '/dismiss', { method: 'POST' }); items = items.filter((x) => x.key !== key); items.length ? paint() : card.remove(); }
      catch (err) { flash(err.message, true); }
    }));
  };
  paint();
  const todosCard = aside.querySelector('[data-todos]');
  if (todosCard) todosCard.after(card); else aside.insertBefore(card, aside.firstChild);
}

/* ══════════════════════════════════════════════════════════════════════
   Family Constellation: the views
   ══════════════════════════════════════════════════════════════════════ */

function ageOf(dob) {
  const d = new Date(dob + 'T00:00:00'); const t = new Date();
  let age = t.getFullYear() - d.getFullYear(); if ((t.getMonth(), t.getDate()) && (t.getMonth() < d.getMonth() || (t.getMonth() === d.getMonth() && t.getDate() < d.getDate()))) age -= 1;
  return age;
}

function todayISO() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
function hhmm(iso) { const d = new Date(iso); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
function members() { return (store.household && store.household.members) || []; }
function childIds() { return members().filter((m) => m.role === 'child').map((m) => m.id); }
function hueForItem(i) {
  if (i.space) return i.space;
  if (i.category) return spaceOf(i.category);
  if (i.action === 'pay') return 'money';
  if (i.subject_member_id && childIds().includes(i.subject_member_id)) return 'school';
  return 'home';
}

/* The day as one list: calendar events, dated things, timed to-dos. */
function dayItems(brief, events, todos, notices) {
  const today = todayISO();
  const byId = {}; (notices || []).forEach((n) => { byId[n.id] = n; });
  const out = [];
  (events || []).forEach((e) => {
    if (!e.starts_at || String(e.starts_at).slice(0, 10) !== today && !(e.all_day && String(e.starts_at).slice(0, 10) <= today && String(e.ends_at).slice(0, 10) > today)) return;
    out.push({ key: 'cal' + e.id, time: e.all_day ? '' : hhmm(e.starts_at), sort: e.all_day ? '00:00' : hhmm(e.starts_at), what: e.summary, who: '', hue: 'cal', href: null });
  });
  (brief.items || []).forEach((i) => {
    if (!i.due_date || i.due_date !== today) return;
    const n = byId[i.artifact_id];
    out.push({ key: 'ob' + (i.obligation_id || i.artifact_id), time: i.due_time ? String(i.due_time).slice(0, 5) : '', sort: i.due_time ? String(i.due_time).slice(0, 5) : '00:01',
      what: i.title, who: i.subject_name || memberName(i.subject_member_id) || '', hue: n ? spaceOfNotice(n) : hueForItem(i), href: i.artifact_id ? '#/notices/' + i.artifact_id : null, pay_url: i.pay_url });
  });
  (todos || []).forEach((t) => {
    if (t.done_at || t.due_date !== today) return;
    out.push({ key: 'td' + t.id, time: t.due_time ? String(t.due_time).slice(0, 5) : '', sort: t.due_time ? String(t.due_time).slice(0, 5) : '00:02', what: t.title, who: memberName(t.assigned_to) || '', hue: 'home', href: null });
  });
  out.sort((a, b) => a.sort < b.sort ? -1 : a.sort > b.sort ? 1 : 0);
  return out;
}

function timeline(items) {
  if (!items.length) return '<p class="muted" style="padding:6px 0 2px">Nothing on the clock today. The week is in Life.</p>';
  const now = hhmm(new Date().toISOString()); let drawn = false;
  return '<ul class="tl">' + items.map((i) => {
    let line = '';
    if (!drawn && i.sort > now && i.time) { drawn = true; line = '<li><span class="now"></span></li>'; }
    return line + '<li><span class="tm">' + esc(i.time || 'all day') + '</span><span class="dt ' + esc(i.hue) + '"></span>'
      + '<span class="ic ' + esc(i.hue) + '">' + icon(i.hue === 'cal' ? 'calendar' : (ICON_PATHS[i.hue] ? i.hue : 'info'), 16) + '</span>'
      + '<span class="grow">' + (i.href ? '<a class="what" href="' + esc(i.href) + '" style="text-decoration:none">' + esc(i.what) + '</a>' : '<span class="what">' + esc(i.what) + '</span>')
      + (i.who ? '<div class="who">' + esc(i.who) + '</div>' : '') + (i.pay_url ? '<div class="who">' + payLinks(i.pay_url, 'plain') + '</div>' : '') + '</span>'
      + (i.who ? '<span class="chip" title="' + esc(i.who) + '">' + esc(initial(i.who)) + '</span>' : '') + '</li>';
  }).join('') + '</ul>';
}

/* The pulse: each person, where they are and what is next for them. From
   what the household has, never invented: a child is at school on a school
   day until something says otherwise; an adult's next thing is their next
   dated item; nothing known is "free". */
function pulseRow(items) {
  const now = hhmm(new Date().toISOString());
  const weekday = new Date().getDay();
  return '<div class="pulse">' + members().map((m) => {
    const mine = items.filter((i) => i.who === m.display_name || (i.who && i.who.startsWith(m.display_name.split(' ')[0])));
    const next = mine.find((i) => i.sort >= now && i.time) || mine[0];
    let state, dot, when;
    if (m.role === 'child') {
      const school = weekday >= 1 && weekday <= 5 && now < '15:30';
      state = school ? 'School' : 'Home'; dot = school ? 'school' : 'home';
      // A time is shown only when it is one: "08:30", not the notice's "not specified".
      const at = next && /^\d{1,2}:\d{2}/.test(next.time || '') ? next.time.slice(0, 5) + ' · ' : '';
      when = next ? at + next.what : (school ? 'until 3:30' : (m.school ? m.school : ''));
    } else {
      state = next ? 'Busy' : 'Free'; dot = next ? 'busy' : 'free';
      const at = next && /^\d{1,2}:\d{2}/.test(next.time || '') ? next.time.slice(0, 5) + ' · ' : '';
      when = next ? at + next.what : 'nothing scheduled';
    }
    return '<div class="person card" data-person="' + esc(m.id) + '"><span class="ring ' + (m.role === 'child' ? 'school' : '') + '">' + esc(initial(m.display_name)) + '</span>'
      + '<span class="n">' + esc(m.display_name.split(' ')[0]) + '</span>'
      + '<span class="s"><i class="' + dot + '"></i>' + esc(state) + '</span>'
      + '<span class="w">' + esc(when.slice(0, 40)) + '</span></div>';
  }).join('') + (store.me && store.me.role === 'guardian' ? '<a class="person card add" href="#/household"><span class="ring">' + icon('plus', 20) + '</span><span class="n">Add</span></a>' : '') + '</div>';
}

/* The hero: the latest shared photo when there is one, else the warm sky. */
function hero(photo) {
  return '<a class="hero-card' + (photo ? ' has-photo' : '') + '" href="#/memories">' + (photo ? '<img alt="" data-pic="' + esc(photo.id) + '">' : '<span class="sky"></span>')
    + '<span class="q">\u201CA calmer, happier life together.\u201D</span></a>';
}

/* FamilyOS noticed: observe, understand, suggest, approve, act. Each from a
   real fact the household has, with a fix that opens Ask or the thing. */
function insights(brief, money, errands, proposed, docs) {
  const out = [];
  for (const c of ((docs && docs.checks) || []).slice(0, 2)) {
    out.push({ title: esc(c.title), body: esc(c.why.charAt(0).toUpperCase() + c.why.slice(1)) + '.', open: '#/notices/' + c.artifact_id,
      fix: c.kind === 'passport_short' ? 'Add a to-do to renew ' + (c.holder_name ? c.holder_name + '\u2019s' : 'the') + ' passport before ' + (c.plan_title || 'the trip') : null });
  }
  const clash = (brief.items || []).find((i) => i.clashes && i.clashes.length);
  if (clash) out.push({ title: (clash.due_date === todayISO() ? 'Today' : fmtDate(clash.due_date)) + ' looks tight.',
    body: esc(clash.title) + ' clashes with ' + esc(clash.clashes[0]) + '. One of them has to move.',
    fix: 'Which of these should move: ' + clash.title + ' or ' + clash.clashes[0] + '?', open: clash.artifact_id ? '#/notices/' + clash.artifact_id : '#/waiting' });
  const asks = (brief.items || []).filter((i) => i.reason === 'assigned');
  if (asks.length) { const a = asks[0]; out.push({ title: (a.assigned_by_name || 'Someone') + ' handed you something.', body: esc(a.title) + (a.note ? ' — “' + esc(a.note) + '”' : ''), fix: 'What do I need to do about ' + a.title + '?', open: '#/notices/' + a.artifact_id, pay_url: a.pay_url }); }
  const missed = (brief.items || []).filter((i) => i.reason === 'missed' || i.reason === 'overdue');
  if (missed.length) out.push({ title: missed.length === 1 ? 'A date went by undecided.' : missed.length + ' dates went by undecided.', body: missed.slice(0, 2).map((i) => esc(i.title)).join(' · ') + (missed.length > 2 ? ' and more' : ''), fix: 'Which of the missed dates still matter?', open: '#/waiting' });
  if (proposed && proposed.length) out.push({ title: proposed.length + (proposed.length === 1 ? ' date is waiting for a yes.' : ' dates are waiting for a yes.'), body: proposed.slice(0, 2).map((o) => esc(o.title)).join(' · '), fix: 'What is still undecided?', open: '#/waiting' });
  const low = (money && money.running_low || []).filter((r) => r.status !== 'fine');
  if (low.length) out.push({ title: 'Running low on ' + esc(low[0].item) + (low.length > 1 ? ' and ' + (low.length - 1) + ' more.' : '.'), body: 'Bought every ~' + low[0].every_days + ' days, last ' + esc(fmtDate(low[0].last_on)) + '.', fix: 'What should we reorder this week?', open: '#/money', link: low[0].reorder_url });
  const waiting = (errands || []).filter((e) => e.status === 'proposed' || e.status === 'needs_you');
  if (waiting.length) { const e = waiting[0]; out.push({ title: e.status === 'needs_you' ? 'An errand needs your hand.' : 'An errand is waiting for approval.', body: esc(e.title), open: '#/errands/' + e.id, fix: null }); }
  return out.slice(0, 3);
}
/* The day, read without any credential: the weather for home today and
   tomorrow, the holidays coming, and the typical school run from home. A
   tile only when the household switched something on; typical drive times,
   never live traffic, and the tile says so. */
function contextCard(c) {
  if (!c || (!c.weather_days && !c.holidays && !c.school_runs)) return '';
  const day = (d) => '<div class="stack" style="gap:2px;min-width:120px"><span class="muted" style="font-size:12px">' + esc(d.label) + '</span>'
    + '<b style="font-size:22px">' + (d.tmax != null ? Math.round(d.tmax) + '°' : '–') + (d.tmin != null ? ' <span class="muted" style="font-size:13px">/ ' + Math.round(d.tmin) + '°</span>' : '') + '</b>'
    + '<span style="font-size:13px">' + esc(d.words || '') + (d.rain != null && d.rain >= 40 ? (d.words ? ', ' : '') + 'rain ' + Math.round(d.rain) + '%' : '') + '</span></div>';
  return '<section class="card pad" data-context-card><div class="row wrap" style="gap:8px;align-items:baseline"><h2>The day</h2><span class="muted" style="font-size:12px">read without any sign-in, for home</span></div>'
    + '<div class="row wrap" style="gap:24px;margin-top:10px;align-items:flex-start">'
    + (c.weather_days || []).map(day).join('')
    + (c.school_runs && c.school_runs.length ? '<div class="stack" style="gap:3px"><span class="muted" style="font-size:12px">School run from home</span>'
        + c.school_runs.map((r) => '<span style="font-size:14px">'
          + (r.live_minutes != null
            ? '<b' + (r.delay_minutes >= 8 ? ' style="color:var(--danger,#b42318)"' : '') + '>' + esc(String(r.live_minutes)) + ' min now</b>'
              + (r.delay_minutes >= 3 ? ' <span class="muted">(' + r.delay_minutes + ' worse than usual)</span>' : ' <span class="muted">(as usual)</span>')
            : '<b>' + esc(String(r.minutes)) + ' min</b>')
          + ' to ' + esc(r.school) + (r.leave_by ? ' <span class="muted">· leave by ' + esc(r.leave_by) + (r.starts_at ? ' for ' + esc(r.starts_at) : '') + '</span>' : '') + '</span>').join('')
        + '<span class="muted" style="font-size:11.5px">' + (c.school_runs.some((r) => r.live_minutes != null) ? 'live traffic, read in the two hours before school' : c.school_runs.some((r) => r.usual) ? 'the usual traffic for the hour; live in the two hours before school' : 'the drive without traffic, from public maps') + '</span></div>' : '')
    + (c.holidays && c.holidays.length ? '<div class="stack" style="gap:2px"><span class="muted" style="font-size:12px">Holidays coming</span>'
        + c.holidays.slice(0, 3).map((h) => '<span style="font-size:14px">' + esc(h.name) + ' <span class="muted">' + esc(fmtDate(h.date).replace(/,.*$/, '')) + '</span></span>').join('') + '</div>' : '')
    + '</div></section>';
}

function insightCard(x) {
  return '<section class="insight"><div class="k"><span class="star">' + icon('sparkle', 14) + '</span> FamilyOS noticed</div>'
    + '<h3>' + x.title + '</h3><p>' + x.body + '</p>'
    + '<div class="acts">' + (x.fix ? '<button class="btn sm" data-fix="' + esc(x.fix) + '">Fix for me</button>' : '')
    + (x.open ? '<a class="btn ghost sm" href="' + esc(x.open) + '" style="text-decoration:none">Show me</a>' : '')
    + (x.pay_url ? payLinks(x.pay_url, 'btn ghost sm') : '') + (x.link ? '<a class="btn ghost sm" href="' + esc(x.link) + '" target="_blank" rel="noopener" style="text-decoration:none">Reorder ↗</a>' : '') + '</div></section>';
}

function spacesGrid(counts) {
  return '<div class="spaces">' + Object.entries(SPACES).filter(([, sp]) => !sp.onLife).map(([key, sp]) =>
    '<a href="' + (key === 'money' ? '#/money' : '#/space/' + key) + '"><span class="ic ' + sp.hue + '">' + icon(key, 20) + '</span>'
    + '<span><span class="nm">' + esc(sp.label) + '</span><br><span class="ct">' + esc(counts[key] || 'nothing new') + '</span></span></a>').join('') + '</div>';
}

async function pulseView(main) {
  main.classList.remove('chat-main');
  const q = hashQuery();
  const [brief, events, todos, notices, money, errands, proposed, accepted, plans, pics, billers, mailboxes, week, docs] = await Promise.all([
    api('/brief?limit=20'), api('/calendar/upcoming?days=2').catch(() => []), api('/todos').catch(() => []),
    api('/inbox?days=14&limit=120').catch(() => []), api('/money?days=120').catch(() => null), api('/errands').catch(() => []),
    api('/obligations?status=proposed&limit=100').catch(() => []), api('/obligations?status=accepted&limit=100').catch(() => []),
    api('/plans').catch(() => []),
    api('/artifacts?limit=60').then((all) => all.filter((a) => /^image\//.test(a.media_type) && a.channel !== 'errand' && !((a.source || {}).picture === 'document'))).catch(() => []),
    api('/billers').catch(() => []), api('/google/mailboxes').catch(() => []), api('/inbox?days=7&limit=40').catch(() => []),
    api('/documents').catch(() => ({ documents: [], checks: [] })),
  ]);
  store.mailboxes = mailboxes;
  const connected = mailboxes.filter((m) => !m.disconnected_at);
  const importing = connected.find((m) => !m.backfill_done);
  const justConnected = q.get('mailbox') === 'connected';
  if (q.get('mailbox') === 'failed') flash('Google did not finish connecting the mailbox. Try again.', true);
  if (q.get('mailbox') === 'cancelled') flash('Connecting the mailbox was cancelled.');
  const fresh = connected.length === 0;
  const items = dayItems(brief, events, todos, notices);
  const open = notices.filter((n) => n.state === 'todo');
  const counts = {
    home: (open.filter((n) => spaceOfNotice(n) === 'home').length || 0) + ' things',
    school: (open.filter((n) => spaceOfNotice(n) === 'school').length || 0) + ' upcoming',
    health: (open.filter((n) => spaceOfNotice(n) === 'health').length || 0) + ' to see',
    travel: plans.filter((p) => p.shape === 'trip' && p.status !== 'dropped').slice(0, 1).map((p) => p.title).join('') || 'no trip planned',
    money: ((money && money.recurring) || []).length + ' bills',
    invest: (open.filter((n) => spaceOfNotice(n) === 'invest').length || 0) + ' to decide',
  };
  const d = new Date();
  const noticed = insights(brief, money, errands, proposed, docs);
  const need = brief.counts ? brief.counts.missed + brief.counts.overdue + brief.counts.today + brief.counts.undecided : 0;
  main.innerHTML = '<div class="greet"><div><h1>Good ' + dayPart() + ', ' + esc((store.me && store.me.display_name || '').split(' ')[0]) + '.</h1>'
    + '<div class="day">' + esc(d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }))
    + (brief.counts ? ' · ' + need + (need === 1 ? ' thing needs' : ' things need') + ' someone' : '')
    + (brief.context && brief.context.weather ? ' · ' + esc(brief.context.weather) : '')
    + (brief.context && brief.context.holidays && brief.context.holidays.length ? ' · ' + brief.context.holidays.slice(0, 2).map((h) => esc(h.name) + ' on ' + esc(fmtDate(h.date).replace(/,.*$/, ''))).join(', ') : '')
    + '</div></div>'
    + '<div class="row" style="gap:8px"><button class="btn ghost sm" data-add>Add a notice</button></div></div>'
    + '<div class="top"><div class="pulse-wrap">' + pulseRow(items) + '</div>' + hero(pics[0]) + '</div>'
    + '<div style="height:18px"></div>'
    + '<div class="home"><div class="stack" style="gap:16px">'
    + ((justConnected || importing) ? importPanel(importing || connected[connected.length - 1]) : (fresh ? setupHero() : ''))
    + contextCard(brief.context)
    + (noticed.length ? insightCard(noticed[0]) : '')
    + urgentStrip(brief)
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Today</h2><span class="muted">' + items.length + (items.length === 1 ? ' thing' : ' things') + '</span>'
    + (items.length > 8 ? '<a class="muted" href="#/life" style="margin-left:auto">all ' + items.length + '</a>' : '') + '</div>' + timeline(items.slice(0, 8)) + '</section>'
    + noticed.slice(1).map(insightCard).join('')
    + spottedSection(proposed)
    + '<div class="section-title" style="margin-top:6px"><h2>Your life</h2></div>' + spacesGrid(counts)
    + (pics.length ? '<div class="section-title" style="margin-top:6px"><h2>Recent memories</h2><a class="muted" href="#/memories" style="margin-left:auto">View all</a></div>'
      + '<div class="memstrip">' + pics.slice(0, 4).map((a) => '<a href="#/memories"><img alt="" data-pic="' + esc(a.id) + '"></a>').join('') + '</div>' : '')
    + '</div><aside class="stack" style="gap:14px">'
    + '<section class="card rail-card me"><div class="row" style="gap:12px"><span class="avatar" style="width:44px;height:44px;border-radius:22px;font-size:16px">' + esc(initial(store.me && store.me.display_name)) + '</span>'
    + '<span><b style="font-size:15px">' + esc(store.me ? store.me.display_name : '') + '</b><br><span class="muted">' + esc(store.me ? store.me.role : '') + '</span></span>'
    + '<a class="ib" href="#/household" style="margin-left:auto" title="Settings">' + icon('settings', 16) + '</a></div></section>'
    + comingUpCard(accepted, proposed)
    + '<div class="stack" data-loaded style="gap:14px"></div>'
    + billsCard(billers)
    + peopleCard(week)
    + guardianCard()
    + '<section class="card rail-card"><h2>Quick actions</h2><div class="quick">'
    + '<button data-fix="Plan our weekend"><span class="ic travel">' + icon('calendar', 16) + '</span>Plan our weekend</button>'
    + '<a href="#/notices"><span class="ic school">' + icon('doc', 16) + '</span>Find documents</a>'
    + '<a href="#/money"><span class="ic money">' + icon('money', 16) + '</span>Pay a bill</a>'
    + '<button data-fix="Plan a trip for us"><span class="ic travel">' + icon('travel', 16) + '</span>Book travel</button>'
    + '</div></section>'
    + '</aside></div>'
    + assignDialog();
  wireHome(main);
  wireAssignDialog(main);
  wireAssignButtons(main);
  wireTodos(main);
  loadRecurringCard(main, '[data-loaded]');
  loadTodosCard(main, '[data-loaded]');
  loadSuggestionsCard(main, '[data-loaded]');
  if (justConnected || importing) {
    const account = importing || connected[connected.length - 1];
    if (account) runImport(main, account);
  }
  main.querySelectorAll('img[data-pic]').forEach(async (img) => {
    try { const blob = await api('/artifacts/' + img.dataset.pic + '/picture', { blob: true }); img.src = URL.createObjectURL(blob); } catch (err) { img.remove(); }
  });
  main.querySelectorAll('[data-fix]').forEach((b) => b.addEventListener('click', () => openPalette(b.dataset.fix)));
  main.querySelectorAll('[data-person]').forEach((p) => p.addEventListener('click', () => openPerson(p.dataset.person)));
}

/* A person, in context: their day, their school, what names them. */

/* Coming up, for a space or a person: the brief's dated items (undecided,
   soon, today) and the dates already accepted, which the brief no longer
   nags about but a parent still wants to see. One line per date. */
function comingUpFor(brief, accepted, keep) {
  const today = todayISO();
  const seen = new Set();
  const out = [];
  for (const i of (brief.items || [])) {
    if (!i.due_date || !keep(i)) continue;
    const k = i.title + '|' + i.due_date; if (seen.has(k)) continue; seen.add(k); out.push(i);
  }
  for (const o of (accepted || [])) {
    if (!o.due_date || o.due_date < today || !keep(o)) continue;
    const k = o.title + '|' + o.due_date; if (seen.has(k)) continue; seen.add(k);
    out.push({ title: o.title, due_date: o.due_date, due_time: o.due_time, artifact_id: o.artifact_id, subject_member_id: o.subject_member_id,
      subject_name: memberName(o.subject_member_id) || null, why: 'accepted' + (o.due_time ? ' \u00B7 ' + o.due_time : '') + (o.end_date && o.end_date !== o.due_date ? ' \u00B7 until ' + fmtDate(o.end_date).replace(/,.*$/, '') : '') + ' \u00B7 on the calendar', reason: 'accepted', pay_url: o.pay_url });
  }
  return out.sort((a, b) => (a.due_date < b.due_date ? -1 : a.due_date > b.due_date ? 1 : 0));
}

function openPerson(id) {
  const m = members().find((x) => x.id === id); if (!m) return;
  openContext(m.display_name, async (body, full) => {
    full.href = '#/family';
    const [notices, brief, todos, accepted, docs] = await Promise.all([api('/inbox?days=60&limit=200').catch(() => []), api('/brief?limit=40').catch(() => ({ items: [] })), api('/todos').catch(() => []), api('/obligations?status=accepted&limit=100').catch(() => []), api('/documents').catch(() => ({ documents: [], checks: [] }))]);
    const theirs = (docs.documents || []).filter((d) => d.holder_member_id === id);
    // Mail to an adult's own address names them, so without this every promo,
    // newsletter and delivery note would be on their page. The same fold as
    // Inbox, plus the records that belong in Money and Investments.
    const RECORDS = { food: 1, shopping: 1, subscriptions: 1, trading: 1 };
    const mine = notices.filter((n) => ((n.subject_member_ids || []).includes(id) || n.assigned_to === id) && !QUIET[n.category] && !RECORDS[n.category]);
    const mineIds = new Set(mine.map((n) => n.id));
    const dated = comingUpFor(brief, accepted, (i) => i.subject_member_id === id || i.subject_name === m.display_name || (i.artifact_id && mineIds.has(i.artifact_id)));
    const todo = todos.filter((t) => t.assigned_to === id && !t.done_at);
    body.innerHTML = '<div class="stack" style="gap:14px">'
      + '<div class="row" style="gap:14px"><span class="ring" style="width:58px;height:58px;border-radius:29px;display:grid;place-items:center;font-family:var(--serif);font-size:22px;border:2.5px solid var(--' + (m.role === 'child' ? 'school' : 'primary') + ')">' + esc(initial(m.display_name)) + '</span>'
      + '<div><div style="font-size:17px;font-weight:600">' + esc(m.display_name) + '</div><div class="muted">' + esc(m.role) + (m.school ? ' · ' + esc(m.school) + (m.class_label ? ', class ' + esc(m.class_label) : '') : '') + '</div></div></div>'
      + '<section class="card pad"><h2>Coming up</h2>' + (dated.length ? '<ul class="tl" style="margin-top:6px">' + dated.slice(0, 6).map((i) => '<li><span class="tm">' + esc(fmtDate(i.due_date)) + '</span><span class="dt ' + hueForItem(i) + '"></span><span class="ic ' + hueForItem(i) + '">' + icon(ICON_PATHS[hueForItem(i)] ? hueForItem(i) : 'calendar', 16) + '</span><span><a class="what" href="#/notices/' + esc(i.artifact_id) + '" style="text-decoration:none">' + esc(i.title) + '</a><div class="who">' + esc(i.why) + '</div></span></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">Nothing dated.</p>') + '</section>'
      + (todo.length ? '<section class="card pad"><h2>To do</h2><div class="stack" style="gap:6px;margin-top:8px">' + todo.map((t) => '<div>' + esc(t.title) + (t.due_date ? ' <span class="muted">by ' + esc(fmtDate(t.due_date)) + '</span>' : '') + '</div>').join('') + '</div></section>' : '')
      + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Documents</h2><span class="muted">' + (theirs.length ? theirs.length + ' held \u00B7 ' : '') + mine.length + ' naming ' + esc(m.display_name.split(' ')[0]) + '</span></div>'
      + (theirs.length ? '<div class="mlist" style="margin-top:4px">' + theirs.map(docRow).join('') + '</div>' : '')
      + (mine.length ? '<div class="stack" style="gap:8px;margin-top:8px">' + mine.slice(0, 8).map((n) => '<a href="#/notices/' + esc(n.id) + '" style="text-decoration:none;color:inherit"><b style="font-size:13.5px">' + esc(n.headline || 'Notice') + '</b><br><span class="muted">' + esc(n.from_label) + ' · ' + esc(ago(n.received_at)) + '</span></a>').join('') + '</div>' : '<p class="muted" style="margin-top:6px">Nothing yet.</p>') + '</section></div>';
  });
}

/* Our family: the constellation. */
async function familyView(main) {
  main.classList.remove('chat-main');
  const ms = members(); const adults = ms.filter((m) => m.role !== 'child'); const kids = ms.filter((m) => m.role === 'child');
  const person = (m) => '<div class="person" data-person="' + esc(m.id) + '"><span class="ring ' + (m.role === 'child' ? 'school' : '') + '">' + esc(initial(m.display_name)) + '</span>'
    + '<span class="n">' + esc(m.display_name) + '</span><span class="s">' + esc(m.role === 'child' ? (m.school || 'child') : m.role) + '</span>'
    + (m.role === 'child' && m.class_label ? '<span class="tags"><span class="tag line" style="text-transform:none;letter-spacing:0">class ' + esc(m.class_label) + '</span></span>' : '') + '</div>';
  main.innerHTML = '<div class="greet"><div><h1>Our family</h1><div class="day">' + esc(store.household ? store.household.name : '') + ' · ' + ms.length + ' people</div></div>'
    + (store.me && store.me.role === 'guardian' ? '<a class="btn ghost" href="#/household" style="text-decoration:none">Add or change someone</a>' : '') + '</div>'
    + '<section class="card constellation" data-constellation>'
    + '<svg class="wire" data-wire aria-hidden="true"></svg>'
    + '<div class="homenode"><span class="ic">' + icon('home', 18) + '</span><span>Our home</span></div>'
    + '<div class="row" data-adults>' + adults.map(person).join('') + '</div>'
    + (kids.length ? '<div class="row" data-kids>' + kids.map(person).join('') + '</div>' : '')
    + '</section>'
    + '<p class="muted" style="margin-top:14px">Tap anyone to see their day, their school and what names them. Everything FamilyOS knows is arranged around the people, not the other way round.</p>'
    + '<div data-offers></div>';
  main.querySelectorAll('[data-person]').forEach((p) => p.addEventListener('click', () => openPerson(p.dataset.person)));
  loadOffersCard(main.querySelector('[data-offers]'));
  // Soft wires from the home to each adult, and from the adults to each child.
  const draw = () => {
    const box = main.querySelector('[data-constellation]'); const svg = main.querySelector('[data-wire]'); if (!box || !svg) return;
    const r = box.getBoundingClientRect(); svg.setAttribute('viewBox', '0 0 ' + r.width + ' ' + r.height); svg.setAttribute('width', r.width); svg.setAttribute('height', r.height);
    const at = (el) => { const b = el.getBoundingClientRect(); return [b.left - r.left + b.width / 2, b.top - r.top + b.height / 2]; };
    const home = at(box.querySelector('.homenode .ic'));
    const ad = [...box.querySelectorAll('[data-adults] .ring')].map(at); const kd = [...box.querySelectorAll('[data-kids] .ring')].map(at);
    const curve = ([x1, y1], [x2, y2]) => 'M' + x1 + ',' + y1 + ' C' + x1 + ',' + (y1 + (y2 - y1) * 0.55) + ' ' + x2 + ',' + (y1 + (y2 - y1) * 0.45) + ' ' + x2 + ',' + y2;
    let paths = ad.map((a) => curve(home, a));
    if (ad.length > 1) paths.push('M' + ad[0][0] + ',' + ad[0][1] + ' L' + ad[ad.length - 1][0] + ',' + ad[ad.length - 1][1]);
    kd.forEach((k) => { const parent = ad.length ? ad.reduce((p, c) => (p[0] + c[0]) / 2 === 0 ? c : [(p[0] + c[0]) / 2, (p[1] + c[1]) / 2]) : home; paths.push(curve(ad.length > 1 ? [(ad[0][0] + ad[ad.length - 1][0]) / 2, ad[0][1]] : (ad[0] || home), k)); });
    svg.innerHTML = paths.map((d) => '<path d="' + d + '"/>').join('');
  };
  setTimeout(draw, 60); window.addEventListener('resize', draw, { once: true });
}

/* Life: the spaces, what is being done, and the week. */
async function lifeView(main) {
  main.classList.remove('chat-main');
  const [notices, plans, errands, money, brief] = await Promise.all([
    api('/inbox?days=30&limit=200').catch(() => []), api('/plans').catch(() => []), api('/errands').catch(() => []),
    api('/money?days=120').catch(() => null), api('/brief?limit=40').catch(() => ({ items: [] })),
  ]);
  const open = notices.filter((n) => n.state === 'todo');
  const counts = {
    home: open.filter((n) => spaceOfNotice(n) === 'home').length + ' things',
    school: open.filter((n) => spaceOfNotice(n) === 'school').length + ' upcoming',
    health: open.filter((n) => spaceOfNotice(n) === 'health').length + ' to see',
    travel: plans.filter((p) => p.shape === 'trip' && p.status !== 'dropped').slice(0, 1).map((p) => p.title).join('') || 'no trip planned',
    money: ((money && money.recurring) || []).length + ' bills',
    invest: open.filter((n) => spaceOfNotice(n) === 'invest').length + ' to decide',
  };
  const doing = errands.filter((e) => !['done', 'cancelled', 'failed', 'stopped'].includes(e.status));
  const week = (brief.items || []).filter((i) => i.due_date && i.due_date >= todayISO()).slice(0, 8);
  const home = notices.filter((n) => spaceOfNotice(n) === 'home');
  const homeRow = spaceRow(SPACES.home, 'home');
  const ms = members();
  const person = (m) => '<div class="person" data-person="' + esc(m.id) + '"><span class="ring ' + (m.role === 'child' ? 'school' : '') + '">' + esc(initial(m.display_name)) + '</span>'
    + '<span class="n">' + esc(m.display_name) + '</span><span class="s">' + esc(m.role === 'child' ? (m.class_label ? 'class ' + m.class_label : 'child') : m.role) + '</span></div>';
  main.innerHTML = '<div class="greet"><div><h1>Our family</h1><div class="day">' + ms.length + ' people, and each space of their life: what arrived, what is due, what is being done.</div></div>'
    + (store.me && store.me.role === 'guardian' ? '<a class="btn ghost" href="#/household" style="text-decoration:none">Add or change someone</a>' : '') + '</div>'
    + '<section class="card constellation" style="margin-bottom:16px"><div class="row" data-adults>' + ms.map(person).join('') + '</div></section>'
    + spacesGrid(counts)
    + '<div class="home" style="margin-top:18px"><div class="stack" style="gap:16px">'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>This week</h2><a class="muted" href="#/today">everything waiting</a></div>'
    + (week.length ? '<ul class="tl" style="margin-top:6px">' + week.map((i) => '<li><span class="tm">' + esc(fmtDate(i.due_date)) + '</span><span class="dt ' + hueForItem(i) + '"></span><span class="ic ' + hueForItem(i) + '">' + icon(ICON_PATHS[hueForItem(i)] ? hueForItem(i) : 'calendar', 16) + '</span><span>' + (i.artifact_id ? '<a class="what" href="#/notices/' + esc(i.artifact_id) + '" style="text-decoration:none">' + esc(i.title) + '</a>' : '<span class="what">' + esc(i.title) + '</span>') + '<div class="who">' + esc(i.why) + (i.subject_name ? ' · ' + esc(i.subject_name) : '') + '</div></span></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">Nothing dated this week.</p>') + '</section>'
    + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Being done for you</h2><a class="muted" href="#/errands">all</a></div>'
    + (doing.length ? '<div class="stack" style="gap:8px;margin-top:8px">' + doing.map((e) => '<a href="#/errands/' + esc(e.id) + '" style="text-decoration:none;color:inherit"><b>' + esc(e.title) + '</b> <span class="tag ' + (ERRAND_TONE[e.status] || '') + '">' + esc(ERRAND_STATUS[e.status] || e.status) + '</span></a>').join('') + '</div>'
      : '<p class="muted" style="margin-top:6px">Nothing right now. Ask for a booking and it appears here, written down in full before anything happens.</p>') + '</section>'
    + ((plans.filter((p) => p.status !== 'dropped' && p.shape !== 'trip').length)
      ? '<section><div class="row wrap" style="gap:8px;margin-bottom:10px"><h2 style="font-size:15px;font-weight:600">Plans at home</h2><span class="grow"></span><a class="btn ghost sm" href="#/plans">Plan something</a></div>'
        + '<div class="stack" style="gap:10px">' + plans.filter((p) => p.status !== 'dropped' && p.shape !== 'trip').slice(0, 4).map(planCard).join('') + '</div></section>'
      : '')
    + '<section class="card"><div class="pad" style="padding-bottom:8px"><div class="row wrap" style="gap:8px"><h2>At home</h2><span class="muted">food, shopping, the house, government, and anything not yet sorted</span></div></div>'
    + (home.length ? home.slice(0, 20).map(homeRow).join('') : '<p class="muted pad">Nothing at home yet.</p>') + '</section>'
    + '</div><aside class="stack" style="gap:14px">'
    + spaceRail('home', SPACES.home, money)
    + '<section class="card rail-card"><h2>Everything that arrived</h2><p class="muted">Every notice, as it came, with what it asks. <a href="#/notices">Open the full list</a></p></section>'
    + '</aside></div>';
  main.querySelectorAll('img[data-pic]').forEach(async (img) => {
    try { const blob = await api('/artifacts/' + img.dataset.pic + '/picture', { blob: true }); img.src = URL.createObjectURL(blob); } catch (err) { img.remove(); }
  });
  main.querySelectorAll('[data-person]').forEach((p) => p.addEventListener('click', () => openPerson(p.dataset.person)));
}

function spaceIcon(key) { return { home: 'home', school: 'school', health: 'health', travel: 'travel', money: 'money', invest: 'invest' }[key] || 'doc'; }
/* One notice as a space lists it. */
function spaceRow(sp, iconName) {
  return (n) => '<a class="inbox-row" href="#/notices/' + esc(n.id) + '" style="text-decoration:none;color:inherit;border-top:1px solid var(--line-soft)">'
    + (/^image\//.test(n.media_type || '') ? '<img class="pic" alt="" data-pic="' + esc(n.id) + '">' : '<span class="glyph ' + sp.hue + '">' + icon((CHANNEL[n.channel] || {}).icon || iconName, 15) + '</span>')
    + '<span class="body"><span class="meta"><b>' + esc(n.from_label) + '</b><span>' + esc(ago(n.received_at)) + '</span>' + (n.subject_member_ids || []).map((id) => '<span class="tag kid">' + esc(memberName(id)) + '</span>').join('') + '</span><span class="title">' + esc(n.headline || 'Notice') + '</span>' + (n.preview && n.preview.length ? '<span class="sub">' + esc(n.preview[0]) + '</span>' : '') + '</span>' + (n.state === 'todo' ? '<span class="tag amber">' + n.open + ' to decide</span>' : '') + '</a>';
}
/* The rail of a space: what was spent here, what charges again, and the
   cards only one space has. Life shows Home's. */
function spaceRail(key, sp, mny) {
  const spent = mny ? mny.charges.filter((c) => sp.categories.includes(c.category)) : [];
  const spentInr = spent.filter((c) => c.currency === 'INR').reduce((a, c) => a + c.amount, 0);
  const recurring = mny ? mny.recurring.filter((r) => sp.categories.includes(r.category)) : [];
  return ''
    + (mny ? '<section class="card rail-card"><h2>Spent here</h2>'
      + (spent.length ? '<div class="row" style="gap:10px;margin:2px 0 10px"><span class="mtile h-' + sp.hue + '">' + icon('money', 15) + '</span><span><b style="font-size:17px">' + esc(money(Math.round(spentInr), 'INR')) + '</b><div class="muted" style="font-size:12px">in ' + mny.days + ' days · ' + spent.length + ' charges</div></span></div>'
        + '<div class="stack" style="gap:7px">' + spent.slice(0, 6).map((c) => '<a class="ledger" href="#/notices/' + esc(c.message_id) + '"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(c.merchant) + '</span><span class="d">' + esc(fmtDate(c.date).replace(/,.*$/, '')) + '</span><b>' + esc(money(c.amount, c.currency)) + '</b></a>').join('') + '</div>'
        : '<p class="muted">No receipts in this space yet.</p>') + '</section>' : '')
    + (recurring.length ? '<section class="card rail-card"><h2>Charges again</h2><div class="stack" style="gap:7px">' + recurring.slice(0, 6).map((r) => '<a class="ledger" href="#/notices/' + esc(r.artifact_id) + '"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(r.merchant) + '</span><span class="d">' + esc(fmtDate(r.next_date).replace(/,.*$/, '')) + '</span><b>' + esc(money(r.next_amount, r.currency)) + '</b></a>').join('') + '</div></section>' : '')
    + (key === 'home' && mny && (mny.services && mny.services.last_done || []).length ? '<section class="card rail-card"><h2>Around the house</h2><div class="pills">' + mny.services.last_done.slice(0, 6).map((e) => '<span class="pill sm">' + esc(e.kind) + ' <span class="n">' + esc(fmtDate(e.date).replace(/,.*$/, '')) + '</span></span>').join('') + '</div></section>' : '')
    + (key === 'school' ? '<section class="card rail-card"><h2>The children</h2><div class="stack" style="gap:8px;margin-top:8px">' + members().filter((m) => m.role === 'child').map((m) => '<div class="row" style="gap:10px;cursor:pointer" data-person="' + esc(m.id) + '"><span class="avatar" style="border-color:var(--school);color:var(--school);background:var(--school-tint)">' + esc(initial(m.display_name)) + '</span><span><b>' + esc(m.display_name) + '</b><br><span class="muted">' + esc(m.school || 'no school set') + (m.class_label ? ', class ' + esc(m.class_label) : '') + '</span></span></div>').join('') + '</div></section>' : '')
  ;
}

/* A space: one part of life, as its own small world. */
async function spaceView(main, args) {
  main.classList.remove('chat-main');
  const key = args[0]; const sp = SPACES[key];
  if (sp && sp.onLife) { location.hash = '#/life'; return; }
  if (!sp) { main.innerHTML = '<div class="head"><div><h1>Not a space</h1></div></div>'; return; }
  const [notices, brief, mny, plans, accepted] = await Promise.all([api('/inbox?days=90&limit=300').catch(() => []), api('/brief?limit=40').catch(() => ({ items: [] })), api('/money?days=120').catch(() => null), key === 'travel' ? api('/plans').catch(() => []) : [], api('/obligations?status=accepted&limit=100').catch(() => [])]);
  const mine = notices.filter((n) => spaceOfNotice(n) === key);
  const ids = new Set(mine.map((n) => n.id));
  const dated = comingUpFor(brief, accepted, (i) => i.artifact_id && ids.has(i.artifact_id));
  const spent = mny ? mny.charges.filter((c) => sp.categories.includes(c.category)) : [];
  const spentInr = spent.filter((c) => c.currency === 'INR').reduce((a, c) => a + c.amount, 0);
  const recurring = mny ? mny.recurring.filter((r) => sp.categories.includes(r.category)) : [];
  const iconName = spaceIcon(key);
  const row = spaceRow(sp, iconName);
  main.innerHTML = '<div class="head"><div><div class="row" style="gap:12px"><span class="ic h-' + sp.hue + '" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center;background:var(--' + sp.hue + '-tint);color:var(--' + sp.hue + ')">' + icon(iconName, 20) + '</span><h1>' + esc(sp.label) + '</h1></div>'
    + '<p>' + mine.length + ' notices · ' + dated.length + ' dated' + (spent.length ? ' · ' + spent.length + ' charges in ' + mny.days + ' days' : '') + '</p></div></div>'
    + '<div class="home"><div class="stack" style="gap:16px">'
    + (dated.length ? '<section class="card pad"><h2>Coming up</h2><ul class="tl" style="margin-top:6px">' + dated.slice(0, 8).map((i) => '<li><span class="tm">' + esc(fmtDate(i.due_date).replace(/,.*$/, '')) + '</span><span class="dt ' + sp.hue + '"></span><span class="ic ' + sp.hue + '">' + icon(iconName, 14) + '</span><span><a class="what" href="#/notices/' + esc(i.artifact_id) + '" style="text-decoration:none">' + esc(i.title) + '</a><div class="who">' + esc(i.why) + (i.subject_name ? ' · ' + esc(i.subject_name) : '') + '</div>' + (i.pay_url ? '<div class="who">' + payLinks(i.pay_url, 'plain') + '</div>' : '') + '</span></li>').join('') + '</ul></section>' : '')
    + (key === 'travel' ? '<section><div class="row wrap" style="gap:8px;margin-bottom:10px"><h2 style="font-size:15px;font-weight:600">Trips</h2><span class="grow"></span><a class="btn ghost sm" href="#/plans">Plan a trip</a></div>'
      + (plans.filter((p) => p.status !== 'dropped' && p.shape === 'trip').length ? '<div class="stack" style="gap:10px">' + plans.filter((p) => p.status !== 'dropped' && p.shape === 'trip').map(planCard).join('') + '</div>' : '<p class="muted">No trip planned yet. Ask “plan our Dubai trip” from the bar below.</p>') + '</section>' : '')
    + '<section class="card"><div class="pad" style="padding-bottom:8px"><h2>What arrived</h2></div>' + (mine.length ? mine.slice(0, 30).map(row).join('') : '<p class="muted pad">Nothing in this space yet.</p>') + '</section>'
    + '</div><aside class="stack" style="gap:14px">'
    + spaceRail(key, sp, mny)
    + '</aside></div>';
  main.querySelectorAll('[data-person]').forEach((p) => p.addEventListener('click', () => openPerson(p.dataset.person)));
  main.querySelectorAll('img[data-pic]').forEach(async (img) => {
    try { const blob = await api('/artifacts/' + img.dataset.pic + '/picture', { blob: true }); img.src = URL.createObjectURL(blob); } catch (err) { img.remove(); }
  });
}

/* Memories: editorial and photographic. Real pictures only -- the ones the
   family has shared from their phones. */
async function memoriesView(main) {
  main.classList.remove('chat-main');
  const all = await api('/artifacts?limit=200').catch(() => []);
  const pics = all.filter((a) => /^image\//.test(a.media_type) && a.channel !== 'errand' && !((a.source || {}).picture === 'document')).sort((a, b) => (a.received_at < b.received_at ? 1 : -1));
  const year = new Date().getFullYear();
  main.innerHTML = '<div class="memories"><div class="story">Our story</div><div class="year">' + year + '</div>'
    + (pics.length ? '<div class="masonry">' + pics.map((a) => '<figure><img alt="" data-pic="' + esc(a.id) + '"><figcaption>' + esc((a.source && a.source.subject) || a.note || a.filename || 'A moment') + '<span>' + esc(new Date(a.received_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long' })) + (a.submitted_by ? ' · ' + esc(memberName(a.submitted_by) || '') : '') + '</span></figcaption></figure>').join('') + '</div>'
      : '<section class="card empty"><h2>Nothing here yet.</h2><p class="muted" style="margin-top:8px;max-width:48ch;margin-left:auto;margin-right:auto">Share a photo from your phone with Send to FamilyOS and it lands here, with the date and who shared it. The story writes itself from there.</p></section>')
    + '</div>';
  main.querySelectorAll('img[data-pic]').forEach(async (img) => {
    try { const blob = await api('/artifacts/' + img.dataset.pic + '/picture', { blob: true }); img.src = URL.createObjectURL(blob); } catch (err) { img.closest('figure').remove(); }
  });
}
