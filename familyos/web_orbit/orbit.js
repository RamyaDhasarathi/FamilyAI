/* Orbit: the FamilyOS console as an ambient home with the household at the
   centre. Same API and the same sign-in as /app (the token lives in this
   origin's storage). It shows what the record says and offers only what the
   product does: read, propose, remind, hand over, and wait for a person. It
   never pays, books or moves money. */

import { Ambient, Field } from './avatar.js';
import * as D from './data.js';
import { icon } from './icons.js';

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

/* ── plumbing ─────────────────────────────────────────────────── */

const S = {
  token: readToken(), model: null, stage: 7, seg: 'adult', persona: null,
  layerEls: [], chat: [], chatOpen: false, afterPop: null, booted: false,
};

function readToken() { try { return localStorage.getItem('familyos.token'); } catch (e) { return null; } }
function writeToken(v) { try { if (v) localStorage.setItem('familyos.token', v); else localStorage.removeItem('familyos.token'); } catch (e) { /* private window */ } }

class ApiError extends Error {
  constructor(status, body) { super((body && (body.detail || body.error)) || ('HTTP ' + status)); this.status = status; this.body = body || {}; }
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers);
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  let body = opts.body;
  if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json); }
  const res = await fetch('/v1' + path, { method: opts.method || 'GET', headers, body });
  if (res.status === 204) return null;
  if (!res.ok) {
    const raw = await res.text();
    let parsed = null; try { parsed = raw ? JSON.parse(raw) : null; } catch (e) { parsed = { detail: raw }; }
    if (res.status === 401 && S.token) { S.token = null; writeToken(null); if (S.booted) showGate('You were signed out. Sign in again.'); }
    throw new ApiError(res.status, parsed);
  }
  if (opts.blob) return res.blob();
  const raw = await res.text();
  return raw ? JSON.parse(raw) : null;
}

let toastTimer = null;
function toast(msg, bad) {
  const el = $('#toast');
  el.textContent = msg; el.className = 'toast glass show' + (bad ? ' bad' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.className = 'toast glass'; }, 3200);
}

function payLinks(url, cls) {
  if (!url) return '';
  const a = (href, label) => '<a class="' + (cls || 'btn') + '" href="' + esc(href) + '" target="_blank" rel="noopener">' + label + ' ' + icon('link', 14) + '</a>';
  if (/^upi:\/\/pay\?/i.test(url)) return a(url, 'Open the pay link') + a('gpay://upi/pay?' + url.split('?')[1], 'Google Pay');
  return a(url, 'Open the pay link');
}

async function loadPics(root) {
  for (const img of $$('img[data-pic]', root)) {
    const id = img.dataset.pic; img.removeAttribute('data-pic');
    try { const blob = await api('/artifacts/' + id + '/picture', { blob: true }); img.src = URL.createObjectURL(blob); img.closest('.pic').classList.add('ready'); }
    catch (e) { const f = img.closest('.pic'); if (f) f.remove(); }
  }
}

/* ── the drawn layer and its loop ─────────────────────────────── */

const ambient = new Ambient($('#ambient'));
const field = new Field($('#fieldCanvas'));
let rafId = 0, last = 0, frameN = 0;

function tick(t) {
  rafId = 0;
  const dt = t - (last || t); last = t; frameN++;
  if (frameN % 2 === 0 || reducedQuery.matches) ambient.frame(t, dt * 2);
  const out = field.frame(t);
  placeOrbs(out);
  drawWave(t);
  if (!reducedQuery.matches && !document.hidden) rafId = requestAnimationFrame(tick);
}
function kick() { if (!rafId) rafId = requestAnimationFrame(tick); }
document.addEventListener('visibilitychange', () => { if (!document.hidden) { last = 0; kick(); } });
reducedQuery.addEventListener('change', () => { field.configure({ reduced: reducedQuery.matches }); kick(); });
window.addEventListener('resize', () => kick());
field.configure({ reduced: reducedQuery.matches });

function placeOrbs(out) {
  $$('#orbs .orb').forEach((el, i) => {
    const p = out.agents[i]; if (!p) return;
    el.style.transform = 'translate(' + p.x.toFixed(1) + 'px,' + p.y.toFixed(1) + 'px) scale(' + p.scale.toFixed(3) + ')';
    el.style.zIndex = p.depth > 0 ? 3 : 2;
  });
  $$('#orbs .note-orb').forEach((el, j) => {
    const p = out.notes[j]; if (!p) return;
    el.style.transform = 'translate(' + p.x.toFixed(1) + 'px,' + p.y.toFixed(1) + 'px) scale(' + (p.shown ? Math.min(1.15, 0.4 + p.p * 0.6).toFixed(3) : 0) + ')';
    el.style.opacity = p.shown ? Math.min(1, p.p * 1.6).toFixed(2) : 0;
  });
}

/* The waveform strip beside the FAB on the sheet: a quiet idle shimmer,
   livelier while the day is being read aloud. */
const wave = { bars: 26, el: null };
function drawWave(t) {
  const c = $('#wave'); if (!c || !document.body.classList.contains('sheet-open')) return;
  const ctx = c.getContext('2d'), dpr = Math.min(devicePixelRatio || 1, 2);
  const w = c.clientWidth, h = c.clientHeight; if (!w) return;
  if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  const gap = 84, half = (w - gap) / 2, n = 22, bw = half / n;
  const live = speech.active ? 1 : 0.35, s = reducedQuery.matches ? 0 : t / 1000;
  for (let side = 0; side < 2; side++) for (let i = 0; i < n; i++) {
    const k = side ? i : n - 1 - i; // taller towards the FAB
    const env = Math.pow((k + 1) / n, 1.6);
    const a = (0.25 + 0.75 * Math.abs(Math.sin(s * 3.1 + i * 0.7 + side) * Math.cos(s * 1.7 + i * 0.31))) * env * live;
    const bh = Math.max(2, a * h * 0.9);
    const x = side ? half + gap + i * bw : i * bw;
    const g = ctx.createLinearGradient(0, h / 2 - bh / 2, 0, h / 2 + bh / 2);
    g.addColorStop(0, 'rgba(120,140,255,0.9)'); g.addColorStop(1, 'rgba(210,90,255,0.9)');
    ctx.fillStyle = g; ctx.fillRect(x + bw * 0.3, h / 2 - bh / 2, Math.max(1, bw * 0.4), bh);
  }
}

/* ── who is looking ───────────────────────────────────────────── */

function applyStage() {
  const params = new URLSearchParams(location.search);
  const persona = params.get('persona');
  S.persona = persona && D.PERSONAS[persona] ? persona : null;
  S.stage = S.persona ? D.PERSONAS[S.persona] : D.stageFor(S.model && S.model.me, S.model ? S.model.today : D.localIso(new Date()));
  S.seg = D.segOf(S.stage);
  document.documentElement.dataset.stage = S.stage;
  document.documentElement.dataset.seg = S.seg;
  ambient.setSeg(S.seg);
}

/* ── home ─────────────────────────────────────────────────────── */

const ORB_ICON = { finance: 'finance', education: 'education', household: 'household', calendar: 'calendar', grocery: 'grocery' };
const REASON_WORD = { missed: 'went by undecided', overdue: 'date has passed', undecided: 'undecided', mailbox: 'mailbox not being read', needs_you: 'needs you', today: 'today', soon: 'soon' };

function orbLabel(key, a) {
  const info = D.AGENT[key];
  const parts = [info.label + ':'];
  parts.push(a.badge ? a.badge + (a.badge === 1 ? ' thing' : ' things') : 'nothing open');
  if (a.urgent) parts[1] += ', ' + a.urgent + ' past its date or needing a person';
  return parts.join(' ') + '. Opens ' + info.label + '.';
}

function renderHome() {
  const m = S.model;
  $('#brandName').textContent = 'FamilyOS';
  $('#podName').textContent = (m.me && m.me.display_name) || '';
  $('#podHouse').textContent = (m.household && m.household.name) || '';
  $('#pod').setAttribute('aria-label', 'Active pod: ' + (m.household && m.household.name) + ', ' + (m.me && m.me.display_name) + (S.persona ? ', previewing the ' + S.persona + ' view' : '') + '. Open the pod menu.');
  $('#personaTag').textContent = S.persona ? 'preview: ' + D.STAGE_NAMES[S.stage] : '';
  const orbs = $('#orbs');
  orbs.innerHTML = D.AGENTS.map((ag) => {
    const a = m.agents[ag.key];
    return '<button class="orb' + (a.tension ? ' tense' : '') + '" data-agent="' + ag.key + '" style="--c:' + ag.color + '" aria-label="' + esc(orbLabel(ag.key, a)) + '">'
      + '<span class="sphere">' + icon(ORB_ICON[ag.key], 22, 1.7) + (a.badge ? '<span class="badge">' + a.badge + '</span>' : '') + '</span>'
      + '<span class="orb-label">' + esc(ag.label) + '</span></button>';
  }).join('') + (S.seg === 'senior' ? '' : m.notes.map((n, j) => {
    const title = n.kind === 'errand' ? n.errand.title : n.item.title;
    return '<button class="note-orb" data-note="' + j + '" style="--c:' + n.color + '" aria-label="' + esc((REASON_WORD[n.reason] || n.reason) + ': ' + title + '. Open.') + '"><span class="note-core"></span></button>';
  }).join(''));
  field.configure({
    stage: S.stage, status: m.status,
    agents: D.AGENTS.map((ag) => ({ key: ag.key, color: ag.color, tension: m.agents[ag.key].tension, badge: m.agents[ag.key].badge })),
    notes: S.seg === 'senior' ? [] : m.notes.map((n) => ({ id: n.id, color: n.color })),
  });
  $$('#orbs .orb').forEach((b) => b.addEventListener('click', (ev) => { if (swallowClick(ev)) return; navigate('#/dashboard/' + b.dataset.agent, { via: true }); }));
  $$('#orbs .note-orb').forEach((b) => b.addEventListener('click', (ev) => { if (swallowClick(ev)) return; openNote(m.notes[Number(b.dataset.note)], b); }));
  $('#statusWord').textContent = { red: 'Something went by or needs a person', amber: 'Some things wait for a decision', calm: 'Nothing waits on you' }[m.status];
  $('#statusWord').dataset.tone = m.status;
  renderSeniorCard();
  kick();
}

/* Older adults: no orbit for alerts; one large card, one action. */
let seniorIdx = 0;
function renderSeniorCard() {
  const box = $('#noteCard');
  const m = S.model;
  if (S.seg !== 'senior') { box.hidden = true; return; }
  box.hidden = false;
  const list = m.notesAll;
  if (!list.length) { box.innerHTML = '<p class="nc-kicker">All quiet</p><h2 class="nc-title">Nothing needs you right now.</h2>'; return; }
  seniorIdx = seniorIdx % list.length;
  const n = list[seniorIdx];
  const i = n.item || {};
  const title = n.kind === 'errand' ? n.errand.title : i.title;
  const when = i.due_date ? D.fmtDay(i.due_date, m.today) + (D.cleanTime(i.due_time) ? ', ' + D.cleanTime(i.due_time) : '') : '';
  let action = '';
  if (n.kind === 'errand') action = '<a class="btn primary big" href="/app/#/errands/' + esc(n.errand.id) + '">Open the errand</a>';
  else if (i.status === 'proposed' && i.obligation_id) action = '<button class="btn primary big" data-decide="accepted" data-id="' + esc(i.obligation_id) + '">Accept</button>';
  else if (i.pay_url) action = payLinks(i.pay_url, 'btn primary big').split('</a>')[0] + '</a>';
  else if (i.artifact_id) action = '<button class="btn primary big" data-notice="' + esc(i.artifact_id) + '">Read the notice</button>';
  box.innerHTML = '<p class="nc-kicker">' + esc(REASON_WORD[n.reason] || n.reason) + (list.length > 1 ? ' · ' + (seniorIdx + 1) + ' of ' + list.length : '') + '</p>'
    + '<h2 class="nc-title">' + esc(title) + '</h2>'
    + (when || i.subject ? '<p class="nc-when">' + esc([when, i.subject].filter(Boolean).join(' · ')) + '</p>' : '')
    + (i.why ? '<p class="nc-why">' + esc(cap(i.why)) + '.</p>' : '')
    + '<div class="nc-actions">' + action + (list.length > 1 ? '<button class="btn plain big" data-next>Next</button>' : '') + '</div>';
  wireDecisions(box);
  const nx = $('[data-next]', box); if (nx) nx.addEventListener('click', () => { seniorIdx++; renderSeniorCard(); });
}
function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }

/* ── the localized modal for an orbital notification ──────────── */

let modalReturn = null;
function openNote(n, from) {
  const m = S.model;
  const root = $('#modalRoot');
  const ag = D.catInfo(n.agent);
  let body = '';
  if (n.kind === 'errand') {
    const e = n.errand;
    const steps = (e.outcome && e.outcome.steps) || [];
    body = '<p class="mm-kicker" style="color:' + ag.color + '">' + esc(ag.label) + ' · needs you</p><h2 class="mm-title">' + esc(e.title) + '</h2>'
      + '<p class="mm-why">The errand stopped and is waiting for a person to take over.' + (steps.length ? ' Last step: “' + esc(steps[steps.length - 1].said) + '”' : '') + '</p>'
      + '<div class="mm-actions"><a class="btn primary" href="/app/#/errands/' + esc(e.id) + '">Open the errand</a></div>';
  } else {
    const i = n.item;
    const when = i.due_date ? D.fmtDay(i.due_date, m.today) + (D.cleanTime(i.due_time) ? ', ' + D.cleanTime(i.due_time) : '') : '';
    const acts = [];
    if (i.status === 'proposed' && i.obligation_id) acts.push('<button class="btn primary" data-decide="accepted" data-id="' + esc(i.obligation_id) + '">Accept</button>', '<button class="btn" data-decide="dismissed" data-id="' + esc(i.obligation_id) + '">Not this</button>');
    if (i.pay_url) acts.push(payLinks(i.pay_url, 'btn'));
    if (i.artifact_id) acts.push('<button class="btn plain" data-notice="' + esc(i.artifact_id) + '">Read the notice</button>');
    if (i.reason === 'mailbox') acts.push('<a class="btn" href="/app/#/household">Reconnect in FamilyOS</a>');
    body = '<p class="mm-kicker" style="color:' + ag.color + '">' + esc(ag.label) + ' · ' + esc(REASON_WORD[i.reason] || i.reason) + '</p>'
      + '<h2 class="mm-title">' + esc(i.title) + '</h2>'
      + '<dl class="mm-facts">' + (when ? '<div><dt>Date</dt><dd>' + esc(when) + (i.when ? ' (' + esc(i.when) + ')' : '') + '</dd></div>' : '')
      + (i.subject ? '<div><dt>For</dt><dd>' + esc(i.subject) + '</dd></div>' : '')
      + '<div><dt>Status</dt><dd>' + esc(i.status === 'proposed' ? 'Proposed by me, not yet decided' : i.status === 'accepted' ? 'Accepted' + (i.handled_by_name ? ', handled by ' + i.handled_by_name : '') : i.status || '') + '</dd></div></dl>'
      + (i.why ? '<p class="mm-why">' + esc(cap(i.why)) + '.</p>' : '')
      + (i.action === 'pay' ? '<p class="mm-note">' + (i.pay_url ? 'The link opens the biller’s own page; you pay there. FamilyOS never pays.' : 'A reminder only. FamilyOS never pays.') + '</p>' : '')
      + '<div class="mm-actions">' + acts.join('') + '</div>';
  }
  root.innerHTML = '<div class="scrim" data-close></div><div class="modal glass" role="dialog" aria-modal="true" aria-labelledby="mmTitle" style="--c:' + ag.color + '">'
    + '<button class="icon-btn mm-close" data-close aria-label="Close">' + icon('close', 18) + '</button>' + body + '</div>';
  const modal = $('.modal', root);
  $('.mm-title', modal).id = 'mmTitle';
  // Localized: grow out of the orb that was tapped, stay on screen.
  const r = from ? from.getBoundingClientRect() : { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };
  const mw = Math.min(360, innerWidth - 24);
  modal.style.width = mw + 'px';
  const ox = r.left + r.width / 2, oy = r.top + r.height / 2;
  const mh = modal.offsetHeight;
  let left = Math.min(Math.max(12, ox - mw / 2), innerWidth - mw - 12);
  let top = oy + 28; if (top + mh > innerHeight - 12) top = Math.max(12, oy - mh - 28);
  modal.style.left = left + 'px'; modal.style.top = top + 'px';
  modal.style.transformOrigin = (ox - left) + 'px ' + (oy - top) + 'px';
  root.classList.add('open');
  modalReturn = from || null;
  requestAnimationFrame(() => modal.classList.add('in'));
  $$('[data-close]', root).forEach((b) => b.addEventListener('click', closeModal));
  wireDecisions(modal);
  const first = $('.mm-actions .btn, .mm-close', modal); if (first) first.focus();
}
function closeModal() {
  const root = $('#modalRoot');
  if (!root.classList.contains('open')) return false;
  root.classList.remove('open'); root.innerHTML = '';
  if (modalReturn && document.body.contains(modalReturn)) modalReturn.focus();
  modalReturn = null;
  return true;
}

/* Accept / Not this, and "read the notice", wherever they appear. */
function wireDecisions(scope) {
  $$('[data-decide]', scope).forEach((b) => b.addEventListener('click', async () => {
    b.disabled = true;
    try {
      await api('/obligations/' + b.dataset.id + '/decision', { method: 'POST', json: { status: b.dataset.decide } });
      toast(b.dataset.decide === 'accepted' ? 'Accepted. It is on the family’s list now.' : 'Dismissed. I will not remind anyone about it.');
      closeModal();
      await refresh();
    } catch (err) { b.disabled = false; toast(err.message || 'That did not go through.', true); }
  }));
  $$('[data-notice]', scope).forEach((b) => b.addEventListener('click', () => {
    closeModal();
    const cur = currentLayers();
    const base = cur.length ? hashFor(cur) : '#/dashboard';
    navigate(base + '/notice/' + b.dataset.notice, { via: !cur.length });
  }));
}

/* ── routes: #/dashboard, #/dashboard/<space>, …/notice/<id> ───── */

function parseHash(h) {
  const parts = (h || '').replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts[0] !== 'dashboard') return [];
  const layers = [{ kind: 'root' }];
  for (let i = 1; i < parts.length; i++) {
    if (parts[i] === 'notice' && parts[i + 1]) { layers.push({ kind: 'notice', id: parts[i + 1] }); i++; }
    else layers.push({ kind: 'cat', cat: parts[i] });
  }
  return layers;
}
function hashFor(layers) {
  if (!layers.length) return '#/';
  return '#/dashboard' + layers.slice(1).map((l) => (l.kind === 'notice' ? '/notice/' + l.id : '/' + l.cat)).join('');
}
function currentLayers() { return parseHash(location.hash); }
function urlFor(hash) { return location.pathname + location.search + hash; }

/* via: also push the dashboard root first, so back from a space opened
   straight from an orb lands on the bento, not on home. */
function navigate(hash, opts = {}) {
  const floor = (history.state && history.state.floor) || 0;
  if (opts.replace) history.replaceState({ orbit: 1, depth: parseHash(hash).length, floor: opts.floor !== undefined ? opts.floor : floor }, '', urlFor(hash));
  else {
    if (opts.via && currentLayers().length === 0) history.pushState({ orbit: 1, depth: 1, floor }, '', urlFor('#/dashboard'));
    history.pushState({ orbit: 1, depth: parseHash(hash).length, floor }, '', urlFor(hash));
  }
  applyRoute();
}

/* Escape to a depth: back through our own entries, then replace whatever
   was entered directly (a pasted deep link has nothing behind it). */
function retreat(target) {
  const d = currentLayers().length;
  if (d <= target) return;
  const floor = (history.state && history.state.floor) || 0;
  const steps = d - Math.max(target, floor);
  const finish = () => {
    if (currentLayers().length > target) navigate(hashFor(currentLayers().slice(0, target)), { replace: true, floor: Math.min(floor, target) });
  };
  if (steps > 0) { S.afterPop = finish; history.go(-steps); } else finish();
}
window.addEventListener('popstate', () => { applyRoute(); const f = S.afterPop; S.afterPop = null; if (f) f(); });
window.addEventListener('hashchange', () => applyRoute());

function applyRoute() {
  if (!S.model) return;
  const layers = currentLayers();
  setSheet(layers.length > 0);
  syncLayers(layers);
}

/* ── the sheet ────────────────────────────────────────────────── */

const appEl = $('#app');
function setP(p) { appEl.style.setProperty('--p', p.toFixed(4)); }
function setSheet(open) {
  const was = document.body.classList.contains('sheet-open');
  document.body.classList.toggle('sheet-open', open);
  appEl.classList.remove('dragging');
  setP(open ? 1 : 0);
  $('#home').inert = open;
  $('#sheet').inert = !open;
  $('#sheet').setAttribute('aria-hidden', String(!open));
  $('#sliver').tabIndex = open ? 0 : -1;
  if (open && !was) { closeModal(); setTimeout(() => { const c = $('#crumbs'); if (c) c.focus({ preventScroll: true }); }, 60); }
  if (!open && was) { $('#openDash').focus({ preventScroll: true }); }
  kick();
}

function layerKey(l) { return l.kind === 'root' ? 'root' : l.kind === 'notice' ? 'notice:' + l.id : 'cat:' + l.cat; }
function layerTitle(l) {
  if (l.kind === 'root') return 'Dashboard';
  if (l.kind === 'notice') return 'Notice';
  return D.catInfo(l.cat).label;
}

function syncLayers(target) {
  const box = $('#layers');
  const els = S.layerEls;
  let k = 0;
  while (k < els.length && k < target.length && els[k].key === layerKey(target[k])) k++;
  // Leave to the right.
  for (let i = els.length - 1; i >= k; i--) {
    const el = els[i].el; el.classList.remove('is-active', 'is-behind'); el.classList.add('is-leaving');
    setTimeout(() => el.remove(), reducedQuery.matches ? 0 : 380);
  }
  S.layerEls = els.slice(0, k);
  // Enter from the right.
  for (let i = k; i < target.length; i++) {
    const el = document.createElement('div');
    el.className = 'layer is-entering' + (target[i].kind === 'root' ? ' root' : '');
    el.setAttribute('role', 'region');
    el.setAttribute('aria-label', layerTitle(target[i]));
    box.appendChild(el);
    S.layerEls.push({ key: layerKey(target[i]), el, spec: target[i] });
    renderLayer(target[i], el);
    requestAnimationFrame(() => requestAnimationFrame(() => el.classList.remove('is-entering')));
  }
  S.layerEls.forEach((x, i) => {
    const active = i === S.layerEls.length - 1;
    x.el.classList.toggle('is-active', active);
    x.el.classList.toggle('is-behind', !active);
    x.el.inert = !active;
  });
  const crumbs = $('#crumbs');
  crumbs.innerHTML = target.map((l, i) => '<span' + (i === target.length - 1 ? ' aria-current="page"' : '') + '>' + esc(layerTitle(l)) + '</span>').join('<span class="sep" aria-hidden="true">/</span>');
  $('#bentoBtn').disabled = target.length <= 1;
  const deep = target.length > 1;
  document.body.classList.toggle('deep', deep);
  const top = target[target.length - 1];
  updateDock(top && top.kind === 'cat' ? top.cat : top && top.kind === 'notice' ? 'notice' : null);
}

function rerenderLayers() { S.layerEls.forEach((x) => renderLayer(x.spec, x.el)); }

/* ── gestures: swipe up from home, pull down on the handle ───── */

let drag = null, suppressClick = false;
function swallowClick(ev) { if (suppressClick) { ev.preventDefault(); ev.stopPropagation(); suppressClick = false; return true; } return false; }
function sheetPx() { return innerHeight * 0.9; }

$('#home').addEventListener('pointerdown', (ev) => {
  if (ev.button !== 0 || document.body.classList.contains('sheet-open') || S.chatOpen) return;
  drag = { y: ev.clientY, t: performance.now(), mode: 'up', moved: false, id: ev.pointerId };
});
$('#grip').addEventListener('pointerdown', (ev) => {
  if (ev.button !== 0) return;
  drag = { y: ev.clientY, t: performance.now(), mode: 'down', moved: false, id: ev.pointerId };
  try { $('#grip').setPointerCapture(ev.pointerId); } catch (e) { /* fine */ }
});
window.addEventListener('pointermove', (ev) => {
  if (!drag || ev.pointerId !== drag.id) return;
  const dy = ev.clientY - drag.y;
  if (!drag.moved && Math.abs(dy) > 10) { drag.moved = true; appEl.classList.add('dragging'); }
  if (!drag.moved) return;
  if (drag.mode === 'up') setP(Math.max(0, Math.min(1, -dy / sheetPx())));
  else setP(Math.max(0, Math.min(1, 1 - dy / sheetPx())));
});
window.addEventListener('pointerup', (ev) => {
  if (!drag || ev.pointerId !== drag.id) return;
  const dy = ev.clientY - drag.y, v = dy / Math.max(1, performance.now() - drag.t);
  const d = drag; drag = null;
  appEl.classList.remove('dragging');
  if (!d.moved) { if (d.mode === 'down') retreat(0); return; }
  suppressClick = true; setTimeout(() => { suppressClick = false; }, 300);
  if (d.mode === 'up') { if (-dy > 70 || v < -0.5) navigate('#/dashboard'); else setP(0); }
  else { if (dy > 80 || v > 0.5) retreat(0); else setP(1); }
});
window.addEventListener('pointercancel', () => { if (drag) { drag = null; appEl.classList.remove('dragging'); applyRoute(); } });
$('#home').addEventListener('wheel', (ev) => { if (ev.deltaY > 40 && !document.body.classList.contains('sheet-open') && !S.chatOpen) navigate('#/dashboard'); }, { passive: true });
$('#openDash').addEventListener('click', (ev) => { if (swallowClick(ev)) return; navigate('#/dashboard'); });
$('#sliver').addEventListener('click', () => retreat(0));
$('#bentoBtn').addEventListener('click', () => retreat(1));
$('#grip').addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); retreat(0); } });
document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape') return;
  if (closeModal()) return;
  if (!$('#podMenu').hidden) { togglePod(false); return; }
  if (speech.active || !$('#speech').hidden) { stopSpeech(); return; }
  if (S.chatOpen) { setChat(false); return; }
  if (currentLayers().length) history.back();
});

/* ── the pod menu (who is active, and previews) ───────────────── */

function togglePod(open) {
  const menu = $('#podMenu');
  open = open === undefined ? menu.hidden : open;
  menu.hidden = !open;
  $('#pod').setAttribute('aria-expanded', String(open));
  if (!open) return;
  const m = S.model;
  const roles = { guardian: 'guardian', adult: 'adult', child: 'child' };
  const here = new URLSearchParams(location.search);
  const link = (p) => { const q = new URLSearchParams(here); if (p) q.set('persona', p); else q.delete('persona'); const s = q.toString(); return location.pathname + (s ? '?' + s : ''); };
  menu.innerHTML = '<p class="pm-h">In this pod</p><ul class="pm-people">' + m.members.map((x) => '<li' + (x.id === m.me.id ? ' class="me"' : '') + '><span class="dot" aria-hidden="true">' + esc(x.display_name.charAt(0)) + '</span>' + esc(x.display_name) + '<small>' + esc(roles[x.role] || x.role) + (x.id === m.me.id ? ' · signed in' : '') + '</small></li>').join('') + '</ul>'
    + '<p class="pm-h">See Orbit as</p><div class="pm-personas">' + [['', 'Me'], ['toddler', '3–5'], ['child', '6–8'], ['preteen', '9–12'], ['teen', '13–15'], ['lateteen', '16–18'], ['young', '19–25'], ['adult', '26–59'], ['senior', '60+']]
      .map(([p, l]) => '<a href="' + esc(link(p)) + '"' + ((S.persona || '') === p ? ' aria-current="true"' : '') + '>' + l + '</a>').join('') + '</div>'
    + '<div class="pm-foot"><a href="/app/">Open the full app</a><button type="button" data-signout>Sign out</button></div>';
  $('[data-signout]', menu).addEventListener('click', async () => { try { await api('/signout', { method: 'POST' }); } catch (e) { /* gone already */ } S.token = null; writeToken(null); location.href = location.pathname; });
}
$('#pod').addEventListener('click', (ev) => { ev.stopPropagation(); togglePod(); });
document.addEventListener('click', (ev) => { const menu = $('#podMenu'); if (!menu.hidden && !menu.contains(ev.target) && ev.target !== $('#pod')) togglePod(false); });

/* ── bento roots ──────────────────────────────────────────────── */

function card(cat, cls, inner, opts = {}) {
  const info = D.catInfo(cat);
  const tag = opts.static ? 'div' : 'button';
  return '<' + tag + ' class="bento ' + cls + '" style="--c:' + (opts.color || info.color) + '"' + (opts.static ? '' : ' data-open="' + esc(opts.to || cat) + '"')
    + (opts.label ? ' aria-label="' + esc(opts.label) + '"' : '') + '>' + inner + '</' + tag + '>';
}
function head(title, sub, badge) {
  return '<span class="b-head"><span class="b-title">' + esc(title) + '</span>' + (badge ? '<span class="b-badge">' + esc(badge) + '</span>' : '') + '</span>' + (sub ? '<span class="b-sub">' + sub + '</span>' : '');
}

function sparkSvg(vals, w, h, color, area) {
  if (!vals.length || vals.every((v) => !v)) return '<svg class="spark empty" viewBox="0 0 ' + w + ' ' + h + '" aria-hidden="true"><line x1="0" y1="' + (h - 2) + '" x2="' + w + '" y2="' + (h - 2) + '" stroke="' + color + '" stroke-opacity=".3" stroke-dasharray="2 4"/></svg>';
  // Square root keeps one large purchase from flattening every other week.
  const sv = vals.map((v) => Math.sqrt(Math.max(0, v)));
  const max = Math.max(...sv) || 1;
  const pts = sv.map((v, i) => [(i / (sv.length - 1)) * w, h - 3 - (v / max) * (h - 8)]);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const id = 'g' + Math.random().toString(36).slice(2, 8);
  const lastP = pts[pts.length - 1];
  return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + color + '" stop-opacity=".45"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/></linearGradient>'
    + '<filter id="' + id + 'f" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="2.2"/></filter></defs>'
    + (area ? '<path d="' + d + ' L' + w + ' ' + h + ' L0 ' + h + 'Z" fill="url(#' + id + ')"/>' : '')
    + '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="3" opacity=".55" filter="url(#' + id + 'f)"/>'
    + '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="1.6" stroke-linejoin="round"/>'
    + '<circle cx="' + lastP[0].toFixed(1) + '" cy="' + lastP[1].toFixed(1) + '" r="2.6" fill="#fff"/></svg>';
}

function ring(frac, color, size, center, track) {
  const r = (size - 10) / 2, c = 2 * Math.PI * r, f = Math.max(0, Math.min(1, frac || 0));
  return '<span class="ring" style="width:' + size + 'px;height:' + size + 'px;--rc:' + color + '"><svg viewBox="0 0 ' + size + ' ' + size + '" aria-hidden="true">'
    + '<circle cx="' + size / 2 + '" cy="' + size / 2 + '" r="' + r + '" fill="none" stroke="' + (track || 'rgba(255,255,255,.1)') + '" stroke-width="6"/>'
    + (f > 0 ? '<circle cx="' + size / 2 + '" cy="' + size / 2 + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="6" stroke-linecap="round" stroke-dasharray="' + (c * f).toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 ' + size / 2 + ' ' + size / 2 + ')"/>' : '')
    + '</svg>' + (center !== undefined ? '<b>' + esc(center) + '</b>' : '') + '</span>';
}

function firstName(n) { return String(n || '').split(' ')[0]; }

function clashBlock(m, cls) {
  const clash = m.clashes[0], ov = m.overlapOffers[0];
  if (!clash && !ov) return card('conflicts', cls + ' calm', '<span class="chip ok">' + icon('check', 13, 2.2) + 'No clashes</span><span class="b-line">I see nothing overlapping on the calendar this week.</span>', { color: '#7cc4ff', label: 'Clashes: none found this week' });
  let line, who = '';
  if (ov) {
    line = String(ov.title).replace(/\s*Want it checked\?\s*$/, '');
  } else {
    const c = Array.isArray(clash.clashes) ? clash.clashes.map((x) => x.summary || x.title || x).join(', ') : String(clash.clashes);
    line = clash.title + (clash.due_date ? ' (' + D.fmtDay(clash.due_date, m.today) + ')' : '') + ' overlaps ' + c;
    who = clash.subject || '';
  }
  const n = m.clashes.length + m.overlapOffers.length;
  return card('conflicts', cls, '<span class="clash-top"><span class="chip warn">' + icon('conflicts', 13, 2.2) + 'Calendar clash' + (n > 1 ? ' \u00B7 ' + n : '') + '</span>'
    + '<span class="avs">' + m.members.slice(0, 3).map((x) => '<i title="' + esc(x.display_name) + '">' + esc(x.display_name.charAt(0)) + '</i>').join('') + '</span></span>'
    + '<span class="b-line strong">' + esc(line) + (who ? ' \u00B7 ' + esc(who) : '') + '</span>', { color: '#7cc4ff', label: 'Calendar clash: ' + line });
}

function financeBlock(m, cls) {
  const has = m.loaded.money;
  const fig = m.monthTotal !== null && m.monthTotal !== undefined ? D.money(m.monthTotal, m.currency) : '—';
  let trend = '';
  if (m.monthTotal !== null && m.monthComparable && m.monthPrev !== undefined) {
    const d = m.monthTotal - m.monthPrev;
    trend = '<span class="trend ' + (d > 0 ? 'up' : 'down') + '">' + (d > 0 ? '+' : '−') + D.money(Math.abs(d), m.currency) + '</span> <span class="muted">vs the 30 days before</span>';
  }
  const next = m.outThisWeek.length ? m.outThisWeek.map((r) => r.merchant + ' ' + D.money(r.next_amount, r.currency) + ', ' + D.fmtDay(r.next_date)).slice(0, 2).join(' · ')
    : m.nextBill ? 'Next: ' + m.nextBill.merchant + ' ' + D.money(m.nextBill.next_amount, m.nextBill.currency) + ', ' + D.fmtDay(m.nextBill.next_date) : 'No recurring charge read yet';
  return card('finance', cls, head('Finance', 'Agent', m.agents.finance.badge ? String(m.agents.finance.badge) : '')
    + sparkSvg(m.spark, 120, 44, '#2dd4bf', false)
    + '<span class="b-fig">' + esc(fig) + '</span><span class="b-cap">receipts read,<br>last 30 days</span>'
    + (trend ? '<span class="b-trend">' + trend + '</span>' : '')
    + '<span class="b-cap2">' + esc(m.moneyLine || next) + '</span>'
    + '<span class="b-bottom">' + sparkSvg(m.spark.slice(-8), 120, 40, '#2dd4bf', true) + '<span class="b-cap2">' + esc(next) + '</span></span>',
  { label: 'Finance: ' + (has ? fig + ' on receipts read in the last 30 days. ' + (m.moneyLine || next) : 'money could not be loaded') });
}

function educationBlock(m, cls) {
  const kids = m.children;
  const lines = kids.slice(0, 2).map((c) => {
    const a = m.adventures.find((x) => x.who === c.display_name);
    return '<span class="b-kid"><b>' + esc(firstName(c.display_name)) + ':</b> ' + esc(a ? a.title + ', ' + D.fmtDay(a.date, m.today) : 'nothing dated ahead') + '</span>';
  }).join('');
  const total = Math.max(1, m.agents.education.badge);
  const bars = '<span class="bars">' + kids.slice(0, 3).map((c) => { const n = m.brief.filter((i) => i.subject_member_id === c.id && i.reason !== 'handled').length; return '<i style="--f:' + Math.min(1, n / total).toFixed(2) + '"></i>'; }).join('') + '</span>';
  return card('education', cls, head('Education', kids.length ? '• ' + esc(kids.map((c) => firstName(c.display_name)).join(' & ')) : 'No children in the pod', m.agents.education.badge ? String(m.agents.education.badge) : '')
    + (kids.length ? bars : '') + lines, { label: 'Education: ' + m.agents.education.badge + ' open' });
}

function householdBlock(m, cls) {
  const all = m.errands.filter((e) => e.status !== 'cancelled');
  const done = all.filter((e) => e.status === 'done').length;
  const act = m.errandsActive[0];
  const svc = m.money && m.money.services && m.money.services.timeline && m.money.services.timeline[0];
  return card('household', cls, head('Household', '• ' + (m.errandsActive.length ? m.errandsActive.length + ' errand' + (m.errandsActive.length > 1 ? 's' : '') + ' active' : 'no errand running'), m.agents.household.badge ? String(m.agents.household.badge) : '')
    + '<span class="b-ringwrap">' + ring(all.length ? done / all.length : 0, '#ffb547', 64, all.length ? done + '/' + all.length : '0') + '</span>'
    + '<span class="b-cap">errands finished</span>'
    + (act ? '<span class="b-line">' + esc(act.title) + ' — ' + esc({ proposed: 'waiting for approval', approved: 'approved, not yet run', running: 'running', needs_you: 'needs you' }[act.status]) + '</span>' : '')
    + (svc ? '<span class="b-line muted">Last service: ' + esc(cap(svc.kind)) + ', ' + esc(D.fmtDay(svc.date)) + '</span>' : ''), { label: 'Household: ' + m.errandsActive.length + ' errands active' });
}

function healthBlock(m, cls) {
  const open = m.medical.filter((r) => r.state === 'todo').length, done = m.medical.filter((r) => r.state === 'done').length;
  const tot = open + done;
  return card('health', cls, head('Health', '• Medical notices')
    + '<span class="b-ringwrap">' + ring(tot ? done / tot : 0, '#34d399', 58, tot ? Math.round((done / tot) * 100) + '%' : '–', 'rgba(255,90,120,.18)') + '</span>'
    + '<span class="b-cap center">' + (m.medical.length ? done + ' handled, ' + open + ' open' : 'No medical notices in 60 days') + '</span>', { color: '#f472b6', label: 'Health: ' + (m.medical.length ? open + ' open medical notices' : 'no medical notices in 60 days') });
}

function groceryBlock(m, cls) {
  const low = m.runningLow, todo = m.groceryTodos;
  const attn = low.length || todo.some((t) => t.due_date && t.due_date <= m.today);
  let line;
  if (low.length) line = low.slice(0, 3).map((x) => x.item || x.name || x.title).join(', ') + ' running low';
  else if (todo.length) line = todo[0].title + (todo[0].assigned_to ? ' — ' + m.name(todo[0].assigned_to) : '') + (todo[0].due_date ? ', due ' + D.fmtDay(todo[0].due_date, m.today).toLowerCase() : '');
  else line = 'Nothing running low on the receipts I have read.';
  return card('grocery', cls, '<span class="b-head"><span class="b-title">Grocery</span><span class="b-sub inline">• ' + (attn ? 'Needs attention' : 'Calm') + '</span>' + (m.agents.grocery.badge ? '<span class="b-badge">' + m.agents.grocery.badge + '</span>' : '') + '</span>'
    + '<span class="b-line">' + icon('grocery', 14) + ' ' + esc(line) + '</span>', { label: 'Grocery: ' + line });
}

function waitingBlock(m, cls) {
  const bits = [];
  if (m.proposed.length) bits.push(m.proposed.length + ' date' + (m.proposed.length > 1 ? 's' : '') + ' to accept or dismiss');
  if (m.errandsProposed.length) bits.push(m.errandsProposed.length + ' errand' + (m.errandsProposed.length > 1 ? 's' : '') + ' to approve');
  if (m.offersOpen.length) bits.push(m.offersOpen.length + ' offer' + (m.offersOpen.length > 1 ? 's' : ''));
  return card('waiting', cls, '<span class="b-head"><span class="b-title">Waiting for you</span>' + (m.waitingCount ? '<span class="b-badge">' + m.waitingCount + '</span>' : '') + '</span>'
    + '<span class="b-line">' + icon('waiting', 14) + ' ' + esc(bits.length ? bits.join(' · ') : 'Nothing is waiting for approval.') + '</span>', { label: 'Waiting for you: ' + (bits.join(', ') || 'nothing') });
}

function memoriesBlock(m, cls) {
  const ph = m.photos.slice(0, 3);
  return card('memories', cls, head('Memories', '• photos the family shared')
    + (ph.length ? '<span class="thumbs">' + ph.map((r) => '<span class="pic"><img alt="" data-pic="' + esc(r.id) + '"></span>').join('') + '</span><span class="b-cap">' + m.photos.length + ' in 60 days</span>'
      : '<span class="b-line muted">No photos shared in the last 60 days.</span>'), { label: 'Memories: ' + m.photos.length + ' photos shared' });
}

function calendarBlock(m, cls) {
  const n = m.nextThing;
  return card('calendar', cls, head('Calendar', '• ' + m.week.length + ' this week')
    + (n ? '<span class="b-when">' + esc(D.fmtDay(n.date, m.today)) + (n.time ? ' · ' + esc(n.time) : '') + '</span><span class="b-line">' + esc(n.title) + '</span>' : '<span class="b-line muted">Nothing dated this week.</span>'), { label: 'Calendar: ' + m.week.length + ' this week' + (n ? '; next ' + n.title : '') });
}

function todosBlock(m, cls) {
  const late = m.todos.filter((t) => t.due_date && t.due_date < m.today).length;
  return card('todos', cls, head('To-dos', '• shared')
    + '<span class="b-num">' + m.todos.length + '</span><span class="b-cap">open' + (late ? ' · <span class="warnc">' + late + ' past their date</span>' : '') + '</span>', { label: 'To-dos: ' + m.todos.length + ' open' });
}

function rootAdult(m) {
  return '<div class="bento-grid adult">'
    + financeBlock(m, 'a-fin') + clashBlock(m, 'a-clash') + educationBlock(m, 'a-edu') + householdBlock(m, 'a-hh') + healthBlock(m, 'a-health')
    + groceryBlock(m, 'a-groc') + waitingBlock(m, 'a-wait') + memoriesBlock(m, 'a-mem') + calendarBlock(m, 'a-cal') + todosBlock(m, 'a-todo')
    + '</div>';
}

function rootTeen(m) {
  const sched = m.week.slice(0, 4);
  const social = m.brief.filter((i) => i.action === 'attend' && i.due_date && i.due_date >= m.today);
  const allowance = m.todos.filter((t) => /allowance|pocket money|budget/i.test(t.title)).concat(m.charges.filter((c) => /allowance|pocket money/i.test(c.title || '')));
  return '<div class="bento-grid teen">'
    + card('calendar', 't-sched', head('Schedule', '• ' + m.week.length + ' this week') + (sched.length ? '<ul class="t-list">' + sched.map((x) => '<li><b>' + esc(D.fmtDay(x.date, m.today)) + (x.time ? ' ' + esc(x.time) : '') + '</b><span>' + esc(x.title) + '</span></li>').join('') + '</ul>' : '<span class="b-line muted">Nothing dated this week.</span>'))
    + card('calendar', 't-social', head('Events', '• to go to') + (social.length ? '<span class="b-num">' + social.length + '</span><span class="b-line">' + esc(social[0].title) + ', ' + esc(D.fmtDay(social[0].due_date, m.today)) + '</span>' : '<span class="b-line muted">No events to attend on the record.</span>'), { to: 'calendar' })
    + (allowance.length ? card('finance', 't-budget', head('Allowance', '• budget') + '<span class="b-line">' + esc(allowance[0].title) + '</span>')
      : card('finance', 't-budget', head('Allowance', '• budget') + '<span class="b-line muted">Nothing on record about an allowance. I only show what a notice or a to-do says.</span>', { static: true }))
    + card('health', 't-fit', head('Health', '• abstract') + '<span class="b-ringwrap">' + ring(m.medical.length ? m.medical.filter((r) => r.state === 'done').length / m.medical.length : 0, '#39ff14', 60, m.medical.length || '–') + '</span>')
    + card('education', 't-school', head('School', '• ' + m.agents.education.badge + ' open') + (m.nextSchool ? '<span class="b-line">' + esc(m.nextSchool.title) + ', ' + esc(D.fmtDay(m.nextSchool.date, m.today)) + '</span>' : '<span class="b-line muted">Nothing dated ahead.</span>'))
    + '</div>';
}

function rootKid(m) {
  const adv = m.adventures.slice(0, 5);
  const hues = ['#00e5ff', '#ff2bd6', '#ffd23f', '#7cff6b', '#9b7bff'];
  return '<div class="bento-grid kid">'
    + card('education', 'k-stars', '<span class="k-star">' + icon('star', 34, 2) + '</span><span class="k-big">' + m.adventuresDone + '</span><span class="k-cap">adventures done</span>', { static: true, label: m.adventuresDone + ' adventures done' })
    + (adv.length ? adv.map((a, i) => {
      const days = D.daysBetween(m.today, a.date);
      return '<button class="bento k-adv" style="--c:' + hues[i % hues.length] + '"' + (a.artifact_id ? ' data-notice-open="' + esc(a.artifact_id) + '"' : ' data-open="education"') + ' aria-label="' + esc(a.title + ', ' + D.fmtDay(a.date, m.today) + (a.who ? ', ' + a.who : '')) + '">'
        + '<span class="k-when">' + (days === 0 ? 'Today!' : days === 1 ? 'Tomorrow' : 'In ' + days + ' days') + '</span>'
        + '<span class="k-icon">' + icon(i % 2 ? 'flag' : 'education', 30, 2) + '</span>'
        + '<span class="k-title">' + esc(a.title) + '</span>' + (a.who ? '<span class="k-who">' + esc(firstName(a.who)) + '</span>' : '') + '</button>';
    }).join('') : '<div class="bento k-adv empty" style="--c:#00e5ff"><span class="k-title">No adventures on the calendar yet.</span></div>')
    + '</div>';
}

function rootSenior(m) {
  const today = m.todayItems;
  const phones = m.members.filter((x) => x.phone && x.id !== m.me.id);
  const meds = m.medical.filter((r) => r.state === 'todo');
  return '<div class="bento-grid senior">'
    + '<section class="bento s-block" style="--c:#ffd60a"><h3>Today’s Schedule</h3>'
    + (today.length ? '<ul class="s-list">' + today.map((x) => '<li>' + (x.time ? '<b>' + esc(x.time) + '</b> ' : '') + esc(x.title) + '</li>').join('') + '</ul>'
      : '<p>Nothing is dated today.' + (m.nextThing ? ' Next: ' + esc(m.nextThing.title) + ', ' + esc(D.fmtDay(m.nextThing.date, m.today)) + '.' : '') + '</p>')
    + '<button class="btn primary big" data-open="calendar">Open the calendar</button></section>'
    + '<section class="bento s-block" style="--c:#34d399"><h3>Health &amp; Meds</h3>'
    + (meds.length ? '<ul class="s-list">' + meds.slice(0, 3).map((r) => '<li>' + esc(r.headline) + '</li>').join('') + '</ul>' : '<p>No medical notices or medicines on the record.</p>')
    + '<button class="btn primary big" data-open="health">See health notices</button></section>'
    + '<section class="bento s-block" style="--c:#5cc8ff"><h3>Call Family</h3>'
    + (phones.length ? '<div class="s-calls">' + phones.map((x) => '<a class="btn primary big" href="tel:' + esc(x.phone) + '">' + icon('phone', 22) + ' Call ' + esc(x.display_name) + '</a>').join('') + '</div>'
      : '<p>No phone numbers are saved for the family yet. Add them in the full app, under Household.</p><a class="btn primary big" href="/app/#/household">Add phone numbers</a>')
    + '</section></div>';
}

/* ── deep layers ──────────────────────────────────────────────── */

const CTX = {
  finance: { ask: 'Ask Finance anything…', q: 'Which bills come due this week, and which have a pay link?' },
  education: { ask: 'Ask about school…', q: 'What does school need from us this week?' },
  household: { ask: 'Ask for an errand…', q: 'Can you set up an errand to ' },
  calendar: { ask: 'Ask the calendar…', q: 'What clashes this week?' },
  grocery: { ask: 'Ask about groceries…', q: 'What do we usually order, and when did we last order it?' },
  health: { ask: 'Ask about health notices…', q: 'Is there anything medical we need to do?' },
  memories: { ask: 'Ask about a photo…', q: 'What photos were shared this month?' },
  waiting: { ask: 'Ask what is undecided…', q: 'What is still undecided, worst first?' },
  conflicts: { ask: 'Ask what clashes…', q: 'What clashes this week, and what would have to move?' },
  todos: { ask: 'Ask about to-dos…', q: 'Which to-dos are past their date?' },
  documents: { ask: 'Ask about documents…', q: 'Which documents expire soon?' },
  notice: { ask: 'Ask about this notice…', q: '' },
};

/* The contextual action, bottom right: something the product really does. */
function ctxAction(cat) {
  const m = S.model;
  if (cat === 'finance') return m.payLink ? payLinks(m.payLink, 'ctx-fab').split('</a>')[0] + '</a>' : '<button class="ctx-fab" data-ask="' + esc(CTX.finance.q) + '">' + icon('receipt', 16) + 'Ask about a bill</button>';
  if (cat === 'household') return '<button class="ctx-fab" data-prefill="' + esc(CTX.household.q) + '">' + icon('wrench', 16) + 'Ask for an errand</button>';
  if (cat === 'calendar' || cat === 'conflicts') return '<button class="ctx-fab" data-ask="' + esc(CTX.calendar.q) + '">' + icon('conflicts', 16) + 'Ask what clashes</button>';
  if (cat === 'education') return '<button class="ctx-fab" data-ask="' + esc(CTX.education.q) + '">' + icon('education', 16) + 'Ask about school</button>';
  if (cat === 'grocery') return '<button class="ctx-fab" data-ask="' + esc(CTX.grocery.q) + '">' + icon('grocery', 16) + 'What we usually order</button>';
  if (cat === 'waiting') return '<button class="ctx-fab" data-ask="' + esc(CTX.waiting.q) + '">' + icon('waiting', 16) + 'Ask what is undecided</button>';
  if (cat === 'memories') return '<a class="ctx-fab" href="/app/#/inbox">' + icon('memories', 16) + 'Share a photo in FamilyOS</a>';
  if (cat === 'todos') return '<a class="ctx-fab" href="/app/#/life">' + icon('todos', 16) + 'Add a to-do</a>';
  return '';
}

const KIND_ICON = { Proposed: 'sparkle', Accepted: 'check', Dismissed: 'close', Replaced: 'documents', Reminded: 'bell', 'Handed over': 'link', Handled: 'check', Read: 'documents', Errand: 'wrench', Approved: 'check', 'Errand step': 'wrench', 'Needs you': 'bell', 'Errand done': 'check', Expected: 'receipt', 'Receipt read': 'receipt', Service: 'household', 'To-do': 'todos', Done: 'check', 'On the calendar': 'calendar' };

function streamHtml(events, cat, limit = 60) {
  const m = S.model;
  const info = D.catInfo(cat);
  if (!events.length) return '<p class="empty-line">Nothing recorded here yet. When I read, propose or remind anything for ' + esc(info.label.toLowerCase()) + ', it shows up in this stream.</p>';
  return '<ol class="stream">' + events.slice(0, limit).map((e) => {
    const from = e.artifact_id ? (m.notice(e.artifact_id) || {}).headline : '';
    const date = e.future ? D.fmtDay(String(e.at).slice(0, 10), m.today) : D.fmtWhen(e.at);
    return '<li class="ev tone-' + e.tone + '" style="--c:' + info.color + '"><span class="ev-ic">' + icon(KIND_ICON[e.kind] || 'sparkle', 18) + '</span><span class="ev-body">'
      + '<span class="ev-h"><b>' + esc(info.label.toUpperCase()) + ': ' + esc(e.kind) + '</b> • ' + esc(date) + '</span>'
      + '<span class="ev-t">' + esc(e.text) + '</span>'
      + (e.sub ? '<span class="ev-from">Errand: ' + esc(e.sub) + '</span>' : '')
      + (e.pics && e.pics.length ? '<span class="ev-pics">' + e.pics.slice(0, 3).map((p) => '<span class="pic"><img alt="A picture the errand recorded" data-pic="' + esc(p) + '"></span>').join('') + '</span>' : '')
      + (e.artifact_id ? '<button class="ev-link" data-notice="' + esc(e.artifact_id) + '">' + (from ? 'From “' + esc(from) + '”' : 'Open the notice it came from') + '</button>' : '')
      + (e.errand ? '<a class="ev-link" href="/app/#/errands/' + esc(e.errand) + '">Open the errand</a>' : '')
      + '</span></li>';
  }).join('') + '</ol>';
}

function hero(cat, fig, side, lines, extra) {
  const info = D.catInfo(cat);
  return '<section class="hero" style="--c:' + info.color + '"><p class="h-kicker"><b>' + esc(info.label.toUpperCase()) + '</b> AGENT</p>'
    + '<div class="h-row"><span class="h-fig">' + esc(fig) + '</span>' + (side ? '<span class="h-side">' + side + '</span>' : '') + '</div>'
    + (lines || '') + (extra || '') + '</section>';
}

function deepHtml(cat) {
  const m = S.model;
  const ev = (c) => m.events.filter((e) => e.cats.includes(c));
  if (cat === 'finance') {
    const figItem = m.outThisWeek.length ? m.outThisWeek.reduce((s, r) => s + (r.currency === m.currency ? r.next_amount : 0), 0) : null;
    const fig = figItem ? D.money(figItem, m.currency) : m.nextBill ? D.money(m.nextBill.next_amount, m.nextBill.currency) : '—';
    const side = figItem ? 'comes out<br>this week' : m.nextBill ? 'next bill,<br>' + esc(m.nextBill.merchant) + ' ' + esc(D.fmtDay(m.nextBill.next_date)) : 'nothing<br>read yet';
    const sub = m.outThisWeek.length ? m.outThisWeek.map((r) => r.merchant + ' on ' + D.fmtDay(r.next_date)).join(', ') + ', from past receipts' : '';
    const pay = m.payItems.filter((i) => i.reason !== 'handled');
    const stats = '<p class="h-stats">Receipts, 30 days: ' + (m.monthTotal !== null ? D.money(m.monthTotal, m.currency) : '—') + ' | Recurring: ' + ((m.money && m.money.recurring) || []).length + ' | Bills to pay: ' + pay.length + '</p>';
    return hero('finance', fig, side, (sub ? '<p class="h-trend">' + esc(sub) + '</p>' : '') + '<p class="h-note">I read these; FamilyOS never pays. A pay link opens the biller’s own page.</p>',
      '<div class="h-spark">' + sparkSvg(m.spark, 340, 86, '#2dd4bf', true) + '</div>' + stats)
      + streamHtml(ev('finance'), 'finance');
  }
  if (cat === 'education') {
    const n = m.nextSchool;
    return hero('education', n ? D.fmtDay(n.date, m.today) : '—', n ? 'next school<br>date' : 'nothing<br>dated ahead',
      n ? '<p class="h-trend">' + esc(n.title) + (n.who ? ' · ' + esc(n.who) : '') + '</p>' : '',
      '<p class="h-stats">' + m.children.map((c) => esc(c.display_name) + (c.class_label ? ' (' + esc(c.class_label) + (c.school ? ', ' + esc(c.school) : '') + ')' : '')).join(' | ') + '</p>')
      + streamHtml(ev('education'), 'education');
  }
  if (cat === 'household') {
    const a = m.errandsActive;
    return hero('household', String(a.length), 'errand' + (a.length === 1 ? '' : 's') + '<br>in progress',
      a.length ? '<p class="h-trend">' + a.map((e) => esc(e.title) + ' — ' + esc({ proposed: 'waiting for approval', approved: 'approved, not yet run', running: 'running', needs_you: 'needs you' }[e.status])).join('<br>') + '</p>' : '<p class="h-trend">No errand is running.</p>',
      '<p class="h-stats">Home notices open: ' + m.home.filter((r) => r.state === 'todo').length + ' | Running low: ' + m.runningLow.length + ' | Services on record: ' + ((m.money && m.money.services && m.money.services.timeline) || []).length + '</p>')
      + streamHtml(ev('household'), 'household');
  }
  if (cat === 'calendar') {
    const n = m.nextThing;
    const upcoming = m.week.map((x) => ({ at: x.at || x.date + 'T00:00:00', cats: ['calendar'], kind: x.src === 'calendar' ? 'On the calendar' : 'Proposed', tone: 'blue', text: x.title + (x.who ? ' · ' + x.who : '') + (x.time ? ' · ' + x.time : ''), future: true, artifact_id: x.item ? x.item.artifact_id : null }));
    const past = ev('calendar').filter((e) => !e.future);
    return hero('calendar', n ? D.fmtDay(n.date, m.today) + (n.time ? ', ' + n.time : '') : '—', n ? 'the next<br>thing' : 'nothing<br>this week', n ? '<p class="h-trend">' + esc(n.title) + '</p>' : '',
      '<p class="h-stats">This week: ' + m.week.length + ' | Clashes: ' + (m.clashes.length + m.overlapOffers.length) + ' | Undecided: ' + m.proposed.length + '</p>')
      + '<h3 class="st-h">This week, in order</h3>' + streamHtml(upcoming, 'calendar') + '<h3 class="st-h">Before now</h3>' + streamHtml(past, 'calendar', 40);
  }
  if (cat === 'grocery') {
    const low = m.runningLow;
    return hero('grocery', String(low.length), 'item' + (low.length === 1 ? '' : 's') + '<br>running low',
      low.length ? '<p class="h-trend">' + esc(low.map((x) => x.item || x.name || x.title).join(', ')) + '</p>' : '<p class="h-trend">Nothing marked running low on the receipts I read.</p>',
      m.usual.length ? '<div class="usual"><p class="h-stats">What the family usually orders</p>' + m.usual.slice(0, 5).map((u) => '<a class="usual-i" href="' + esc(u.reorder_url) + '" target="_blank" rel="noopener"><b>' + esc(u.item) + '</b><span>' + esc(u.merchant) + ' · ' + u.times + '×, last ' + esc(D.fmtDay(u.last_on)) + '</span>' + icon('link', 14) + '</a>').join('') + '<p class="h-note">A link opens the shop’s own search. Nothing is ordered from here.</p></div>' : '')
      + streamHtml(ev('grocery'), 'grocery');
  }
  if (cat === 'health') {
    const open = m.medical.filter((r) => r.state === 'todo');
    return hero('health', String(open.length), 'medical notices<br>open', '<p class="h-trend">' + (m.medical.length ? m.medical.length + ' medical notices read in the last 60 days.' : 'I have not read any medical notices in the last 60 days.') + '</p>', '')
      + streamHtml(ev('health'), 'health');
  }
  if (cat === 'memories') {
    return hero('memories', String(m.photos.length), 'photos shared<br>in 60 days', '<p class="h-note">FamilyOS has no emotional agent. These are the pictures the family sent in, as they arrived.</p>', '')
      + (m.photos.length ? '<div class="gallery">' + m.photos.map((r) => '<figure class="pic"><img alt="' + esc(r.headline || 'A photo') + '" data-pic="' + esc(r.id) + '"><figcaption>' + esc(D.fmtWhen(r.received_at)) + (r.submitted_by ? ' · ' + esc(m.name(r.submitted_by)) : '') + '</figcaption></figure>').join('') + '</div>' : '<p class="empty-line">No photos yet.</p>');
  }
  if (cat === 'waiting') {
    return hero('waiting', String(m.waitingCount), 'waiting for<br>a person', '<p class="h-note">I propose; one of you decides. Nothing here happens until someone does.</p>', '')
      + '<ol class="stream">'
      + m.proposed.map((o) => '<li class="ev" style="--c:#ffd60a"><span class="ev-ic">' + icon('sparkle', 18) + '</span><span class="ev-body"><span class="ev-h"><b>PROPOSED</b> • ' + esc(o.due_date ? D.fmtDay(o.due_date, m.today) : 'no date') + '</span><span class="ev-t">' + esc(o.title) + (o.subject_member_id ? ' · ' + esc(m.name(o.subject_member_id)) : '') + '</span>'
        + '<span class="ev-acts"><button class="btn sm primary" data-decide="accepted" data-id="' + esc(o.id) + '">Accept</button><button class="btn sm" data-decide="dismissed" data-id="' + esc(o.id) + '">Not this</button>' + (o.pay_url ? payLinks(o.pay_url, 'btn sm') : '') + '<button class="ev-link" data-notice="' + esc(o.artifact_id) + '">' + esc((m.notice(o.artifact_id) || {}).headline ? 'From “' + m.notice(o.artifact_id).headline + '”' : 'The notice') + '</button></span></span></li>').join('')
      + m.errandsProposed.map((e) => '<li class="ev" style="--c:#ffb547"><span class="ev-ic">' + icon('wrench', 18) + '</span><span class="ev-body"><span class="ev-h"><b>ERRAND</b> • waiting for approval</span><span class="ev-t">' + esc(e.title) + '</span><span class="ev-acts"><a class="btn sm primary" href="/app/#/errands/' + esc(e.id) + '">Open to approve</a></span></span></li>').join('')
      + m.offersOpen.map((o) => '<li class="ev" style="--c:#5cc8ff"><span class="ev-ic">' + icon('sparkle', 18) + '</span><span class="ev-body"><span class="ev-h"><b>OFFER</b></span><span class="ev-t">' + esc(o.title) + '</span><span class="ev-from">' + esc(o.limit) + '</span><span class="ev-acts"><button class="btn sm primary" data-offer-accept="' + esc(o.key) + '">' + esc(o.accept_label || 'Yes') + '</button><button class="btn sm" data-offer-dismiss="' + esc(o.key) + '">Not now</button></span></span></li>').join('')
      + '</ol>' + (m.waitingCount ? '' : '<p class="empty-line">Nothing is waiting for approval.</p>');
  }
  if (cat === 'conflicts') {
    const items = m.clashes.map((i) => ({ title: i.title, text: 'Overlaps ' + (Array.isArray(i.clashes) ? i.clashes.map((x) => x.summary || x.title || x).join(', ') : String(i.clashes)), artifact_id: i.artifact_id }));
    return hero('conflicts', String(m.clashes.length + m.overlapOffers.length), 'clash' + (m.clashes.length + m.overlapOffers.length === 1 ? '' : 'es') + '<br>I can see', '<p class="h-note">I lay accepted dates against calendars and plans. Nothing is moved, booked or cancelled from here.</p>', '')
      + '<ol class="stream">' + items.map((x) => '<li class="ev" style="--c:#ff6b6b"><span class="ev-ic">' + icon('conflicts', 18) + '</span><span class="ev-body"><span class="ev-h"><b>CLASH</b></span><span class="ev-t">' + esc(x.title) + '. ' + esc(x.text) + '</span>' + (x.artifact_id ? '<button class="ev-link" data-notice="' + esc(x.artifact_id) + '">Open the notice</button>' : '') + '</span></li>').join('')
      + m.overlapOffers.map((o) => '<li class="ev" style="--c:#ff6b6b"><span class="ev-ic">' + icon('conflicts', 18) + '</span><span class="ev-body"><span class="ev-h"><b>PLAN OVERLAP</b></span><span class="ev-t">' + esc(o.title) + '</span><span class="ev-from">' + esc(o.limit) + '</span><span class="ev-acts"><button class="btn sm primary" data-offer-accept="' + esc(o.key) + '">' + esc(o.accept_label || 'Check it') + '</button><button class="btn sm" data-offer-dismiss="' + esc(o.key) + '">Not now</button></span></span></li>').join('')
      + '</ol>' + (items.length + m.overlapOffers.length ? '' : '<p class="empty-line">No clashes on the record.</p>');
  }
  if (cat === 'todos') {
    const late = m.todos.filter((t) => t.due_date && t.due_date < m.today).length;
    return hero('todos', String(m.todos.length), 'open<br>to-dos', '<p class="h-trend">' + (late ? late + ' past their date' : 'None past its date') + '</p>', '')
      + '<ul class="todo-list">' + m.todos.map((t) => '<li><label><input type="checkbox" data-todo="' + esc(t.id) + '"><span><b>' + esc(t.title) + '</b><small>' + esc([t.due_date ? 'by ' + D.fmtDay(t.due_date, m.today) : '', m.name(t.assigned_to)].filter(Boolean).join(' · ')) + '</small></span></label></li>').join('') + '</ul>';
  }
  if (cat === 'documents') {
    return hero('documents', String(m.documents.length), 'documents<br>on record', '', '')
      + '<ol class="stream">' + m.documents.map((d) => '<li class="ev" style="--c:#cbd5e1"><span class="ev-ic">' + icon('documents', 18) + '</span><span class="ev-body"><span class="ev-h"><b>' + esc(String(d.label || d.kind).toUpperCase()) + '</b>' + (d.expires_on ? ' • expires ' + esc(D.fmtDay(d.expires_on)) : '') + '</span><span class="ev-t">' + esc(d.title) + (d.holder_name ? ' · ' + esc(d.holder_name) : '') + (d.identifier_tail ? ' · ending ' + esc(d.identifier_tail) : '') + '</span><button class="ev-link" data-notice="' + esc(d.artifact_id) + '">Open</button></span></li>').join('') + '</ol>';
  }
  return '<p class="empty-line">Nothing here.</p>';
}

async function noticeHtml(id) {
  const m = S.model;
  const [a, ex] = await Promise.all([api('/artifacts/' + id), api('/artifacts/' + id + '/extraction').catch(() => null)]);
  const row = m.notice(id);
  const title = (row && row.headline) || (a.source && (a.source.headline || a.source.subject)) || a.filename || 'A notice';
  const from = (row && row.from_label) || (a.source && (a.source.from || a.source.via)) || a.channel;
  const obl = ((m.raw.obligations) || []).filter((o) => o.artifact_id === id);
  // The brief can carry a date the obligations list does not; show it too.
  m.brief.forEach((i) => { if (i.artifact_id === id && i.obligation_id && !obl.some((o) => o.id === i.obligation_id)) obl.push({ id: i.obligation_id, title: i.title, due_date: i.due_date, status: i.status || 'proposed', decided_by: null, pay_url: i.pay_url }); });
  const claims = (ex && ex.extraction && ex.extraction.claims) || [];
  const about = (a.subject_member_ids || []).map((x) => m.name(x)).filter(Boolean);
  return '<section class="hero small" style="--c:#cbd5e1"><p class="h-kicker"><b>NOTICE</b> \u2022 ' + esc(D.fmtWhen(a.received_at)) + '</p></section>'
    + '<section class="notice"><h2 class="n-title">' + esc(title) + '</h2><p class="n-meta">From ' + esc(from) + (about.length ? ' · about ' + esc(about.join(', ')) : '') + (a.category && a.category !== 'unknown' ? ' · ' + esc(a.category) : '') + '</p>'
    + (/^image\//.test(a.media_type) ? '<figure class="pic n-pic"><img alt="' + esc(title) + '" data-pic="' + esc(id) + '"></figure>' : '')
    + (obl.length ? '<h3 class="st-h">What I proposed from it</h3><ol class="stream">' + obl.map((o) => '<li class="ev" style="--c:#5cc8ff"><span class="ev-ic">' + icon(o.status === 'accepted' ? 'check' : o.status === 'dismissed' ? 'close' : 'sparkle', 18) + '</span><span class="ev-body"><span class="ev-h"><b>' + esc(o.status.toUpperCase()) + '</b>' + (o.due_date ? ' • ' + esc(D.fmtDay(o.due_date, m.today)) : '') + '</span><span class="ev-t">' + esc(o.title) + '</span>'
      + (o.decided_by && o.decided_at ? '<span class="ev-from">' + (o.status === 'accepted' ? 'Accepted' : 'Dismissed') + ' by ' + esc(m.name(o.decided_by)) + ', ' + esc(D.fmtWhen(o.decided_at)) + '</span>' : '')
      + (o.status === 'proposed' && !o.superseded_at ? '<span class="ev-acts"><button class="btn sm primary" data-decide="accepted" data-id="' + esc(o.id) + '">Accept</button><button class="btn sm" data-decide="dismissed" data-id="' + esc(o.id) + '">Not this</button>' + (o.pay_url ? payLinks(o.pay_url, 'btn sm') : '') + '</span>' : '')
      + '</span></li>').join('') + '</ol>' : '')
    + (claims.length ? '<h3 class="st-h">Where each date came from</h3><ul class="quotes">' + claims.slice(0, 12).map((c) => '<li><b>' + esc(c.title) + '</b>' + (c.date ? ' · ' + esc(D.fmtDay(c.date)) : '') + (c.quote ? '<q>' + esc(c.quote) + '</q>' : '') + '</li>').join('') + '</ul>' : '<p class="empty-line">I found nothing dated in this notice.</p>')
    + '<a class="btn" href="/app/#/notices/' + esc(id) + '">Open it in the full app</a></section>';
}

async function renderLayer(spec, el) {
  const m = S.model;
  if (spec.kind === 'root') {
    el.innerHTML = '<div class="layer-in">' + (S.seg === 'senior' ? rootSenior(m) : S.seg === 'teen' ? rootTeen(m) : S.seg === 'kid' ? rootKid(m) : rootAdult(m))
      + '<p class="collapse-hint" aria-hidden="true">' + icon('down', 12, 2) + ' Swipe down to collapse</p></div>';
  } else if (spec.kind === 'cat') {
    el.innerHTML = '<div class="layer-in deep-in">' + deepHtml(spec.cat) + '</div><div class="ctx-slot">' + ctxAction(spec.cat) + '</div>';
  } else {
    el.innerHTML = '<div class="layer-in deep-in"><p class="empty-line">Opening the notice…</p></div>';
    try { el.querySelector('.layer-in').innerHTML = await noticeHtml(spec.id); }
    catch (err) { el.querySelector('.layer-in').innerHTML = '<p class="empty-line">' + esc(err.status === 404 ? 'That notice is not visible to you, or no longer exists.' : err.message) + '</p>'; }
  }
  wireLayer(el);
}

function wireLayer(el) {
  $$('[data-open]', el).forEach((b) => b.addEventListener('click', () => navigate(hashFor(currentLayers().slice(0, 1)) + '/' + b.dataset.open)));
  $$('[data-notice-open]', el).forEach((b) => b.addEventListener('click', () => navigate('#/dashboard/notice/' + b.dataset.noticeOpen)));
  wireDecisions(el);
  $$('[data-ask]', el).forEach((b) => b.addEventListener('click', () => { setChat(true); sendChat(b.dataset.ask); }));
  $$('[data-prefill]', el).forEach((b) => b.addEventListener('click', () => { setChat(true); const i = $('#chatInput'); i.value = b.dataset.prefill; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }));
  $$('[data-offer-accept]', el).forEach((b) => b.addEventListener('click', async () => {
    b.disabled = true;
    try {
      const out = await api('/offers/' + encodeURIComponent(b.dataset.offerAccept) + '/accept', { method: 'POST' });
      if (out && out.ask) { setChat(true); sendChat(out.ask); } else toast((out && out.done) || 'Done.');
      await refresh();
    } catch (err) { b.disabled = false; toast(err.message, true); }
  }));
  $$('[data-offer-dismiss]', el).forEach((b) => b.addEventListener('click', async () => {
    try { await api('/offers/' + encodeURIComponent(b.dataset.offerDismiss) + '/dismiss', { method: 'POST' }); toast('Noted. I will not offer that again.'); await refresh(); } catch (err) { toast(err.message, true); }
  }));
  $$('[data-todo]', el).forEach((cb) => cb.addEventListener('change', async () => {
    try { await api('/todos/' + cb.dataset.todo, { method: 'PATCH', json: { done: cb.checked } }); toast('Ticked off.'); await refresh(); } catch (err) { cb.checked = !cb.checked; toast(err.message, true); }
  }));
  loadPics(el);
}

/* ── dock: the FAB, the ask bar in a deep layer ───────────────── */

function updateDock(cat) {
  const bar = $('#askBar');
  if (cat) { bar.hidden = false; $('#askInput').placeholder = (CTX[cat] || CTX.notice).ask; $('#askInput').setAttribute('aria-label', (CTX[cat] || CTX.notice).ask.replace('…', '')); }
  else bar.hidden = true;
  document.body.classList.toggle('ask-mode', !!cat);
}
$('#askBar').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const v = $('#askInput').value.trim(); if (!v) { setChat(true); return; }
  $('#askInput').value = ''; setChat(true); sendChat(v);
});

/* Tap: chat. Press and hold (500 ms): hear the day. */
const fab = $('#fab');
let holdTimer = null, held = false;
fab.addEventListener('pointerdown', (ev) => {
  if (ev.button !== 0) return;
  held = false; fab.classList.add('pressing');
  holdTimer = setTimeout(() => { held = true; fab.classList.remove('pressing'); if (navigator.vibrate) try { navigator.vibrate(12); } catch (e) { /* no haptics */ } startSummary(); }, 500);
});
['pointerup', 'pointerleave', 'pointercancel'].forEach((t) => fab.addEventListener(t, () => { clearTimeout(holdTimer); fab.classList.remove('pressing'); }));
fab.addEventListener('click', (ev) => { if (held) { held = false; ev.preventDefault(); return; } setChat(!S.chatOpen); });
fab.addEventListener('contextmenu', (ev) => ev.preventDefault());

/* ── chat ─────────────────────────────────────────────────────── */

function readThread() { try { return JSON.parse(sessionStorage.getItem('familyos.orbit.thread') || '[]'); } catch (e) { return []; } }
function writeThread() { try { sessionStorage.setItem('familyos.orbit.thread', JSON.stringify(S.chat.slice(-30))); } catch (e) { /* storage off */ } }

function setChat(open) {
  S.chatOpen = open;
  document.body.classList.toggle('chat-open', open);
  $('#chat').hidden = !open;
  fab.setAttribute('aria-expanded', String(open));
  if (open) { closeModal(); paintChat(); setTimeout(() => $('#chatInput').focus(), 30); }
  else fab.focus({ preventScroll: true });
}
$('#chatClose').addEventListener('click', () => setChat(false));
$('#chatListen').addEventListener('click', () => { setChat(false); startSummary(); });
$('#chatClear').addEventListener('click', () => { S.chat = []; writeThread(); paintChat(); });

function bubble(t) {
  if (t.role === 'user') return '<div class="bubble me">' + esc(t.content) + '</div>';
  if (t.pending) return t.content ? '<div class="bubble them pending-text">' + esc(t.content) + '<span class="caret" aria-hidden="true">▍</span></div>'
    : '<div class="bubble them pending"><span></span><span></span><span></span></div>';
  let text = esc(t.content || '');
  (t.citations || []).forEach((c) => {
    const link = c.artifact_id ? '<button class="cite" data-cite="' + esc(c.artifact_id) + '" title="' + esc(c.text) + '">' + esc(c.ref) + '</button>' : '<span class="cite" title="' + esc(c.text) + '">' + esc(c.ref) + '</span>';
    text = text.split('[' + c.ref + ']').join(link);
  });
  return '<div class="bubble them' + (t.error ? ' bad' : '') + '">' + text
    + (t.note ? '<div class="b-note">' + esc(t.note) + '</div>' : '')
    + (t.grounded === false && !t.error && !t.note && !(t.proposals || []).length ? '<div class="b-ungrounded">Not pointing at any notice; treat it as conversation, not fact.</div>' : '')
    + (t.proposals || []).map((p, i) => proposalCard(p, i)).join('') + '</div>';
}

function proposalCard(p, i) {
  const m = S.model;
  const when = (d, tm) => (d ? D.fmtDay(d, m.today) + (tm ? ' ' + String(tm).slice(0, 5) : '') : '');
  let body;
  if (p.kind === 'assign') body = 'Hand <b>' + esc(p.headline || 'the notice') + '</b> to <b>' + esc(p.member_name || '?') + '</b>' + (p.note ? ' — “' + esc(p.note) + '”' : '');
  else if (p.kind === 'todo') body = 'To-do: <b>' + esc(p.title || '') + '</b>' + (p.due_date ? ' by ' + esc(when(p.due_date, p.due_time)) : '') + (p.member_name ? ' — ' + esc(p.member_name) + '’s' : '');
  else if (p.kind === 'handled') body = 'Mark <b>' + esc(p.headline || 'the notice') + '</b> handled' + (p.note ? ' — “' + esc(p.note) + '”' : '');
  else if (p.kind === 'plan') body = 'Plan <b>' + esc(p.title || 'this') + '</b>: an itinerary and the legwork as to-dos. Nothing is booked.';
  else if (p.kind === 'errand') body = (p.look ? 'Look on <b>' : 'Errand on <b>') + esc(p.label || p.service) + '</b>: <b>' + esc(p.what || p.title) + '</b>' + (p.due_date ? ' — ' + esc(when(p.due_date, p.due_time)) : '') + (p.look ? '. Reads only; buys nothing.' : '. Written down for a guardian to approve; paid after the service, by you.');
  else body = (p.status === 'accepted' ? 'Accept' : 'Dismiss') + ' <b>' + esc(p.title || 'the date') + '</b>';
  const done = p.done ? '<span class="done">' + icon('check', 14, 2.2) + ' done</span>' + (p.link ? ' <a href="' + esc(p.link) + '">Open</a>' : '') : '';
  return '<div class="proposal' + (p.ok ? '' : ' off') + '" data-proposal="' + i + '"><span>' + body + (p.why ? '<br><small>' + esc(p.why) + '</small>' : '') + '</span>'
    + (p.ok && !p.done ? '<button class="btn sm primary" data-confirm>Confirm</button>' : done) + '</div>';
}

function paintChat() {
  const th = $('#thread');
  const m = S.model;
  th.innerHTML = S.chat.length ? S.chat.map(bubble).join('')
    : '<div class="chat-hello"><p>Ask about anything in the family’s record, or say what should happen. I can propose a to-do, a handover or an errand; one of you confirms it.</p>'
      + '<div class="chips">' + ['What needs someone this week?', 'What do we pay every month?', 'What is still undecided?', 'When did the plumber last come?'].map((q) => '<button class="chip" data-try>' + esc(q) + '</button>').join('') + '</div></div>';
  $$('[data-try]', th).forEach((b) => b.addEventListener('click', () => sendChat(b.textContent)));
  $$('[data-cite]', th).forEach((b) => b.addEventListener('click', () => { setChat(false); const cur = currentLayers(); navigate((cur.length ? hashFor(cur) : '#/dashboard') + '/notice/' + b.dataset.cite, { via: !cur.length }); }));
  $$('[data-confirm]', th).forEach((b) => b.addEventListener('click', () => confirmProposal(b)));
  th.scrollTop = th.scrollHeight;
  void m;
}

async function confirmProposal(b) {
  const cardEl = b.closest('[data-proposal]');
  const bubbleEl = cardEl.closest('.bubble');
  const turns = S.chat.filter((t) => t.role === 'assistant' && !t.pending);
  const turn = turns[$$('#thread .bubble.them:not(.pending)').indexOf(bubbleEl)];
  const p = turn && turn.proposals[Number(cardEl.dataset.proposal)];
  if (!p) return;
  b.disabled = true;
  try {
    if (p.kind === 'assign') await api('/artifacts/' + p.artifact_id + '/assign', { method: 'POST', json: { member_id: p.member_id, note: p.note } });
    else if (p.kind === 'todo') await api('/todos', { method: 'POST', json: { title: p.title, due_date: p.due_date, due_time: p.due_time, assigned_to: p.member_id, note: p.note } });
    else if (p.kind === 'handled') await api('/artifacts/' + p.artifact_id + '/handled', { method: 'POST', json: { note: p.note } });
    else if (p.kind === 'plan') { b.textContent = 'Planning…'; const made = await api('/plans', { method: 'POST', json: { brief: p.brief, shape: p.shape || 'trip' } }); p.link = '/app/#/plans/' + made.id; }
    else if (p.kind === 'errand') { const made = await api('/errands', { method: 'POST', json: { service: p.service, kind: p.look ? 'look' : 'booking', title: p.title || p.what, spec: { what: p.what || p.title, details: p.details, when: { date: p.due_date, time: p.due_time ? String(p.due_time).slice(0, 5) : null, part: p.part || 'any' }, max_amount: p.max_amount, currency: p.currency || 'INR', payment: 'pay_after_service' } } }); p.link = '/app/#/errands/' + made.id; }
    else await api('/obligations/' + p.obligation_id + '/decision', { method: 'POST', json: { status: p.status } });
    p.done = true;
    toast(p.kind === 'assign' ? 'Handed over.' : p.kind === 'todo' ? 'Added.' : p.kind === 'handled' ? 'Handled.' : p.kind === 'plan' ? 'Planned.' : p.kind === 'errand' ? 'Written down for approval.' : 'Decided.');
    writeThread(); paintChat();
    refresh();
  } catch (err) { b.disabled = false; toast((err && err.message) || 'That did not go through.', true); }
}

/* The answer as it is written: say deltas from /chat/stream into the pending
   bubble, then the finished turn. Falls back to the whole turn. */
async function chatStream(payload, onDelta) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
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

async function sendChat(text) {
  text = (text || '').trim(); if (!text) return;
  S.chat.push({ role: 'user', content: text }, { role: 'assistant', pending: true });
  writeThread(); paintChat();
  const input = $('#chatInput'); input.value = ''; input.disabled = true;
  try {
    const history = S.chat.filter((t) => !t.pending && t.content).slice(-13, -1).map((t) => ({ role: t.role, content: t.content }));
    let frame = 0;
    const turn = await chatStream({ message: text, history }, (said) => {
      S.chat[S.chat.length - 1].content = said.replace(/\s*\[[A-Za-z]+\d*\]/g, '');
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; paintChat(); });
    });
    S.chat.pop();
    S.chat.push({ role: 'assistant', content: turn.say, grounded: turn.grounded, note: turn.note || null, citations: turn.citations, proposals: turn.proposals });
  } catch (err) {
    S.chat.pop();
    S.chat.push({ role: 'assistant', content: (err && err.message) || 'Something went wrong.', error: true });
  }
  input.disabled = false; if (S.chatOpen) input.focus();
  writeThread(); paintChat();
}
$('#chatForm').addEventListener('submit', (ev) => { ev.preventDefault(); sendChat($('#chatInput').value); });

/* The microphone: the browser's own speech recognition, where there is one. */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function wireMic(btn, input, onFinal) {
  if (!SR) { btn.hidden = true; return; }
  let rec = null;
  btn.addEventListener('click', () => {
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = 'en-IN'; rec.interimResults = true; rec.maxAlternatives = 1;
    btn.classList.add('live'); btn.setAttribute('aria-pressed', 'true');
    rec.onresult = (e) => { const r = e.results[e.results.length - 1]; input.value = r[0].transcript; if (r.isFinal) onFinal(input.value); };
    rec.onend = () => { rec = null; btn.classList.remove('live'); btn.setAttribute('aria-pressed', 'false'); };
    rec.onerror = () => { toast('The microphone did not pick anything up.', true); };
    try { rec.start(); } catch (e) { rec = null; btn.classList.remove('live'); }
  });
}
wireMic($('#chatMic'), $('#chatInput'), (v) => sendChat(v));

/* ── hold to listen: the day, read aloud ──────────────────────── */

const speech = { active: false, idx: 0, lines: [] };
function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
function listTitles(items, n) {
  const t = items.slice(0, n).map((x) => x.title);
  if (t.length <= 1) return t.join('');
  return t.slice(0, -1).join('; ') + '; and ' + t[t.length - 1];
}
function buildSummary() {
  const m = S.model, L = [];
  const h = new Date().getHours();
  L.push('Good ' + (h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening') + ', ' + firstName(m.me.display_name) + '. Here is the day for ' + m.household.name + '.');
  const missed = m.brief.filter((i) => i.reason === 'missed'), overdue = m.brief.filter((i) => i.reason === 'overdue'), und = m.brief.filter((i) => i.reason === 'undecided');
  if (missed.length) L.push(plural(missed.length, 'thing', 'things') + ' went by without anyone deciding: ' + listTitles(missed, 3) + '.');
  if (overdue.length) L.push(plural(overdue.length, 'accepted date has', 'accepted dates have') + ' passed: ' + listTitles(overdue, 2) + '.');
  if (und.length) L.push(plural(und.length, 'date waits', 'dates wait') + ' for a decision: ' + listTitles(und, 2) + '.');
  if (m.errandsNeedYou.length) L.push('An errand needs a person to take over: ' + m.errandsNeedYou[0].title + '.');
  if (!missed.length && !overdue.length && !und.length && !m.errandsNeedYou.length) L.push('Nothing needs you right now.');
  if (m.todayItems.length) L.push('Today: ' + m.todayItems.slice(0, 3).map((x) => x.title + (x.time ? ' at ' + x.time : '')).join('; ') + '.');
  else L.push('Nothing is dated today.');
  const soon = m.week.filter((x) => x.date > m.today).slice(0, 3);
  const rel = (iso) => { const d = D.fmtDay(iso, m.today); return /^(Today|Tomorrow|Yesterday)$/.test(d) ? d.toLowerCase() : 'on ' + d; };
  if (soon.length) L.push('Coming up: ' + soon.map((x) => x.title + ' ' + rel(x.date)).join('; ') + '.');
  if (m.moneyLine) L.push(m.moneyLine + ', from the receipts I have read. I do not pay anything; a pay link opens the biller’s own page.');
  const doing = [];
  if (m.errandsActive.length) doing.push(plural(m.errandsActive.length, 'errand is', 'errands are') + ' in hand: ' + m.errandsActive.slice(0, 2).map((e) => e.title).join('; '));
  const fyi = m.offers.filter((o) => o.fyi);
  fyi.slice(0, 1).forEach((o) => doing.push(o.title.replace(/\.$/, '')));
  const pending = m.reminders.filter((r) => r.status === 'pending').length;
  if (pending) doing.push(plural(pending, 'reminder is', 'reminders are') + ' set to go out');
  if (doing.length) L.push('What I am doing: ' + doing.join('. ') + '.');
  if (m.todos.length) L.push(plural(m.todos.length, 'to-do is', 'to-dos are') + ' open.');
  L.push('Every date, task and errand still waits for one of you to approve it.');
  return L;
}

function startSummary() {
  if (!S.model) return;
  stopSpeech(true);
  setChat(false);
  speech.lines = buildSummary(); speech.idx = 0;
  const box = $('#speech');
  box.hidden = false;
  $('#speechText').innerHTML = speech.lines.map((l, i) => '<p data-line="' + i + '">' + esc(l) + '</p>').join('');
  const can = 'speechSynthesis' in window && typeof SpeechSynthesisUtterance === 'function';
  $('#speechNote').textContent = can ? '' : 'This browser cannot speak, so here is the summary to read.';
  $('#speechStop').focus();
  if (!can) return;
  speech.active = true; document.body.classList.add('speaking'); kick();
  const say = () => {
    if (!speech.active) return;
    if (speech.idx >= speech.lines.length) { speech.active = false; document.body.classList.remove('speaking'); $('#speechStop').innerHTML = icon('close', 16) + ' Close'; return; }
    $$('#speechText p').forEach((p, i) => p.classList.toggle('now', i === speech.idx));
    const cur = $('#speechText p.now'); if (cur) cur.scrollIntoView({ block: 'nearest', behavior: reducedQuery.matches ? 'auto' : 'smooth' });
    const u = new SpeechSynthesisUtterance(speech.lines[speech.idx]);
    u.lang = 'en-IN'; u.rate = S.seg === 'senior' ? 0.88 : 1;
    u.onend = () => { speech.idx++; say(); };
    u.onerror = () => { speech.active = false; document.body.classList.remove('speaking'); };
    speechSynthesis.speak(u);
  };
  $('#speechStop').innerHTML = icon('stop', 16) + ' Stop';
  say();
}
function stopSpeech(keepOpen) {
  speech.active = false; document.body.classList.remove('speaking');
  try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) { /* nothing speaking */ }
  if (!keepOpen) { $('#speech').hidden = true; fab.focus({ preventScroll: true }); }
}
$('#speechStop').addEventListener('click', () => stopSpeech());

/* ── sign in ──────────────────────────────────────────────────── */

function showGate(notice) {
  document.body.classList.add('gated');
  $('#app').inert = true;
  const g = $('#gate');
  g.hidden = false;
  g.innerHTML = '<div class="gate-card glass"><h1>FamilyOS</h1><p class="lede">School notices, bills and forms turned into things that get done, without losing track of where each fact came from.</p>'
    + (notice ? '<p class="gate-notice" role="alert">' + esc(notice) + '</p>' : '')
    + '<button class="btn primary wide" data-google>Continue with Google</button>'
    + '<div class="or"><span>or</span></div>'
    + '<form data-link><label for="gEmail">Your email</label><input id="gEmail" type="email" name="email" required autocomplete="email" placeholder="you@example.com">'
    + '<button class="btn wide" type="submit">Email me a link</button><p class="sent" data-sent hidden></p></form>'
    + '<details><summary>I have a token</summary><form data-token><label for="gTok">Sign-in token</label><input id="gTok" type="password" name="token" autocomplete="off" required placeholder="fos_…"><button class="btn wide" type="submit">Sign in</button></form></details>'
    + '<p class="small">Google sign-in returns you to the full app; come back to /orbit/ after, you will be signed in.</p></div>';
  $('[data-google]', g).addEventListener('click', async () => { try { const w = await api('/sign-in/google'); location.href = w.url; } catch (e) { toast(e.message, true); } });
  $('[data-link]', g).addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const email = new FormData(ev.target).get('email').trim(); if (!email) return;
    try { await api('/sign-in/request', { method: 'POST', json: { email } }); } catch (e) { /* the same answer either way */ }
    const s = $('[data-sent]', g); s.hidden = false; s.textContent = 'If ' + email + ' can sign in, a link is on its way. It works once and lasts 15 minutes.';
  });
  $('[data-token]', g).addEventListener('submit', async (ev) => {
    ev.preventDefault();
    S.token = new FormData(ev.target).get('token').trim();
    try { await start(); } catch (e) { S.token = null; toast('That token was not accepted.', true); }
  });
  field.configure({ stage: 7, status: 'calm', agents: [], notes: [] });
  kick();
}

async function redeemLink() {
  const params = new URLSearchParams(location.search);
  const link = params.get('link');
  if (!link) return;
  params.delete('link');
  const clean = location.pathname + (params.toString() ? '?' + params : '') + location.hash;
  history.replaceState(null, '', clean);
  try {
    const signed = await api('/sign-in/redeem', { method: 'POST', json: { link } });
    S.token = signed.token; writeToken(S.token);
  } catch (e) {
    S.token = null; writeToken(null);
    throw new Error('That link has expired or has already been used. Ask for another.');
  }
}

function takeFragmentToken() {
  const mt = location.hash.match(/^#token=([^&]+)/);
  if (!mt) return;
  S.token = decodeURIComponent(mt[1]); writeToken(S.token);
  history.replaceState(null, '', location.pathname + location.search);
}

async function refresh() {
  try {
    S.model = await D.loadAll(api);
    renderHome();
    rerenderLayers();
  } catch (e) { if (e.status !== 401) toast(e.message || 'Could not refresh.', true); }
}

async function start() {
  S.model = await D.loadAll(api);
  writeToken(S.token);
  S.booted = true;
  document.body.classList.remove('gated');
  $('#gate').hidden = true; $('#gate').innerHTML = '';
  $('#app').inert = false;
  applyStage();
  S.chat = readThread();
  renderHome();
  const layers = currentLayers();
  history.replaceState({ orbit: 1, depth: layers.length, floor: layers.length }, '', location.href);
  applyRoute();
  document.body.classList.add('ready');
}

async function boot() {
  applyStage();
  kick();
  takeFragmentToken();
  try { await redeemLink(); } catch (e) { showGate(e.message); return; }
  if (!S.token) { showGate(); return; }
  try { await start(); }
  catch (e) { if (e.status === 401 || !S.token) showGate('Sign in to see the family’s orbit.'); else { showGate(); toast(e.message || 'The server could not be reached.', true); } }
}
boot();
