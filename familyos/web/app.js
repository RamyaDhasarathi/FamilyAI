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

/* The session is an HttpOnly cookie the server sets when a link, a passkey or Google signs the person in: script never holds the token. store.token is
   only a marker ('session': signed in, as far as this page knows) so the code that asks whether anyone is signed in keeps working. Every request carries
   the CSRF header, which the server insists on for anything a cookie changes. */
const SESSION = 'session';
let probing = false;      // the first request after loading only asks whether a cookie is there: a 401 to it is an answer, not a sign-out
/* A browser signed in by an earlier version still holds the token in localStorage: trade it once for the cookie, and let go of it. */
async function adoptLegacyToken() {
  let old = null;
  try { old = localStorage.getItem('familyos.token'); } catch (e) { return; }
  if (!old) return;
  try {
    const r = await fetch('/v1/session', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-FamilyOS-CSRF': '1' }, body: JSON.stringify({ token: old }) });
    /* Let go of it when the server took it, or said the token itself is dead; a rate limit or a server error must not delete the only copy. */
    if (r.ok || r.status === 401) localStorage.removeItem('familyos.token');
  } catch (e) { /* the server could not be reached: keep it, try again next time */ }
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
/* Read-only boxes that select their text when clicked (a phrase, a link). An inline onclick would need script-src 'unsafe-inline'. */
document.addEventListener('click', (ev) => {
  const box = ev.target.closest && ev.target.closest('[data-select]');
  if (box && box.select) box.select();
});

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
  headers['X-FamilyOS-CSRF'] = '1';
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
    if (res.status === 401 && store.token && !probing) { forget(); }
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

/* The cockpit shell (/cockpit) brings its own chrome, Today, sign-in and Ask
   bar in cockpit.js, loaded first; on /app and /classic this is null and
   nothing below changes. */
const COCKPIT_UI = window.COCKPIT_UI || null;

const ROUTES = [
  { path: /^\/(today|home)$/, view: COCKPIT_UI ? COCKPIT_UI.today : pulseView, nav: 'home' },   // #/home is the old name, kept for links in the wild
  { path: /^\/family$/, view: COCKPIT_UI ? COCKPIT_UI.family : familyView, nav: 'family' },
  { path: /^\/me$/, view: myDayView, nav: 'me' },
  { path: /^\/decisions$/, view: decisionsView, nav: 'decisions' },
  { path: /^\/activity$/, view: activityView, nav: 'activity' },
  { path: /^\/knows$/, view: knowsView, nav: 'knows' },
  { path: /^\/map(?:\/(.+))?$/, view: mapView, nav: 'map' },
  { path: /^\/plan$/, view: moneyPlanView, nav: 'money' },
  { path: /^\/emergency$/, view: emergencyView, nav: 'emergency' },
  { path: /^\/whatif$/, view: whatIfView, nav: 'whatif' },
  { path: /^\/kids$/, view: kidsView, nav: 'kids' },
  { path: /^\/life$/, view: lifeView, nav: 'life' },
  { path: /^\/space\/([a-z]+)$/, view: spaceView, nav: 'space' },
  { path: /^\/memories$/, view: memoriesView, nav: 'memories' },
  { path: /^\/chat$/, view: chatView, nav: 'chat' },
  { path: /^\/notices\/([0-9a-f-]{36})$/i, view: COCKPIT_UI ? COCKPIT_UI.notice : noticeView },
  { path: /^\/notices$/, view: COCKPIT_UI ? COCKPIT_UI.inbox : noticesView, nav: 'notices' },
  { path: /^\/waiting$/, view: () => { go('/decisions'); }, nav: 'decisions' },
  { path: /^\/money$/, view: moneyView, nav: 'money' },
  { path: /^\/plans\/([0-9a-f-]{36})$/i, view: COCKPIT_UI ? COCKPIT_UI.plan : planView, nav: 'plans' },
  { path: /^\/plans$/, view: plansView, nav: 'plans' },
  { path: /^\/quarantine$/, view: quarantineView, nav: 'decisions' },
  { path: /^\/revisions$/, view: amendmentsView, nav: 'decisions' },
  { path: /^\/collect$/, view: collectView, nav: 'collect' },
  { path: /^\/household$/, view: householdView, nav: 'household' },
  { path: /^\/sign-in$/, view: signInView, nav: 'household' },
  { path: /^\/errands$/, view: errandsView, nav: 'errands' },
  { path: /^\/errands\/([0-9a-f-]{36})$/i, view: errandView, nav: 'errands' },
  { path: /^\/audit$/, view: auditView, nav: 'activity' },
];
if (COCKPIT_UI) {
  ROUTES.unshift({ path: /^\/more$/, view: COCKPIT_UI.more, nav: 'more' });
  ROUTES.unshift({ path: /^\/constitution$/, view: COCKPIT_UI.constitution, nav: 'more' });
  ROUTES.unshift({ path: /^\/care\/([0-9a-f-]{36})$/i, view: COCKPIT_UI.care, nav: 'family' });
}

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
  if (typeof firstRunDue === 'function' && await firstRunDue()) return;      // a brand-new home sees the first-run screens once (firstrun.js)
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
    + (route.view === chatView ? '' : (COCKPIT_UI ? COCKPIT_UI.askBar() : askBar()));
  wireChrome();
  wireAsk();
  if (COCKPIT_UI) COCKPIT_UI.after(route);
  const main = root.querySelector('main');
  try {
    await route.view(main, args);
    if (route.nav === 'home' || route.nav === 'me') setupBanner(main).catch(() => {});
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
  if (COCKPIT_UI) return COCKPIT_UI.chrome(active);
  const link = (id, name, label, extra, hue) =>
    '<a href="#/' + id + '"' + (active === id ? ' aria-current="page"' : '') + (TABS.includes(id) ? ' data-tab' : '') + '>'
    + '<span class="g"' + (hue ? ' style="color:var(--' + hue + ')"' : '') + '>' + icon(name) + '</span>'
    + '<span class="l">' + label + '</span>' + (extra || '') + '</a>';
  const settingsBadge = '';
  const dark = theme() === 'dark';
  const ms = members();
  return '<aside class="side">'
    + '<div class="brand"><span class="mark">' + icon('home', 16) + '</span><b>FamilyOS</b></div>'
    + '<nav class="nav">'
    + link('home', 'today', 'Today')
    + link('me', 'sparkle', 'My day')
    + link('life', 'family', 'Family')
    + link('memories', 'memories', 'Memories')
    + '<span class="group"></span>'
    + Object.entries(SPACES).filter(([, sp]) => !sp.onLife).map(([key, sp]) => key === 'money'
      ? link('money', 'money', sp.label, '', sp.hue)
      : link('space/' + key, key, sp.label, '', sp.hue).replace('href="#/space/' + key + '"', 'href="#/space/' + key + '"' + (active === 'space:' + key ? ' aria-current="page"' : ''))).join('')
    + '<span class="group"></span>'
    + link('notices', 'mail', 'Inbox')
    + link('decisions', 'bell', 'Needs you', (store.decisionCount || 0) + (store.me && store.me.role === 'guardian' ? (store.quarantineCount || 0) : 0) ? '<span class="count">' + ((store.decisionCount || 0) + (store.me && store.me.role === 'guardian' ? (store.quarantineCount || 0) : 0)) + '</span>' : '')
    + link('chat', 'sparkle', 'Ask')
    + link('activity', 'refresh', 'Activity')
    + link('knows', 'shield', 'What it knows')
    + link('map', 'family', 'Family map')
    + link('errands', 'cart', 'Errands')
    + (() => {      // the pages used less often, folded away; open while one of them is the page you are on
      const rare = [['emergency', 'shield', 'Emergency'], ['whatif', 'sparkle', 'What if']].concat(store.me && store.me.role === 'guardian' ? [['kids', 'family', 'Kids']] : []);
      return '<details class="nav-more"' + (rare.some((r) => r[0] === active) ? ' open' : '') + '><summary><span class="l">More pages</span></summary>' + rare.map((r) => link(r[0], r[1], r[2])).join('') + '</details>';
    })()
    + (store.me && store.me.role === 'guardian'
      ? '<span class="group"></span>'
        + link('collect', 'download', 'Collect')
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
/* Say it: record, and turn it into words on this machine (POST /v1/voice/transcribe; the audio is not kept). Where that is
   off or the microphone is refused, the browser's own speech recognition, if it has one. */
let _recording = null;
async function listen(onText) {
  if (_recording) { _recording.stop(); return; }
  if (navigator.mediaDevices && window.MediaRecorder) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = []; const rec = new MediaRecorder(stream); _recording = rec;
      const stopAt = setTimeout(() => { if (rec.state === 'recording') rec.stop(); }, 15000);
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = async () => {
        clearTimeout(stopAt); stream.getTracks().forEach((tr) => tr.stop()); _recording = null;
        const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
        try {
          const res = await fetch('/v1/voice/transcribe', { method: 'POST', headers: { 'X-FamilyOS-CSRF': '1', 'Content-Type': blob.type }, body: blob });
          if (!res.ok) throw new Error('status ' + res.status);
          const out = await res.json();
          if (out.text) onText(out.text); else flash('I could not make out any words. Try again closer to the microphone.', true);
        } catch (err) { flash('Could not turn that into words; type it instead.', true); }
      };
      rec.start(); flash('Listening. Tap the microphone again when you are done.');
      return;
    } catch (err) { /* no microphone here, or refused: try the browser's own */ }
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { flash('This browser cannot listen; type it instead.', true); return; }
  const r = new SR(); r.lang = 'en-IN'; r.interimResults = false;
  r.onresult = (ev) => { const text = ev.results[0][0].transcript; if (text) onText(text); };
  r.onerror = () => flash('Could not hear that.', true);
  r.start();
}
/* ⌘K: find, or ask. Typing finds pages, people, notices, plans and
   documents by their words; Enter opens the first hit, or, when nothing
   matches or the words end in a question mark, asks FamilyOS. */
const FIND_PAGES = [['Today', '#/today', 'today'], ['My day', '#/me', 'sparkle'], ['Needs you', '#/decisions', 'bell'], ['Activity', '#/activity', 'refresh'], ['What it knows', '#/knows', 'shield'], ['Money plan', '#/plan', 'money'], ['Emergency', '#/emergency', 'shield'], ['What if', '#/whatif', 'sparkle'], ['Kids', '#/kids', 'family'], ['Family', '#/family', 'family'], ['Life', '#/life', 'life'], ['Memories', '#/memories', 'memories'],
  ['Inbox', '#/notices', 'mail'], ['Needs you', '#/decisions', 'bell'], ['Ask', '#/chat', 'sparkle'], ['Plans', '#/plans', 'calendar'],
  ['Errands', '#/errands', 'cart'], ['Money', '#/money', 'money'], ['Settings', '#/household', 'settings'], ['Quarantine', '#/quarantine', 'shield'],
  ['Revisions', '#/revisions', 'refresh'], ['Collect', '#/collect', 'download'], ['Audit (technical log)', '#/audit', 'list']];
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
    timer = setTimeout(async () => {
      const q = input.value.trim(); const idx = await findIndex(); hits = findHits(q, idx); paint();
      // Then, by meaning, on this machine: what the words alone missed ("the plumber" finds "pipe repair").
      if (q.length < 3 || /\?\s*$/.test(q)) return;
      try {
        const found = await api('/search?q=' + encodeURIComponent(q) + '&limit=6');
        if (input.value.trim() !== q || found.mode !== 'meaning') return;
        const seen = new Set(hits.map((h) => h.href));
        found.hits.filter((h) => h.matched === 'meaning' && !seen.has('#/notices/' + h.notice.id)).slice(0, 4).forEach((h) => hits.push({
          kind: 'notice', title: h.notice.headline || 'Notice', sub: 'close in meaning · ' + h.notice.from_label + ' · ' + ago(h.notice.received_at),
          href: '#/notices/' + h.notice.id, icon: 'sparkle' }));
        paint();
      } catch (err) { /* words alone are already shown */ }
    }, 220);
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
  gateView();
}

async function signOut() {
  // End the token on the server first, which also clears the cookie: forgetting it in this page alone would leave it working.
  try {
    if (store.token) await api('/signout', { method: 'POST' });
  } catch (e) { /* already gone, or the server cannot be reached */ }
  forget();
}

/* ── sign in ──────────────────────────────────────────────────── */

function gateView(notice, opts) {
  // A plain signed-out visit, or a sign-out, goes back to the public front page at /. The gate stays for what needs it:
  // a message to show (an expired link), Google's hand-back, and the #start and #signin links from the front page.
  if (!notice && !opts && !/^#(start|signin)$/.test(window.location.hash) && /^\/(app|classic|orbit|cockpit)\//.test(window.location.pathname)) { window.location.replace('/'); return; }
  root.className = '';
  // opts.newEmail: Google verified this address and no household uses it, so
  // the gate opens on Start a household with it filled in rather than on a
  // sign-in that has nothing to sign into.
  const newEmail = (opts && opts.newEmail) || '';
  const founding = (opts && opts.founding) || '';
  if (COCKPIT_UI) root.innerHTML = COCKPIT_UI.gate({ newEmail });
    else root.innerHTML = '<div class="gate landing">'
      + '<nav class="land-nav" aria-label="Main navigation"><button class="land-brand" type="button" data-scroll="land-top" aria-label="FamilyOS home">'
      + '<span class="brand-sigil" aria-hidden="true"><i></i><i></i><i></i></span><b>FamilyOS</b></button>'
      + '<div class="land-nav-links"><button class="land-link" type="button" data-scroll="how-it-works">How it works</button><button class="land-link" type="button" data-scroll="trust">Trust</button>'
      + '<button class="land-link" type="button" data-open-auth="in">Sign in</button>'
      + '<button class="land-nav-cta" type="button" data-open-auth="new">Start your home</button></div></nav>'
      + '<main class="land-main" id="land-top">'
      + '<section class="land-hero" aria-labelledby="land-title"><div class="land-hero-copy">'
      + '<p class="eyebrow"><span></span> Proactive family AI &middot; source-backed</p>'
      + '<h1 id="land-title">Your family doesn\'t need another app.<br><em>It needs an agent.</em></h1>'
      + '<p class="land-deck">FamilyOS notices what your home needs, turns scattered messages into a plan, and brings every important action to you before anything happens.</p>'
      + '<div class="land-actions"><button class="land-primary" type="button" data-open-auth="new">Start with FamilyOS <span aria-hidden="true">&rarr;</span></button>'
      + '<button class="land-secondary" type="button" data-scroll="how-it-works">Watch the agent work <span aria-hidden="true">&darr;</span></button></div>'
      + '<div class="land-assurances"><span><i class="mini-check">&#10003;</i> Asks before it acts</span><span><i class="mini-check">&#10003;</i> Every detail has a source</span><span><i class="mini-check">&#10003;</i> Private by default</span></div>'
      + '</div><div class="hero-moment" aria-label="An example FamilyOS observation">'
      + '<span class="moment-spark">&#10022;</span><div><small>Agent online &middot; FamilyOS noticed</small><b>School bag ready. Museum form still needs you.</b></div>'
      + '<span class="moment-source">Source: Oakridge School &middot; due Thursday &middot; approval required</span>'
      + '</div></section>'
      + '<section class="land-proof" aria-label="FamilyOS principles"><p>One quiet place for the things scattered across</p><div><span>Gmail</span><span>WhatsApp</span><span>School apps</span><span>Documents</span><span>Calendars</span><span>Receipts</span></div></section>'
      + '<section class="land-story" id="how-it-works"><div class="story-copy"><p class="eyebrow"><span></span> 01 &middot; From noise to next step</p>'
      + '<h2>Drop in the chaos.<br><em>Get back a plan.</em></h2><p>Forward it, share it or photograph it. The agent reads what matters, connects it to the right person, and keeps it moving until everyone knows what happens next.</p>'
      + '<div class="story-steps"><article class="is-active"><b>01</b><div><h3>Notice</h3><p>Find the real ask inside messages, PDFs and screenshots.</p></div></article><article><b>02</b><div><h3>Understand</h3><p>Ground every date, amount and name in the original.</p></div></article><article><b>03</b><div><h3>Coordinate</h3><p>Put the right decision in front of the right person.</p></div></article><article><b>04</b><div><h3>Follow through</h3><p>Remind, prepare and track &mdash; without taking over.</p></div></article></div></div>'
      + '<div class="story-visual"><div class="message-stack"><article><span class="source-pill">Forwarded email</span><p>Dear parents, the museum consent form and ₹850 fee are due by Thursday...</p><small>Oakridge School &middot; 8:42 am</small></article><article class="extract-card"><span class="extract-label">FamilyOS noticed</span><h3>Museum trip needs approval</h3><ul><li><b>For</b><span>Meera</span></li><li><b>Due</b><span>Thursday, 12 Oct</span></li><li><b>Amount</b><span>₹850</span></li></ul><div class="source-quote">&ldquo;consent form and ₹850 fee are due by Thursday&rdquo;</div><div class="extract-actions"><button>Not for us</button><button class="approve">Approve</button></div></article></div></div></section>'
      + '<section class="land-bento"><div class="section-heading"><p class="eyebrow"><span></span> 02 &middot; Intelligence with context</p><h2>An AI built for the people<br><em>you actually love.</em></h2></div>'
      + '<div class="bento-grid"><article class="bento bento-wide"><div><span class="bento-kicker">Today</span><h3>One brief, not twelve apps.</h3><p>See what needs attention now, what is already handled and what can wait.</p></div><div class="week-strip"><span><small>M</small><i></i></span><span><small>T</small><i class="hot"></i></span><span class="today"><small>W</small><b>9</b></span><span><small>T</small><i></i></span><span><small>F</small><i></i></span></div></article>'
      + '<article class="bento bento-tall"><span class="bento-kicker">Family memory</span><h3>Context that belongs to your home.</h3><p>FamilyOS remembers preferences and corrections, while keeping visibility clear.</p><div class="people-stack"><span class="p-one">A</span><span class="p-two">P</span><span class="p-three">M</span><span class="p-four">V</span></div><div class="memory-line"><i></i><span>Meera\'s notices are shared with Arun and Priya</span></div></article>'
      + '<article class="bento bento-source"><span class="bento-kicker">Source-backed</span><h3>Tap any fact. See exactly where it came from.</h3><div class="source-paper"><span></span><span class="highlight"></span><span></span><span></span></div></article>'
      + '<article class="bento bento-calm"><span class="bento-kicker">Calm by design</span><h3>It learns what deserves silence.</h3><p>Promotions never become obligations. Investments stay quiet. Your rules win.</p><div class="quiet-control"><span>Only tell me when&hellip;</span><b>A person needs to decide</b><i></i></div></article>'
      + '<article class="bento bento-agent"><div class="agent-status"><i></i> Orbit online</div><span class="bento-kicker">Agent runtime</span><h3>Always looking.<br>Never acting alone.</h3><div class="agent-log"><p><b>09:42</b><span>ingest</span> school_email</p><p><b>09:42</b><span>ground</span> 3 facts to source</p><p><b>09:43</b><span>policy</span> guardian_approval</p><p class="agent-wait"><b>&rarr;</b><span>waiting</span> for Arun</p></div></article></div></section>'
      + '<section class="orbit-section" id="trust"><div class="orbit-intro"><p class="eyebrow light"><span></span> 03 &middot; Orbit inside</p><h2>Not a chatbot.<br><em>A governed family agent.</em></h2><p>FamilyOS runs on Orbit, a permission-first agent system. It can observe, reason and prepare across your tools, but important actions stop with you.</p></div>'
      + '<div class="orbit-flow" aria-label="The Orbit agent flow"><article><b>01</b><span>Observe</span><small>Your chosen sources</small></article><i></i><article><b>02</b><span>Understand</span><small>With evidence</small></article><i></i><article><b>03</b><span>Propose</span><small>A clear plan</small></article><i></i><article class="orbit-you"><b>&#10003;</b><span>You approve</span><small>Nothing important skips this</small></article><i></i><article><b>04</b><span>Follow through</span><small>With a receipt</small></article></div>'
      + '<div class="orbit-policies"><div><strong>Your rules are the operating system.</strong><span>Who can see what &middot; what may be prepared &middot; when to ask &middot; when to stay quiet</span></div><span class="policy-lock">Permission first</span></div></section>'
      + '<section class="land-auth-wrap" id="get-started"><div class="auth-promise"><p class="eyebrow"><span></span> Begin with one household</p><h2>Less chasing.<br><em>More being together.</em></h2><p>Start with the notices already arriving. FamilyOS will help turn them into a calmer week.</p><div class="auth-quote"><span>&ldquo;</span><p>The important thing is not that AI can act. It is that your family always knows <em>why</em>.</p></div></div>'
      + '<div class="auth-shell"><div class="tabs"><button data-tab="in" aria-pressed="' + String(!newEmail) + '">Sign in</button>'
      + '<button data-tab="new" aria-pressed="' + String(!!newEmail) + '">Start a household</button></div>'
      + '<div class="card pad auth-panel" data-panel="in"' + (newEmail ? ' hidden' : '') + '>'
      + '<button class="btn google-button" data-google>Continue with Google</button>'
      + '<p class="auth-note">Google shares your email address only. Reading mail is a separate choice you can decline.</p>'
      + '<div class="auth-rule"><span></span><small>or use a private email link</small><span></span></div>'
      + '<form class="stack" data-form="link">'
      + '<label>Your email<input type="email" name="email" placeholder="you@example.com" required '
      + 'autocomplete="email"></label>'
      + '<button class="btn auth-submit" type="submit">Email me a sign-in link</button>'
      + '<p class="sub" data-linksent hidden></p>'
      + '</form>'
      + '<details class="token-signin"><summary>I have a token</summary>'
      + '<form class="stack" data-form="in" style="margin-top:10px">'
      + '<label>Sign-in token<input type="password" name="token" placeholder="fos_&hellip;" autocomplete="off" required></label>'
      + '<button class="btn ghost" type="submit">Sign in</button></form></details>'
      + '</div>'
      + '<div class="card pad auth-panel" data-panel="new"' + (newEmail ? '' : ' hidden') + '>'
      + (newEmail
        ? '<p class="sub auth-confirmed">Google confirmed <b>' + esc(newEmail) + '</b>. '
          + 'No household uses it yet &mdash; start one and you will be its first guardian.</p>'
        : '')
      + '<form class="stack" data-form="new">'
      // Google has proved the address, so only a name is asked here; the family's name is asked on the first-run screens that follow.
      + (newEmail ? '' : '<label>Household name<input type="text" name="name" placeholder="The Carter family" required maxlength="100"></label>')
      + '<label>Your name<input type="text" name="display_name" placeholder="Emily" required maxlength="100"' + (newEmail ? ' autofocus' : '') + '></label>'
      + (newEmail ? '<input type="hidden" name="email" value="' + esc(newEmail) + '">' : '<label>Your email<input type="email" name="email" placeholder="you@example.com" required></label>')
      + '<p class="auth-note">You become the first guardian. Invite the rest of your family when you are ready.</p>'
      + '<button class="btn auth-submit" type="submit">Create my household</button></form></div></div></section>'
      + '</main><footer class="land-footer"><button class="land-brand" type="button" data-scroll="land-top"><span class="brand-sigil" aria-hidden="true"><i></i><i></i><i></i></span><b>FamilyOS</b></button><p>A home that remembers, without forgetting your boundaries.</p><button type="button" data-open-auth="in">Sign in</button></footer></div>';

  if (notice) flash(notice, true);

  root.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const want = btn.dataset.tab;
      root.querySelectorAll('[data-tab]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === want)));
      root.querySelectorAll('[data-panel]').forEach((p) => { p.hidden = p.dataset.panel !== want; });
    });
  });

  root.querySelectorAll('[data-open-auth]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const want = btn.dataset.openAuth || 'in';
      root.querySelectorAll('[data-tab]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === want)));
      root.querySelectorAll('[data-panel]').forEach((p) => { p.hidden = p.dataset.panel !== want; });
      const target = root.querySelector('#get-started');
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      window.setTimeout(() => {
        const field = root.querySelector('[data-panel="' + want + '"]:not([hidden]) input');
        if (field) field.focus({ preventScroll: true });
      }, 500);
    });
  });

  // The front page at / links here with #start or #signin: open that panel straight away.
  const wantAuth = { '#start': 'new', '#signin': 'in' }[window.location.hash];
  if (wantAuth) { const open = root.querySelector('[data-open-auth="' + wantAuth + '"]'); if (open) window.setTimeout(() => open.click(), 0); }

  root.querySelectorAll('[data-scroll]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = root.querySelector('#' + btn.dataset.scroll);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    try {
      await api('/session', { method: 'POST', json: { token } });      // the cookie; the pasted token is not kept
      store.token = SESSION;
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
      const person = form.get('display_name').trim();
      const made = await api('/households', { method: 'POST', json: {
        name: (form.get('name') || '').trim() || 'The ' + (person.split(' ').slice(-1)[0] || 'Our') + ' family',
        guardian: { display_name: form.get('display_name').trim(), email: form.get('email').trim() },
        founding: founding,
      } });
      store.token = SESSION;                  // the server set the cookie
      await boot();
    } catch (err) { fail(err); }
  });
}

/* A link arrives as #link=lnk_... on the console's own URL. Spend it, keep the
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
  /* The link now travels in the fragment (#link=...), which no server, proxy log or Referer header ever sees.
     The query form (?link=) is still honoured for mails sent before the change. */
  const params = new URLSearchParams(location.search);
  const fromHash = location.hash.match(/^#link=([^&]+)/);
  let link = null;
  try { link = fromHash ? decodeURIComponent(fromHash[1]) : params.get('link'); } catch (e) { link = fromHash ? fromHash[1] : null; }   // a malformed escape is still a link, and fails below like any bad one
  if (!link) return false;
  params.delete('link');
  const clean = location.pathname + (params.toString() ? '?' + params : '') + (fromHash ? '' : location.hash);
  try {
    await api('/sign-in/redeem', { method: 'POST', json: { link } });
    store.token = SESSION;
    history.replaceState(null, '', clean);
    await boot();
    return true;
  } catch (err) {
    history.replaceState(null, '', clean);
    store.token = null;
    gateView('That link has expired or has already been used. Ask for another.');
    return true;
  }
}

async function boot() {
  const me = await api('/me');
  store.me = me;
  store.token = SESSION;
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

const REASON_LABEL = { scam: 'Scam?', handled: 'Handled',
  missed: 'Missed', overdue: 'Overdue', today: 'Today', undecided: 'Undecided', soon: 'Coming up',
  amendment: 'Changed', quarantine: 'Held', mailbox: 'Mailbox', unbilled: 'No bill', school_year: 'New year', birthday: 'Birthday', majority: 'Of age', money: 'Money', prepare: 'Prepare',
};
const REASON_TONE = { scam: 'red', handled: 'green', missed: 'red', overdue: 'red', today: 'amber', undecided: 'amber', amendment: 'rust', quarantine: 'rust', mailbox: 'red', unbilled: 'rust', soon: 'blue' };

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
    + (i.pay_url ? '<span class="row wrap" style="gap:6px;margin-top:8px">' + payLinks(i.pay_url, '', i) + '</span>' : '')
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
    + (o.pay_url ? ' · ' + payLinks(o.pay_url, 'plain', o) : '') + '</div></span>'
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
      if (COCKPIT_UI && body.member_id) COCKPIT_UI.reversible('Handed over.', () => api('/artifacts/' + id + '/assign', { method: 'POST', json: { member_id: null, note: null } }));
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
    + '<p class="muted" style="line-height:1.55" data-shortcut-file hidden><b>Quicker:</b> open this page on the iPhone and <a href="/v1/shortcut">add the ready-made shortcut</a>.</p>'
    + '<p class="muted" style="line-height:1.55"><b>Android.</b> The same request from Tasker or MacroDroid, which '
    + 'can also fire on a notification \u2014 the only way to catch something nobody opened. iPhones cannot do that.</p>'
    + '<div class="row" style="justify-content:flex-end"><button class="btn" data-close-help>Close</button></div>'
    + '</div>';
  main.appendChild(el);
  fetch('/v1/shortcut', { credentials: 'same-origin' }).then((r) => { if (r.ok) el.querySelector('[data-shortcut-file]').hidden = false; }).catch(() => {});
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
    // Subresource Integrity for pdf.js 3.11.174 (the hash cdnjs publishes for this file).
    s.integrity = 'sha512-q+4liFwdPC/bNdhUpZx6aXDx/h77yEQtn4I1slHydcbZK34nLaR3cAeYSJshoxIOq3mjEf7xJE8YWIUHMn+oCQ==';
    s.crossOrigin = 'anonymous';
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
function payLinks(url, cls, item) {
  if (!url) return '';
  if (item && item.pay_host_new && item.pay_host) {      // a site this household has not paid through before: say where the button goes
    return '<span class="tag amber" style="text-transform:none;letter-spacing:0">first time paying ' + (item.pay_host.indexOf('@') > -1 ? 'to ' : 'via ') + esc(item.pay_host) + ' \u2014 check it is the biller</span> ' + payLinks(url, cls);
  }
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
    + (o.pay_url && o.status !== 'dismissed' && !gone ? payLinks(o.pay_url, '', o) : '')
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
  scam: { tone: 'red', label: 'scam?', glyph: '!', icon: 'shield' },
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
  main.innerHTML = needsTabs('quarantine') + '<div class="head"><div><div class="row" style="gap:10px"><h1>Quarantine</h1>'
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

  main.innerHTML = needsTabs('revisions') + '<div class="head"><div><h1>Revisions</h1>'
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
          + (sc.portal_url && /^https:\/\//i.test(sc.portal_url) ? '<a class="muted" href="' + esc(sc.portal_url) + '" target="_blank" rel="noopener">portal</a>' : '')
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

/* The Settings page is grouped, not one long list: each section opens and closes, the first two start open, and a link opens the one it names. */
function settingsSection(id, title, sub, open, inner) {
  return '<details class="set-sec" data-sec="' + id + '"' + (open ? ' open' : '') + '><summary><b>' + title + '</b><small class="muted">' + sub + '</small></summary><div class="stack">' + inner + '</div></details>';
}
function wireSettingsSections(main) {
  const secs = [...main.querySelectorAll('.set-sec')];
  const key = 'familyos.settings.open';
  let saved = null; try { saved = JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { /* default */ }
  if (Array.isArray(saved)) secs.forEach((d) => { d.open = saved.includes(d.dataset.sec); });
  const remember = () => { try { localStorage.setItem(key, JSON.stringify(secs.filter((d) => d.open).map((d) => d.dataset.sec))); } catch (e) { /* this session only */ } };
  secs.forEach((d) => d.addEventListener('toggle', remember));
  if (hashQuery().get('mailbox')) { const c = main.querySelector('.set-sec[data-sec="connections"]'); if (c) c.open = true; }
  const want = hashQuery().get('open'); if (want) { const w = main.querySelector('.set-sec[data-sec="' + want.replace(/[^a-z]/g, '') + '"]'); if (w) { w.open = true; w.scrollIntoView(); } }      // Google hands back to #/household?mailbox=connected
  main.querySelectorAll('[data-jump]').forEach((a) => a.addEventListener('click', (ev) => {
    ev.preventDefault();
    const d = main.querySelector('.set-sec[data-sec="' + a.dataset.jump + '"]'); if (!d) return;
    d.open = true; d.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
  let assistantsHtml = ''; if (store.me.role !== 'child') { try { assistantsHtml = await assistantSection(); } catch (e) { assistantsHtml = ''; } }
  store.household = household;
  store.mailboxes = mailboxes;
  const isGuardian = store.me.role === 'guardian';
  const children = (household.members || []).filter((m) => m.role === 'child');
  const active = (id) => consents.find((c) => c.subject_member_id === id && !c.withdrawn_at);

  main.innerHTML = '<div class="head"><div><h1>' + esc(household.name) + '</h1>'
    + '<p>Guardians manage the household and consent for the children. Children are not accounts and do not sign in.</p></div>'
    + (isGuardian ? '<button class="btn" data-addmember>Add a member</button>' : '') + '</div>'
    + '<div class="set-jump" role="navigation" aria-label="Settings sections"><a href="#/household" data-jump="people">People</a><a href="#/household" data-jump="privacy">Privacy and security</a>'
    + '<a href="#/household" data-jump="connections">Connections</a><a href="#/household" data-jump="rules">Notifications and rules</a><a href="#/household" data-jump="data">Your data</a><a href="#/household" data-jump="advanced">Advanced</a></div>'
    + '<div class="stack">'
    + settingsSection('people', 'People', 'Who is in the home, and what the children’s consent covers.', true,
        '<div class="card list" data-members></div><div class="card pad stack" data-consent></div>')
    + settingsSection('privacy', 'Privacy and security', 'Who can read your family’s words, and how people get in.', true,
        familyKeyCard() + modelsCard() + passkeysCard() + walletCard() + sessionsCard(mySessions))
    + settingsSection('connections', 'Connections', 'Where notices come from, and who else is connected.', false,
        mailboxesCard(mailboxes) + telegramCard(household) + whatsappCard() + phoneCard() + signedInCard(signedIn, sitesOffered, openSitting) + assistantsHtml)
    + settingsSection('rules', 'Notifications and rules', 'What FamilyOS may do, and when it reaches you.', false,
        rulesCard() + weeklyDigestCard())
    + settingsSection('data', 'Your data', 'A copy to download, and erasing the household. Documents (passports, policies) are on the Family page.', false,
        exportCard() + (isGuardian ? dangerCard(household) : ''))
    + settingsSection('advanced', 'Advanced', 'Setup helpers for what should arrive. Most families never need these.', false,
        watchesCard(watches) + gapsCard(summary, gaps))
    + '</div>'
    + memberDialog()
    + watchDialog()
    + gapDialog();

  wireDigest(main);
  wireRules(main);
  wirePhone(main);
  wireSignedIn(main);
  wireTelegram(main);
  wireFamilyKey(main);
  wireModels(main);
  wirePasskeys(main);
  wireWallet(main);
  wireWhatsApp(main);
  bindAssistant(main, () => householdView(main));
  wireSettingsSections(main);
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
      + (m.role !== 'child' && m.joined === false ? '<span class="tag">waiting to join</span>' : '')
      + (m.role !== 'child' && isGuardian && m.id !== store.me.id
        ? '<button class="btn ' + (m.joined === false ? '' : 'ghost ') + 'sm" data-invite="' + esc(m.id) + '" data-name="' + esc(m.display_name) + '">' + (m.joined === false ? 'Invite' : 'New sign-in link') + '</button>' : '')
      + (isGuardian || m.id === store.me.id ? '<button class="btn ghost sm" data-profile="' + esc(m.id) + '">Profile</button>' : '')
      + (m.role !== 'child' && (isGuardian || m.id === store.me.id)
        ? '<button class="btn ghost sm" data-signoutall="' + esc(m.id) + '">Sign out everywhere</button>' : '')
      + '<div class="invite-out" data-invite-out hidden style="flex-basis:100%"></div></div>';
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
    + '<div class="row wrap" style="gap:8px"><button class="btn ghost" type="button" data-read-school>Read the school app</button><a class="btn" href="#/chat" style="text-decoration:none">Ask for one</a></div></div>'
    + (list.length ? '<div class="stack" style="gap:10px">' + list.map(errandLine).join('') + '</div>'
      : '<section class="card pad"><p class="muted">Nothing yet. In Ask, say something like “book a kitchen deep clean on Urban Company Saturday morning, under ₹3,000”.</p></section>');
  // A look at the school's parent app, read on the phone: written down and opened, and its page says how to start the driver.
  const readSchool = main.querySelector('[data-read-school]');
  if (readSchool) readSchool.addEventListener('click', async () => {
    readSchool.disabled = true;
    try { const made = await api('/errands', { method: 'POST', json: { service: 'myclassboard', kind: 'look', title: 'Read the school app\u2019s announcements', spec: { what: 'Announcements' } } }); go('/errands/' + made.id); }
    catch (err) { readSchool.disabled = false; fail(err); }
  });
}

async function errandView(main, args) {
  main.classList.remove('chat-main');
  const e = await api('/errands/' + args[0]);
  const sp = e.spec || {};
  // An app on the person's phone (a school's parent app): read by the phone's own hands through the driver a Mac starts,
  // never by the server's browser, so the page says that and shows how to start it.
  const onPhone = !!(sp.where && sp.where.on === 'the phone');
  const isGuardian = store.me && store.me.role === 'guardian';
  const row = (k, v) => '<div class="row" style="gap:12px;align-items:flex-start"><span class="muted" style="width:120px;flex-shrink:0">' + k + '</span><span>' + v + '</span></div>';
  const stopList = Array.isArray(sp.stop_rules) ? sp.stop_rules.map((t) => '<span class="tag amber" style="text-transform:none;letter-spacing:0">' + esc(t) + '</span>').join('') : null;
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
    + (onPhone ? '' : row('When', sp.when && sp.when.date ? esc(fmtDate(sp.when.date)) + (sp.when.time ? ' at ' + esc(sp.when.time) : sp.when.part !== 'any' ? ', ' + esc(sp.when.part) : '') : 'any time' + (sp.when && sp.when.by ? ', by ' + esc(fmtDate(sp.when.by)) : '')))
    + row('Where', onPhone ? esc((sp.where.label || e.service) + ', on your phone') + (sp.where.bundle ? ' <span class="muted mono">(' + esc(sp.where.bundle) + ')</span>' : '') : esc((sp.where && sp.where.address) || 'the saved home address') + ' · ' + esc(((sp.where && sp.where.hosts) || []).join(', ')))
    + (onPhone ? '' : row('At most', '<b>' + esc(money(sp.limits ? sp.limits.max_amount : 0, sp.limits ? sp.limits.currency : 'INR')) + '</b>, one of it'))
    + (onPhone ? '' : row('Paid', sp.payment && sp.payment.mode === 'upi_request' ? 'by a UPI request you approve on your phone' : 'after the service, from the invoice that lands in the Inbox'))
    + (onPhone ? '' : row('Card', 'none — FamilyOS holds no card, PIN or password'))
    + row('Stops if', '<span class="row wrap" style="gap:6px">' + (stopList !== null ? stopList : stops) + '</span>')
    + '<p class="muted" style="font-size:12px">Fingerprint <span class="mono">' + esc(e.params_sha256.slice(0, 16)) + '…</span>. Approval is of exactly this; if anything about it changes, the approval no longer applies.</p>'
    + '</section>'
    + (e.status === 'approved' && onPhone ? '<section class="card pad stack" style="gap:10px"><h2>Approved. Waiting for the phone driver</h2><p class="muted">This is read on your iPhone, in the school\u2019s own app, by a driver a Mac starts. Unlock the phone, then run the command below on the Mac the phone is paired with. The sign-in stays in the app on the phone.</p>'
        + '<div class="row wrap" style="gap:8px"><button class="btn" data-copy-driver>Copy the driver\u2019s address</button><span class="muted" data-driver-said></span></div>'
        + '<pre class="mono" style="white-space:pre-wrap;font-size:12px;margin:0;padding:12px;border-radius:10px;background:var(--surface-2,rgba(128,128,128,.12))">TEST_RUNNER_FAMILYOS_SOCKET=\'&lt;the address you copied&gt;\' \\\nTEST_RUNNER_FAMILYOS_MINUTES=5 \\\nxcodebuild test -project ios/FamilyOS.xcodeproj -scheme FamilyOSDriver \\\n  -destination \'id=&lt;the phone\\u2019s UDID&gt;\' -allowProvisioningUpdates</pre>'
        + '<p class="muted" style="font-size:12px">The copied address works once, for ten minutes. Paste it only into that command.</p></section>' : '')
    + (e.status === 'approved' && !onPhone ? '<section class="card pad"><h2>Approved</h2><p class="muted">Starting in a fresh browser with your sealed ' + esc(e.service) + ' session. Steps appear below as they happen.</p></section>' : '')
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
    + (onPhone ? '<section class="card rail-card"><h2>How it runs</h2><p class="muted">On your iPhone, in the school\u2019s own app. A driver on a Mac opens the app, taps to the page named here, reads the words on the screen and keeps them as your private notice. Nothing is typed, sent or bought, and the app\u2019s sign-in never leaves the phone.</p></section>' : '<section class="card rail-card"><h2>How it runs</h2><p class="muted">In a fresh browser holding your sealed ' + esc((sp.where && sp.where.service) || e.service) + ' session, for the length of the run only. Every page it reaches is checked against the site’s own hosts. A screenshot is kept at each step. If a rule stops it, it stops and says why; if it needs you, you get the browser.</p></section>')
    + '</aside></div>';
  const copyDriver = main.querySelector('[data-copy-driver]');
  if (copyDriver) copyDriver.addEventListener('click', async () => {
    const said = main.querySelector('[data-driver-said]');
    // A one-use ticket, not the session token: it opens this errand's phone socket once, within ten minutes.
    try {
      const t = await api('/errands/' + e.id + '/phone-ticket', { method: 'POST' });
      await navigator.clipboard.writeText((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + t.path);
      said.textContent = 'Copied. It works once, for ten minutes.';
    } catch (x) { said.textContent = 'Could not copy here.'; }
  });
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

// ---- Where the household's words are read: model profiles, routing and the floor (modelroute.py)
function modelsCard() {
  return '<div class="card pad stack" data-models style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Where your words are read</h2></div><div data-models-body class="muted">Loading…</div></div>';
}
async function wireModels(main) {
  const card = main.querySelector('[data-models]'); if (!card) return;
  const body = card.querySelector('[data-models-body]'); const guardian = store.me && store.me.role === 'guardian';
  let m; try { m = await api('/household/models'); } catch (err) { body.textContent = err.message || 'Could not load.'; return; }
  const opt = (p, cur) => '<option value="' + esc(p.name) + '"' + (p.name === cur ? ' selected' : '') + '>' + esc(p.name === 'default' ? 'Default' : p.name) + ' · ' + esc(p.trust) + '</option>';
  const pick = (name, label, cur) => '<label>' + label + '<select name="' + name + '"' + (guardian ? '' : ' disabled') + '>' + m.profiles.map((p) => opt(p, cur)).join('') + '</select></label>';
  body.innerHTML = '<p style="line-height:1.55">Notices are read, and questions answered, by a language model. <b>cloud</b>: ' + esc(m.trust.cloud) + '. <b>confidential</b>: ' + esc(m.trust.confidential) + '. <b>own</b>: ' + esc(m.trust.own) + '.</p>'
    + '<ul class="mdlist">' + m.profiles.map((p) => '<li class="mdrow"><span class="grow"><b>' + esc(p.name === 'default' ? 'Default' : p.name) + '</b><small class="muted">' + esc(p.model) + ' · runs at ' + esc(p.where || 'this server') + '</small></span><span class="tag ' + (p.trust === 'cloud' ? 'amber' : 'green') + '">' + esc(p.trust) + '</span></li>').join('') + '</ul>'
    + '<form class="md-form" data-models-form>' + pick('extraction', 'Reads notices', m.routing.extraction) + pick('ask', 'Answers Ask', m.routing.ask)
    + '<label>Never below<select name="floor"' + (guardian ? '' : ' disabled') + '>' + ['cloud', 'confidential', 'own'].map((f) => '<option' + (f === m.routing.floor ? ' selected' : '') + '>' + f + '</option>').join('') + '</select></label>'
    + (guardian ? '<button class="btn sm" type="submit">Save</button>' : '<p class="muted" style="grid-column:1/-1">A guardian chooses.</p>') + '</form>'
    + '<p class="muted" style="font-size:12px;line-height:1.5">A choice below the floor is refused, never quietly sent somewhere else. Models beyond the default are added by whoever runs this server.</p>';
  const f = body.querySelector('[data-models-form]');
  if (guardian) f.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try { await api('/household/models', { method: 'PUT', json: { extraction: f.extraction.value, ask: f.ask.value, floor: f.floor.value } }); flash('Saved.'); } catch (err) { flash((err && err.message) || 'Could not save that.', true); }
  });
}

// ---- Passkeys: sign in with Face ID or the device unlock (passkeys.py)
function pkBuf(b64u) { let s = b64u.replace(/-/g, '+').replace(/_/g, '/'); s += '==='.slice((s.length + 3) % 4); const raw = atob(s); const out = new Uint8Array(raw.length); for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i); return out.buffer; }
function pkB64u(ab) { const b = new Uint8Array(ab); let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
function passkeysCard() {
  return '<div class="card pad stack" data-passkeys style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Passkeys</h2><span class="muted">sign in with Face ID</span></div><div data-passkeys-body class="muted">Loading…</div></div>';
}
async function wirePasskeys(main) {
  const card = main.querySelector('[data-passkeys]'); if (!card) return;
  const body = card.querySelector('[data-passkeys-body]');
  const fail = (err, d) => flash((err && err.name === 'NotAllowedError') ? 'No passkey was added.' : ((err && err.message) || d), true);
  const draw = async () => {
    let list; try { list = await api('/me/passkeys'); } catch (err) { body.textContent = err.message || 'Could not load.'; return; }
    const can = !!(window.PublicKeyCredential && navigator.credentials);
    body.innerHTML = '<p style="line-height:1.55">A passkey lets you sign in with Face ID or this device’s unlock: nothing to type, nothing to phish, no email to wait for. FamilyOS keeps only a public key. Add one on each device you use; a password manager can keep it across devices.</p>'
      + '<ul class="mdlist">' + (list.length ? list.map((k) => '<li class="mdrow" data-pid="' + esc(k.id) + '"><span class="grow"><b>' + esc(k.label) + '</b><small class="muted">' + (k.last_used_at ? 'last used ' + esc(new Date(k.last_used_at).toLocaleDateString('en', { day: 'numeric', month: 'short' })) : 'not used yet') + (k.backed_up ? ' · kept by a password manager' : '') + '</small></span><button class="btn ghost sm" data-pk-rm type="button">Remove</button></li>').join('') : '<li class="muted">None yet.</li>') + '</ul>'
      + (can ? '<form class="md-form" data-pk-add><label>Name this device<input name="l" maxlength="60" value="This device"></label><button class="btn sm" type="submit">Add a passkey on this device</button></form>' : '<p class="muted">This browser cannot make a passkey.</p>');
    body.querySelectorAll('[data-pk-rm]').forEach((b) => b.addEventListener('click', async () => { try { await api('/me/passkeys/' + b.closest('[data-pid]').dataset.pid, { method: 'DELETE' }); draw(); } catch (err) { fail(err, 'Could not remove it.'); } }));
    const f = body.querySelector('[data-pk-add]');
    if (f) f.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try {
        const o = await api('/me/passkeys/options', { method: 'POST' });
        const c = await navigator.credentials.create({ publicKey: { rp: o.rp, user: { id: pkBuf(o.user.id), name: o.user.name, displayName: o.user.displayName }, challenge: pkBuf(o.challenge), pubKeyCredParams: o.pubKeyCredParams, timeout: o.timeout,
          excludeCredentials: (o.excludeCredentials || []).map((x) => ({ type: x.type, id: pkBuf(x.id), transports: x.transports })), authenticatorSelection: o.authenticatorSelection, attestation: 'none', extensions: { prf: {} } } });
        await api('/me/passkeys', { method: 'POST', json: { label: f.l.value, credential: { id: c.id, rawId: pkB64u(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
          response: { clientDataJSON: pkB64u(c.response.clientDataJSON), attestationObject: pkB64u(c.response.attestationObject), transports: c.response.getTransports ? c.response.getTransports() : [] } } } });
        flash('Passkey added.'); draw();
      } catch (err) { fail(err, 'Could not add a passkey.'); }
    });
  };
  draw();
}

// ---- WhatsApp reading: the chats a member names, from their own linked WhatsApp Web (whatsapp_watch.py)
function whatsappCard() {
  return '<div class="card pad stack" data-wa style="gap:10px;display:none"><div class="row wrap" style="gap:8px"><h2>WhatsApp reading</h2><span class="muted" data-wa-tag></span></div><div data-wa-body class="muted">Loading…</div></div>';
}
async function wireWhatsApp(main) {
  const card = main.querySelector('[data-wa]'); if (!card) return;
  const body = card.querySelector('[data-wa-body]'); const tag = card.querySelector('[data-wa-tag]');
  let poll = null;
  const fail = (err, d) => flash((err && err.message) || d, true);
  const when = (v) => v ? new Date(v).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'not yet';
  const draw = async () => {
    let s; try { s = await api('/me/whatsapp'); } catch (err) { return; }
    if (!s.available) { card.style.display = 'none'; return; }
    card.style.display = '';
    tag.textContent = s.enabled ? 'reading every ' + s.every_minutes + ' min' : (s.status === 'linked' ? 'linked, not reading' : 'off');
    const costs = '<ul class="mdlist" style="margin:6px 0">' + s.consent.map((c) => '<li class="mdrow"><span class="grow"><small>' + esc(c) + '</small></span></li>').join('') + '</ul>';
    const hosted = s.model && s.model.trust === 'cloud';
    body.innerHTML = '<p style="line-height:1.55">FamilyOS reads <b>only the chats you name</b>, from your own WhatsApp Web, and turns dates and tasks in them into proposals you accept or not. It never sends, replies or reacts.</p>'
      + (s.has_phone ? '' : '<form class="md-form" data-wa-phone><label>Your phone number, with country code (the number your WhatsApp uses)<input name="p" type="tel" placeholder="+91 98765 43210" required></label><button class="btn sm" type="submit">Save number</button></form>')
      + (s.enabled && !s.needs_consent ? '' : costs)
      + '<form class="md-form" data-wa-chats><label>Chats to read, one per line (up to 8, exactly as WhatsApp names them)<textarea name="c" rows="3" placeholder="Class 2 Parents">' + esc(s.chats.join('\n')) + '</textarea></label><button class="btn ghost sm" type="submit">Save chats</button></form>'
      + ((s.chats.length && s.schools && s.schools.length)
        ? '<div class="stack" data-wa-tags style="gap:6px"><small class="muted">Whose is each chat? Its messages are attributed to the children at that school.</small>' + s.chats.map((c) => '<label class="row wrap" style="gap:8px;align-items:center"><span class="grow">' + esc(c) + '</span><select data-wa-tag="' + esc(c) + '"><option value="">Nobody in particular</option>' + s.schools.map((x) => '<option value="' + esc(x.school) + '"' + ((s.tags || {})[c] === x.school ? ' selected' : '') + '>' + esc(x.school + ' (' + x.children.join(', ') + ')') + '</option>').join('') + '</select></label>').join('') + '</div>'
        : '')
      + '<div class="row wrap" style="gap:8px;align-items:center"><span>Link: <b>' + esc(s.status.replace('_', ' ')) + '</b></span><button class="btn ghost sm" data-wa-link type="button">' + (s.status === 'linked' ? 'Link again' : 'Link WhatsApp') + '</button></div><div data-wa-code></div>'
      + (s.enabled
        ? (s.needs_consent ? '<p style="color:var(--amber, #b45309)"><b>Paused.</b> ' + esc(s.last_error || 'The model that reads your notices changed.') + '</p>' : '') + '<p class="muted">Last read ' + esc(when(s.last_ok_at)) + (s.last_found ? ', ' + s.last_found + ' new' : '') + (s.last_error ? '. ' + esc(s.last_error) : '') + '</p><div class="row wrap" style="gap:8px"><button class="btn sm" data-wa-now type="button">Read now</button><button class="btn danger sm" data-wa-forget type="button">Stop and forget</button></div>'
        : '')
      // The yes form: to start, and again when the consent no longer covers where the words go (the paused state).
      + ((!s.enabled || s.needs_consent)
        ? '<form class="md-form" data-wa-on><label class="row" style="gap:8px"><input type="checkbox" name="u"> I have read what this costs</label>'
          + (hosted ? '<label class="row" style="gap:8px"><input type="checkbox" name="h"> These chats may be read by ' + esc(s.model.where) + '</label>' : '')
          + '<button class="btn sm" type="submit">' + (s.enabled ? 'Resume reading' : 'Start reading every ' + s.every_minutes + ' minutes') + '</button></form>'
        : '');
    const ph = body.querySelector('[data-wa-phone]');
    if (ph) ph.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/me/phone', { method: 'PUT', json: { phone: ph.p.value } }); flash('Number saved.'); draw(); } catch (err) { fail(err, 'Could not save the number.'); } });
    body.querySelectorAll('[data-wa-tag]').forEach((sel) => sel.addEventListener('change', async () => { try { await api('/me/whatsapp/chats', { method: 'PUT', json: { chats: s.chats, tags: { [sel.dataset.waTag]: sel.value } } }); flash(sel.value ? 'Saved: its messages go to the children at ' + sel.value + '.' : 'Saved.'); } catch (err) { fail(err, 'Could not save.'); draw(); } }));
    body.querySelector('[data-wa-chats]').addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/me/whatsapp/chats', { method: 'PUT', json: { chats: ev.target.c.value.split('\n').map((x) => x.trim()).filter(Boolean) } }); flash('Saved.'); draw(); } catch (err) { fail(err, 'Could not save.'); } });
    body.querySelector('[data-wa-link]').addEventListener('click', async () => {
      const box = body.querySelector('[data-wa-code]');
      try {
        const o = await api('/me/whatsapp/link', { method: 'POST' });
        if (o.linked) { flash('Already linked.'); draw(); return; }
        box.innerHTML = o.code
          ? '<p style="margin-top:8px;line-height:1.55">On your phone: WhatsApp → Settings → Linked devices → Link a device → <b>Link with phone number instead</b>, then type this code:</p><p style="font:600 26px ui-monospace,Menlo,monospace;letter-spacing:.08em;margin:6px 0">' + esc(o.code) + '</p><p class="muted">Waiting for it…</p>'
          : '<p style="margin-top:8px;line-height:1.55">WhatsApp gave no code, so scan this QR instead. On your phone: WhatsApp → Settings → Linked devices → <b>Link a device</b>, then point the camera at it.</p><img data-wa-qr alt="WhatsApp QR code" style="width:220px;height:220px;background:#fff;padding:8px;border-radius:8px" src="data:image/png;base64,' + esc(o.qr || '') + '"><p class="muted">Waiting for you to scan it…</p>';
        const stop = Date.now() + (o.expires_in || 180) * 1000; clearInterval(poll);
        poll = setInterval(async () => {
          if (Date.now() > stop) { clearInterval(poll); box.innerHTML = '<p class="muted">The code expired. Press Link WhatsApp for a new one.</p>'; return; }
          try { const r = await api('/me/whatsapp/link'); if (r.status === 'linked') { clearInterval(poll); flash('Linked.'); draw(); } else if (r.qr) { const im = box.querySelector('[data-wa-qr]'); if (im) im.src = 'data:image/png;base64,' + r.qr; } } catch (e) { /* keep waiting */ }
        }, 4000);
      } catch (err) { fail(err, 'Could not start linking.'); }
    });
    const on = body.querySelector('[data-wa-on]');
    if (on) on.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/me/whatsapp/enable', { method: 'POST', json: { understood: !!on.u.checked, cloud_ok: !!(on.h && on.h.checked) } }); flash('Reading is on.'); draw(); } catch (err) { fail(err, 'Could not switch on.'); } });
    const now = body.querySelector('[data-wa-now]');
    if (now) now.addEventListener('click', async () => { now.disabled = true; try { await api('/me/whatsapp/read-now', { method: 'POST' }); flash('Read.'); } catch (err) { fail(err, 'Could not read now.'); } draw(); });
    const fg = body.querySelector('[data-wa-forget]');
    if (fg) fg.addEventListener('click', async () => { try { const r = await api('/me/whatsapp', { method: 'DELETE' }); flash(r.note || 'Forgotten.'); draw(); } catch (err) { fail(err, 'Could not forget.'); } });
  };
  draw();
}

// ---- First-run checklist: sign in, name the home, add the family, make it private (onboarding.py)
function printRecoveryKit(shares, threshold) {
  const w = window.open('', '_blank'); if (!w) { flash('Allow pop-ups to print the kit, or copy the shares by hand.', true); return; }
  const card = (x, i) => '<section><h2>Recovery share ' + (i + 1) + ' of ' + shares.length + '</h2><p class="who">Held by: ______________________</p><ol>'
    + x.split(' ').map((word) => '<li>' + word.replace(/[<>&]/g, '') + '</li>').join('') + '</ol></section>';
  w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>FamilyOS recovery kit</title><style>'
    + 'body{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:24px;color:#111}h1{font-size:20px;margin:0 0 4px}p.s{margin:0 0 18px;color:#444}'
    + 'section{border:2px dashed #888;border-radius:12px;padding:14px 18px;margin:0 0 16px;page-break-inside:avoid}h2{font-size:15px;margin:0 0 4px}.who{margin:0 0 8px;color:#444}'
    + 'ol{columns:3;margin:0;padding-left:26px;font:13px/1.7 ui-monospace,Menlo,monospace}@media print{body{margin:12mm}}</style></head><body>'
    + '<h1>FamilyOS recovery kit</h1><p class="s">Any ' + threshold + ' of these ' + shares.length + ' shares open your family’s home. FamilyOS keeps none. Cut along the lines, give each share to a different person or place, and never keep two together. If fewer than ' + threshold + ' survive, nobody can recover the home, including us.</p>'
    + shares.map(card).join('') + '</body></html>');
  w.document.close(); w.focus(); setTimeout(() => w.print(), 300);
}
let fkGoto = false;   // set by the checklist's "Make it private"; the Family key card scrolls to its button once drawn
async function setupBanner(main) {
  let s; try { s = await api('/household/onboarding'); } catch (e) { return; }
  if (!s.show || main.querySelector('[data-setup]')) return;
  const act = (st) => {
    if (st.done) return '<span class="tag green">done</span>';
    if (st.key === 'named') return '<button class="btn sm" data-setup-do="named" type="button">Looks right</button>';
    if (st.key === 'family') return '<a class="btn sm" href="#/household" style="text-decoration:none">Add family</a>';
    if (st.key === 'private') return '<a class="btn sm" href="#/household" data-fk-goto style="text-decoration:none">Make it private</a><button class="btn ghost sm" data-setup-do="skip_private" type="button">Later</button>';
    return '';
  };
  const rows = s.steps.map((st) => '<li class="mdrow"><span class="dot' + (st.done ? '' : ' warn') + '" style="' + (st.done ? 'background:var(--green)' : '') + '"></span><span class="grow"><b>' + esc(st.title) + '</b><small class="muted">' + esc(st.detail) + (st.optional && !st.done ? ' (optional)' : '') + '</small></span>' + act(st) + '</li>').join('');
  main.insertAdjacentHTML('afterbegin', '<section class="card pad setup" data-setup style="margin-bottom:14px"><div class="row wrap" style="gap:10px"><h2>Set up your home</h2><span class="muted">' + s.done + ' of ' + s.total + ' done</span><span class="grow"></span><button class="btn ghost sm" data-setup-do="dismissed" type="button">Hide</button></div><ul class="mdlist">' + rows + '</ul></section>');
  // The phrase is a deliberate act, so the checklist takes the guardian to the button rather than tapping it for them.
  main.querySelectorAll('[data-fk-goto]').forEach((a) => a.addEventListener('click', () => {
    fkGoto = true;
    if (location.hash === '#/household') { const c = document.querySelector('[data-fk-simple]'); if (c) { c.scrollIntoView({ block: 'center' }); c.focus(); fkGoto = false; } }
  }));
  main.querySelectorAll('[data-setup-do]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/household/onboarding/' + b.dataset.setupDo, { method: 'POST' }); const old = main.querySelector('[data-setup]'); if (old) old.remove(); await setupBanner(main); } catch (err) { flash((err && err.message) || 'Could not save that.', true); }
  }));
}

// ---- Family key: the household's key held as Shamir shares (familykey.py, docs/family-key.md)
function familyKeyCard() {
  return '<div class="card pad stack" data-fkey style="gap:10px"><div class="row wrap" style="gap:8px"><h2>Family key</h2><span class="muted" data-fkey-tag></span></div><div data-fkey-body class="muted">Loading…</div></div>';
}
function parseShares(text) {
  const words = (text || '').toLowerCase().split(/\s+/).filter(Boolean); const out = [];
  for (let i = 0; i + 33 <= words.length; i += 33) out.push(words.slice(i, i + 33).join(' '));
  return out;
}

// Make it private: one recovery phrase plus this browser's own device secret (familykey.py, docs/family-key.md). The phrase is shown once and
// never kept here; the device secret lives only in this browser, so a passkey sign-in plus this browser opens the household.
function fkDevKey() { return 'familyos.fkdev.' + ((store.me && (store.me.id || store.me.member_id)) || ''); }
function fkReadDev() { try { return JSON.parse(localStorage.getItem(fkDevKey()) || 'null'); } catch (e) { return null; } }
function fkWriteDev(v) { try { if (v) localStorage.setItem(fkDevKey(), JSON.stringify(v)); else localStorage.removeItem(fkDevKey()); } catch (e) { /* a private window cannot keep it */ } }
async function fkPasskeySignIn() {
  const o = await api('/sign-in/passkey/options', { method: 'POST' });
  const c = await navigator.credentials.get({ publicKey: { challenge: pkBuf(o.challenge), rpId: o.rpId, timeout: o.timeout, userVerification: 'required', allowCredentials: [] } });
  const r = c.response;
  const done = await api('/sign-in/passkey', { method: 'POST', json: { credential: { id: c.id, rawId: pkB64u(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
    response: { clientDataJSON: pkB64u(r.clientDataJSON), authenticatorData: pkB64u(r.authenticatorData), signature: pkB64u(r.signature), userHandle: r.userHandle ? pkB64u(r.userHandle) : null } } } });
  store.token = SESSION;
}
function saveRecoveryPhrase(phrase) {
  const text = 'FamilyOS recovery phrase\n\n' + phrase.split(' ').reduce((acc, w, i) => acc + w + ((i + 1) % 6 === 0 ? '\n' : ' '), '').trim()
    + '\n\nThis phrase opens your family’s home if every trusted device is lost. FamilyOS does not keep it and cannot recover it. Keep it somewhere safe and private: a password manager, or paper in a drawer. Anyone who has it can open the household.\n';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' })); a.download = 'FamilyOS-recovery-phrase.txt';
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
function printRecoveryPhrase(phrase) {
  const w = window.open('', '_blank'); if (!w) { flash('Allow pop-ups to print it, or download it instead.', true); return; }
  w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>FamilyOS recovery phrase</title><style>body{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:24px;color:#111}'
    + 'section{border:2px dashed #888;border-radius:12px;padding:14px 18px}ol{columns:3;margin:8px 0 0;padding-left:26px;font:13px/1.7 ui-monospace,Menlo,monospace}@media print{body{margin:12mm}}</style></head><body>'
    + '<h1>FamilyOS recovery phrase</h1><p>Opens your family’s home if every trusted device is lost. FamilyOS keeps no copy. Keep it private and safe.</p><section><ol>'
    + phrase.split(' ').map((word) => '<li>' + word.replace(/[<>&]/g, '') + '</li>').join('') + '</ol></section></body></html>');
  w.document.close(); w.focus(); setTimeout(() => w.print(), 300);
}
function phraseBlock(phrase, intro) {
  return '<div class="stack" style="gap:8px;margin-top:10px"><p style="font-weight:600">' + intro + '</p>'
    + '<textarea readonly rows="5" data-fk-phrase style="font-family:var(--mono);font-size:12px" data-select>' + esc(phrase) + '</textarea>'
    + '<div class="row wrap" style="gap:8px"><button class="btn sm" data-fk-save type="button">Download recovery phrase</button><button class="btn ghost sm" data-fk-print type="button">Print it</button></div>'
    + '<label class="row" style="gap:8px"><input type="checkbox" data-fk-saved> I have saved it somewhere safe</label>'
    + '<div><button class="btn sm" data-fk-finish type="button" disabled>Done</button></div></div>';
}
function wirePhraseBlock(root, phrase, onDone) {
  root.querySelector('[data-fk-save]').addEventListener('click', () => saveRecoveryPhrase(phrase));
  root.querySelector('[data-fk-print]').addEventListener('click', () => printRecoveryPhrase(phrase));
  const box = root.querySelector('[data-fk-saved]'); const fin = root.querySelector('[data-fk-finish]');
  box.addEventListener('change', () => { fin.disabled = !box.checked; });
  fin.addEventListener('click', onDone);
}
async function wireFamilyKey(main) {
  const card = main.querySelector('[data-fkey]'); if (!card) return;
  const body = card.querySelector('[data-fkey-body]'); const tag = card.querySelector('[data-fkey-tag]');
  const guardian = store.me && store.me.role === 'guardian';
  const fail = (err, d) => flash((err && err.message) || d, true);
  const shareBox = (label, id) => '<label>' + label + '<textarea data-sh="' + id + '" rows="4" placeholder="Paste the shares, one after another" style="font-family:var(--mono);font-size:12px"></textarea></label>';
  const drawSimple = async (s) => {
    tag.textContent = s.locked ? 'locked' : 'unlocked';
    const dev = fkReadDev(); const canKey = !!(window.PublicKeyCredential && navigator.credentials);
    let mine = []; try { mine = await api('/household/family-key/devices'); } catch (e) { /* the list is a convenience */ }
    const trustedHere = !!(dev && mine.some((d) => d.id === dev.id));
    const prfDev = mine.find((d) => d.prf);                       // a device whose secret lives in a passkey, not in this browser
    const phraseForm = '<form data-fk-recover class="stack" style="gap:8px;margin-top:8px"><label>Recovery phrase<textarea data-fk-in rows="4" placeholder="Paste your recovery phrase" style="font-family:var(--mono);font-size:12px"></textarea></label><button class="btn ghost sm" type="submit">Use recovery phrase</button></form>';
    const devices = '<ul class="mdlist" style="margin-top:8px">' + mine.map((d) => '<li class="mdrow" data-did="' + esc(d.id) + '"><span class="grow"><b>' + esc(d.label) + (dev && dev.id === d.id ? ' (this browser)' : '') + '</b><small class="muted">' + (d.last_used_at ? 'last opened ' + esc(new Date(d.last_used_at).toLocaleDateString()) : 'not opened yet') + '</small></span><button class="btn ghost sm" data-fk-rmdev type="button">Remove</button></li>').join('') + '</ul>';
    if (s.locked) {
      body.innerHTML = '<p style="line-height:1.55">The household is <b>locked</b>. Everything sealed stays unreadable until someone opens it.</p>'
        + ((trustedHere || prfDev) && canKey ? '<div style="margin-top:8px"><button class="btn" data-fk-pk type="button">Unlock with passkey</button></div>'
          : '<p class="muted" style="line-height:1.55">' + (trustedHere ? 'This browser cannot use a passkey.' : 'This browser is not a trusted device yet. Use your recovery phrase now, then choose “Trust this browser”.') + '</p>')
        + '<details style="margin-top:10px"' + ((trustedHere || prfDev) && canKey ? '' : ' open') + '><summary>Use recovery phrase</summary>' + phraseForm + '</details>';
    } else {
      body.innerHTML = '<p style="line-height:1.55">The household is <b>unlocked</b> for about ' + s.unlocked_for_minutes + ' more minutes, then it locks again.</p>'
        + (!trustedHere && !prfDev && canKey ? '<p class="muted" style="line-height:1.55">You opened it with the recovery phrase. Trust this browser and next time a passkey opens it, with no phrase to find.</p>' : '')
        + '<div class="row wrap" style="gap:8px;margin-top:6px"><button class="btn ghost sm" data-fk-lock type="button">Lock now</button>' + (trustedHere ? '' : '<button class="btn sm" data-fk-trust type="button">Trust this browser</button>') + '</div>'
        + '<p class="muted" style="margin-top:12px">Trusted devices</p>' + devices
        + (guardian ? '<details style="margin-top:10px"><summary>Make a new recovery phrase</summary><p class="muted" style="line-height:1.55;margin:6px 0">The old phrase stops working. Your devices keep working.</p><button class="btn ghost sm" data-fk-newphrase type="button">Make a new phrase</button><div data-fk-newout></div></details>'
          + '<details style="margin-top:6px"><summary>Go back to the server holding the key</summary><form class="md-form" data-fk-off><label>Recovery phrase<textarea data-fk-in rows="4" placeholder="Paste your recovery phrase" style="font-family:var(--mono);font-size:12px"></textarea></label><button class="btn danger sm" type="submit">Go back</button></form></details>' : '');
    }
    const pk = body.querySelector('[data-fk-pk]');
    if (pk) pk.addEventListener('click', async () => {
      // A local device sends its stored secret; a passkey-derived one is asked of the passkey now (a second tap) and kept nowhere.
      const send = async () => {
        if (trustedHere) return api('/household/family-key/unlock-with-passkey', { method: 'POST', json: { device_id: dev.id, device_secret: dev.secret } });
        const d = await fkPrfDerive({ credentialId: prfDev.credential_id, salt: prfDev.salt });
        if (!d) throw new Error('This passkey cannot open the household here. Use your recovery phrase.');
        return api('/household/family-key/unlock-with-passkey', { method: 'POST', json: { device_id: prfDev.id, device_secret: d.secret } });
      };
      try {
        try { await send(); } catch (err) { if (err && err.body && err.body.error === 'passkey_needed') { await fkPasskeySignIn(); await send(); } else throw err; }
        flash('Unlocked.'); draw();
      } catch (err) { flash((err && err.name === 'NotAllowedError') ? 'No passkey was used.' : ((err && err.message) || 'Could not unlock.'), true); }
    });
    const rec = body.querySelector('[data-fk-recover]');
    if (rec) rec.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/household/family-key/recover', { method: 'POST', json: { phrase: rec.querySelector('[data-fk-in]').value } }); flash('Unlocked.'); draw(); } catch (err) { fail(err, 'That phrase did not work.'); } });
    const tr = body.querySelector('[data-fk-trust]');
    if (tr) tr.addEventListener('click', async () => {
      try {
        let derived = null;
        try { if ((await api('/me/passkeys')).length) derived = await fkPrfDerive({}); } catch (e) { derived = null; }      // no passkey, or none that does PRF: the stored secret below
        if (derived) {
          await api('/household/family-key/devices', { method: 'POST', json: { label: 'This passkey', prf: fkPrfBody(derived) } });
          flash('Trusted. The secret lives in your passkey; this browser keeps nothing.'); draw(); return;
        }
        const r = await api('/household/family-key/devices', { method: 'POST', json: { label: 'This browser' } });
        fkWriteDev({ id: r.id, secret: r.secret }); const kept = fkReadDev();
        if (!kept || kept.secret !== r.secret) { flash('This browser cannot keep a device secret (a private window?).', true); return; }
        flash('This browser is trusted.'); draw();
      } catch (err) { fail(err, 'Could not trust this browser.'); }
    });
    body.querySelectorAll('[data-fk-rmdev]').forEach((b) => b.addEventListener('click', async () => {
      const id = b.closest('[data-did]').dataset.did;
      try { await api('/household/family-key/devices/' + id, { method: 'DELETE' }); if (dev && dev.id === id) fkWriteDev(null); draw(); } catch (err) { fail(err, 'Could not remove it.'); }
    }));
    const lk = body.querySelector('[data-fk-lock]'); if (lk) lk.addEventListener('click', async () => { try { await api('/household/family-key/lock', { method: 'POST' }); flash('Locked.'); draw(); } catch (err) { fail(err, 'Could not lock.'); } });
    const np = body.querySelector('[data-fk-newphrase]');
    if (np) np.addEventListener('click', async () => {
      try {
        const r = await api('/household/family-key/new-phrase', { method: 'POST' }); np.hidden = true;
        const out = body.querySelector('[data-fk-newout]'); out.innerHTML = phraseBlock(r.phrase, 'Your new recovery phrase. The old one no longer works.');
        wirePhraseBlock(out, r.phrase, () => { flash('Saved.'); draw(); });
      } catch (err) { fail(err, 'Could not make a new phrase.'); }
    });
    const off = body.querySelector('[data-fk-off]');
    if (off) off.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try { await api('/household/family-key/disable', { method: 'POST', json: { shares: [off.querySelector('[data-fk-in]').value] } }); fkWriteDev(null); flash('The server holds the key again.'); draw(); } catch (err) { fail(err, 'That phrase did not work.'); }
    });
  };
  const draw = async () => {
    let s; try { s = await api('/household/family-key'); } catch (err) { body.textContent = err.message || 'Could not load.'; return; }
    if (s.mode === 'server') {
      tag.textContent = 'held by the server';
      body.innerHTML = '<p style="line-height:1.55">Make your family’s home private to your family. One tap makes a recovery phrase for you to keep. After that FamilyOS holds no key it can open the home with on its own, and each of your devices opens it with a passkey.</p>'
        + '<p class="muted" style="line-height:1.55;margin-top:6px">Protects the original files, the mailbox connection and signed-in sessions, at rest and in backups, and the text read out of notices once it is sealed. It does not hide what FamilyOS reads while the household is unlocked, or from the model provider doing the reading.</p>'
        + (guardian ? '<div style="margin-top:10px"><button class="btn" data-fk-simple type="button">Make it private</button></div><div data-fk-simple-out></div>'
          + '<details style="margin-top:12px"><summary>Advanced: split among several people</summary><p class="muted" style="line-height:1.55;margin:6px 0">Instead of one phrase, make word shares and give them to different people; any few open the household. FamilyOS keeps no share.</p>' + '<form class="md-form" data-fk-begin><label>Shares needed to open<select name="t">' + [2, 3, 4].map((n) => '<option>' + n + '</option>').join('') + '</select></label><label>Shares made<select name="n">' + [3, 4, 5, 6].map((n) => '<option>' + n + '</option>').join('') + '</select></label><button class="btn sm" type="submit">Make the shares</button></form><div data-fk-out></div>' + '</details>' : '<p class="muted">A guardian can switch this on.</p>');
      const mk = body.querySelector('[data-fk-simple]');
      if (mk && fkGoto) { fkGoto = false; mk.scrollIntoView({ block: 'center' }); mk.focus(); }
      if (mk) mk.addEventListener('click', async () => {
        try {
          let derived = null;
          try { if ((await api('/me/passkeys')).length) derived = await fkPrfDerive({}); } catch (e) { derived = null; }   // a passkey that does PRF keeps the secret; else this browser does
          const r = await api('/household/family-key/simple', { method: 'POST', json: derived ? { label: 'This passkey', prf: fkPrfBody(derived) } : { label: 'This browser' } });
          let kept;
          if (derived) { kept = { id: r.device.id, secret: derived.secret }; }
          else {
            fkWriteDev({ id: r.device.id, secret: r.device.secret });
            kept = fkReadDev();
            if (!kept || kept.secret !== r.device.secret) { flash('This browser cannot keep a device secret (a private window?). Open FamilyOS in a normal window and try again.', true); return; }
          }
          mk.hidden = true;
          const out = body.querySelector('[data-fk-simple-out]');
          out.innerHTML = phraseBlock(r.phrase, 'Your recovery phrase. Shown once; FamilyOS does not keep it.');
          wirePhraseBlock(out, r.phrase, async () => {
            try { await api('/household/family-key/simple/done', { method: 'POST', json: { device_id: kept.id, device_secret: kept.secret } }); flash('It is private now.'); draw(); } catch (err) { fail(err, 'Could not switch it on.'); }
          });
        } catch (err) { fail(err, 'Could not make it private.'); }
      });

      const f = body.querySelector('[data-fk-begin]');
      if (f) f.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        try {
          const r = await api('/household/family-key/begin', { method: 'POST', json: { threshold: +f.t.value, count: +f.n.value } });
          body.querySelector('[data-fk-out]').innerHTML = '<p style="margin-top:10px;font-weight:600">Write each share on paper, or keep it in a password manager, and give them to ' + r.count + ' different people. Shown once.</p>'
            + r.shares.map((x, i) => '<label style="margin-top:8px">Share ' + (i + 1) + ' of ' + r.count + '<textarea readonly rows="5" style="font-family:var(--mono);font-size:12px" data-select>' + esc(x) + '</textarea></label>').join('')
            + '<button class="btn ghost sm" data-fk-print type="button" style="margin-top:10px">Print the recovery kit</button>'
            + '<form data-fk-confirm style="margin-top:12px">' + shareBox('Nothing has changed yet. To switch on, paste ' + r.threshold + ' of them back', 'c') + '<button class="btn sm" type="submit" style="margin-top:8px">Switch on the family key</button></form>';
          body.querySelector('[data-fk-print]').addEventListener('click', () => printRecoveryKit(r.shares, r.threshold));
          body.querySelector('[data-fk-confirm]').addEventListener('submit', async (e2) => {
            e2.preventDefault(); const got = parseShares(body.querySelector('[data-sh=c]').value);
            if (got.length < r.threshold) { flash('Paste ' + r.threshold + ' shares.', true); return; }
            try { await api('/household/family-key/confirm', { method: 'POST', json: { shares: got } }); flash('The family key is on.'); draw(); } catch (err) { fail(err, 'Those shares did not work.'); }
          });
        } catch (err) { fail(err, 'Could not make the shares.'); }
      });
      return;
    }
    if (s.simple) { await drawSimple(s); return; }
    tag.textContent = s.locked ? 'locked' : 'unlocked';
    const reshareForm = '<details style="margin-top:10px"><summary>Make new shares</summary><form class="md-form" data-fk-reshare>' + shareBox('Current shares', 'r') + '<label>Shares needed<select name="t">' + [2, 3, 4].map((n) => '<option>' + n + '</option>').join('') + '</select></label><label>Shares made<select name="n">' + [3, 4, 5, 6].map((n) => '<option>' + n + '</option>').join('') + '</select></label><button class="btn sm" type="submit">Make new shares</button></form><div data-fk-out2></div></details>'
      + '<details style="margin-top:6px"><summary>Go back to the server holding the key</summary><form class="md-form" data-fk-off>' + shareBox('Current shares', 'o') + '<button class="btn danger sm" type="submit">Go back</button></form></details>';
    body.innerHTML = '<p style="line-height:1.55">' + (s.locked ? 'The household is <b>locked</b>. The files stay sealed until ' + s.threshold + ' of the ' + s.shares + ' shares are given.' : 'The household is <b>unlocked</b> for about ' + s.unlocked_for_minutes + ' more minutes, then it locks again.') + '</p>'
      + (s.locked ? '<form data-fk-unlock>' + shareBox('Paste ' + s.threshold + ' shares', 'u') + '<button class="btn sm" type="submit" style="margin-top:8px">Unlock</button></form>' : '<button class="btn ghost sm" data-fk-lock type="button">Lock now</button>')
      + (guardian ? reshareForm : '');
    const act = (sel, path, key, extra) => { const el = body.querySelector(sel); if (el) el.addEventListener('submit', async (ev) => { ev.preventDefault(); const got = parseShares(body.querySelector('[data-sh=' + key + ']').value); if (got.length < s.threshold) { flash('Paste ' + s.threshold + ' shares.', true); return; } try { await extra(path, got, el); } catch (err) { fail(err, 'Those shares did not work.'); } }); };
    act('[data-fk-unlock]', '/household/family-key/unlock', 'u', async (p, got) => { await api(p, { method: 'POST', json: { shares: got } }); flash('Unlocked.'); draw(); });
    act('[data-fk-off]', '/household/family-key/disable', 'o', async (p, got) => { await api(p, { method: 'POST', json: { shares: got } }); flash('The server holds the key again.'); draw(); });
    act('[data-fk-reshare]', '/household/family-key/reshare', 'r', async (p, got, el) => {
      const r = await api(p, { method: 'POST', json: { shares: got, threshold: +el.t.value, count: +el.n.value } });
      body.querySelector('[data-fk-out2]').innerHTML = '<p style="margin-top:10px;font-weight:600">New shares. The old ones no longer open anything. Shown once.</p>' + r.shares.map((x, i) => '<label style="margin-top:8px">Share ' + (i + 1) + ' of ' + r.count + '<textarea readonly rows="5" style="font-family:var(--mono);font-size:12px" data-select>' + esc(x) + '</textarea></label>').join('');
    });
    const lk = body.querySelector('[data-fk-lock]'); if (lk) lk.addEventListener('click', async () => { try { await api('/household/family-key/lock', { method: 'POST' }); flash('Locked.'); draw(); } catch (err) { fail(err, 'Could not lock.'); } });
    await wirePasskeyShares(body, s, fail, draw);
  };
  draw();
}

/* Shares kept in passkeys (familykey.seal_share, contribute): each member keeps their own share sealed to their passkey, and an unlock is a tap
   from each of t members. The browser wraps and opens the share under a secret the passkey derives (fkprf.js); the server holds only ciphertext. */
async function wirePasskeyShares(body, s, fail, draw) {
  if (!(window.PublicKeyCredential && navigator.credentials)) return;
  let seals; try { seals = await api('/household/family-key/share-seals'); } catch (e) { return; }
  const mine = seals.mine;
  const names = seals.holders.map((h) => esc(h.display_name)).join(', ') || 'nobody yet';
  const box = document.createElement('details');
  box.style.marginTop = '10px'; box.open = !!(s.locked && mine);
  box.innerHTML = '<summary>Keep my share in my passkey</summary>'
    + '<p class="muted" style="line-height:1.55;margin:6px 0">Held in a passkey now: ' + names + '. Your share is sealed to your own passkey here, so FamilyOS keeps only ciphertext it cannot open; when ' + s.threshold + ' members give theirs the household opens. The words you wrote down still work.</p>'
    + (mine ? ((s.locked ? '<button class="btn sm" data-fk-give type="button">Give my share with my passkey</button> <span class="muted">' + s.contributed + ' of ' + s.threshold + ' given</span><br>' : '')
        + '<button class="btn ghost sm" data-fk-unseal type="button" style="margin-top:6px">Stop keeping it in my passkey</button>')
      : '<form data-fk-seal class="stack" style="gap:8px"><label>Your share<textarea data-fk-sharein rows="3" placeholder="Paste your share once" style="font-family:var(--mono);font-size:12px"></textarea></label><button class="btn sm" type="submit">Keep it in my passkey</button></form>');
  body.appendChild(box);
  const seal = box.querySelector('[data-fk-seal]');
  if (seal) seal.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const share = parseShares(box.querySelector('[data-fk-sharein]').value)[0];
      if (!share) { flash('Paste one 33-word share.', true); return; }
      const d = await fkPrfDerive({});
      if (!d) { flash('This passkey cannot hold a share here (no PRF). Keep the words instead.', true); return; }
      await api('/household/family-key/share-seals', { method: 'POST', json: { credential_id: d.credentialId, salt: d.salt, wrapped: await fkWrapShare(d.secret, share) } });
      flash('Your share is kept in your passkey.'); draw();
    } catch (err) { fail(err, 'Could not keep it in your passkey.'); }
  });
  const give = box.querySelector('[data-fk-give]');
  if (give) give.addEventListener('click', async () => {
    try {
      const d = await fkPrfDerive({ credentialId: mine.credential_id, salt: mine.salt });
      if (!d) { flash('This passkey did not answer. Use the words instead.', true); return; }
      const share = await fkUnwrapShare(d.secret, mine.wrapped);
      const send = () => api('/household/family-key/contribute', { method: 'POST', json: { share } });
      let out;
      try { out = await send(); } catch (err) { if (err && err.body && err.body.error === 'passkey_needed') { await fkPasskeySignIn(); out = await send(); } else throw err; }
      flash(out.locked ? 'Given. ' + out.contributed + ' of ' + s.threshold + '.' : 'Unlocked.'); draw();
    } catch (err) { flash((err && err.name === 'NotAllowedError') ? 'No passkey was used.' : ((err && err.message) || 'Could not give your share.'), true); }
  });
  const un = box.querySelector('[data-fk-unseal]');
  if (un) un.addEventListener('click', async () => { try { await api('/household/family-key/share-seals', { method: 'DELETE' }); flash('Removed. You still hold the words.'); draw(); } catch (err) { fail(err, 'Could not remove it.'); } });
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
    // Only what a feature already uses, and every one of them optional: the number a WhatsApp forward comes from, and what the emergency card shows.
    + '<details class="stack" style="gap:10px"><summary style="cursor:pointer"><b>Optional, add later</b> <small class="muted">each one has a use; skip any</small></summary>'
    + '<div class="stack" style="gap:10px;margin-top:10px">'
    + '<label data-phonewrap>Phone number, with country code<input type="tel" name="phone" maxlength="24" placeholder="+91 98765 43210"><small class="muted">The number they forward WhatsApp messages from, so those land in their home.</small></label>'
    + '<label>Allergies<input type="text" name="allergies" maxlength="300" placeholder="Penicillin, peanuts"><small class="muted">Shown on the emergency card.</small></label>'
    + '<label>Blood group<select name="blood_group"><option value="">Not set</option>' + ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((g) => '<option>' + g + '</option>').join('') + '</select></label>'
    + '</div></details>'
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

/* A person's profile, in one dialog: how they are reached, where they work and when they usually start, and (for a guardian) the medical details
   the emergency card shows. Opened from their row in Settings and from their panel on the Family page. Server: familyos/profile.py. */
async function openMemberProfile(id) {
  let p; try { p = await api('/members/' + id + '/profile'); } catch (err) { flash((err && err.message) || 'Could not open the profile.', true); return; }
  const guardian = store.me && store.me.role === 'guardian';
  const adult = p.role !== 'child';
  const sel = (name, value, opts) => '<select name="' + name + '">' + opts.map(([v, l]) => '<option value="' + v + '"' + (String(v) === String(value) ? ' selected' : '') + '>' + esc(l) + '</option>').join('') + '</select>';
  const r = p.reach;
  const dlg = document.createElement('dialog'); dlg.className = 'card'; dlg.style.cssText = 'max-width:520px;width:calc(100% - 32px);padding:20px;border:1px solid var(--line)';
  dlg.innerHTML = '<div class="stack" style="gap:14px"><div class="row wrap" style="gap:8px"><h2 style="margin:0">' + esc(p.display_name) + '</h2><span class="tag">' + esc(p.role) + '</span>' + (p.is_me ? '<span class="tag line">you</span>' : '') + '<span class="grow"></span><button class="btn ghost sm" type="button" data-pclose>Close</button></div>'
    + (p.email ? '<p class="muted" style="margin:0">' + esc(p.email) + '</p>' : '')
    + (p.is_me && adult
      ? '<section class="stack" style="gap:8px"><h3 style="margin:0;font-size:14px">How FamilyOS reaches you</h3>'
        + '<form class="md-form" data-pphone><label>Your phone number, with country code<input name="p" type="tel" maxlength="24" value="' + esc(p.phone || '') + '" placeholder="+91 98765 43210"><small class="muted">The number you forward WhatsApp messages from, and the one WhatsApp reading links to.</small></label><button class="btn ghost sm" type="submit">Save number</button></form>'
        + '<p class="muted" style="margin:0">Telegram: ' + (p.telegram_linked ? 'linked' : 'not linked. Link it in Settings, Connections.') + '</p>'
        + (r ? '<form class="md-form" data-preach><label>Morning message' + sel('morning', r.morning_hour == null ? 'off' : r.morning_hour, [['off', 'Off']].concat(HOURS.map((h) => [h, hourName(h)]))) + '</label>'
          + '<label>Quiet from' + sel('quiet_from', r.quiet_from, HOURS.map((h) => [h, hourName(h)])) + '</label><label>Quiet until' + sel('quiet_to', r.quiet_to, HOURS.map((h) => [h, hourName(h)])) + '</label>'
          + '<label>At most a day' + sel('daily_cap', r.daily_cap, [0, 1, 2, 3, 4, 5, 8, 10, 15, 20].map((n) => [n, n === 0 ? 'None' : String(n)])) + '</label><button class="btn sm" type="submit">Save</button></form>' : '')
        + '</section>' : '')
    + (adult && p.work
      ? '<section class="stack" style="gap:8px"><h3 style="margin:0;font-size:14px">Work</h3>'
        + '<p class="muted" style="margin:0;line-height:1.5">Where ' + (p.is_me ? 'you work' : esc(p.display_name) + ' works') + ' and when the day usually starts, for the drive on Today. Only ' + (p.is_me ? 'you and guardians' : 'they and guardians') + ' see it.</p>'
        + '<div class="row wrap" style="gap:8px"><b data-pwork-label>' + esc(p.work.place || 'No work place set') + '</b><button class="btn ghost sm" type="button" data-pwork-edit>' + (p.work.place ? 'change' : 'set') + '</button></div><div data-pwork-box></div>'
        + '<form class="md-form" data-pstarts><label>Usual start<input name="t" type="time" value="' + esc(p.work.starts || '') + '"></label><button class="btn ghost sm" type="submit">Save time</button></form></section>' : '')
    + (guardian
      ? '<section class="stack" style="gap:8px"><h3 style="margin:0;font-size:14px">Emergency card</h3><form class="md-form" data-pmed><label>Allergies<input name="a" maxlength="300" value="' + esc(p.allergies || '') + '" placeholder="Penicillin, peanuts"></label>'
        + '<label>Blood group<select name="b"><option value="">Not set</option>' + ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((g) => '<option' + (p.blood_group === g ? ' selected' : '') + '>' + g + '</option>').join('') + '</select></label><button class="btn ghost sm" type="submit">Save</button></form></section>' : '')
    + '</div>';
  document.body.appendChild(dlg);
  const done = () => { dlg.close(); dlg.remove(); };
  dlg.querySelector('[data-pclose]').addEventListener('click', done);
  dlg.addEventListener('close', () => dlg.remove());
  const fail = (e, d) => flash((e && e.message) || d, true);
  const ph = dlg.querySelector('[data-pphone]');
  if (ph) ph.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/me/phone', { method: 'PUT', json: { phone: ph.p.value } }); flash('Number saved.'); } catch (e) { fail(e, 'Could not save the number.'); } });
  const rf = dlg.querySelector('[data-preach]');
  if (rf) rf.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const body = { quiet_from: +rf.quiet_from.value, quiet_to: +rf.quiet_to.value, daily_cap: +rf.daily_cap.value };
    if (rf.morning.value === 'off') body.morning_off = true; else body.morning_hour = +rf.morning.value;
    try { await api('/me/interruptions', { method: 'PUT', json: body }); flash('Saved.'); } catch (e) { fail(e, 'Could not save.'); }
  });
  const saveWork = async (label, lat, lon, starts, what) => {
    try { const out = await api('/members/' + id + '/work', { method: 'PUT', json: { label, lat, lon, starts } }); p.work = out.work; dlg.querySelector('[data-pwork-label]').textContent = out.work.place || 'No work place set'; dlg.querySelector('[data-pwork-edit]').textContent = out.work.place ? 'change' : 'set'; flash(what); const bx = dlg.querySelector('[data-pwork-box]'); if (bx) bx.innerHTML = ''; }
    catch (e) { fail(e, 'Could not save.'); }
  };
  const we = dlg.querySelector('[data-pwork-edit]');
  if (we) we.addEventListener('click', () => {
    const bx = dlg.querySelector('[data-pwork-box]'); if (bx.firstChild) { bx.innerHTML = ''; return; }
    placeSearch(bx, { initial: p.work.place, placeholder: 'The office address, or a Google Maps link',
      onPick: (f) => saveWork(f.label, f.lat, f.lon, p.work.starts, 'Work place saved.'),
      onClear: p.work.place ? () => saveWork(null, null, null, null, 'Work place cleared.') : null });
  });
  const st = dlg.querySelector('[data-pstarts]');
  if (st) st.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!p.work.place) { flash('Set the work place first.', true); return; }
    await saveWork(p.work.place, p.work.lat, p.work.lon, st.t.value || null, 'Start time saved.');
  });
  const md = dlg.querySelector('[data-pmed]');
  if (md) md.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/members/' + id + '/medical', { method: 'PUT', json: { allergies: md.a.value || null, blood_group: md.b.value || null } }); flash('Saved.'); } catch (e) { fail(e, 'Could not save.'); } });
  dlg.showModal();
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
    dlg.querySelector('[data-phonewrap]').hidden = child;       // a child has no number to forward from
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
    } else if ((f.get('phone') || '').trim()) body.phone = f.get('phone').trim();
    const allergies = (f.get('allergies') || '').trim(); const blood = f.get('blood_group') || '';
    try {
      const made = await api('/household/members', { method: 'POST', json: body });
      let medicalNote = '';
      const newId = (made.member && made.member.id) || made.id;       // an adult comes back with a token (Credentials), a child as the member itself
      if ((allergies || blood) && newId) {
        try { await api('/members/' + newId + '/medical', { method: 'PUT', json: { allergies: allergies || null, blood_group: blood || null } }); }
        catch (e2) { medicalNote = ' (Allergies and blood group were not saved: ' + ((e2 && e2.message) || 'try again on the Emergency page') + '.)'; }
      }
      dlg.close();
      if (medicalNote) flash('Added.' + medicalNote, true);
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
    if (!confirm('Do you confirm you are this child\u2019s parent or lawful guardian, and that you consent to FamilyOS keeping their household records?')) return;
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
          declares_guardian: true,
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

  main.querySelectorAll('[data-invite]').forEach((b) => b.addEventListener('click', async () => {
    const box = b.parentElement.querySelector('[data-invite-out]');
    b.closest('.item').style.flexWrap = 'wrap';
    b.disabled = true;
    try {
      const out = await api('/members/' + b.dataset.invite + '/invite', { method: 'POST', json: { send_email: true } });
      const url = location.origin + '/app/#link=' + encodeURIComponent(out.token);
      box.hidden = false;
      box.innerHTML = '<p class="muted" style="margin:6px 0">' + (out.emailed ? 'Emailed to ' + esc(b.dataset.name) + ', and here is the link too. ' : 'Send ' + esc(b.dataset.name) + ' this link in a message. ')
        + 'It works once, lasts a week, and a new one replaces it.</p><div class="row" style="gap:6px"><input type="text" readonly value="' + esc(url) + '" style="flex:1" data-select><button class="btn sm" type="button" data-copy-invite>Copy</button></div>';
      box.querySelector('[data-copy-invite]').addEventListener('click', async (ev) => { try { await navigator.clipboard.writeText(url); ev.target.textContent = 'Copied'; } catch (e) { box.querySelector('input').select(); } });
    } catch (err) { flash(err.message || 'Could not make an invitation.', true); }
    b.disabled = false;
  }));
  main.querySelectorAll('[data-profile]').forEach((b) => b.addEventListener('click', () => openMemberProfile(b.dataset.profile)));
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
  main.innerHTML = activityTabs('log') + '<div class="head"><div><div class="row" style="gap:10px"><h1>Technical log</h1>'
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
  // Google hands back to /app/ with the cookie already set. A #token= fragment from a mail or a link made before this version is traded for one.
  const fromFragment = takeTokenFromFragment();
  if (fromFragment) {
    try { await api('/session', { method: 'POST', json: { token: fromFragment } }); store.token = SESSION; await boot(); return; } catch (e) { store.token = null; }
  }
  await adoptLegacyToken();
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
  // Whether a cookie is there, script cannot tell: ask. A 401 is the answer "no", and the gate is shown.
  store.token = SESSION; probing = true;
  boot().catch(() => {
    store.token = null;
    gateView(said === 'failed' ? 'That Google account cannot sign in here.'
      : said === 'cancelled' ? 'Signing in with Google was cancelled.' : null);
  }).finally(() => { probing = false; });
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
  main.innerHTML = moneyTabs('seen') + '<div class="head"><div><h1>Money</h1>'
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
    + '<div class="opening stack" data-opening style="gap:6px;margin-bottom:10px;flex:none;max-height:36vh;overflow-y:auto"></div>'
    + '<div class="chat-thread" data-thread></div>'
    + '<div class="chat-dock">'
    + '<div class="chips" data-chips>'
    + ['What needs someone this week?', 'What do we pay every month?', 'When did the plumber last come?', 'What is still undecided?']
      .map((q) => '<button class="chip" data-try>' + esc(q) + '</button>').join('')
    + '</div>'
    + '<form class="chat-composer" data-composer>'
    + '<textarea name="message" rows="1" maxlength="1000" placeholder="Ask, or say what should happen…" required></textarea>'
    + '<button class="ib" type="button" data-composer-mic title="Say it" aria-label="Say it">' + icon('mic') + '</button>'
    + '<button class="send" type="submit" aria-label="Send">' + icon('arrow-up', 18) + '</button></form>'
    + '<p class="chat-foot">The assistant sees only what you can see. It never sends, pays or changes anything on its own.</p>'
    + '</div></div>';
  const threadEl = main.querySelector('[data-thread]');
  const form = main.querySelector('[data-composer]');
  const box = form.querySelector('textarea');
  const chips = main.querySelector('[data-chips]');
  // What needs you, as cards with the answer one tap away (GET /v1/chat/opening). The cards come from the server; a confirm
  // button runs the action it was made for, as you, and nothing else.
  const openingBox = main.querySelector('[data-opening]');
  if (openingBox && !readThread().length) api('/chat/opening').then((op) => {
    const one = (c) => {
      if (c.type === 'text') return '<p class="muted" style="margin:0">' + esc(c.text) + '</p>';
      if (c.type !== 'action') return '';
      return '<div class="card stack" style="gap:4px;padding:10px 12px"><b style="font-size:14px">' + esc(c.title) + '</b>' + (c.sub ? '<span class="muted" style="font-size:13px">' + esc(c.sub) + '</span>' : '')
        + '<div class="row wrap" style="gap:8px">' + c.buttons.map((b, i) => '<button type="button" class="btn' + (i ? ' ghost' : '') + ' sm" data-card-' + b.kind + '="' + esc(b.id || b.url || b.text || '') + '">' + esc(b.label) + '</button>').join('') + '</div></div>';
    };
    let seen = 0; const cards = op.cards.filter((c) => c.type !== 'chips' && (c.type !== 'action' || ++seen <= 3));
    if (!cards.some((c) => c.type === 'action') && !cards.length) return;
    openingBox.innerHTML = '<p style="margin:0"><b>' + esc(op.say) + '</b></p>' + cards.map(one).join('');
    openingBox.querySelectorAll('[data-card-confirm]').forEach((b) => b.addEventListener('click', async () => {
      b.disabled = true;
      try { const done = await api('/chat/pending/' + b.dataset.cardConfirm + '/confirm', { method: 'POST' }); flash(done.said); b.closest('.card').remove(); }
      catch (err) { b.disabled = false; fail(err); }
    }));
    openingBox.querySelectorAll('[data-card-cancel]').forEach((b) => b.addEventListener('click', async () => {
      b.disabled = true;
      try { await api('/chat/pending/' + b.dataset.cardCancel + '/cancel', { method: 'POST' }); b.closest('.card').remove(); }
      catch (err) { b.disabled = false; fail(err); }
    }));
    openingBox.querySelectorAll('[data-card-link]').forEach((b) => b.addEventListener('click', () => window.open(b.dataset.cardLink, '_blank', 'noopener')));
  }).catch(() => { /* the opening is a convenience; the chat works without it */ });
  form.querySelector('[data-composer-mic]').addEventListener('click', () => listen((said) => { box.value = said; grow(); form.requestSubmit(); }));
  let thread = readThread();
  const grow = () => { box.style.height = 'auto'; box.style.height = Math.min(box.scrollHeight, 160) + 'px'; };
  const paint = (smooth) => {
    threadEl.innerHTML = thread.length ? thread.map(chatBubble).join('')
      : '<div class="chat-hello"><div class="orb" aria-hidden="true">' + icon('sparkle', 22) + '</div>'
        + '<h2>Good ' + dayPart() + ', ' + esc((store.me && store.me.display_name) || '') + '.</h2>'
        + '<p>The household’s mail, the dates spotted, the to-dos and what you pay for are all in front of me. Ask away, or try one below.</p></div>';
    chips.hidden = thread.length > 0;
    wireProposals(main, thread, paint);
    // Ask asked back: the choices are chips under its question, and tapping one sends it as the next message.
    const lastTurn = thread[thread.length - 1];
    if (lastTurn && lastTurn.role === 'assistant' && lastTurn.clarify && lastTurn.clarify.choices) {
      threadEl.insertAdjacentHTML('beforeend', '<div class="chips" data-clarify style="margin:8px 0 0">' + lastTurn.clarify.choices.map((c) => '<button class="chip" type="button" data-pick>' + esc(c) + '</button>').join('') + '</div>');
      threadEl.querySelectorAll('[data-pick]').forEach((b) => b.addEventListener('click', () => send(b.textContent)));
    }
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
      thread.push({ role: 'assistant', content: turn.say, grounded: turn.grounded, note: turn.note || null, citations: turn.citations, proposals: turn.proposals, clarify: turn.clarify || null });
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
  const headers = { 'Content-Type': 'application/json', 'X-FamilyOS-CSRF': '1' };
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
    + (COCKPIT_UI ? COCKPIT_UI.sources(t) : '')
    + '</div>';
}

function proposalCard(p, i) {
  const done = p.done ? '<span class="tag green">done</span>' : '';
  let body;
  if (p.kind === 'assign') body = 'Hand <b>' + esc(p.headline || 'the notice') + '</b> to <b>' + esc(p.member_name || '?') + '</b>' + (p.note ? ' — “' + esc(p.note) + '”' : '');
  else if (p.kind === 'todo') body = 'To-do: <b>' + esc(p.title || '') + '</b>' + (p.due_date ? ' by ' + esc(fmtDate(p.due_date)) + (p.due_time ? ' ' + esc(String(p.due_time).slice(0, 5)) : '') : '') + (p.member_name ? ' — ' + esc(p.member_name) + '’s' : '') + (p.note ? ' — “' + esc(p.note) + '”' : '');
  else if (p.kind === 'handled') body = 'Mark <b>' + esc(p.headline || 'the notice') + '</b> handled' + (p.note ? ' \u2014 \u201C' + esc(p.note) + '\u201D' : '');
  else if (p.kind === 'plan') body = 'Plan <b>' + esc(p.title || 'this') + '</b> \u2014 itinerary, candidate bookings as pages to open, and the legwork as to-dos. Nothing is booked.';
  else if (p.kind === 'rule') body = 'Turn <b>' + (p.on ? 'on' : 'off') + '</b> the rule <b>' + esc(p.title || p.switch_key) + '</b>. It changes what happens from now on; nothing already done is undone. Only a guardian can do this, and it is written to the activity record.';
  else if (p.kind === 'routine') body = 'Routine: <b>' + esc(p.instruction || p.title) + '</b>' + (p.weekday == null ? ', every day' : ', every ' + ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][p.weekday]) + ' at ' + (p.hour % 12 || 12) + (p.hour < 12 ? ' am' : ' pm') + '. It only reads and says; with nothing to say it stays silent, and it keeps to your quiet hours and daily cap.';
  else if (p.kind === 'errand') body = (p.look ? 'Look on <b>' : 'Errand on <b>') + esc(p.label || p.service) + '</b>: <b>' + esc(p.what || p.title) + '</b>' + (p.due_date ? ' \u2014 ' + esc(fmtDate(p.due_date)) + (p.due_time ? ' ' + esc(String(p.due_time).slice(0, 5)) : (p.part && p.part !== 'any' ? ' ' + esc(p.part) : '')) : '')
    + (p.on_phone ? '. Reads that page in the app on your phone through the driver a Mac starts; nothing is typed or bought.' : p.look ? '. Reads the slots and the price in your signed-in session; buys nothing, so it runs at once.' : (p.max_amount ? ' \u2014 at most ' + esc(money(p.max_amount, p.currency)) : '') + '. Written down in full for a guardian to approve; paid after the service, or by a UPI request on your phone.');
  else body = (p.status === 'accepted' ? 'Accept' : 'Dismiss') + ' <b>' + esc(p.title || 'the date') + '</b>';
  if (p.clashes && p.clashes.length) body += '<br><span class="tag amber" style="text-transform:none;letter-spacing:0">same time as ' + esc(p.clashes.join(', ')) + ' in your calendar \u2014 add it anyway?</span>';
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
      else if (p.kind === 'rule') { await api('/household/rules', { method: 'PUT', json: { [p.switch_key]: p.on } }); p.done = true; writeThread(thread); flash('Rule changed.'); render(); return; }
      else if (p.kind === 'routine') { await api('/routines', { method: 'POST', json: { instruction: p.instruction, weekday: p.weekday, hour: p.hour } }); p.done = true; writeThread(thread); flash('Routine set.'); render(); return; }
      else if (p.kind === 'errand') { const made = await api('/errands', { method: 'POST', json: { service: p.service, kind: p.look ? 'look' : 'booking', title: p.title || p.what, spec: { what: p.what || p.title, details: p.details, bundle: p.bundle || undefined, when: { date: p.due_date, time: p.due_time ? String(p.due_time).slice(0, 5) : null, part: p.part || 'any' }, max_amount: p.max_amount, currency: p.currency || 'INR', payment: 'pay_after_service' } } }); p.done = true; writeThread(thread); go('/errands/' + made.id); return; }
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
      + (t.due_date ? '<span class="muted" style="white-space:nowrap;color:var(--primary)">' + esc(fmtDate(t.due_date).replace(/,.*$/, '')) + '</span>' : '') + (t.clashes && t.clashes.length ? '<span class="tag amber" title="Same time as ' + esc(t.clashes.join(', ')) + '" style="text-transform:none;letter-spacing:0">clash</span>' : '') + '</span></label>').join('') + '</div>'
      : '<p class="muted">Say “add a to-do” in Ask, or add one in Life.</p>')
    + (todos.length > 8 ? '<a class="muted" href="#/life" style="align-self:flex-end">View all \u2192</a>' : '');
}

function todosCardBody(todos) {
  return '<div class="row wrap" style="gap:8px"><h2>To-dos</h2><span class="muted">' + (todos.length ? todos.length + ' open' : 'none open') + '</span></div>'
    + (todos.length ? '<div class="stack" style="gap:6px">' + todos.map((t) => '<label class="todo"><input type="checkbox" data-todo="' + esc(t.id) + '">'
      + '<span><span>' + esc(t.title) + '</span>'
      + '<span class="muted">' + [t.due_date ? 'by ' + fmtDate(t.due_date) + (t.due_time ? ' ' + t.due_time.slice(0, 5) : '') : '', memberName(t.assigned_to) || '', t.calendar_event_id ? 'on your calendar' : ''].filter(Boolean).join(' · ') + '</span>' + (t.clashes && t.clashes.length ? '<span class="tag amber" style="text-transform:none;letter-spacing:0">same time as ' + esc(t.clashes[0]) + (t.clashes.length > 1 ? ' and ' + (t.clashes.length - 1) + ' more' : '') + '</span>' : '') + '</span></label>').join('') + '</div>'
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
    if (COCKPIT_UI && cb.checked) { const todoId = cb.dataset.todo; COCKPIT_UI.reversible('Marked done.', () => api('/todos/' + todoId, { method: 'PATCH', json: { done: false } })); }
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
      + (x.kind === 'number' ? '' : '<span class="tag ' + (x.on ? 'kid' : '') + '">' + (x.fixed ? esc(x.why_fixed || 'built in') : x.on ? 'on' : 'off') + '</span>')
      + (x.kind === 'number'
        ? (isGuardian ? '<span class="row" style="margin-left:auto;gap:6px"><input type="number" class="pill sm" style="width:84px" min="0" max="365" inputmode="numeric" data-rule-num="' + esc(x.key) + '" value="' + esc(x.value) + '" aria-label="' + esc(x.title) + '"><span class="muted">' + esc(x.unit || '') + '</span></span>'
          : '<span class="muted" style="margin-left:auto">' + esc(x.value) + ' ' + esc(x.unit || '') + '</span>')
        : x.kind === 'place'
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
    box.querySelectorAll('[data-rule-num]').forEach((inp) => inp.addEventListener('change', async () => {
      const patch = {}; patch[inp.dataset.ruleNum] = Number(inp.value);
      try { paint(await api('/household/rules', { method: 'PUT', json: patch })); flash('Saved.'); }
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
    + '<form class="row" style="gap:6px" data-device-form><input type="text" name="label" placeholder="Emily’s iPhone" maxlength="80" required style="flex:1">'
    + '<button class="btn sm" type="submit">New phone token</button></form>'
    + '<div class="card" style="padding:12px;background:var(--sunk)" data-device-issued hidden></div>'
    + '<div class="row wrap" style="gap:8px;align-items:center" data-shortcut-dl hidden><a class="btn sm" href="/v1/shortcut" style="text-decoration:none">Download the shortcut</a>'
    + '<span class="muted" style="font-size:12.5px">Open this page on the iPhone. On a server that can sign it, it comes with a token of its own (listed above as \u201CShortcut\u201D; revoke it there) and nothing is pasted; otherwise it asks for a phone token once.</span></div>'
    + '<details><summary class="muted" style="cursor:pointer">How to set up the shortcut (iPhone, 2 minutes)</summary>'
    + '<ol class="muted" style="line-height:1.6;padding-left:18px;margin-top:8px">'
    + '<li>Shortcuts app → <b>+</b> → name it <b>Send to FamilyOS</b>.</li>'
    + '<li>Tap <b>ⓘ</b> → turn on <b>Show in Share Sheet</b>. In the <i>Receive</i> action pick Text, URLs, Images, PDFs, Files.</li>'
    + '<li>Add the action <b>Get Contents of URL</b>: URL = the address below; Method <b>POST</b>; Headers: <code>Authorization</code> = <code>Bearer &lt;your token&gt;</code>; Request Body <b>Form</b>, one field <code>item</code> = <i>Shortcut Input</i>, with the field\u2019s type set to <b>File</b> (tap the field, choose File), so a photo or a PDF travels as the file and not as its name. '
    + 'If the File field will not take Shortcut Input, set Request Body to <b>File</b> instead, with <i>Shortcut Input</i> as the file, and put the tag in a header <code>X-Tag</code> = <i>Chosen Item</i>.</li>'
    + '<li>To tag as you share: add <b>Choose from List</b> <i>before</i> Get Contents of URL with the children\u2019s names and \u201CNobody\u201D, and add a second form field <code>tag</code> = <i>Chosen Item</i>. One share, already tagged.</li>'
    + '<li>Add <b>Show Notification</b> after it, with its text set to <i>Contents of URL</i> \u2192 <i>message</i>, so each share says what happened (\u201CSaved to your Inbox\u201D, \u201CTagged: Lily\u201D).</li>'
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
  fetch('/v1/shortcut', { credentials: 'same-origin' }).then((r) => { if (r.ok) box.querySelector('[data-shortcut-dl]').hidden = false; }).catch(() => {});
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
      what: i.title, who: i.subject_name || memberName(i.subject_member_id) || '', hue: n ? spaceOfNotice(n) : hueForItem(i), href: i.artifact_id ? '#/notices/' + i.artifact_id : null, pay_url: i.pay_url, pay_host: i.pay_host, pay_host_new: i.pay_host_new });
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
      + (i.who ? '<div class="who">' + esc(i.who) + '</div>' : '') + (i.pay_url ? '<div class="who">' + payLinks(i.pay_url, 'plain', i) + '</div>' : '') + '</span>'
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
  if (asks.length) { const a = asks[0]; out.push({ title: (a.assigned_by_name || 'Someone') + ' handed you something.', body: esc(a.title) + (a.note ? ' — “' + esc(a.note) + '”' : ''), fix: 'What do I need to do about ' + a.title + '?', open: '#/notices/' + a.artifact_id, pay_url: a.pay_url, pay_host: a.pay_host, pay_host_new: a.pay_host_new }); }
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
  const sky = (words) => {
    const w = String(words || '').toLowerCase();
    const d = w.includes('thunder') ? '<path d="M7 15a4 4 0 010-8 5 5 0 019.5 1.5A3.3 3.3 0 0117 15"/><path d="M12 12l-2 4h3l-2 4"/>'
      : /rain|drizzle|shower/.test(w) ? '<path d="M7 14a4 4 0 010-8 5 5 0 019.5 1.5A3.3 3.3 0 0117 14"/><path d="M8 17l-1 3M12 17l-1 3M16 17l-1 3"/>'
      : /cloud|overcast|fog|mist/.test(w) ? '<path d="M7 18a4 4 0 010-8 5 5 0 019.5 1.5A3.3 3.3 0 0117 18z"/>'
      : '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>';
    return '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  };
  const day = (d) => '<div class="day-wx"><span class="day-k">' + esc(d.label) + '</span>'
    + '<span class="day-ic">' + sky(d.words) + '</span>'
    + '<b class="day-t">' + (d.tmax != null ? Math.round(d.tmax) + '°' : '–') + (d.tmin != null ? '<small>' + Math.round(d.tmin) + '°</small>' : '') + '</b>'
    + '<span class="day-w">' + esc(d.words || '') + '</span>' + (d.rain != null && d.rain >= 40 ? '<span class="day-w">Rain ' + Math.round(d.rain) + '%</span>' : '') + '</div>';
  const runs = c.school_runs && c.school_runs.length ? '<div class="day-panel"><span class="day-k">School run from home</span>'
    + c.school_runs.map((r) => {
      const live = r.live_minutes != null;
      const mins = live ? r.live_minutes : r.minutes;
      const slow = live && r.delay_minutes >= 8;
      return '<div class="day-run"><span class="day-min' + (slow ? ' slow' : '') + '"><b>' + esc(String(mins)) + '</b>min</span>'
        + '<span class="day-run-t"><span class="day-run-n">' + esc(r.school) + '</span>'
        + '<span class="day-run-s">' + (r.leave_by ? 'Leave by ' + esc(r.leave_by) + (r.starts_at ? ' for ' + esc(r.starts_at) : '') : '')
        + (live ? (r.leave_by ? ' · ' : '') + (r.delay_minutes >= 3 ? r.delay_minutes + ' min worse than usual' : 'as usual') : '') + '</span></span></div>';
    }).join('')
    + '<span class="day-foot">' + (c.school_runs.some((r) => r.live_minutes != null) ? 'Live traffic, read in the two hours before school.' : c.school_runs.some((r) => r.usual) ? 'The usual traffic for the hour; live in the two hours before school.' : 'The drive without traffic, from public maps.') + '</span></div>' : '';
  const hol = c.holidays && c.holidays.length ? '<div class="day-panel"><span class="day-k">Holidays coming</span>'
    + c.holidays.slice(0, 3).map((h) => {
      const dt = new Date(String(h.date).slice(0, 10) + 'T00:00:00');
      return '<div class="day-hol"><span class="day-date"><b>' + dt.getDate() + '</b>' + dt.toLocaleString('en', { month: 'short' }) + '</span><span class="day-hol-n">' + esc(h.name) + '</span></div>';
    }).join('') + '</div>' : '';
  return '<section class="card pad day-card" data-context-card><div class="day-head"><h2>The day</h2><span>For home, read without any sign-in</span></div>'
    + '<div class="day-grid">' + ((c.weather_days || []).length ? '<div class="day-wxs">' + (c.weather_days || []).map(day).join('') + '</div>' : '') + runs + hol + '</div></section>';
}

function insightCard(x) {
  return '<section class="insight"><div class="k"><span class="star">' + icon('sparkle', 14) + '</span> FamilyOS noticed</div>'
    + '<h3>' + x.title + '</h3><p>' + x.body + '</p>'
    + '<div class="acts">' + (x.fix ? '<button class="btn sm" data-fix="' + esc(x.fix) + '">Fix for me</button>' : '')
    + (x.open ? '<a class="btn ghost sm" href="' + esc(x.open) + '" style="text-decoration:none">Show me</a>' : '')
    + (x.pay_url ? payLinks(x.pay_url, 'btn ghost sm', x) : '') + (x.link ? '<a class="btn ghost sm" href="' + esc(x.link) + '" target="_blank" rel="noopener" style="text-decoration:none">Reorder ↗</a>' : '') + '</div></section>';
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
  wireDocuments(main);
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
      subject_name: memberName(o.subject_member_id) || null, why: 'accepted' + (o.due_time ? ' \u00B7 ' + o.due_time : '') + (o.end_date && o.end_date !== o.due_date ? ' \u00B7 until ' + fmtDate(o.end_date).replace(/,.*$/, '') : '') + ' \u00B7 on the calendar', reason: 'accepted', pay_url: o.pay_url, pay_host: o.pay_host, pay_host_new: o.pay_host_new });
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
      + '<div><div style="font-size:17px;font-weight:600">' + esc(m.display_name) + '</div><div class="muted">' + esc(m.role) + (m.school ? ' · ' + esc(m.school) + (m.class_label ? ', class ' + esc(m.class_label) : '') : '') + '</div></div>'
      + (store.me && (store.me.role === 'guardian' || store.me.id === id) ? '<span class="grow"></span><button class="btn ghost sm" type="button" data-person-profile>Profile</button>' : '') + '</div>'
      + '<section class="card pad"><h2>Coming up</h2>' + (dated.length ? '<ul class="tl" style="margin-top:6px">' + dated.slice(0, 6).map((i) => '<li><span class="tm">' + esc(fmtDate(i.due_date)) + '</span><span class="dt ' + hueForItem(i) + '"></span><span class="ic ' + hueForItem(i) + '">' + icon(ICON_PATHS[hueForItem(i)] ? hueForItem(i) : 'calendar', 16) + '</span><span><a class="what" href="#/notices/' + esc(i.artifact_id) + '" style="text-decoration:none">' + esc(i.title) + '</a><div class="who">' + esc(i.why) + '</div></span></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">Nothing dated.</p>') + '</section>'
      + (todo.length ? '<section class="card pad"><h2>To do</h2><div class="stack" style="gap:6px;margin-top:8px">' + todo.map((t) => '<div>' + esc(t.title) + (t.due_date ? ' <span class="muted">by ' + esc(fmtDate(t.due_date)) + '</span>' : '') + '</div>').join('') + '</div></section>' : '')
      + '<section class="card pad"><div class="row wrap" style="gap:8px"><h2>Documents</h2><span class="muted">' + (theirs.length ? theirs.length + ' held \u00B7 ' : '') + mine.length + ' naming ' + esc(m.display_name.split(' ')[0]) + '</span></div>'
      + (theirs.length ? '<div class="mlist" style="margin-top:4px">' + theirs.map(docRow).join('') + '</div>' : '')
      + (mine.length ? '<div class="stack" style="gap:8px;margin-top:8px">' + mine.slice(0, 8).map((n) => '<a href="#/notices/' + esc(n.id) + '" style="text-decoration:none;color:inherit"><b style="font-size:13.5px">' + esc(n.headline || 'Notice') + '</b><br><span class="muted">' + esc(n.from_label) + ' · ' + esc(ago(n.received_at)) + '</span></a>').join('') + '</div>' : '<p class="muted" style="margin-top:6px">Nothing yet.</p>') + '</section></div>';
    const pb = body.querySelector('[data-person-profile]'); if (pb) pb.addEventListener('click', () => openMemberProfile(id));
  });
}

/* Kids: a guardian gives a child their own key and sets their day (kid.py). The child's page is /kid/; the journal stays theirs. */
async function kidsView(main) {
  main.classList.remove('chat-main');
  const kids = members().filter((m) => m.role === 'child');
  if (!kids.length) { main.innerHTML = '<div class="greet"><div><h1>Kids</h1></div></div><p class="muted pad">No children in the household yet.</p>'; return; }
  const per = await Promise.all(kids.map(async (k) => ({ k, keys: await api('/members/' + k.id + '/kid-keys').catch(() => []), shared: await api('/members/' + k.id + '/kid-journal').catch(() => []) })));
  const card = ({ k, keys, shared }) => '<section class="card pad" data-kid="' + esc(k.id) + '"><h2>' + esc(k.display_name) + '</h2>'
    + '<h3 style="font-size:13px;margin-top:8px">Their link</h3><ul class="mdlist">' + (keys.length ? keys.map((x) => '<li class="mdrow" data-kk="' + esc(x.id) + '"><span class="grow">' + (x.active ? 'Works until ' + esc(new Date(x.expires_at).toLocaleDateString('en', { day: 'numeric', month: 'short' })) : (x.revoked_at ? 'Revoked' : 'Expired')) + '<small class="muted">' + (x.last_used_at ? 'last opened ' + esc(new Date(x.last_used_at).toLocaleDateString('en', { day: 'numeric', month: 'short' })) : 'not opened yet') + '</small></span>' + (x.active ? '<button class="btn ghost sm" data-revoke type="button">Revoke</button>' : '') + '</li>').join('') : '<li class="muted">No link yet.</li>') + '</ul>'
    + '<button class="btn sm" data-key type="button" style="margin-top:8px">Make a link for ' + esc(k.display_name.split(' ')[0]) + '</button><div data-linkout></div>'
    + '<h3 style="font-size:13px;margin-top:14px">Morning and evening routine</h3><form data-routine><textarea name="r" rows="5" style="width:100%" placeholder="morning: Brush teeth&#10;morning: Pack the bag&#10;evening: Set out the uniform"></textarea><button class="btn ghost sm" type="submit" style="margin-top:6px">Save routine</button></form>'
    + '<h3 style="font-size:13px;margin-top:14px">Savings goal and allowance</h3><form class="md-form" data-goal><label>Goal<input name="t" maxlength="120" placeholder="Bicycle"></label><label>Target<input name="a" type="number" min="1"></label><button class="btn ghost sm" type="submit">Add goal</button></form>'
    + '<h3 style="font-size:13px;margin-top:14px">Notes they chose to share</h3>' + (shared.length ? '<ul class="mdlist">' + shared.map((e) => '<li class="mdrow"><span class="grow">' + esc(e.text) + '<small class="muted">' + esc(new Date(e.at).toLocaleDateString('en', { day: 'numeric', month: 'short' })) + '</small></span></li>').join('') + '</ul>' : '<p class="muted" style="font-size:12.5px">Nothing shared. Their journal is theirs.</p>') + '</section>';
  main.innerHTML = '<div class="greet"><div><h1>Kids</h1><div class="day">Their own day, on their own link. Their journal is theirs unless they share a note.</div></div></div><div class="md-grid">' + per.map(card).join('') + '</div>';
  main.querySelectorAll('[data-kid]').forEach((sec) => {
    const id = sec.dataset.kid;
    sec.querySelector('[data-key]').addEventListener('click', async () => { try { const r = await api('/members/' + id + '/kid-key', { method: 'POST', json: { days: 180 } }); sec.querySelector('[data-linkout]').innerHTML = '<p style="margin-top:8px;font-size:13px">Shown once. Open it on their device:</p><input readonly value="' + esc(location.origin + r.path) + '" style="width:100%" data-select>'; } catch (err) { flash(err.message || 'Could not make a link.', true); } });
    sec.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', async () => { try { await api('/kid-keys/' + b.closest('[data-kk]').dataset.kk, { method: 'DELETE' }); kidsView(main); } catch (err) { flash(err.message || 'Could not revoke.', true); } }));
    sec.querySelector('[data-routine]').addEventListener('submit', async (ev) => { ev.preventDefault();
      const items = ev.target.r.value.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => { const m = l.match(/^(morning|evening)\s*:\s*(.+)$/i); return m ? { slot: m[1].toLowerCase(), label: m[2].trim() } : null; }).filter(Boolean);
      try { await api('/members/' + id + '/kid-routine', { method: 'PUT', json: { items } }); flash('Routine saved.'); } catch (err) { flash(err.message || 'Could not save.', true); } });
    sec.querySelector('[data-goal]').addEventListener('submit', async (ev) => { ev.preventDefault(); const f = ev.target; if (!f.t.value || !f.a.value) return;
      try { await api('/finance/goals', { method: 'POST', json: { title: f.t.value, target_amount: +f.a.value, owner_member_id: id } }); flash('Goal added. Add allowance from Money plan.'); } catch (err) { flash(err.message || 'Could not add it.', true); } });
  });
}

/* What if: an impact map from the record that changes nothing (POST /v1/scenarios). */
async function whatIfView(main) {
  main.classList.remove('chat-main');
  const adults = members().filter((m) => m.role !== 'child');
  const today = new Date().toISOString().slice(0, 10);
  main.innerHTML = '<div class="greet"><div><h1>What if</h1><div class="day">See what a change would touch before you make it. Nothing here changes anything.</div></div></div>'
    + '<div class="md-grid" style="max-width:900px"><section class="card pad"><h2>Someone is away</h2><form class="md-form" data-away><label>Who<select name="m">' + adults.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.display_name) + '</option>').join('') + '</select></label><label>From<input type="date" name="s" value="' + today + '" required></label><label>To<input type="date" name="e" value="' + today + '" required></label><button class="btn sm" type="submit">Show</button></form></section>'
    + '<section class="card pad"><h2>We spend some money</h2><form class="md-form" data-spend><label>Amount<input type="number" name="a" min="1" required></label><label>Budget category (optional)<input name="c" maxlength="40" placeholder="shopping"></label><button class="btn sm" type="submit">Show</button></form></section>'
    + '<section class="card pad"><h2>School reopens earlier</h2><form class="md-form" data-reopen><label>New date<input type="date" name="d" value="' + today + '" required></label><button class="btn sm" type="submit">Show</button></form></section></div>'
    + '<section class="card pad" data-out style="margin-top:14px;max-width:900px" hidden></section>';
  const show = (r) => {
    const box = main.querySelector('[data-out]'); box.hidden = false;
    box.innerHTML = '<h2>' + esc(r.headline) + '</h2>' + (r.impacts.length ? '<ul class="mdlist">' + r.impacts.map((i) => '<li class="mdrow"><span class="grow">' + (i.artifact_id ? '<a href="#/notices/' + esc(i.artifact_id) + '">' + esc(i.title) + '</a>' : esc(i.title))
      + '<small class="muted">' + esc([i.date ? fmtDate(i.date).replace(/,.*$/, '') : '', i.note || '', (i.cover && i.cover.length) ? 'could be covered by ' + i.cover.join(', ') : ''].filter(Boolean).join(' · ')) + '</small></span></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">Nothing in the record is touched.</p>')
      + '<p class="muted" style="font-size:12px;margin-top:8px">This changed nothing.</p>';
  };
  const run = async (body) => { try { show(await api('/scenarios', { method: 'POST', json: body })); } catch (err) { flash(err.message || 'Could not work that out.', true); } };
  main.querySelector('[data-away]').addEventListener('submit', (ev) => { ev.preventDefault(); const f = ev.target; run({ kind: 'member_away', member_id: f.m.value, start: f.s.value, end: f.e.value }); });
  main.querySelector('[data-spend]').addEventListener('submit', (ev) => { ev.preventDefault(); const f = ev.target; run({ kind: 'spend', amount: +f.a.value, category: f.c.value || null }); });
  main.querySelector('[data-reopen]').addEventListener('submit', (ev) => { ev.preventDefault(); run({ kind: 'school_reopens', reopens_on: ev.target.d.value }); });
}

/* Emergency: one card, shared by a link that expires and can be revoked, and I'm-safe check-ins (GET /v1/emergency/*). */
async function emergencyView(main) {
  main.classList.remove('chat-main');
  const isG = store.me && store.me.role === 'guardian';
  const [card, shares, checks] = await Promise.all([api('/emergency/card').catch(() => null), isG ? api('/emergency/shares').catch(() => []) : Promise.resolve([]), api('/emergency/checkins').catch(() => [])]);
  if (!card) { main.innerHTML = '<p class="muted pad">Could not load the emergency card.</p>'; return; }
  const rowOf = (c, keys) => '<div class="md-form" data-row style="margin-top:6px">' + keys.map((k) => '<label>' + esc(k[1]) + '<input name="' + k[0] + '" value="' + esc(c[k[0]] || '') + '" maxlength="120"></label>').join('') + '</div>';
  const contactKeys = [['name', 'Name'], ['relation', 'Relation'], ['phone', 'Phone']];
  const pickKeys = [['child', 'Child'], ['name', 'Who may collect'], ['relation', 'Relation'], ['phone', 'Phone']];
  const people = card.people.map((x) => '<li class="mdrow"><span class="grow"><b>' + esc(x.name) + '</b><small class="muted">Allergies: ' + esc(x.allergies || 'none recorded') + ' · blood group ' + esc(x.blood_group || 'not recorded') + (x.medicines.length ? ' · ' + esc(x.medicines.join('; ')) : '') + '</small></span></li>').join('');
  const checkHtml = checks.length ? '<ul class="mdlist">' + checks.map((c) => '<li class="mdrow"><span class="grow"><b>' + esc(c.name) + '</b><small class="' + (c.status === 'need_help' ? 'warn' : 'muted') + '">' + (c.status === 'safe' ? 'safe' : 'needs help') + ' · ' + esc(new Date(c.at).toLocaleString('en', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })) + (c.note ? ' · ' + esc(c.note) : '') + '</small></span></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">No check-ins yet.</p>';
  const shareHtml = isG ? '<ul class="mdlist">' + (shares.length ? shares.map((x) => '<li class="mdrow" data-sid="' + esc(x.id) + '"><span class="grow"><b>' + esc(x.label) + '</b><small class="muted">' + (x.active ? 'open until ' + esc(new Date(x.expires_at).toLocaleString('en', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })) : (x.revoked_at ? 'revoked' : 'expired')) + ' · opened ' + x.opened_count + (x.opened_count === 1 ? ' time' : ' times') + (x.include_home ? ' · includes home access' : '') + '</small></span>' + (x.active ? '<button class="btn ghost sm" data-revoke type="button">Revoke</button>' : '') + '</li>').join('') : '<li class="muted">No links shared.</li>') + '</ul>'
    + '<form class="md-form" data-share style="margin-top:10px"><label>For whom<input name="l" required maxlength="80" placeholder="Neighbour"></label><label>Hours (max 72)<input name="h" type="number" min="1" max="72" value="24"></label><label style="grid-column:1/-1"><span><input name="home" type="checkbox"> Include home access</span></label><button class="btn sm" type="submit">Make a link</button></form><div data-link-out></div>' : '<p class="muted">A guardian shares the card.</p>';
  main.innerHTML = '<div class="greet"><div><h1>Emergency</h1><div class="day">One card for when it matters. Shared on purpose, for a short time, and recorded every time it is opened.</div></div></div>'
    + '<div class="md-grid"><section class="card pad"><h2>I’m safe</h2><div class="row" style="gap:8px;margin-top:8px"><button class="btn sm" data-ci="safe" type="button">I’m safe</button><button class="btn ghost sm" data-ci="need_help" type="button">I need help</button></div>' + checkHtml + '</section>'
    + '<section class="card pad"><h2>The card</h2><ul class="mdlist">' + people + '</ul><p class="muted" style="margin-top:6px;font-size:12.5px">Medicines come from the prescriptions FamilyOS has read; insurance and passports from the documents it holds.</p></section>'
    + (isG ? '<section class="card pad"><h2>Edit the card</h2><form data-profile><h3 style="font-size:13px;margin-top:6px">Who to call</h3>' + (card.contacts.concat([{}, {}]).slice(0, Math.max(3, card.contacts.length + 1))).map((c) => rowOf(c, contactKeys)).join('')
      + '<h3 style="font-size:13px;margin-top:12px">Who may collect the children</h3>' + (card.pickup.concat([{}]).map((c) => rowOf(c, pickKeys))).join('')
      + '<label class="md-form" style="display:flex;flex-direction:column;gap:4px;margin-top:12px;font-size:12px;color:var(--ink-3)">Home access (shared only if you include it)<textarea name="home" rows="2" maxlength="600" style="width:100%">' + esc(card.home_access || '') + '</textarea></label><button class="btn sm" type="submit" style="margin-top:8px">Save the card</button></form></section>' : '')
    + '<section class="card pad"><h2>Shared links</h2>' + shareHtml + '</section></div>';
  main.querySelectorAll('[data-ci]').forEach((b) => b.addEventListener('click', async () => { try { await api('/emergency/checkin', { method: 'POST', json: { status: b.dataset.ci } }); flash(b.dataset.ci === 'safe' ? 'Noted.' : 'The guardians have been told.'); emergencyView(main); } catch (err) { flash(err.message || 'Could not check in.', true); } }));
  main.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', async () => { try { await api('/emergency/shares/' + b.closest('[data-sid]').dataset.sid, { method: 'DELETE' }); emergencyView(main); } catch (err) { flash(err.message || 'Could not revoke.', true); } }));
  const sf = main.querySelector('[data-share]');
  if (sf) sf.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try { const r = await api('/emergency/share', { method: 'POST', json: { label: sf.l.value, hours: +sf.h.value, include_home: sf.home.checked } });
      const url = location.origin + r.path; main.querySelector('[data-link-out]').innerHTML = '<p style="margin-top:8px;font-size:13px">Shown once. Send it to ' + esc(r.label) + ':</p><input readonly value="' + esc(url) + '" style="width:100%" data-select>'; }
    catch (err) { flash(err.message || 'Could not make a link.', true); }
  });
  const pf = main.querySelector('[data-profile]');
  if (pf) pf.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const rows = [...pf.querySelectorAll('[data-row]')].map((r) => Object.fromEntries([...r.querySelectorAll('input')].map((i) => [i.name, i.value])));
    const contacts = rows.filter((r) => 'phone' in r && !('child' in r) && r.name).slice(0); const pickup = rows.filter((r) => 'child' in r && r.name && r.child);
    try { await api('/emergency/profile', { method: 'PUT', json: { contacts, pickup, home_access: pf.home.value } }); flash('Saved.'); emergencyView(main); } catch (err) { flash(err.message || 'Could not save.', true); }
  });
}

/* Money plan: the coordination layer above the accounts (GET /v1/finance/*). It never moves money. */
async function moneyPlanView(main) {
  main.classList.remove('chat-main');
  const get = (p, d) => api(p).catch(() => d);
  const [tl, bud, goals, splits, wars] = await Promise.all([get('/finance/timeline?days=45', null), get('/finance/budgets', []), get('/finance/goals', []), get('/finance/splits', []), get('/finance/warranties', [])]);
  const money = (n, c) => (c === 'INR' ? '₹' : (c || '') + ' ') + Math.round(n).toLocaleString('en');
  const adults = members().filter((m) => m.role !== 'child');
  const isG = store.me && store.me.role === 'guardian';
  const when = (d) => esc(fmtDate(d).replace(/,.*$/, ''));
  const flow = tl ? (tl.days.length ? '<ul class="mdlist">' + tl.days.slice(0, 14).map((d) => '<li class="mdrow"><span class="grow"><b>' + when(d.date) + '</b>' + d.items.map((i) => '<small class="muted">' + esc(i.title) + (i.amount != null ? ' · ' + esc(money(i.amount, i.currency)) : '') + '</small>').join('') + '</span></li>').join('') + '</ul>'
    + '<p class="muted" style="margin-top:8px;font-size:12.5px">Next 45 days: ' + (Object.keys(tl.totals).length ? Object.entries(tl.totals).map(([c, a]) => esc(money(a, c))).join(' + ') : 'nothing with an amount') + '</p>' : '<p class="muted" style="margin-top:6px">Nothing is expected to go out in the next 45 days.</p>') : '';
  const budHtml = (bud.length ? '<ul class="mdlist">' + bud.map((b) => '<li class="mdrow"><span class="grow"><b>' + esc(b.category) + '</b><small class="' + (b.over ? 'warn' : 'muted') + '">' + esc(money(b.spent, b.currency)) + ' of ' + esc(money(b.monthly_limit, b.currency)) + ' · ' + b.percent + '%' + (b.over ? ' · over' : '') + '</small></span></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">No budgets set.</p>')
    + (isG ? '<form class="md-form" data-budget style="margin-top:10px"><label>Category<input name="c" required maxlength="40" placeholder="food"></label><label>Per month<input name="a" type="number" min="1" required></label><button class="btn sm" type="submit">Set budget</button></form>' : '');
  const goalHtml = (goals.length ? '<ul class="mdlist">' + goals.map((g) => '<li class="mdrow" data-gid="' + esc(g.id) + '"><span class="grow"><b>' + esc(g.title) + '</b><small class="muted">' + esc(money(g.saved, g.currency)) + ' of ' + esc(money(g.target, g.currency)) + ' · ' + g.percent + '%' + (g.by_date ? ' · by ' + when(g.by_date) : '') + '</small></span><input type="number" min="1" placeholder="Add" aria-label="Add to the goal" style="width:84px"><button class="btn ghost sm" data-add type="button">Add</button></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">No goals yet.</p>')
    + '<form class="md-form" data-goal style="margin-top:10px"><label>Goal<input name="t" required maxlength="120" placeholder="Summer trip"></label><label>Target<input name="a" type="number" min="1" required></label><button class="btn sm" type="submit">Add goal</button></form>';
  const splitHtml = (splits.length ? '<ul class="mdlist">' + splits.map((x) => '<li class="mdrow"><span class="grow"><b>' + esc(x.title) + '</b><small class="muted">' + esc(money(x.amount, x.currency)) + ' paid by ' + esc(x.paid_by) + (x.owed.length ? ' · ' + x.owed.map((o) => esc(o.name) + ' owes ' + esc(money(o.amount, x.currency))).join(', ') : ' · settled') + '</small></span>'
    + x.shares.filter((sh) => !sh.settled).map((sh) => '<button class="btn ghost sm" data-settle="' + esc(x.id + '/' + sh.member_id) + '" type="button">' + esc(sh.name) + ' paid</button>').join('') + '</li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">Nothing split.</p>')
    + (adults.length > 1 ? '<form class="md-form" data-split style="margin-top:10px"><label>Bill<input name="t" required maxlength="160" placeholder="Electricity"></label><label>Amount<input name="a" type="number" min="1" required></label><label>Paid by<select name="p">' + adults.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.display_name) + '</option>').join('') + '</select></label><button class="btn sm" type="submit">Split evenly</button></form>' : '');
  const warHtml = (wars.length ? '<ul class="mdlist">' + wars.map((w) => '<li class="mdrow" data-wid="' + esc(w.id) + '"><span class="grow"><b>' + esc(w.title) + '</b><small class="muted">' + (w.return_by ? 'return by ' + when(w.return_by) : '') + (w.return_by && w.warranty_until ? ' · ' : '') + (w.warranty_until ? 'warranty to ' + when(w.warranty_until) : '') + '</small></span><button class="btn ghost sm" data-done type="button">Done</button></li>').join('') + '</ul>' : '<p class="muted" style="margin-top:6px">No purchases tracked.</p>')
    + '<form class="md-form" data-war style="margin-top:10px"><label>Bought<input name="t" required maxlength="160" placeholder="Water purifier"></label><label>Return days<input name="r" type="number" min="1" max="365" placeholder="10"></label><label>Warranty months<input name="w" type="number" min="1" max="120" placeholder="12"></label><button class="btn sm" type="submit">Track it</button></form>';
  main.innerHTML = moneyTabs('plan') + '<div class="greet"><div><h1>Money plan</h1><div class="day">What is coming up, budgets, goals, shared bills, returns and warranties. Nothing here moves money.</div></div></div>'
    + '<div class="md-grid">' + '<section class="card pad"><h2>Coming up</h2>' + flow + '</section><section class="card pad"><h2>Budgets this month</h2>' + budHtml + '</section>'
    + '<section class="card pad"><h2>Savings goals</h2>' + goalHtml + '</section><section class="card pad"><h2>Shared bills</h2>' + splitHtml + '</section><section class="card pad"><h2>Returns and warranties</h2>' + warHtml + '</section></div>';
  const post = async (p, body, m) => { try { await api(p, { method: m || 'POST', json: body }); myRerun(); } catch (err) { flash(err.message || 'Could not save.', true); } };
  const myRerun = () => moneyPlanView(main);
  const bf = main.querySelector('[data-budget]'); if (bf) bf.addEventListener('submit', (ev) => { ev.preventDefault(); post('/finance/budgets', { category: bf.c.value, monthly_limit: +bf.a.value }, 'PUT'); });
  main.querySelector('[data-goal]').addEventListener('submit', (ev) => { ev.preventDefault(); const f = ev.target; post('/finance/goals', { title: f.t.value, target_amount: +f.a.value }); });
  main.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => { const li = b.closest('[data-gid]'); const v = +li.querySelector('input').value; if (v) post('/finance/goals/' + li.dataset.gid + '/contribute', { amount: v }); }));
  const sf = main.querySelector('[data-split]'); if (sf) sf.addEventListener('submit', (ev) => { ev.preventDefault(); const half = 100 / adults.length; post('/finance/splits', { title: sf.t.value, amount: +sf.a.value, paid_by: sf.p.value, shares: adults.map((m) => ({ member_id: m.id, percent: half })) }); });
  main.querySelectorAll('[data-settle]').forEach((b) => b.addEventListener('click', () => post('/finance/splits/' + b.dataset.settle.split('/')[0] + '/settle/' + b.dataset.settle.split('/')[1], {})));
  main.querySelector('[data-war]').addEventListener('submit', (ev) => { ev.preventDefault(); const f = ev.target; post('/finance/warranties', { title: f.t.value, return_days: f.r.value ? +f.r.value : null, warranty_months: f.w.value ? +f.w.value : null }); });
  main.querySelectorAll('[data-done]').forEach((b) => b.addEventListener('click', async () => { try { await api('/finance/warranties/' + b.closest('[data-wid]').dataset.wid, { method: 'DELETE' }); myRerun(); } catch (err) { flash(err.message || 'Could not close it.', true); } }));
}

/* What it knows: each fact with its source, how it is known, who corrected it, when it was last confirmed (GET /v1/memory). Ask why,
   confirm it, or correct a child's school; a document is corrected in its own notice. */
async function knowsView(main) {
  main.classList.remove('chat-main');
  let facts; try { facts = await api('/memory'); } catch (err) { main.innerHTML = '<p class="muted pad">' + esc(err.message || 'Could not load.') + '</p>'; return; }
  const day = (v) => v ? esc(fmtDate(v).replace(/,.*$/, '') + ' ' + String(v).slice(0, 4)) : '';
  const row = (f) => '<li class="kn" data-key="' + esc(f.key) + '"><div class="kn-main"><span class="grow"><b>' + esc(f.label) + '</b><span>' + esc(f.value) + '</span>'
    + '<small class="muted">' + esc(f.source.text) + (f.last_verified ? ' · confirmed ' + day(f.last_verified) : ' · not confirmed yet') + (f.review_by ? ' · look again by ' + day(f.review_by) : '') + '</small></span>'
    + '<button class="btn ghost sm" data-why type="button">Why?</button><button class="btn ghost sm" data-ok type="button">That’s right</button>'
    + (f.correctable ? '<button class="btn ghost sm" data-fix type="button">Correct</button>' : '') + '</div><div class="kn-out" data-out></div></li>';
  main.innerHTML = '<div class="greet"><div><h1>What it knows</h1><div class="day">Each fact, where it came from, and how to correct it.</div></div></div>'
    + '<section class="card pad" style="margin-top:14px;max-width:820px">' + (facts.length ? '<ul class="mdlist">' + facts.map(row).join('') + '</ul>' : '<p class="muted">Nothing yet.</p>') + '</section>';
  const rerun = () => knowsView(main);
  main.querySelectorAll('[data-why]').forEach((b) => b.addEventListener('click', async () => {
    const li = b.closest('[data-key]'); const out = li.querySelector('[data-out]');
    if (out.innerHTML) { out.innerHTML = ''; return; }
    try { const w = await api('/memory/why?key=' + encodeURIComponent(li.dataset.key)); out.innerHTML = '<ol class="kn-steps">' + w.explanation.map((x) => '<li>' + esc(x) + '</li>').join('') + '</ol>' + (w.how_to_correct ? '<p class="muted" style="font-size:12.5px">' + esc(w.how_to_correct) + '</p>' : ''); }
    catch (err) { flash(err.message || 'Could not explain.', true); }
  }));
  main.querySelectorAll('[data-ok]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/memory/verify', { method: 'POST', json: { key: b.closest('[data-key]').dataset.key } }); flash('Confirmed.'); rerun(); } catch (err) { flash(err.message || 'Could not confirm.', true); }
  }));
  main.querySelectorAll('[data-fix]').forEach((b) => b.addEventListener('click', () => {
    const li = b.closest('[data-key]'); const out = li.querySelector('[data-out]');
    out.innerHTML = '<form class="md-form" data-form style="margin-top:8px"><label>School<input name="v" maxlength="160" required></label><label>Class<input name="c" maxlength="40"></label><button class="btn sm" type="submit">Save correction</button></form>';
    out.querySelector('[data-form]').addEventListener('submit', async (ev) => {
      ev.preventDefault(); const f = ev.target;
      try { await api('/memory/correct', { method: 'POST', json: { key: li.dataset.key, value: f.v.value, class_label: f.c.value || null } }); flash('Corrected.'); rerun(); } catch (err) { flash(err.message || 'Could not correct it.', true); }
    });
  }));
}

/* Family activity: each action as a receipt, with undo where nothing has changed since (GET /v1/activity). A guardian sees the
   household's; anyone else their own. */
/* One page, several views of it: a row of tabs shown on each route, so what used to be separate nav items reads as one place. */
function pageTabs(tabs, current) {
  if (tabs.length < 2) return '';        // one tab is not a choice: a member who cannot see the other views gets no tab row
  return '<div class="set-jump" role="navigation" aria-label="Views">' + tabs.map(([key, label, href]) =>
    '<a href="' + href + '"' + (key === current ? ' aria-current="page" style="background:var(--card-solid);color:var(--ink);border-color:var(--line-2)"' : '') + '>' + label + '</a>').join('') + '</div>';
}
function needsTabs(current) {
  const g = store.me && store.me.role === 'guardian';
  return pageTabs([['decisions', 'Needs you' + (store.decisionCount ? ' (' + store.decisionCount + ')' : ''), '#/decisions']]
    .concat(g ? [['quarantine', 'Quarantine' + (store.quarantineCount ? ' (' + store.quarantineCount + ')' : ''), '#/quarantine'],
                 ['revisions', 'Revisions' + (store.amendmentCount ? ' (' + store.amendmentCount + ')' : ''), '#/revisions']] : []), current);
}
function moneyTabs(current) {
  return pageTabs([['seen', 'Seen in mail', '#/money'], ['plan', 'Plan', '#/plan']], current);
}
function activityTabs(current) {
  return pageTabs([['receipts', 'Receipts', '#/activity']].concat(store.me && store.me.role === 'guardian' ? [['log', 'Technical log', '#/audit']] : []), current);
}

async function activityView(main) {
  main.classList.remove('chat-main');
  let rows; try { rows = await api('/activity?limit=60'); } catch (err) { main.innerHTML = '<p class="muted pad">' + esc(err.message || 'Could not load.') + '</p>'; return; }
  const when = (iso) => { const d = new Date(iso); return d.toLocaleDateString('en', { day: 'numeric', month: 'short' }) + ' ' + d.toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' }); };
  const line = (k, v) => v ? '<div class="rc-line"><span>' + esc(k) + '</span><span>' + esc(v) + '</span></div>' : '';
  const row = (r) => '<li class="rc" data-id="' + r.id + '"><div class="rc-main"><span class="grow"><b>' + esc(r.said) + '</b><small class="muted">' + esc(when(r.at)) + '</small></span>'
    + (r.undo ? '<button class="btn ghost sm" data-undo type="button">' + esc(r.undo.label) + '</button>' : '') + '</div>'
    + '<details class="rc-more"><summary>Receipt</summary>'
    + line('Observed', r.receipt.observed) + line('Read', r.receipt.inferred) + line('Because', r.receipt.rule) + line('Approved by', r.receipt.approved_by)
    + line('Changed', r.receipt.changed) + line('Outside', r.receipt.external ? 'calendar event ' + (r.receipt.external.event_id || '') : null) + '</details></li>';
  main.innerHTML = activityTabs('receipts') + '<div class="greet"><div><h1>Family activity</h1><div class="day">What was done, by whom, and on what. Undo appears only while nothing has changed since.</div></div></div>'
    + '<section class="card pad" style="margin-top:14px;max-width:820px">' + (rows.length ? '<ul class="mdlist">' + rows.map(row).join('') + '</ul>' : '<p class="muted">Nothing yet.</p>') + '</section>';
  main.querySelectorAll('[data-undo]').forEach((b) => b.addEventListener('click', async () => {
    const id = b.closest('[data-id]').dataset.id; b.disabled = true;
    try { await api('/activity/' + id + '/undo', { method: 'POST' }); flash('Undone.'); activityView(main); } catch (err) { b.disabled = false; flash(err.message || 'That can no longer be undone.', true); }
  }));
}

/* Needs you: only what waits on a person (GET /v1/decisions). Each card carries its source, what FamilyOS would do and
   why, what waiting costs, and buttons that are the existing endpoints; a click calls the one it describes. */
async function decisionsView(main) {
  main.classList.remove('chat-main');
  let cards; try { cards = await api('/decisions'); } catch (err) { main.innerHTML = '<p class="muted pad">' + esc(err.message || 'Could not load.') + '</p>'; return; }
  store.decisionCount = cards.length;
  let waiting = []; try { waiting = (await api('/handoffs')).items.filter((x) => x.direction === 'waiting_on'); } catch (e) { /* the queue still stands */ }
  const btn = (a, cls) => a.href ? '<a class="btn ghost sm" href="' + esc(a.href) + '" style="text-decoration:none">' + esc(a.label) + '</a>'
    : '<button class="btn ' + cls + ' sm" type="button" data-act="' + esc(JSON.stringify({ m: a.method, p: a.path, b: a.body })) + '">' + esc(a.label) + '</button>';
  const card = (c) => '<article class="card pad dq' + (c.late ? ' late' : '') + '" data-card="' + esc(c.id) + '">'
    + '<div class="dq-top"><span class="tag ' + (c.late ? 'red' : '') + '">' + esc({ date: 'a date', handed: 'handed to you', revision: 'a change', errand: 'an errand', purchase: 'a purchase', kid_request: 'a question', agent_proposal: 'from your assistant', pointer: 'waiting in the app', warranty: 'a warranty', document: 'a document', heads_up: 'a heads-up' }[c.kind] || c.kind) + '</span>'
    + (c.deadline ? '<span class="muted dq-when">' + (c.late ? 'was ' : 'by ') + esc(fmtDate(c.deadline).replace(/,.*$/, '')) + '</span>' : (c.when ? '<span class="muted dq-when">' + esc(c.when) + '</span>' : ''))
    + ((c.affects || []).length ? '<span class="muted dq-who">' + esc(c.affects.join(', ')) + '</span>' : '') + '</div>'
    + '<h2>' + esc(c.title) + '</h2><p class="dq-what">' + esc(c.happened) + '</p>'
    + (c.source && c.source.quote ? '<blockquote class="dq-src">“' + esc(c.source.quote) + '”' + (c.source.artifact_id ? ' <a href="#/notices/' + esc(c.source.artifact_id) + '">source</a>' : '') + '</blockquote>' : '')
    + '<div class="dq-rec"><b>FamilyOS suggests</b> ' + esc(c.recommendation.text) + '</div>'
    + '<p class="dq-cost muted"><b>If you wait:</b> ' + esc(c.consequence) + '</p>'
    + '<div class="dq-actions">' + c.actions.map((a) => a.choices
      ? '<span class="dq-del"><select data-del aria-label="Hand to">' + '<option value="">Hand to…</option>' + a.choices.map((ch) => '<option value="' + esc(JSON.stringify({ m: ch.method, p: ch.path, b: ch.body })) + '">' + esc(ch.label) + '</option>').join('') + '</select></span>'
      : btn(a, a.primary ? '' : 'ghost')).join('') + '</div></article>';
  main.innerHTML = needsTabs('decisions') + '<div class="greet"><div><h1>Needs you</h1><div class="day">' + (cards.length ? cards.length + (cards.length === 1 ? ' decision' : ' decisions') + ' waiting' : 'Nothing is waiting on you') + '</div></div></div>'
    + (cards.length ? '<div class="dq-list">' + cards.map(card).join('') + '</div>' : '<section class="card pad"><p class="muted">Every date, handover and approval has been answered. New ones appear here, and nowhere else is a decision hidden.</p></section>');
  if (waiting.length) {
    const sec = document.createElement('section'); sec.className = 'card pad'; sec.style.cssText = 'margin-top:18px;max-width:760px';
    sec.innerHTML = '<h2>You are waiting on</h2><ul class="mdlist">' + waiting.map((x) => '<li class="mdrow" data-wid="' + esc(x.id) + '"><span class="grow"><a href="#/notices/' + esc(x.id) + '">' + esc(x.title) + '</a>'
      + '<small class="muted">' + esc(x.with) + ' · ' + (x.state === 'pending' ? 'has not answered' : x.state === 'accepted' ? 'has it' : x.state) + (x.has_backup ? ' · a backup is named' : '') + '</small></span>'
      + '<button class="btn ghost sm" data-takeback type="button">Take it back</button></li>').join('') + '</ul>';
    main.appendChild(sec);
    sec.querySelectorAll('[data-takeback]').forEach((b) => b.addEventListener('click', async () => {
      try { await api('/artifacts/' + b.closest('[data-wid]').dataset.wid + '/assign', { method: 'POST', json: { member_id: null } }); flash('Taken back.'); decisionsView(main); } catch (err) { flash(err.message || 'Could not take it back.', true); }
    }));
  }
  const call = async (spec) => { const x = JSON.parse(spec); await api(x.p.replace(/^\/v1/, ''), { method: x.m, json: Object.keys(x.b || {}).length || x.m !== 'POST' ? x.b : undefined }); };
  main.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', async () => {
    b.disabled = true;
    try { await call(b.dataset.act); flash('Done.'); decisionsView(main); } catch (err) { b.disabled = false; flash(err.message || 'Could not do that.', true); }
  }));
  main.querySelectorAll('[data-del]').forEach((sel) => sel.addEventListener('change', async () => {
    if (!sel.value) return;
    try { await call(sel.value); flash('Handed on.'); decisionsView(main); } catch (err) { sel.value = ''; flash(err.message || 'Could not hand it on.', true); }
  }));
}

/* My day: one page for the signed-in person, from what is already theirs (GET /v1/me/day): what needs them, ideas ranked by
   what they accept, how FamilyOS may reach them, their routines, what it has counted, and their Health line if they use it. */
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hourName = (h) => (h % 12 === 0 ? 12 : h % 12) + (h < 12 ? ' am' : ' pm');
// ---- Ask my assistant: tasks sent to my own Claude or Grok, and the outside MCP servers I allow (assistant_tasks.py, mcp_client.py)
const ASST_PROVIDERS = [['claude', 'Claude, my API key (needs a public address)'], ['grok', 'Grok, my xAI key (needs a public address)'], ['claude_code', 'Claude Code on this server (works here, development)']];
function asstTaskHtml(t) {
  const state = t.status === 'done' ? '' : t.status === 'failed' ? '<small class="muted">Did not work: ' + esc(t.error || 'no answer') + '</small>' : '<small class="muted">Working on it…</small>';
  return '<li class="asst-task"><b>' + esc(t.instruction) + '</b><small class="muted">' + esc(t.label) + ' · ' + esc(new Date(t.created_at).toLocaleString('en', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })) + '</small>' + state
    + (t.result ? '<blockquote class="asst-reply">' + esc(t.result) + '</blockquote><small class="muted">Your assistant’s reply, as text. Nothing in it has been done.</small>' : '') + '</li>';
}
async function assistantSection() {
  let conns = [], tasks = [], servers = [];
  try { conns = await api('/me/assistant-connections'); tasks = await api('/me/assistant-tasks'); } catch (e) { /* stays empty */ }
  try { servers = await api('/me/mcp-servers'); } catch (e) { /* stays empty */ }
  const opts = ASST_PROVIDERS.map((p) => '<option value="' + p[0] + '">' + esc(p[1]) + '</option>').join('');
  return '<section class="card pad wide" data-asst><h2>Ask my assistant</h2><p class="muted" style="font-size:12.5px">Send an instruction to your own Claude or Grok. It looks at FamilyOS as you, can only read and propose, and answers in text. Its key is yours, kept sealed here and never shown again.</p>'
    + (conns.length ? '<form class="md-form" data-asst-send><label style="grid-column:1/-1">Instruction<textarea name="i" required minlength="3" maxlength="1500" rows="2" placeholder="What needs me this week, and what can wait?"></textarea></label>'
      + '<label>Send to<select name="c">' + conns.map((c) => '<option value="' + esc(c.id) + '">' + esc(c.label) + ' (' + c.used_today + ' of ' + c.daily_cap + ' today)</option>').join('') + '</select></label><button class="btn sm" type="submit">Send</button></form>'
      + '<ul class="asst-tasks" data-asst-tasks>' + tasks.map(asstTaskHtml).join('') + '</ul>' : '<p class="muted" style="margin-top:8px">Add a connection to start.</p>')
    + '<details class="asst-more"' + (conns.length ? '' : ' open') + '><summary>Connections (' + conns.length + ')</summary><ul class="mdlist">' + conns.map((c) => '<li class="mdrow" data-cid="' + esc(c.id) + '"><span class="grow"><b>' + esc(c.label) + '</b><small class="muted">' + esc(c.provider) + (c.model ? ' · ' + esc(c.model) : '') + ' · up to ' + c.daily_cap + ' a day</small></span><button class="btn ghost sm" data-asst-rm type="button">Remove</button></li>').join('')
    + '</ul><form class="md-form" data-asst-add><label>Assistant<select name="p">' + opts + '</select></label><label>Name<input name="l" maxlength="60" placeholder="My Claude"></label>'
    + '<label style="grid-column:1/-1">API key<input name="k" type="password" autocomplete="off" maxlength="400" placeholder="Pasted once, then sealed"></label><button class="btn sm" type="submit">Add connection</button></form></details>'
    + '<details class="asst-more"><summary>Outside servers (' + servers.length + ')</summary><p class="muted" style="font-size:12.5px;margin-top:6px">Other MCP servers you choose to use: https only, no private addresses. You tick which tools may be called and you make each call. What comes back is not kept.</p><ul class="mdlist">'
    + servers.map((s) => '<li class="mdrow" data-sid="' + esc(s.id) + '" style="flex-wrap:wrap"><span class="grow"><b>' + esc(s.label) + '</b><small class="muted">' + esc(s.url) + ' · ' + s.allowed_tools.length + ' tool' + (s.allowed_tools.length === 1 ? '' : 's') + ' allowed</small></span><button class="btn ghost sm" data-srv-tools type="button">Choose tools</button><button class="btn ghost sm" data-srv-rm type="button">Remove</button><div class="asst-srv" style="flex-basis:100%"></div></li>').join('')
    + '</ul><form class="md-form" data-srv-add><label>Name<input name="l" required maxlength="60" placeholder="School library"></label><label>Address<input name="u" type="url" required maxlength="500" placeholder="https://…/mcp"></label>'
    + '<label style="grid-column:1/-1">Access key, if it needs one<input name="a" type="password" autocomplete="off" maxlength="600"></label><button class="btn sm" type="submit">Add server</button></form></details></section>';
}
function bindAssistant(main, redo = () => myDayView(main)) {
  const root = main.querySelector('[data-asst]'); if (!root) return;
  const fail = (err, fallback) => flash((err && err.message) || fallback, true);
  const add = root.querySelector('[data-asst-add]');
  if (add) add.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/me/assistant-connections', { method: 'POST', json: { provider: add.p.value, label: add.l.value, api_key: add.k.value } }); flash('Connected.'); redo(); } catch (err) { fail(err, 'Could not add it.'); } });
  root.querySelectorAll('[data-asst-rm]').forEach((b) => b.addEventListener('click', async () => { try { await api('/me/assistant-connections/' + b.closest('[data-cid]').dataset.cid, { method: 'DELETE' }); redo(); } catch (err) { fail(err, 'Could not remove it.'); } }));
  const list = root.querySelector('[data-asst-tasks]');
  const poll = (n) => setTimeout(async () => {
    if (!list.isConnected) return;
    try { const ts = await api('/me/assistant-tasks'); list.innerHTML = ts.map(asstTaskHtml).join(''); if (ts.some((t) => t.status === 'queued' || t.status === 'running') && n < 90) poll(n + 1); } catch (e) { /* try again next time */ }
  }, 2500);
  if (list) poll(0);
  const send = root.querySelector('[data-asst-send]');
  if (send) send.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try { await api('/me/assistant-tasks', { method: 'POST', json: { connection_id: send.c.value, instruction: send.i.value } }); send.i.value = ''; const ts = await api('/me/assistant-tasks'); list.innerHTML = ts.map(asstTaskHtml).join(''); poll(0); } catch (err) { fail(err, 'Could not send it.'); }
  });
  const sadd = root.querySelector('[data-srv-add]');
  if (sadd) sadd.addEventListener('submit', async (ev) => { ev.preventDefault(); try { await api('/me/mcp-servers', { method: 'POST', json: { label: sadd.l.value, url: sadd.u.value, auth: sadd.a.value } }); flash('Added.'); redo(); } catch (err) { fail(err, 'Could not add it.'); } });
  root.querySelectorAll('[data-srv-rm]').forEach((b) => b.addEventListener('click', async () => { try { await api('/me/mcp-servers/' + b.closest('[data-sid]').dataset.sid, { method: 'DELETE' }); redo(); } catch (err) { fail(err, 'Could not remove it.'); } }));
  root.querySelectorAll('[data-srv-tools]').forEach((b) => b.addEventListener('click', async () => {
    const li = b.closest('[data-sid]'); const box = li.querySelector('.asst-srv'); const sid = li.dataset.sid;
    if (box.innerHTML) { box.innerHTML = ''; return; }
    box.innerHTML = '<p class="muted" style="font-size:12.5px">Asking the server…</p>';
    try {
      const r = await api('/me/mcp-servers/' + sid + '/tools');
      box.innerHTML = '<p class="muted" style="font-size:12px">' + esc(r.notice) + '</p>' + (r.tools.length ? r.tools.map((t) => '<label class="asst-tool"><input type="checkbox" value="' + esc(t.name) + '"' + (t.allowed ? ' checked' : '') + '><span><b>' + esc(t.name) + '</b><small class="muted">' + esc(t.description) + '</small></span></label>').join('') + '<button class="btn sm" data-srv-save type="button">Save allowed tools</button>' : '<p class="muted">It lists no tools.</p>')
        + '<div data-srv-try hidden><h3 style="font-size:13px;margin-top:10px">Try an allowed tool</h3><div class="md-form"><label>Tool<select data-t></select></label><label>Arguments (JSON)<input data-a value="{}"></label><button class="btn sm" data-srv-go type="button">Call it</button></div><pre class="asst-out" data-o hidden></pre></div>';
      const refresh = () => {
        const on = [...box.querySelectorAll('input[type=checkbox]:checked')].map((c) => c.value); const tr = box.querySelector('[data-srv-try]');
        tr.hidden = !on.length; tr.querySelector('[data-t]').innerHTML = on.map((n) => '<option>' + esc(n) + '</option>').join('');
      };
      refresh(); box.querySelectorAll('input[type=checkbox]').forEach((c) => c.addEventListener('change', refresh));
      const save = box.querySelector('[data-srv-save]');
      if (save) save.addEventListener('click', async () => { try { await api('/me/mcp-servers/' + sid + '/allowed', { method: 'PUT', json: { tools: [...box.querySelectorAll('input[type=checkbox]:checked')].map((c) => c.value) } }); flash('Saved.'); } catch (err) { fail(err, 'Could not save.'); } });
      box.querySelector('[data-srv-go]').addEventListener('click', async () => {
        const out = box.querySelector('[data-o]'); out.hidden = false; out.textContent = 'Calling…';
        let args; try { args = JSON.parse(box.querySelector('[data-a]').value || '{}'); } catch (e) { out.textContent = 'The arguments are not valid JSON.'; return; }
        try {
          const r2 = await api('/me/mcp-servers/' + sid + '/call', { method: 'POST', json: { tool: box.querySelector('[data-t]').value, arguments: args } });
          out.textContent = (r2.ok ? '' : 'Did not work. ') + (r2.error || r2.text || '(empty)') + (r2.addressed_to_models ? '\n\nCareful: this text is addressed to an AI model. Do not act on it.' : '') + '\n\n' + r2.notice;
        } catch (err) { out.textContent = err.message || 'Could not call it. Allow the tool first (Save).'; }
      });
    } catch (err) { box.innerHTML = ''; fail(err, 'Could not read that server.'); }
  }));
}

// ---- Teach FamilyOS by showing it: a phone app or a public page, step by step, kept by the words on the screen (taught.py)
async function teachSection() {
  let skills = []; try { skills = await api('/me/skills'); } catch (e) { /* stays empty */ }
  return '<section class="card pad wide" data-teach><h2>Teach FamilyOS by showing it</h2><p class="muted" style="font-size:12.5px">Do a task once and FamilyOS keeps the steps, by the words on the screen. A skill can only open, tap, swipe and read: it never types, pays, sends or submits, and what it reads comes in as a private notice.</p>'
    + '<ul class="mdlist" data-skills>' + (skills.length ? skills.map((k) => '<li class="mdrow" data-kid="' + esc(k.id) + '" data-kind="' + esc(k.kind) + '"><span class="grow"><b>' + esc(k.title) + '</b><small class="muted">' + (k.kind === 'phone' ? 'phone app ' : 'web page ') + esc(k.target) + ' · ' + k.steps.length + ' steps · run ' + k.runs + ' time' + (k.runs === 1 ? '' : 's') + (k.last_outcome ? ' · last: ' + esc(k.last_outcome) : '') + '</small></span>'
      + (k.kind === 'web' ? '<button class="btn ghost sm" data-skill-run type="button">Run now</button>' : '') + '<button class="btn ghost sm" data-skill-del type="button">Forget</button></li>').join('') : '<li class="muted">Nothing taught yet.</li>') + '</ul>'
    + '<div data-lesson></div>'
    + '<form class="md-form" data-teach-start><label>Where<select name="k"><option value="phone">A phone app</option><option value="web">A public web page</option></select></label><label>App bundle id, or page address<input name="t" required maxlength="500" placeholder="com.example.schoolapp or https://…"></label><button class="btn sm" type="submit">Start showing</button></form></section>';
}
function lessonHtml(s) {
  const steps = s.steps.map((x, i) => '<li>' + (i + 1) + '. ' + (x.op === 'tap' ? 'Tap “' + esc(x.text) + '”' : x.op === 'swipe' ? 'Swipe ' + esc(x.direction) : 'Read this screen') + '</li>').join('');
  let body;
  if (!s.connected) {
    body = '<p style="margin-top:8px">Waiting for the phone. Run the phone driver on your Mac with a one-use address (it works once, for ten minutes):</p><button class="btn sm" data-lticket type="button">Copy the address</button>';
  } else if (!s.words && s.kind === 'phone' && !s.steps.length) {
    body = '<p style="margin-top:8px">Phone connected.</p><button class="btn sm" data-lstep=\'{"op":"open"}\' type="button">Open the app</button>';
  } else {
    body = '<pre class="asst-out">' + esc(s.words || '(nothing readable on this screen)') + '</pre><div class="asst-chips">'
      + s.labels.map((l) => '<button class="btn ghost sm" data-ltap="' + esc(l) + '" type="button">' + esc(l) + '</button>').join('')
      + '</div><div class="row" style="gap:8px;margin-top:8px;flex-wrap:wrap"><button class="btn sm" data-lstep=\'{"op":"read"}\' type="button">Read this screen</button><button class="btn ghost sm" data-lstep=\'{"op":"swipe","direction":"up"}\' type="button">Swipe up</button><button class="btn ghost sm" data-lundo type="button">Undo last step</button></div>'
      + (s.not_offered.length ? '<p class="muted" style="font-size:12px;margin-top:6px">Not offered, because it would do something: ' + s.not_offered.map(esc).join(', ') + '.</p>' : '');
  }
  return '<div class="asst-lesson"><h3 style="font-size:14px">Showing: ' + esc(s.target) + '</h3>' + body + (steps ? '<ol class="asst-steps">' + steps + '</ol>' : '')
    + '<form class="md-form" data-lsave style="margin-top:10px"><label>Name this skill<input name="n" required maxlength="80" placeholder="School announcements"></label><button class="btn sm" type="submit">Save skill</button></form><button class="btn ghost sm" data-lcancel type="button">Cancel</button></div>';
}
function bindTeach(main) {
  const root = main.querySelector('[data-teach]'); if (!root) return;
  const box = root.querySelector('[data-lesson]'); let lid = null; let timer = null;
  const fail = (err, fallback) => flash((err && err.message) || fallback, true);
  const draw = (s) => { lid = s.id; box.innerHTML = lessonHtml(s); wire(); if (!s.connected) { clearTimeout(timer); timer = setTimeout(async () => { if (box.isConnected && lid) { try { draw(await api('/me/teach/' + lid)); } catch (e) { /* ended */ } } }, 2500); } };
  const step = async (body) => { try { draw(await api('/me/teach/' + lid + '/step', { method: 'POST', json: body })); } catch (err) { fail(err, 'That did not work.'); } };
  function wire() {
    box.querySelectorAll('[data-lstep]').forEach((b) => b.addEventListener('click', () => step(JSON.parse(b.dataset.lstep))));
    box.querySelectorAll('[data-ltap]').forEach((b) => b.addEventListener('click', () => step({ op: 'tap', text: b.dataset.ltap })));
    const tk = box.querySelector('[data-lticket]'); if (tk) tk.addEventListener('click', async () => { try { const t = await api('/me/teach/' + lid + '/phone-ticket', { method: 'POST' }); await navigator.clipboard.writeText((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + t.path); flash('Copied. It works once, for ten minutes.'); } catch (err) { fail(err, 'Could not copy here.'); } });
    const u = box.querySelector('[data-lundo]'); if (u) u.addEventListener('click', async () => { try { draw(await api('/me/teach/' + lid + '/undo', { method: 'POST' })); } catch (err) { fail(err, 'Could not undo.'); } });
    const c = box.querySelector('[data-lcancel]'); if (c) c.addEventListener('click', async () => { clearTimeout(timer); try { await api('/me/teach/' + lid, { method: 'DELETE' }); } catch (e) { /* gone already */ } lid = null; box.innerHTML = ''; });
    const f = box.querySelector('[data-lsave]'); if (f) f.addEventListener('submit', async (ev) => { ev.preventDefault(); clearTimeout(timer); try { await api('/me/teach/' + lid + '/save', { method: 'POST', json: { title: f.n.value } }); flash('Saved.'); myDayView(main); } catch (err) { fail(err, 'Could not save it.'); } });
  }
  const st = root.querySelector('[data-teach-start]');
  st.addEventListener('submit', async (ev) => { ev.preventDefault(); try { draw(await api('/me/teach', { method: 'POST', json: { kind: st.k.value, target: st.t.value } })); } catch (err) { fail(err, 'Could not start.'); } });
  root.querySelectorAll('[data-skill-del]').forEach((b) => b.addEventListener('click', async () => { try { await api('/me/skills/' + b.closest('[data-kid]').dataset.kid, { method: 'DELETE' }); myDayView(main); } catch (err) { fail(err, 'Could not forget it.'); } }));
  root.querySelectorAll('[data-skill-run]').forEach((b) => b.addEventListener('click', async () => {
    b.disabled = true; b.textContent = 'Running…';
    try { const r = await api('/me/skills/' + b.closest('[data-kid]').dataset.kid + '/run', { method: 'POST' }); flash(r.status === 'done' ? 'Done. ' + r.handed_in + ' brought in as a private notice.' : 'Stopped: ' + (r.stopped || 'it needs you'), r.status !== 'done'); myDayView(main); } catch (err) { b.disabled = false; b.textContent = 'Run now'; fail(err, 'Could not run it.'); }
  }));
}

// ---- Family map: how what the household holds connects (graph.py). Click anything to centre on it.
const MAP_TYPES = { person: 'People', obligation: 'Dates and tasks', document: 'Documents', warranty: 'Warranties', medication: 'Medicines', org: 'Shops and clinics', artifact: 'Notices' };
function mapPos(conns, ref, cx, cy) {
  const ring1 = conns.filter((c) => c.distance === 1).slice(0, 12); const ring2 = conns.filter((c) => c.distance === 2).slice(0, 18);
  const at = {}; const TAU = Math.PI * 2;
  ring1.forEach((c, i) => { const a = -Math.PI / 2 + (i * TAU) / Math.max(ring1.length, 1); at[c.node.ref] = { x: cx + 165 * Math.cos(a), y: cy + 165 * Math.sin(a), a }; });
  const byParent = {};
  ring2.forEach((c) => { const first = c.path[0]; const parent = first.from === ref ? first.to : first.from; (byParent[parent] ||= []).push(c); });
  Object.entries(byParent).forEach(([parent, list]) => {
    const base = at[parent] ? at[parent].a : 0; const step = Math.min(0.3, 1.1 / Math.max(list.length, 1));
    list.forEach((c, i) => { const a = base + (i - (list.length - 1) / 2) * step; at[c.node.ref] = { x: cx + 275 * Math.cos(a), y: cy + 275 * Math.sin(a), a, parent: at[parent] }; });
  });
  return { ring1, ring2, at };
}
async function mapView(main, args) {
  let ref = decodeURIComponent((args && args[0]) || '') || ('person:' + store.me.id); let t;
  try { t = await api('/graph/touches?depth=2&ref=' + encodeURIComponent(ref)); } catch (err) {
    if (ref !== 'person:' + store.me.id) { go('/map/' + encodeURIComponent('person:' + store.me.id)); return; }
    throw err;
  }
  let notice = []; try { notice = await api('/graph/insights'); } catch (e) { /* the map still works */ }
  const e = t.entity; const conns = t.connections; const W = 780, H = 640, cx = W / 2, cy = H / 2;
  const { ring1, ring2, at } = mapPos(conns, e.ref, cx, cy); const shown = new Set([...ring1, ...ring2].map((c) => c.node.ref));
  const short = (s) => (s.length > 20 ? s.slice(0, 19) + '…' : s);
  const lines = [...ring1, ...ring2].map((c) => { const to = at[c.node.ref]; const from = c.distance === 1 ? { x: cx, y: cy } : (to.parent || { x: cx, y: cy }); return '<line class="fe d' + c.distance + '" x1="' + from.x.toFixed(1) + '" y1="' + from.y.toFixed(1) + '" x2="' + to.x.toFixed(1) + '" y2="' + to.y.toFixed(1) + '"/>'; }).join('');
  const dot = (n, x, y, big) => '<g class="fn t-' + n.type + (big ? ' me' : '') + '" tabindex="0" role="link" data-ref="' + esc(n.ref) + '" transform="translate(' + x.toFixed(1) + ' ' + y.toFixed(1) + ')"><title>' + esc(n.label) + '</title><circle r="' + (big ? 26 : 17) + '"/><text class="fl" y="' + (big ? 44 : 33) + '" text-anchor="middle">' + esc(short(n.label)) + '</text></g>';
  const nodes = [...ring1, ...ring2].map((c) => dot(c.node, at[c.node.ref].x, at[c.node.ref].y, false)).join('') + dot(e, cx, cy, true);
  const rest = conns.filter((c) => !shown.has(c.node.ref));
  const facts = [e.due ? 'due ' + fmtDate(e.due) : '', e.expires_on ? 'expires ' + fmtDate(e.expires_on) : '', e.warranty_until ? 'warranty to ' + fmtDate(e.warranty_until) : '', e.kind ? e.kind.replace('_', ' ') : ''].filter(Boolean).join(' · ');
  const row = (c) => '<li class="mdrow" data-ref="' + esc(c.node.ref) + '"><span class="grow"><b>' + esc(c.node.label) + '</b><small class="muted">' + esc(c.path[c.path.length - 1].phrase) + '</small></span>'
    + (c.path[c.path.length - 1].source_artifact_id ? '<a class="btn ghost sm" href="#/notices/' + esc(c.path[c.path.length - 1].source_artifact_id) + '">Read the notice</a>' : '') + '<button class="btn ghost sm" data-centre type="button">Centre here</button></li>';
  const groups = Object.entries(MAP_TYPES).map(([k, label]) => { const items = conns.filter((c) => c.node.type === k); return items.length ? '<h3 class="map-h">' + label + ' <span class="muted">' + items.length + '</span></h3><ul class="mdlist">' + items.map(row).join('') + '</ul>' : ''; }).join('');
  main.innerHTML = '<div class="greet"><div><h1>Family map</h1><div class="day">How what your home holds connects. Click anything to centre on it.</div></div></div>'
    + '<div class="map-grid"><section class="card pad fmap"><div class="map-search"><input type="text" data-find placeholder="Find a person, shop, clinic or document…" autocomplete="off" aria-label="Find on the map"><ul class="map-hits" data-hits hidden></ul></div>'
    + '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc('Connections around ' + e.label) + '">' + lines + nodes + '</svg>'
    + '<div class="map-key">' + Object.entries(MAP_TYPES).map(([k, label]) => '<span><i class="kd t-' + k + '"></i>' + label + '</span>').join('') + '</div></section>'
    + '<section class="card pad"><h2>' + esc(e.label) + '</h2><p class="muted" style="margin-top:2px">' + esc(MAP_TYPES[e.type] ? MAP_TYPES[e.type].replace(/s$/, '') : e.type) + (facts ? ' · ' + esc(facts) : '') + '</p>'
    + (notice.length ? '<div class="map-notice"><h3 class="map-h">Worth a look</h3><ul class="mdlist">' + notice.map((n) => '<li class="mdrow"><span class="grow"><b>' + esc(n.title) + '</b><small class="muted">' + esc(n.why) + '</small></span><a class="btn ghost sm" href="#/map/' + encodeURIComponent(n.ref) + '">Open</a></li>').join('') + '</ul></div>' : '')
    + (conns.length ? groups : '<p class="muted" style="margin-top:10px">Nothing is connected to this yet.</p>') + (rest.length ? '<p class="muted" style="margin-top:8px">' + rest.length + ' more not drawn; they are listed above.</p>' : '') + '</section></div>';
  const centre = (r) => go('/map/' + encodeURIComponent(r));
  main.querySelectorAll('svg .fn').forEach((g) => { g.addEventListener('click', () => centre(g.dataset.ref)); g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') centre(g.dataset.ref); }); });
  main.querySelectorAll('[data-centre]').forEach((b) => b.addEventListener('click', () => centre(b.closest('li').dataset.ref)));
  const input = main.querySelector('[data-find]'); const hits = main.querySelector('[data-hits]'); let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim(); if (q.length < 2) { hits.hidden = true; return; }
      try { const found = await api('/graph/find?q=' + encodeURIComponent(q)); hits.innerHTML = found.length ? found.map((n) => '<li><button type="button" data-go="' + esc(n.ref) + '">' + esc(n.label) + ' <span class="muted">' + esc(n.type) + '</span></button></li>').join('') : '<li class="muted" style="padding:6px 10px">Nothing by that name.</li>'; hits.hidden = false; hits.querySelectorAll('[data-go]').forEach((b) => b.addEventListener('click', () => centre(b.dataset.go))); } catch (err) { hits.hidden = true; }
    }, 250);
  });
}

async function myDayView(main) {
  main.classList.remove('chat-main');
  let d; try { d = await api('/me/day'); } catch (err) { main.innerHTML = '<p class="muted pad">' + esc(err.message || 'Could not load your day.') + '</p>'; return; }
  const sel = (name, value, opts) => '<select name="' + name + '">' + opts.map(([v, l]) => '<option value="' + v + '"' + (String(v) === String(value) ? ' selected' : '') + '>' + esc(l) + '</option>').join('') + '</select>';
  const r = d.reach_me || {};
  let shop = { enabled: false }; try { shop = await api('/shop/status'); } catch (e) { /* stays off */ }
  const needs = (d.needs || []).map((i) => '<li class="mdrow"><span class="dot ' + (i.reason === 'missed' || i.reason === 'overdue' ? 'warn' : '') + '"></span><span class="grow">'
    + (i.artifact_id ? '<a href="#/notices/' + esc(i.artifact_id) + '">' + esc(i.title) + '</a>' : esc(i.title))
    + '<small class="muted">' + esc(i.when || '') + (i.when && i.why ? ' · ' : '') + esc(i.why || '') + '</small></span></li>').join('');
  const ideas = (d.suggestions || []).map((x) => '<li class="mdrow" data-key="' + esc(x.key) + '"><span class="grow"><b>' + esc(x.title) + '</b><small class="muted">' + esc(x.why || '') + '</small></span>'
    + '<button class="btn sm" data-add type="button">Add</button>' + (shop.enabled ? '<button class="btn ghost sm" data-find type="button">Find options</button>' : '') + '<button class="btn ghost sm" data-no type="button">Not this</button><div class="kn-out" data-shop style="flex-basis:100%"></div></li>').join('');
  const outcomeWord = { sent: 'said something', silent: 'had nothing to say', waited: 'waited for quiet hours to end', failed: 'could not run' };
  const routinesHtml = (d.routines || []).map((x) => '<li class="mdrow" data-rid="' + esc(x.id) + '" style="flex-wrap:wrap"><span class="grow">' + esc(x.instruction)
    + '<small class="muted">' + esc(x.when) + (x.policy === 'prepare' ? ' · prepares buttons' : ' · tells you') + (x.paused ? ' · paused' : '') + (x.last_outcome ? ' · last ' + esc(outcomeWord[x.last_outcome] || x.last_outcome) : '') + '</small></span>'
    + '<button class="btn ghost sm" data-pause type="button" data-paused="' + (x.paused ? '1' : '') + '">' + (x.paused ? 'Resume' : 'Pause') + '</button>'
    + '<button class="btn ghost sm" data-hist type="button">History</button><button class="btn ghost sm" data-stop type="button">Stop</button><div class="kn-out" data-hout style="flex-basis:100%"></div></li>').join('');
  const learned = (d.learned || []).map((x) => '<li class="mdrow"><span class="grow"><b>' + esc(x.kind) + '</b><small class="muted">added ' + x.accepted + ' · waved away ' + x.dismissed + (x.quiet ? ' · now quiet' : '') + '</small></span></li>').join('');
  let load = []; if (d.role !== 'child') { try { load = await api('/workload'); } catch (e) { load = []; } }
  let bal = { enabled: false, nudges: [] }; try { bal = await api('/me/balance'); } catch (e) { /* stays off */ }
  const asst = d.role !== 'child' ? '<section class="card pad wide"><p class="muted" style="line-height:1.5">Your assistants (Claude, Grok, outside servers) are in <a href="#/household?open=connections">Settings → Connections</a>.</p></section>' : '';
  let teach = ''; if (d.role !== 'child') { try { teach = await teachSection(); } catch (e) { teach = ''; } }
  let agentsList = []; if (d.role !== 'child') { try { agentsList = await api('/me/agents'); } catch (e) { agentsList = []; } }
  const hl = d.health || {};
  main.innerHTML = '<div class="greet"><div><h1>My day</h1><div class="day">' + esc(fmtDate(d.date)) + ' · ' + esc(d.display_name) + '</div></div></div>'
    + '<div class="md-grid">'
    + '<section class="card pad"><h2>Needs you</h2>' + (needs ? '<ul class="mdlist">' + needs + '</ul>' + (d.more ? '<p class="muted" style="margin-top:6px">and ' + d.more + ' more · <a href="#/today">see all</a></p>' : '') : '<p class="muted" style="margin-top:6px">Nothing needs you right now.</p>') + '</section>'
    + '<section class="card pad"><h2>Ideas for you</h2><p class="muted" style="font-size:12.5px">Ordered by what you accept; a kind you keep waving away goes quiet.</p>'
    + (ideas ? '<ul class="mdlist">' + ideas + '</ul>' : '<p class="muted" style="margin-top:6px">No ideas right now.</p>') + '</section>'
    + '<section class="card pad"><h2>How FamilyOS reaches me</h2><p class="muted" style="line-height:1.5;margin-top:6px">Your morning message, quiet hours and the most it may say in a day are in your profile, with your phone number and work.</p><button class="btn ghost sm" type="button" data-open-profile>Open my profile</button></section>'
    + '<section class="card pad"><h2>My autopilot</h2><span class="muted" style="font-size:12.5px">Rules that run on a clock or when something happens. They only read and say; “prepares buttons” also stages what it would do for you to confirm. Pause any of them.</span>'
    + (routinesHtml ? '<ul class="mdlist">' + routinesHtml + '</ul>' : '<p class="muted" style="margin-top:6px">None yet.</p>')
    + '<form class="md-form" data-newrule style="margin-top:12px"><label style="grid-column:1/-1">What should it do?<input name="i" required minlength="3" maxlength="400" placeholder="Compare it with the usual amount"></label>'
    + '<label>When<select name="t"><option value="time">At a time</option><option value="bill_arrived">A bill arrives</option><option value="date_changed">A notice changes a date</option><option value="trip_soon">Days before travel</option><option value="conflict">Two things clash</option></select></label>'
    + '<label data-for="time">Hour' + sel('h', 18, HOURS.map((h) => [h, hourName(h)])) + '</label><label data-for="trip_soon" hidden>Days before<input name="n" type="number" min="0" max="60" value="3"></label>'
    + '<label>Then' + sel('p', 'tell', [['tell', 'Tell me'], ['prepare', 'Prepare buttons']]) + '</label><button class="btn sm" type="submit">Add</button></form></section>'
    + '<section class="card pad"><h2>What it has counted about me</h2><p class="muted" style="font-size:12.5px">Only which kinds of ideas you add or wave away, over 90 days. It only orders and quiets ideas.</p>'
    + (learned ? '<ul class="mdlist">' + learned + '</ul><button class="btn ghost sm" data-forget type="button" style="margin-top:8px">Forget these</button>' : '<p class="muted" style="margin-top:6px">Nothing yet.</p>') + '</section>'
    + (bal.nudges.length ? '<section class="card pad"><h2>A gentle word</h2>' + bal.nudges.map((n) => '<p style="margin-top:6px">' + esc(n.text) + '</p><div class="row" style="gap:8px;margin-top:6px"><a class="btn ghost sm" href="#/decisions" style="text-decoration:none">See what is waiting</a><button class="btn ghost sm" data-balno="' + esc(n.domain) + '" type="button">Not now</button></div>').join('') + '<p class="muted" style="font-size:12px;margin-top:8px">Only you see this. It is never a score.</p></section>' : '')
    + (d.role !== 'child' ? '<section class="card pad"><h2>My assistant</h2><p class="muted" style="font-size:12.5px">Connect your own assistant (Grok Bot, Claude, ChatGPT, any MCP client). It sees what you see, can propose things for you to confirm, and shares with the family only if you allow it.</p>'
      + '<ul class="mdlist">' + (agentsList.length ? agentsList.map((k) => '<li class="mdrow" data-aid="' + esc(k.id) + '"><span class="grow"><b>' + esc(k.label) + '</b><small class="muted">' + (k.active ? 'connected until ' + esc(new Date(k.expires_at).toLocaleDateString('en', { day: 'numeric', month: 'short' })) : (k.revoked_at ? 'disconnected' : 'expired')) + (k.can_share ? ' · may share with the family' : ' · read and propose only') + ' · ' + k.calls_7d + ' calls this week</small></span>' + (k.active ? '<button class="btn ghost sm" data-disc type="button">Disconnect</button>' : '') + '</li>').join('') : '<li class="muted">None connected.</li>') + '</ul>'
      + '<form class="md-form" data-agent style="margin-top:10px"><label>Its name<input name="l" required maxlength="60" placeholder="Grok Bot"></label><label>Lasts (days)<input name="d" type="number" min="1" max="365" value="90"></label><label style="grid-column:1/-1"><span><input name="s" type="checkbox"> May share a note with the family</span></label><button class="btn sm" type="submit">Connect</button></form><div data-agent-out></div></section>' : '')
    + asst
    + teach
    + (d.role === 'guardian' ? '<section class="card pad"><h2>Product search</h2><p class="muted" style="font-size:12.5px">Shows real product options under a gift or reorder idea. It sends only the words for the thing (never a name) and your country to Shopify’s catalogue, and keeps nothing. Off unless you switch it on.</p><button class="btn ghost sm" data-shopsw type="button" style="margin-top:8px">' + (shop.enabled ? 'Switch off' : 'Switch on') + '</button></section>' : '')
    + (d.role === 'guardian' ? '<section class="card pad"><h2>Balance</h2><p class="muted" style="font-size:12.5px">A private word to whoever has closed most of one kind of thing lately, offering to hand the next to someone else. Off unless you switch it on.</p><button class="btn ghost sm" data-balsw type="button" style="margin-top:8px">' + (bal.enabled ? 'Switch off' : 'Switch on') + '</button></section>' : '')
    + (load.length > 1 ? '<section class="card pad"><h2>Who is carrying what</h2><p class="muted" style="font-size:12.5px">Open hand-offs and what each adult closed in the last 30 days. Plain counts, to talk about, not a score.</p><ul class="mdlist">' + load.map((w) => '<li class="mdrow"><span class="grow"><b>' + esc(w.name) + '</b><small class="muted">' + w.open + ' open · ' + w.handled_30d + ' closed in 30 days</small></span></li>').join('') + '</ul></section>' : '')
    + (hl.available ? '<section class="card pad"><h2>My body</h2>' + (hl.sync ? '<p style="margin-top:6px">' + esc(hl.line || 'Nothing has arrived from the Health app yet.') + '</p><a class="btn ghost sm" href="#/space/health" style="text-decoration:none;margin-top:8px">See my charts</a>' : '<p class="muted" style="margin-top:6px">Off. Switch on Health device data in the phone app, on the Family tab.</p>') + '</section>' : '')
    + '</div>';
  main.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', async () => {
    const li = b.closest('[data-key]');
    try { await api('/suggestions/' + encodeURIComponent(li.dataset.key) + '/accept', { method: 'POST', json: {} }); flash('Added to to-dos.'); myDayView(main); } catch (err) { flash(err.message || 'Could not add it.', true); }
  }));
  main.querySelectorAll('[data-no]').forEach((b) => b.addEventListener('click', async () => {
    const li = b.closest('[data-key]');
    try { await api('/suggestions/' + encodeURIComponent(li.dataset.key) + '/dismiss', { method: 'POST' }); myDayView(main); } catch (err) { flash(err.message || 'Could not dismiss it.', true); }
  }));
  main.querySelectorAll('[data-find]').forEach((b) => b.addEventListener('click', async () => {
    const li = b.closest('[data-key]'); const out = li.querySelector('[data-shop]'); li.style.flexWrap = 'wrap';
    if (out.innerHTML) { out.innerHTML = ''; return; }
    out.innerHTML = '<p class="muted" style="font-size:12.5px">Looking…</p>';
    try {
      const r = await api('/shop/search?suggestion=' + encodeURIComponent(li.dataset.key));
      out.innerHTML = (r.error ? '<p class="muted">' + esc(r.error) + '</p>' : '') + (r.messages || []).map((m) => '<p class="muted" style="font-size:12px">' + esc(m) + '</p>').join('')
        + '<ul class="mdlist">' + r.products.map((x) => '<li class="mdrow">' + (x.image_url ? '<img src="' + esc(x.image_url) + '" alt="" referrerpolicy="no-referrer" loading="lazy" style="width:44px;height:44px;object-fit:cover;border-radius:8px">' : '')
          + '<span class="grow"><a href="' + esc(x.url) + '" target="_blank" rel="noopener">' + esc(x.title) + '</a><small class="muted">' + esc([x.seller && x.seller.name, x.price ? x.price.currency + ' ' + x.price.amount.toLocaleString('en') : '', x.rating ? x.rating.value + ' of ' + x.rating.scale_max + ' (' + x.rating.count + ' reviews)' : '', x.options, x.local === false ? 'check it ships to you' : '', x.available === false ? 'out of stock' : ''].filter(Boolean).join(' · ')) + '</small></span></li>').join('') + '</ul>'
        + '<p class="muted" style="font-size:12px;margin-top:6px">' + esc(r.note || '') + ' Nothing is bought here.</p>';
    } catch (err) { out.innerHTML = ''; flash(err.message || 'Could not search.', true); }
  }));
  main.querySelectorAll('[data-balno]').forEach((b) => b.addEventListener('click', async () => { try { await api('/me/balance/dismiss', { method: 'POST', json: { domain: b.dataset.balno } }); myDayView(main); } catch (err) { flash(err.message || 'Could not do that.', true); } }));
  main.querySelectorAll('[data-disc]').forEach((b) => b.addEventListener('click', async () => { try { await api('/me/agents/' + b.closest('[data-aid]').dataset.aid, { method: 'DELETE' }); myDayView(main); } catch (err) { flash(err.message || 'Could not disconnect.', true); } }));
  const af = main.querySelector('[data-agent]');
  if (af) af.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const r = await api('/me/agents', { method: 'POST', json: { label: af.l.value, days: +af.d.value, can_share: af.s.checked } });
      main.querySelector('[data-agent-out]').innerHTML = '<p style="margin-top:8px;font-size:13px">Shown once. In your assistant, add a custom MCP connector with this address and key:</p><input readonly value="' + esc(location.origin + '/mcp') + '" style="width:100%" data-select><input readonly value="' + esc(r.token) + '" style="width:100%;margin-top:6px" data-select><p class="muted" style="font-size:12px;margin-top:6px">It can: ' + esc(r.can.join('; ')) + '. A hosted assistant needs this server reachable from the internet.</p>';
    } catch (err) { flash(err.message || 'Could not connect it.', true); }
  });
  bindTeach(main);
  const ss = main.querySelector('[data-shopsw]'); if (ss) ss.addEventListener('click', async () => { try { await api('/household/shop-search', { method: 'PUT', json: { enabled: !shop.enabled } }); myDayView(main); } catch (err) { flash(err.message || 'Could not change it.', true); } });
  const bs = main.querySelector('[data-balsw]'); if (bs) bs.addEventListener('click', async () => { try { await api('/household/balance', { method: 'PUT', json: { enabled: !bal.enabled } }); myDayView(main); } catch (err) { flash(err.message || 'Could not change it.', true); } });
  const nr = main.querySelector('[data-newrule]');
  if (nr) {
    const sync = () => { nr.querySelectorAll('[data-for]').forEach((l) => { l.hidden = l.dataset.for !== nr.t.value; }); };
    nr.t.addEventListener('change', sync); sync();
    nr.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const body = { instruction: nr.i.value, trigger: nr.t.value, policy: nr.p.value };
      if (nr.t.value === 'time') body.hour = +nr.h.value; if (nr.t.value === 'trip_soon') body.trigger_days = +nr.n.value;
      try { await api('/routines', { method: 'POST', json: body }); flash('Added.'); myDayView(main); } catch (err) { flash(err.message || 'Could not add it.', true); }
    });
  }
  main.querySelectorAll('[data-pause]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/routines/' + b.closest('[data-rid]').dataset.rid + '/pause', { method: 'PUT', json: { paused: !b.dataset.paused } }); myDayView(main); } catch (err) { flash(err.message || 'Could not change it.', true); }
  }));
  main.querySelectorAll('[data-hist]').forEach((b) => b.addEventListener('click', async () => {
    const li = b.closest('[data-rid]'); const out = li.querySelector('[data-hout]');
    if (out.innerHTML) { out.innerHTML = ''; return; }
    try {
      const h = await api('/routines/' + li.dataset.rid + '/history');
      out.innerHTML = h.length ? '<ol class="kn-steps">' + h.map((x) => '<li>' + esc(new Date(x.ran_at).toLocaleString('en', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })) + ' · ' + esc(outcomeWord[x.outcome] || x.outcome) + (x.said ? ': ' + esc(x.said.slice(0, 160)) : '') + '</li>').join('') + '</ol>' : '<p class="muted" style="font-size:12.5px">It has not run yet.</p>';
    } catch (err) { flash(err.message || 'Could not load the history.', true); }
  }));
  main.querySelectorAll('[data-stop]').forEach((b) => b.addEventListener('click', async () => {
    try { await api('/routines/' + b.closest('[data-rid]').dataset.rid, { method: 'DELETE' }); myDayView(main); } catch (err) { flash(err.message || 'Could not stop it.', true); }
  }));
  const forget = main.querySelector('[data-forget]');
  if (forget) forget.addEventListener('click', async () => { try { await api('/me/learned', { method: 'DELETE' }); myDayView(main); } catch (err) { flash(err.message || 'Could not clear it.', true); } });
  main.querySelector('[data-open-profile]').addEventListener('click', () => openMemberProfile(store.me.id));
}

/* Our family: the constellation. */
/* Health device data on the Family page: whether your phone sends its daily Health summary (the Health app, which holds the
   Apple Watch's numbers). Switching on needs the phone, which alone can read Health; switching off, and deleting, works here. */
async function loadHealthDeviceCard(el) {
  if (!el || !store.me || store.me.role === 'child') return;
  let st; try { st = await api('/health/sync'); } catch (e) { return; }
  if (!st.available) return;
  el.innerHTML = '<section class="card pad" style="margin-top:14px"><div class="row wrap" style="gap:10px;align-items:center">'
    + '<span class="ic h-health" style="width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:var(--health-tint);color:var(--health)">' + icon('health', 18) + '</span>'
    + '<div><h2 style="font-size:15px">Health device data</h2><span class="muted" style="font-size:12.5px">' + (st.sync ? 'On' + (st.last_day ? ' · latest day ' + esc(fmtDate(st.last_day).replace(/,.*$/, '')) : '') : 'Off') + '</span></div>'
    + '<span class="grow"></span>' + (st.sync ? '<a class="btn ghost sm" href="#/space/health" style="text-decoration:none">See your charts</a><button class="btn ghost sm" data-hd-off type="button">Switch off and delete</button>' : '') + '</div>'
    + '<p class="muted" style="margin-top:8px;font-size:13px">Steps, sleep, resting heart rate and workouts from the Health app and your Apple Watch. One summary a day, only yours, never medical advice.'
    + (st.sync ? '' : ' To switch it on, open the FamilyOS app on your iPhone, go to <b>Family</b> and turn on <b>Health device data</b>; only the phone can read Health.') + '</p></section>';
  const off = el.querySelector('[data-hd-off]');
  if (off) off.addEventListener('click', async () => {
    if (!window.confirm('Delete your Health summary from FamilyOS and stop syncing?')) return;
    try { await api('/health/sync', { method: 'PUT', json: { sync: false } }); loadHealthDeviceCard(el); } catch (err) { flash(err.message || 'Could not switch it off.', true); }
  });
}
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
    + '<div data-offers></div><div data-health-device></div>';
  main.querySelectorAll('[data-person]').forEach((p) => p.addEventListener('click', () => openPerson(p.dataset.person)));
  loadOffersCard(main.querySelector('[data-offers]'));
  loadHealthDeviceCard(main.querySelector('[data-health-device]'));
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
    + documentsCard()
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
/* Your own Health numbers on the Health page: the last two weeks of steps, sleep and resting heart rate, from the phone's
   Health app (which holds the Apple Watch's data). Only the signed-in member's own; switching on needs the phone, switching off is here. */
async function healthData() {
  try { const st = await api('/health/sync'); if (!st.available) return null; return { sync: st.sync, rows: st.sync ? await api('/health/daily?days=14') : [] }; }
  catch (e) { return null; }
}
function healthChart(title, unit, rows, pick, fmt, bars) {
  const days = rows.slice().reverse();                       // oldest first
  const vals = days.map(pick);
  const have = vals.filter((v) => v != null);
  if (!have.length) return '';
  const W = 300, H = 76, pad = 6, n = days.length;
  const mean = have.reduce((a, b) => a + b, 0) / have.length;
  const lo = bars ? 0 : Math.min(...have) - 4, hi = Math.max(...have) + (bars ? 0 : 4) || 1;
  const x = (i) => pad + (n === 1 ? (W - 2 * pad) / 2 : i * (W - 2 * pad) / (n - 1));
  const y = (v) => H - pad - ((v - lo) / ((hi - lo) || 1)) * (H - 2 * pad);
  let g = '<line x1="' + pad + '" x2="' + (W - pad) + '" y1="' + y(mean).toFixed(1) + '" y2="' + y(mean).toFixed(1) + '" stroke="var(--ink-3)" stroke-opacity=".5" stroke-dasharray="3 3"/>';
  if (bars) {
    const bw = Math.max(4, (W - 2 * pad) / n - 5);
    g += vals.map((v, i) => v == null ? '' : '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + y(v).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + Math.max(1, H - pad - y(v)).toFixed(1) + '" rx="3" fill="var(--primary)" opacity=".9"><title>' + esc(fmtDate(days[i].day).replace(/,.*$/, '')) + ': ' + fmt(v) + '</title></rect>').join('');
  } else {
    const pts = vals.map((v, i) => v == null ? null : [x(i), y(v)]).filter(Boolean);
    g += '<polyline points="' + pts.map((q) => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ') + '" fill="none" stroke="var(--primary)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
      + pts.map((q) => '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="2.6" fill="var(--primary)"/>').join('');
  }
  return '<div class="hx"><div class="hx-h"><b>' + esc(title) + '</b><span>' + fmt(mean) + ' ' + esc(unit) + ', average</span></div>'
    + '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(title) + ', last two weeks, average ' + esc(fmt(mean)) + ' ' + esc(unit) + '" preserveAspectRatio="none">' + g + '</svg>'
    + '<div class="hx-x"><span>' + esc(fmtDate(days[0].day).replace(/,.*$/, '')) + '</span><span>' + esc(fmtDate(days[n - 1].day).replace(/,.*$/, '')) + '</span></div></div>';
}
function healthCard(h) {
  if (!h) return '';
  if (!h.sync) return '<section class="card pad"><h2>Your body</h2><p class="muted" style="margin-top:6px">Steps, sleep and resting heart rate from your iPhone’s Health app and Apple Watch. Switch on <b>Health device data</b> on the Family tab of the phone app; only you can see it.</p></section>';
  const charts = [
    healthChart('Steps', 'a day', h.rows, (r) => r.steps, (v) => Math.round(v).toLocaleString('en'), true),
    healthChart('Sleep', 'a night', h.rows, (r) => r.sleep_minutes == null ? null : r.sleep_minutes / 60, (v) => v.toFixed(1) + ' h', true),
    healthChart('Resting heart rate', 'bpm', h.rows, (r) => r.resting_hr, (v) => String(Math.round(v)), false),
  ].join('');
  return '<section class="card pad health-card"><div class="row wrap" style="gap:8px;align-items:baseline"><h2>Your body</h2><span class="muted" style="font-size:12px">last two weeks · only you see this · not advice</span>'
    + '<span class="grow"></span><button class="btn ghost sm" data-health-off type="button">Switch off and delete</button></div>'
    + (charts ? '<div class="hx-grid">' + charts + '</div>' : '<p class="muted" style="margin-top:8px">Nothing has arrived yet. Open the phone app, and check Health, Data Access that FamilyOS may read steps, sleep and heart rate.</p>') + '</section>';
}
/* School copilot on the School page: what each child needs tomorrow, the forms still to come back, an absence note to edit. */
async function schoolData() {
  try { const [day, forms] = await Promise.all([api('/school/tomorrow'), api('/school/forms')]); return { day, forms }; } catch (e) { return null; }
}
function schoolCards(d) {
  if (!d) return '';
  const kids = d.day.children || [];
  const tomorrow = '<section class="card pad"><h2>Tomorrow at school</h2><span class="muted" style="font-size:12.5px">' + esc(fmtDate(d.day.date)) + '</span>'
    + (kids.length ? kids.map((k) => '<div class="sc-kid"><b>' + esc(k.child) + '</b>' + (k.class ? '<span class="muted"> · class ' + esc(k.class) + '</span>' : '')
      + '<ul class="mdlist">' + k.items.map((i) => '<li class="mdrow"><span class="grow"><a href="#/notices/' + esc(i.artifact_id) + '">' + esc(i.title) + '</a><small class="muted">' + esc({ form: 'a form', pay: 'a payment', event: 'an event', note: 'to know' }[i.kind] || '') + (i.time ? ' · ' + esc(i.time) : '') + (i.undecided ? ' · not yet accepted' : '') + '</small></span></li>').join('')
      + k.bring.map((b) => '<li class="mdrow"><span class="grow">' + esc(b) + '<small class="muted">to bring or wear</small></span></li>').join('') + '</ul></div>').join('')
      : '<p class="muted" style="margin-top:6px">Nothing is dated for tomorrow.</p>') + '</section>';
  const forms = d.forms || [];
  const formsHtml = '<section class="card pad"><h2>Forms to come back</h2>' + (forms.length ? '<ul class="mdlist">' + forms.map((f) => '<li class="mdrow"><span class="grow"><a href="#/notices/' + esc(f.artifact_id) + '">' + esc(f.title) + '</a>'
    + '<small class="muted">' + esc((f.child ? f.child + ' · ' : '') + (f.state === 'returned' ? 'returned' : (f.late ? 'late, was ' : 'by ') + fmtDate(f.due_date).replace(/,.*$/, '')) + (f.state === 'undecided' ? ' · not yet accepted' : '')) + '</small></span></li>').join('') + '</ul>'
    : '<p class="muted" style="margin-top:6px">No forms are waiting.</p>') + '</section>';
  const kidsList = members().filter((m) => m.role === 'child');
  const note = kidsList.length ? '<section class="card pad"><h2>Absence note</h2><span class="muted" style="font-size:12.5px">A draft to edit and send yourself. FamilyOS does not send it.</span>'
    + '<form class="md-form" data-absence style="margin-top:8px"><label>Child<select name="c">' + kidsList.map((k) => '<option value="' + esc(k.id) + '">' + esc(k.display_name) + '</option>').join('') + '</select></label>'
    + '<label>Date<input type="date" name="on" required value="' + esc(d.day.date) + '"></label><label style="grid-column:1/-1">Reason (optional)<input type="text" name="r" maxlength="200" placeholder="she has a fever"></label>'
    + '<button class="btn sm" type="submit">Draft</button></form><div data-note-out></div></section>' : '';
  return '<div class="md-grid" style="margin-bottom:14px;align-items:start">' + tomorrow + formsHtml + note + '</div>';
}
function wireSchool(main) {
  const f = main.querySelector('[data-absence]'); if (!f) return;
  f.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const n = await api('/school/absence-note', { method: 'POST', json: { child_id: f.c.value, on: f.on.value, reason: f.r.value || null } });
      const out = main.querySelector('[data-note-out]');
      out.innerHTML = '<textarea rows="9" style="width:100%;margin-top:10px" aria-label="Absence note">' + esc(n.body) + '</textarea><div class="row" style="gap:8px;margin-top:6px"><button class="btn ghost sm" data-copy type="button">Copy</button><span class="muted" style="font-size:12px">' + esc(n.subject) + '</span></div>';
      out.querySelector('[data-copy]').addEventListener('click', async () => { try { await navigator.clipboard.writeText(out.querySelector('textarea').value); flash('Copied.'); } catch (e) { out.querySelector('textarea').select(); } });
    } catch (err) { flash(err.message || 'Could not draft it.', true); }
  });
}
/* Prescriptions on the Health page: one block per person (the newest prescription's person first), each
   prescription newest first with its date, prescriber and medicines; finished ones fold away. */
function rxCard(r) {
  const chip = { refill: ['refill due', 'amber'], current: ['current', 'green'], finished: ['finished', ''] }[r.status] || ['', ''];
  return '<div style="padding:10px 0;border-top:1px solid var(--line-soft, rgba(128,128,128,.2))">'
    + '<div style="display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline"><a href="#/notices/' + esc(r.artifact_id) + '" style="font-weight:600">' + esc(fmtDate(r.date).replace(/,.*$/, '') + ' ' + String(r.date).slice(0, 4)) + '</a>'
    + '<span class="tag ' + chip[1] + '">' + chip[0] + '</span>'
    + '<button type="button" data-fix-rx="' + esc(r.artifact_id) + '" data-date="' + esc(String(r.date).slice(0, 10)) + '" data-clinic="' + esc(r.clinic || '') + '" style="margin-left:auto;background:none;border:0;padding:6px 0;font:inherit;font-size:12.5px;color:var(--muted, #888);text-decoration:underline;cursor:pointer">Edit</button></div>'
    + '<div style="margin-top:2px;font-size:13px">' + (r.clinic ? '<b style="font-weight:600">' + esc(r.clinic) + '</b>' : '<span class="muted">Clinic not read</span>')
    + (r.prescriber ? '<span class="muted"> · ' + esc(r.prescriber) + '</span>' : '') + '</div>'
    + r.medicines.map((md) => '<div style="margin-top:6px"><span>' + esc(md.drug) + '</span>' + (md.dose_text ? ' <span class="muted">· ' + esc(md.dose_text) + '</span>' : '')
      + '<div class="muted" style="font-size:12.5px">' + esc([md.times_per_day ? md.times_per_day + ' a day' : '', md.ends_on ? 'to ' + fmtDate(md.ends_on).replace(/,.*$/, '') : '', md.status === 'refill' ? 'refill due' : ''].filter(Boolean).join(' · ')) + '</div></div>').join('')
    + (r.from_picture ? '<div style="margin-top:6px;font-size:12.5px;color:var(--warn, #b7791f)">Read from handwriting: check the names and the date on the paper.</div>' : '') + '</div>';
}
/* "Edit" opens the date and the clinic in place; a new date moves every medicine of that prescription. */
function wireRxDates(root_) {
  root_.querySelectorAll('[data-fix-rx]').forEach((b) => b.addEventListener('click', () => {
    if (b.nextElementSibling && b.nextElementSibling.matches('[data-rx-form]')) return;
    const form = document.createElement('form'); form.dataset.rxForm = '1'; form.style.cssText = 'display:flex;gap:6px;align-items:center;flex-basis:100%;margin-top:6px';
    form.style.flexWrap = 'wrap';
    form.innerHTML = '<input type="date" name="d" required aria-label="The date on the prescription" value="' + esc(b.dataset.date) + '">'
      + '<input type="text" name="c" maxlength="160" placeholder="Clinic or hospital" aria-label="Clinic or hospital" value="' + esc(b.dataset.clinic) + '" style="flex:1 1 160px">'
      + '<select name="p" aria-label="Whose prescription is this"><option value="">Whose? (keep as is)</option>'
      + ((store.household && store.household.members) || []).map((m) => '<option value="' + esc(m.id) + '">' + esc(m.display_name) + '</option>').join('')
      + '</select><button class="btn sm" type="submit">Save</button>';
    b.after(form);
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try { await api('/prescriptions/' + b.dataset.fixRx, { method: 'PATCH', json: Object.assign({ date: form.d.value, clinic: form.c.value }, form.p.value ? { patient_member_id: form.p.value } : {}) }); render(); }
      catch (err) { flash(err.message || 'Could not change the date.', true); }
    });
  }));
}
function prescriptionsOf(g) {
  const live = g.prescriptions.filter((r) => r.status !== 'finished'); const done = g.prescriptions.filter((r) => r.status === 'finished');
  const shown = live.length ? live : done.slice(0, 1); const folded = live.length ? done : done.slice(1);
  return '<div style="margin-top:14px"><div style="display:flex;align-items:baseline;gap:8px"><b>' + esc(g.name || 'Not matched to a person') + '</b><span class="muted" style="font-size:12.5px">'
    + g.prescriptions.length + (g.prescriptions.length === 1 ? ' prescription' : ' prescriptions') + '</span></div>'
    + shown.map(rxCard).join('')
    + (folded.length ? '<details style="margin-top:4px"><summary class="muted" style="cursor:pointer;padding:6px 0;font-size:13px">Earlier, finished (' + folded.length + ')</summary>' + folded.map(rxCard).join('') + '</details>' : '') + '</div>';
}

async function spaceView(main, args) {
  main.classList.remove('chat-main');
  const key = args[0]; const sp = SPACES[key];
  if (sp && sp.onLife) { location.hash = '#/life'; return; }
  if (!sp) { main.innerHTML = '<div class="head"><div><h1>Not a space</h1></div></div>'; return; }
  const [notices, brief, mny, plans, accepted, meds] = await Promise.all([api('/inbox?days=90&limit=300').catch(() => []), api('/brief?limit=40').catch(() => ({ items: [] })), api('/money?days=120').catch(() => null), key === 'travel' ? api('/plans').catch(() => []) : [], api('/obligations?status=accepted&limit=100').catch(() => []), key === 'health' ? api('/prescriptions').catch(() => []) : []]);
  const mine = notices.filter((n) => spaceOfNotice(n) === key);
  const ids = new Set(mine.map((n) => n.id));
  const dated = comingUpFor(brief, accepted, (i) => i.artifact_id && ids.has(i.artifact_id));
  const spent = mny ? mny.charges.filter((c) => sp.categories.includes(c.category)) : [];
  const spentInr = spent.filter((c) => c.currency === 'INR').reduce((a, c) => a + c.amount, 0);
  const recurring = mny ? mny.recurring.filter((r) => sp.categories.includes(r.category)) : [];
  const hx = key === 'health' ? await healthData() : null;
  const sx = key === 'school' ? await schoolData() : null;
  const iconName = spaceIcon(key);
  const row = spaceRow(sp, iconName);
  main.innerHTML = '<div class="head"><div><div class="row" style="gap:12px"><span class="ic h-' + sp.hue + '" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center;background:var(--' + sp.hue + '-tint);color:var(--' + sp.hue + ')">' + icon(iconName, 20) + '</span><h1>' + esc(sp.label) + '</h1></div>'
    + '<p>' + mine.length + (mine.length === 1 ? ' notice' : ' notices') + ' · ' + dated.length + ' dated' + (spent.length ? ' · ' + spent.length + (spent.length === 1 ? ' charge' : ' charges') + ' in ' + mny.days + ' days' : '') + '</p></div></div>'
    + '<div class="home"><div class="stack" style="gap:16px">'
    + (dated.length ? '<section class="card pad"><h2>Coming up</h2><ul class="tl" style="margin-top:6px">' + dated.slice(0, 8).map((i) => '<li><span class="tm">' + esc(fmtDate(i.due_date).replace(/,.*$/, '')) + '</span><span class="dt ' + sp.hue + '"></span><span class="ic ' + sp.hue + '">' + icon(iconName, 14) + '</span><span><a class="what" href="#/notices/' + esc(i.artifact_id) + '" style="text-decoration:none">' + esc(i.title) + '</a><div class="who">' + esc(i.why) + (i.subject_name ? ' · ' + esc(i.subject_name) : '') + '</div>' + (i.pay_url ? '<div class="who">' + payLinks(i.pay_url, 'plain', i) + '</div>' : '') + '</span></li>').join('') + '</ul></section>' : '')
    + (key === 'health' ? healthCard(hx) : '')
    + (key === 'school' ? schoolCards(sx) : '')
    + (key === 'health' ? '<section class="card pad"><h2>Medicines</h2><span class="muted" style="font-size:12.5px">the doctor’s words, as written; not advice</span>'
      + (meds.length ? meds.map(prescriptionsOf).join('') : '<p class="muted" style="margin-top:6px">No prescription has been read yet. Share a photo of one and each medicine is kept here with its dose and the last day of the supply.</p>') + '</section>' : '')
    + (key === 'travel' ? '<section><div class="row wrap" style="gap:8px;margin-bottom:10px"><h2 style="font-size:15px;font-weight:600">Trips</h2><span class="grow"></span><a class="btn ghost sm" href="#/plans">Plan a trip</a></div>'
      + (plans.filter((p) => p.status !== 'dropped' && p.shape === 'trip').length ? '<div class="stack" style="gap:10px">' + plans.filter((p) => p.status !== 'dropped' && p.shape === 'trip').map(planCard).join('') + '</div>' : '<p class="muted">No trip planned yet. Ask “plan our Dubai trip” from the bar below.</p>') + '</section>' : '')
    + '<section class="card"><div class="pad" style="padding-bottom:8px"><h2>What arrived</h2></div>' + (mine.length ? mine.slice(0, 30).map(row).join('') : '<p class="muted pad">Nothing in this space yet.</p>') + '</section>'
    + '</div><aside class="stack" style="gap:14px">'
    + spaceRail(key, sp, mny)
    + '</aside></div>';
  wireRxDates(main);
  wireSchool(main);
  const hoff = main.querySelector('[data-health-off]');
  if (hoff) hoff.addEventListener('click', async () => { if (!window.confirm('Delete your Health summary from FamilyOS and stop syncing?')) return; try { await api('/health/sync', { method: 'PUT', json: { sync: false } }); render(); } catch (err) { flash(err.message || 'Could not switch it off.', true); } });
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
