/* The cockpit: the same console as /app with the design review's eight
   priorities applied. app.js looks for window.COCKPIT_UI and, when it is
   there, asks it for the chrome, Today, the sign-in screen, the Ask bar and
   a More page; everything else (notices, family, plans, money, settings) is
   app.js's own, drawn in this shell's look.

   This file is loaded before app.js and uses its functions only when called,
   after both have loaded.

   1  Today is a decision queue: needs you now, then handled, then coming up.
   2  One obligation is one row, however many notices, calendars and lists say it.
   3  Five jobs in the navigation; the rest is under More.
   4  A decision row says Private or Shared, who it is about and where it came
      from; selecting it opens the evidence beside the page.
   5  Labelled 44px buttons, and a short Undo after a decision, a hand-over or a done.
   6  One look (cockpit.css).
   7  Ask is a bar on a laptop and the middle of the tab bar on a phone.
   8  Sign-in sells the trust before it asks for an address. */
(function () {
  'use strict';

  /* ── small helpers ───────────────────────────────────────────── */

  const clock = (t) => {
    const m = /^(\d{1,2}):(\d{2})/.exec(String(t || ''));
    if (!m) return t ? String(t) : '';
    const h = +m[1];
    return ((h % 12) || 12) + ':' + m[2] + ' ' + (h >= 12 ? 'pm' : 'am');
  };
  const dayDiff = (iso) => {
    const t = new Date(); t.setHours(0, 0, 0, 0);
    return Math.round((new Date(iso + 'T00:00:00') - t) / 86400000);
  };
  const weekday = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { weekday: 'long' });
  const shortDay = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });

  /* "Due today, 4:00 pm" -- what a person asks of a date. */
  function when(date, time) {
    if (!date) return 'No date yet';
    const d = dayDiff(date), at = time ? ', ' + clock(time) : '';
    if (d === 0) return 'Due today' + at;
    if (d === 1) return 'Due tomorrow' + at;
    if (d === -1) return 'Was due yesterday';
    if (d < 0) return 'Was due ' + (-d) + ' days ago';
    if (d < 7) return 'Due ' + weekday(date) + at;
    return 'Due ' + shortDay(date) + at;
  }

  const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
  /* The same thing said twice: equal words, or one inside the other when it is long enough to mean something. */
  const same = (a, b) => a === b || (a.length >= 8 && b.includes(a)) || (b.length >= 8 && a.includes(b));

  /* ── 5: undo ─────────────────────────────────────────────────── */

  const pending = new Set();
  function flushAll() { Array.from(pending).forEach((f) => f()); }
  window.addEventListener('pagehide', flushAll);
  window.addEventListener('hashchange', flushAll);   // a decision is committed when the person moves on

  function snack(message, label, onUndo, ms) {
    document.querySelectorAll('.ck-undo').forEach((n) => n.remove());
    const el = document.createElement('div');
    el.className = 'ck-undo'; el.setAttribute('role', 'status');
    el.innerHTML = '<span>' + esc(message) + '</span><button type="button" class="btn ghost" data-undo>' + esc(label || 'Undo') + '</button>';
    document.body.appendChild(el);
    el.querySelector('[data-undo]').addEventListener('click', () => { el.remove(); onUndo(); });
    setTimeout(() => el.remove(), ms || 7000);
    return el;
  }

  /* A decision that waits six seconds before it is made: the row leaves at
     once, Undo brings it back and nothing was sent; otherwise it is sent. */
  function deferred(message, commit, hide, restore) {
    flushAll();
    hide();
    let done = false, timer;
    const finish = async (run) => {
      if (done) return;
      done = true; clearTimeout(timer); pending.delete(flush);
      document.querySelectorAll('.ck-undo').forEach((n) => n.remove());
      if (!run) { restore(); return; }
      try { await commit(); } catch (err) { fail(err); restore(); }
    };
    const flush = () => finish(true);
    pending.add(flush);
    snack(message, 'Undo', () => finish(false), 6000);
    timer = setTimeout(flush, 6000);
  }

  /* An action already done, with a way back: a hand-over, a done. */
  function reversible(message, reverse) {
    snack(message, 'Undo', async () => {
      try { await reverse(); flash('Undone.'); } catch (err) { fail(err); }
      render().catch(() => {});
    }, 8000);
  }

  /* ── 3: the navigation ───────────────────────────────────────── */

  const PRIMARY = new Set(['home', 'notices', 'life', 'family', 'plans', 'chat']);
  const SPACE_NAV = new Set(['money', 'space:school', 'space:health', 'space:travel', 'space:invest', 'space:home']);

  function chrome(active) {
    const link = (id, name, label, extra, attrs) =>
      '<a href="#/' + id + '"' + (attrs || '') + (active === id || (id === 'today' && active === 'today') ? ' aria-current="page"' : '') + '>'
      + '<span class="g">' + icon(name, 20) + '</span><span class="l">' + label + '</span>' + (extra || '') + '</a>';
    const dark = theme() === 'dark';
    const inMore = !PRIMARY.has(active) && !SPACE_NAV.has(active);
    const needs = store.needCount ? '<span class="count" data-needs-badge>' + store.needCount + '</span>' : '<span class="count" data-needs-badge hidden></span>';
    const space = (key, label, ic, hue) => {
      const id = key === 'money' ? 'money' : 'space/' + key;
      const cur = active === (key === 'money' ? 'money' : 'space:' + key);
      return '<a href="#/' + id + '"' + (cur ? ' aria-current="page"' : '') + '><span class="g" style="color:var(--' + hue + ')">' + icon(ic, 20) + '</span><span class="l">' + label + '</span></a>';
    };
    return '<aside class="side">'
      + '<div class="brand"><span class="mark">' + icon('home', 16) + '</span><b>FamilyOS</b></div>'
      + '<nav class="nav" aria-label="Main">'
      + '<a href="#/today" data-tab' + (active === 'home' ? ' aria-current="page"' : '') + '><span class="g">' + icon('today', 22) + '</span><span class="l">Today</span></a>'
      + '<a href="#/notices" data-tab' + (active === 'notices' ? ' aria-current="page"' : '') + '><span class="g">' + icon('mail', 22) + '</span><span class="l">Inbox</span>' + needs + '</a>'
      + '<a href="#/chat" class="ck-ask-tab" data-tab' + (active === 'chat' ? ' aria-current="page"' : '') + '><span class="fab">' + icon('sparkle', 22) + '</span><span class="l">Ask</span></a>'
      + '<a href="#/family" data-tab' + (active === 'life' || active === 'family' ? ' aria-current="page"' : '') + '><span class="g">' + icon('family', 22) + '</span><span class="l">Family</span></a>'
      + '<a href="#/plans"' + (active === 'plans' ? ' aria-current="page"' : '') + '><span class="g">' + icon('calendar', 22) + '</span><span class="l">Plans</span></a>'
      + '<a href="#" data-open-search><span class="g">' + icon('search', 22) + '</span><span class="l">Search</span><span class="kbd" style="margin-left:auto">⌘K</span></a>'
      + '<span class="group">Spaces</span>'
      + space('school', 'School', 'school', 'school') + space('money', 'Money', 'money', 'money') + space('health', 'Health', 'health', 'health')
      + space('travel', 'Travel', 'travel', 'travel') + space('invest', 'Investments', 'invest', 'invest')
      + '<span class="group"></span>'
      + '<a href="#/more" data-tab' + (inMore ? ' aria-current="page"' : '') + '><span class="g">' + icon('more', 22) + '</span><span class="l">More</span>'
      + (store.quarantineCount ? '<span class="count">' + store.quarantineCount + '</span>' : '') + '</a>'
      + '</nav>'
      + '<div class="who"><span class="avatar">' + esc(initial(store.me && store.me.display_name)) + '</span>'
      + '<span class="name">' + esc(store.me ? store.me.display_name : '') + '</span>'
      + '<button class="icon-btn" data-theme-toggle title="' + (dark ? 'Switch to light' : 'Switch to dark') + '" aria-label="' + (dark ? 'Switch to light' : 'Switch to dark') + '">' + icon(dark ? 'sun' : 'moon', 18) + '</button>'
      + '<button class="icon-btn" data-signout title="Sign out" aria-label="Sign out">' + icon('logout', 18) + '</button></div>'
      + '</aside>';
  }

  /* After a page is drawn: the Inbox badge says how many decisions wait. */
  let badgeAt = 0;
  async function after(route) {
    wireAskBar();
    if (route && route.view === today) return;   // Today counts its own rows
    if (Date.now() - badgeAt < 20000 && store.needCount !== undefined) return paintBadge();
    badgeAt = Date.now();
    try {
      // The same rows Today draws, counted the same way, so the badge and "Needs you now" never disagree.
      const [b, proposed] = await Promise.all([api('/brief?limit=40'), api('/obligations?status=proposed&limit=100').catch(() => [])]);
      store.needCount = decisions(b, proposed, {}).length;
      paintBadge();
    } catch (e) { /* the badge is a courtesy */ }
  }
  function paintBadge() {
    const el = document.querySelector('[data-needs-badge]');
    if (!el) return;
    el.textContent = store.needCount || '';
    el.hidden = !store.needCount;
  }

  /* More: everything that is not one of the five jobs or a space. */
  async function more(main) {
    main.classList.remove('chat-main');
    const guardian = store.me && store.me.role === 'guardian';
    const tile = (href, ic, title, sub, badge) =>
      '<a class="card lift ck-tile" href="' + href + '"><span class="ic">' + icon(ic, 22) + '</span><span class="grow"><b>' + title + '</b><span class="muted">' + sub + '</span></span>'
      + (badge ? '<span class="count">' + badge + '</span>' : '') + '</a>';
    main.innerHTML = '<div class="ck-head"><div><h1>More</h1><p class="day">The rest of FamilyOS, out of the way until you need it.</p></div></div>'
      + '<div class="ck-sections">'
      + '<section><h2 class="ck-h">Plans and search</h2><div class="ck-tiles">'
      + tile('#/plans', 'calendar', 'Plans', 'Trips, meals, anything with steps')
      + '<a class="card lift ck-tile" href="#" data-open-search><span class="ic">' + icon('search', 22) + '</span><span class="grow"><b>Search</b><span class="muted">Notices, dates, people, documents</span></span></a>'
      + tile('#/memories', 'memories', 'Memories', 'Photos the family shared')
      + '</div></section>'
      + '<section><h2 class="ck-h">Waiting on you</h2><div class="ck-tiles">'
      + tile('#/waiting', 'bell', 'Waiting on you', 'Everything undecided, in one list')
      + tile('#/errands', 'cart', 'Errands', 'Things FamilyOS does on sites for you, each one approved')
      + '</div></section>'
      + (guardian ? '<section><h2 class="ck-h">Looking after the record</h2><div class="ck-tiles">'
        + tile('#/quarantine', 'shield', 'Quarantine', 'Mail from strangers, held until you look', store.quarantineCount || '')
        + tile('#/revisions', 'refresh', 'Revisions', 'A later notice that changes an earlier one', store.amendmentCount || '')
        + tile('#/collect', 'download', 'Collect', 'Bring in what sites hold for you')
        + tile('#/audit', 'list', 'Audit', 'Every change, who made it and when')
        + '</div></section>' : '')
      + '<section><h2 class="ck-h">Looking after someone far away</h2><div class="ck-tiles">'
      + '<button class="card lift ck-tile" type="button" data-more-report><span class="ic">' + icon('shield', 22) + '</span><span class="grow"><b>Report a call or a message</b><span class="muted">Check it for the shapes of a scam</span></span></button>'
      + tile('#/constitution', 'list', 'Rules and access', 'What is always true, who sees what, and the household\u2019s rules')
      + (store.household ? store.household.members.filter((x) => x.circle_role === 'parent').map((x) => tile('#/care/' + esc(x.id), 'family', esc(x.display_name), 'Papers, bills, appointments and warnings')).join('') : '')
      + '</div></section>'
      + '<section><h2 class="ck-h">The household</h2><div class="ck-tiles">'
      + tile('#/household', 'settings', 'Settings', 'People, places, rules, connections, devices')
      + '<button class="card lift ck-tile" type="button" data-more-theme><span class="ic">' + icon(theme() === 'dark' ? 'sun' : 'moon', 22) + '</span><span class="grow"><b>' + (theme() === 'dark' ? 'Light appearance' : 'Dark appearance') + '</b><span class="muted">For this browser</span></span></button>'
      + '<button class="card lift ck-tile" type="button" data-more-signout><span class="ic">' + icon('logout', 22) + '</span><span class="grow"><b>Sign out</b><span class="muted">Ends this session only</span></span></button>'
      + '</div></section></div>';
    main.querySelector('[data-more-report]').addEventListener('click', () => reportCall());
    main.querySelector('[data-more-theme]').addEventListener('click', async () => { setTheme(theme() === 'dark' ? 'light' : 'dark'); await render(); });
    main.querySelector('[data-more-signout]').addEventListener('click', () => { signOut().catch(() => forget()); });
    main.querySelectorAll('[data-open-search]').forEach((a) => a.addEventListener('click', (ev) => { ev.preventDefault(); openPalette(); }));
  }

  /* ── 7: Ask ──────────────────────────────────────────────────── */

  /* The bar is a real field: type a question and press Enter or the arrow, and
     Ask opens with it answered. Search is the other half (Ctrl or Cmd K). */
  function askBar() {
    return '<form class="askbar ck-ask" data-ck-askform role="search" aria-label="Ask FamilyOS"><span class="star">' + icon('sparkle', 20) + '</span>'
      + '<input class="ph" name="q" type="text" autocomplete="off" placeholder="Ask about a notice, date, bill or plan…" aria-label="Ask FamilyOS" maxlength="500">'
      + '<button class="ib" type="button" data-ck-attach title="Add a notice or a photo" aria-label="Add a notice or a photo">' + icon('attach', 20) + '</button>'
      + '<button class="ib" type="button" data-ck-mic title="Say it" aria-label="Say it">' + icon('mic', 20) + '</button>'
      + '<button class="send" type="submit" aria-label="Ask">' + icon('arrow-up', 20) + '</button></form>';
  }
  function wireAskBar() {
    const form = document.querySelector('[data-ck-askform]');
    if (!form) return;
    const input = form.querySelector('input');
    form.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const q = input.value.trim();
      if (!q) { input.focus(); return; }
      input.value = '';
      if (/spend|spending|pay every|bills?\b|subscriptions?/i.test(q) && !/plan|book|order/i.test(q)) { go('/money'); return; }
      openAsk(q);
    });
    form.querySelector('[data-ck-attach]').addEventListener('click', () => go('/notices'));
    form.querySelector('[data-ck-mic]').addEventListener('click', () => listen((t) => { input.value = t; form.requestSubmit(); }));
  }

  /* ── 8: sign-in ──────────────────────────────────────────────── */

  function gate(opts) {
    const newEmail = (opts && opts.newEmail) || '';
    return '<div class="ck-gate">'
      + '<section class="ck-hero"><div class="ck-brand">' + icon('home', 18) + '<b>FamilyOS</b></div>'
      + '<h1>The family’s loose ends, gathered and carried.</h1>'
      + '<p>School notices, bills, forms and plans become clear decisions — with the original source always one tap away.</p>'
      + '<ul class="ck-promises"><li><b>Private by default</b><span>Nothing is shared until you say so.</span></li>'
      + '<li><b>Source-backed facts</b><span>Every date shows the words it came from.</span></li>'
      + '<li><b>You approve every action</b><span>FamilyOS never pays or books on its own.</span></li></ul></section>'
      + '<section class="ck-form">'
      + '<div data-panel="in"' + (newEmail ? ' hidden' : '') + '>'
      + '<h2>Welcome back</h2><p class="muted">Sign in to your household.</p>'
      + '<button class="btn ghost ck-google" data-google type="button"><span class="gmark">G</span>Continue with Google</button>'
      + '<div class="ck-or"><span>or use email</span></div>'
      + '<form class="stack" data-form="link"><label>Email address<input type="email" name="email" placeholder="you@example.com" required autocomplete="email"></label>'
      + '<button class="btn" type="submit">Send a secure sign-in link</button><p class="sub" data-linksent hidden></p></form>'
      + '<p class="ck-trust">' + icon('shield', 20) + '<span>Google shares only your email for sign-in. Mail access is a separate, optional connection after you enter.</span></p>'
      + '<details class="ck-token"><summary>I have a token</summary><form class="stack" data-form="in"><label>Sign-in token<input type="password" name="token" placeholder="fos_…" autocomplete="off" required></label>'
      + '<button class="btn ghost" type="submit">Sign in</button></form></details>'
      + '<p class="ck-new">New to FamilyOS? <button class="linklike" type="button" data-tab="new">Start a household</button></p></div>'
      + '<div data-panel="new"' + (newEmail ? '' : ' hidden') + '>'
      + '<h2>Start a household</h2>'
      + (newEmail ? '<p class="muted">Google confirmed <b>' + esc(newEmail) + '</b>. No household uses it yet — start one and you will be its first guardian.</p>'
        : '<p class="muted">You will be its first guardian. Everything stays private until you share it.</p>')
      + '<form class="stack" data-form="new"><label>Household name<input type="text" name="name" placeholder="The Iyer family" required maxlength="100"' + (newEmail ? ' autofocus' : '') + '></label>'
      + '<label>Your name<input type="text" name="display_name" placeholder="Amma" required maxlength="100"></label>'
      + '<label>Your email<input type="email" name="email" placeholder="you@example.com" required value="' + esc(newEmail) + '"></label>'
      + '<button class="btn" type="submit">Create household</button></form>'
      + '<p class="ck-new">Already have one? <button class="linklike" type="button" data-tab="in">Sign in</button></p></div>'
      + '</section></div>';
  }

  /* ── 1, 2, 4: Today ──────────────────────────────────────────── */

  /* Reasons that are a call for a person today; the rest are facts for the
     lists they belong to. */
  const CALLS = { scam: -1, missed: 0, overdue: 1, today: 2, amendment: 3, quarantine: 3, mailbox: 3, undecided: 4 };
  const REASON_WORDS = { scam: 'Scam?', missed: 'Missed', overdue: 'Overdue', today: 'Today', amendment: 'Changed', quarantine: 'Held', mailbox: 'Mailbox', undecided: 'To decide' };

  /* One row per obligation: the brief's items and the proposed dates, joined
     by obligation id, then by the same words on the same day (two notices that
     say one thing are one thing, and say so). */
  function decisions(brief, proposed, byArtifact) {
    const rows = [];
    const add = (r) => {
      const words = norm(r.title);
      const twin = rows.find((x) => (r.obligationId && x.obligationId === r.obligationId)
        || (x.due === r.due && x.due && same(norm(x.title), words)));
      if (!twin) { rows.push(Object.assign({ alsoIn: 0 }, r)); return; }
      if (twin.obligationId !== r.obligationId || twin.artifactId !== r.artifactId) twin.alsoIn += 1;
      if (CALLS[r.reason] < CALLS[twin.reason]) { twin.reason = r.reason; twin.why = r.why || twin.why; }
      twin.obligationId = twin.obligationId || r.obligationId;
      if (r.status === 'proposed') twin.status = 'proposed';
      twin.artifactId = twin.artifactId || r.artifactId;
      twin.pay = twin.pay || r.pay;
      twin.clash = twin.clash || r.clash;
    };
    (brief.items || []).filter((i) => i.reason in CALLS).forEach((i) => add({
      reason: i.reason, status: i.status, title: i.title, due: i.due_date, time: i.due_time, why: i.why, obligationId: i.obligation_id, artifactId: i.artifact_id,
      subject: i.subject_name || memberName(i.subject_member_id) || '', pay: i.pay_url, clash: (i.clashes || [])[0] || '',
      leave: i.leave_by ? 'Leave by ' + i.leave_by : '',
    }));
    (proposed || []).forEach((o) => add({
      reason: 'undecided', status: 'proposed', title: o.title, due: o.due_date, time: o.due_time, why: o.action, obligationId: o.id, artifactId: o.artifact_id,
      subject: memberName(o.subject_member_id) || '', pay: o.pay_url, clash: '', leave: '',
    }));
    rows.forEach((r) => {
      const n = byArtifact[r.artifactId];
      r.notice = n || null;
      r.hue = n ? spaceOfNotice(n) : hueForItem({ reason: r.reason, action: r.why });
    });
    rows.sort((a, b) => (CALLS[a.reason] - CALLS[b.reason]) || String(a.due || '9999').localeCompare(String(b.due || '9999')) || String(a.time || '').localeCompare(String(b.time || '')));
    return rows;
  }

  const GROUPS = [['look', 'Needs a look'], ['late', 'Late'], ['today', 'Today'], ['week', 'This week'], ['later', 'Later']];
  function groupOf(r) {
    if (r.reason === 'scam' || r.reason === 'amendment' || r.reason === 'quarantine' || r.reason === 'mailbox') return 'look';
    if (r.reason === 'missed' || r.reason === 'overdue') return 'late';
    if (!r.due) return 'later';
    const d = dayDiff(r.due);
    return d < 0 ? 'late' : d === 0 ? 'today' : d <= 7 ? 'week' : 'later';
  }
  const canDecideRow = (r) => !!(r.obligationId && r.status === 'proposed');

  /* The queue in groups, worst first. A group with two or more dates still to
     decide offers Accept all, one tap with one Undo; it acts only on the dates
     shown, and each stays a date a person chose to accept. */
  function queue(rows) {
    if (!rows.length) return '<p class="ck-empty">Nothing is waiting on you. New notices will appear here as FamilyOS reads them.</p>';
    let firstDrawn = false;
    return GROUPS.map(([key, label]) => {
      const mine = rows.filter((r) => groupOf(r) === key);
      if (!mine.length) return '';
      const decidable = mine.filter(canDecideRow).length;
      const draw = (r) => { const first = !firstDrawn; firstDrawn = true; return decisionRow(r, first); };
      return '<div class="ck-group" data-ck-group="' + key + '"><div class="ck-gh"><h3>' + label + ' <span>' + mine.length + '</span></h3>'
        + (decidable > 1 ? '<button class="btn ghost" type="button" data-ck-all title="Accepts every date in this group that is still undecided">Accept all ' + decidable + '</button>' : '') + '</div>'
        + mine.slice(0, 5).map(draw).join('')
        + (mine.length > 5 ? '<details class="ck-more"><summary class="btn ghost">Show ' + (mine.length - 5) + ' more</summary>' + mine.slice(5).map(draw).join('') + '</details>' : '')
        + '</div>';
    }).join('');
  }

  /* ── the day: weather, the school run and when to leave ──────── */

  function dayCard(c) {
    if (!c || (!c.weather_days && !c.school_runs && !c.holidays)) return '';
    const temps = (c.weather_days || []).map((d) => '<div class="ck-wx"><span>' + esc(d.label) + '</span><b>' + (d.tmax != null ? Math.round(d.tmax) + '°' : '–') + '</b>'
      + '<span>' + esc(d.words || '') + (d.rain != null && d.rain >= 40 ? (d.words ? ', ' : '') + 'rain ' + Math.round(d.rain) + '%' : '') + '</span></div>').join('');
    const runs = (c.school_runs || []).map((r) => {
      const slow = (r.delay_minutes || 0) >= 8;
      const mins = r.live_minutes != null ? r.live_minutes + ' min now' + ((r.delay_minutes || 0) >= 3 ? ', ' + r.delay_minutes + ' worse than usual' : ', as usual') : r.minutes + ' min' + (r.usual ? ', usual traffic' : '');
      return '<div class="ck-run' + (slow ? ' slow' : '') + '"><span class="ck-run-to">' + icon(r.office ? 'home' : 'school', 18) + esc(r.office ? 'Commute to ' + r.school : r.school) + '</span>'
        + (r.leave_by ? '<b class="ck-leave">Leave by ' + esc(r.leave_by) + '</b>' : '<b class="ck-leave plain">' + esc(String(r.live_minutes != null ? r.live_minutes : r.minutes)) + ' min</b>')
        + '<span class="ck-run-sub">' + esc(mins) + (r.starts_at ? ' · school starts ' + esc(clock(r.starts_at)) : '') + '</span></div>';
    }).join('');
    const hol = (c.holidays || []).slice(0, 2).map((h) => esc(h.name) + ' <span>' + esc(fmtDate(h.date).replace(/,.*$/, '')) + '</span>').join(' · ');
    const late = (c.school_runs || []).find((r) => (r.delay_minutes || 0) >= 8);
    return '<section class="ck-day" aria-label="The day">'
      + (late ? '<p class="ck-alert">' + icon('bell', 18) + 'Traffic to ' + esc(late.school) + ' is ' + late.delay_minutes + ' minutes worse than usual' + (late.leave_by ? '. Leave by ' + esc(late.leave_by) + '.' : '.') + '</p>' : '')
      + '<div class="ck-day-grid">' + (temps ? '<div class="ck-day-w">' + temps + '</div>' : '') + (runs ? '<div class="ck-day-r">' + runs + '</div>' : '') + '</div>'
      + (hol ? '<p class="ck-hol">Holidays coming: ' + hol + '</p>' : '') + '</section>';
  }

  function decisionRow(r, first) {
    const n = r.notice;
    const shared = n && n.visibility === 'shared';
    const via = n ? channelLabel(n.channel) : '';
    const source = n ? (via && !norm(via).includes(norm(n.from_label)) && !norm(n.from_label).includes(norm(via)) ? [n.from_label, via] : [n.from_label]).filter(Boolean).join(' · ') : '';
    const canDecide = canDecideRow(r);
    const href = r.artifactId ? '#/notices/' + r.artifactId : (r.reason === 'mailbox' ? '#/household' : r.reason === 'quarantine' ? '#/quarantine' : '#/waiting');
    const ic = ICON_PATHS[r.hue] ? r.hue : 'calendar';
    return '<article class="ck-row' + (first ? ' first' : '') + (r.reason === 'missed' || r.reason === 'overdue' || r.reason === 'scam' ? ' late' : '') + (r.reason === 'scam' ? ' scam' : '') + '" data-ck-row="' + esc(r.obligationId || r.artifactId || r.title) + '"'
      + (r.obligationId ? ' data-oid="' + esc(r.obligationId) + '"' : '') + ' tabindex="-1">'
      + '<span class="ck-ic" data-hue="' + esc(r.hue) + '">' + icon(ic, 22) + '</span>'
      + '<div class="ck-body"><h3>' + esc(r.title) + '</h3>'
      + '<p class="ck-meta"><span class="' + (r.reason === 'missed' || r.reason === 'overdue' || r.reason === 'scam' ? 'late' : '') + '">' + esc(r.reason === 'scam' ? 'Received ' + shortDay(r.due) : r.due ? when(r.due, r.time) : (REASON_WORDS[r.reason] || '')) + '</span>'
      + (r.subject ? '<span>' + esc(r.subject) + '</span>' : '')
      + (n ? '<span class="ck-vis ' + (shared ? 'shared' : 'private') + '">' + icon(shared ? 'family' : 'shield', 16) + (shared ? 'Shared' : 'Private') + '</span>' : '')
      + (r.leave ? '<span>' + esc(r.leave) + '</span>' : '') + '</p>'
      + (source ? '<p class="ck-src">From ' + esc(source) + (r.alsoIn ? ' · also in ' + r.alsoIn + ' other notice' + (r.alsoIn > 1 ? 's' : '') : '') + '</p>' : '')
      + (r.clash ? '<p class="ck-src">Clashes with ' + esc(r.clash) + '</p>' : '')
      + (r.reason === 'scam' ? '<p class="ck-src ck-scamwhy">' + esc(r.why) + '</p>' : '')
      + '</div>'
      + '<div class="ck-acts">'
      + (canDecide ? '<button class="btn" type="button" data-ck-decide="accepted" title="Puts it on the calendar and reminds you">Accept</button>'
        + '<button class="btn ghost" type="button" data-ck-decide="dismissed">Not this</button>' : '')
      + (r.reason === 'scam' && r.artifactId ? '<button class="btn" type="button" data-ck-dealt="' + esc(r.artifactId) + '" title="Marks it dealt with; nothing else happens">Dealt with</button>' : '')
      + '<a class="btn' + (canDecide || r.reason === 'scam' ? ' ghost' : '') + '" data-review href="' + esc(href) + '">' + (canDecide ? 'Review' : (r.reason === 'quarantine' ? 'Look' : 'Open')) + '</a>'
      + (r.pay ? payLinks(r.pay, 'btn ghost') : '') + '</div></article>';
  }

  /* What is on the calendar in the next week, once: accepted dates, FamilyOS
     to-dos and the calendar's own events, the same thing from two sources counted once. */
  function comingUp(accepted, events, brief, todos) {
    const items = [];
    const put = (title, date, time, hue) => {
      if (!date || dayDiff(date) < 0 || dayDiff(date) > 10) return;
      const words = norm(title);
      if (items.some((x) => x.date === date && same(x.words, words))) return;
      items.push({ title, date, time: time || '', hue: hue || 'cal', words });
    };
    (accepted || []).forEach((o) => put(o.title, o.due_date, o.due_time, 'school'));
    (brief.items || []).filter((i) => i.reason === 'soon' || i.reason === 'birthday').forEach((i) => put(i.title, i.due_date, i.due_time, i.reason === 'birthday' ? 'health' : 'school'));
    (todos || []).filter((t) => !t.done_at).forEach((t) => put(t.title, t.due_date, t.due_time, 'home'));
    (events || []).forEach((e) => {
      const date = e.starts_at ? String(e.starts_at).slice(0, 10) : null;
      put(e.summary, date, e.all_day ? '' : hhmm(e.starts_at), 'cal');
    });
    items.sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time));
    return items;
  }

  function comingCard(i) {
    const d = dayDiff(i.date);
    const day = d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : weekday(i.date);
    return '<div class="ck-card" data-hue="' + esc(i.hue) + '"><span class="ck-when">' + esc(day) + (i.time ? ' · ' + esc(clock(i.time)) : '') + '</span><b>' + esc(i.title) + '</b></div>';
  }

  async function today(main) {
    main.classList.remove('chat-main');
    const q = hashQuery();
    const [brief, events, todos, notices, money, errands, proposed, accepted, mailboxes, docs] = await Promise.all([
      api('/brief?limit=40'), api('/calendar/upcoming?days=8').catch(() => []), api('/todos').catch(() => []),
      api('/inbox?days=120&limit=400').catch(() => []), api('/money?days=120').catch(() => null), api('/errands').catch(() => []),
      api('/obligations?status=proposed&limit=100').catch(() => []), api('/obligations?status=accepted&limit=100').catch(() => []),
      api('/google/mailboxes').catch(() => []), api('/documents').catch(() => ({ documents: [], checks: [] })),
    ]);
    store.mailboxes = mailboxes;
    const connected = mailboxes.filter((m) => !m.disconnected_at);
    const importing = connected.find((m) => !m.backfill_done);
    if (q.get('mailbox') === 'failed') flash('Google did not finish connecting the mailbox. Try again.', true);
    if (q.get('mailbox') === 'cancelled') flash('Connecting the mailbox was cancelled.');
    const byArtifact = {}; notices.forEach((n) => { byArtifact[n.id] = n; });
    const rows = decisions(brief, proposed, byArtifact);
    const handled = (brief.items || []).filter((i) => i.reason === 'handled');
    const doneToday = (todos || []).filter((t) => t.done_at && String(t.done_at).slice(0, 10) === todayISO());
    const upcoming = comingUp(accepted, events, brief, todos);
    const nowHm = hhmm(new Date().toISOString());
    const next = upcoming.find((u) => u.date > todayISO() || (u.date === todayISO() && u.time && u.time >= nowHm)) || upcoming[0];
    store.needCount = rows.length; badgeAt = Date.now(); paintBadge();
    const first = ((store.me && store.me.display_name) || '').split(' ')[0];
    const noticed = insights(brief, money, errands, proposed, docs).slice(0, 2);
    const ctx = brief.context || {};
    const line = rows.length === 0 ? 'Nothing needs you right now.'
      : 'the family has ' + (rows.length === 1 ? 'one decision' : rows.length + ' decisions') + (rows.some((r) => r.due === todayISO()) ? ' today.' : ' waiting.');

    main.innerHTML = '<div class="ck-head"><div><h1>Good ' + dayPart() + ', ' + esc(first) + '.</h1>'
      + '<p class="day">' + esc(new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })) + ' · ' + esc(line)
      + '</p></div>'
      + '<button class="btn ghost ck-report" type="button" data-report title="Check a call or a message for the shapes of a scam">' + icon('shield', 18) + 'Report a call</button>'
      + '<a class="icon-btn ck-bell" href="#/waiting" aria-label="Waiting on you" title="Waiting on you">' + icon('bell', 22) + '</a></div>'
      + ((importing) ? importPanel(importing) : (connected.length === 0 ? setupHero() : ''))
      + '<div class="ck-stats">'
      + '<div class="ck-stat hero" data-ck-stat="need"><span>Needs you now</span><b>' + rows.length + (rows.length === 1 ? ' decision' : ' decisions') + '</b></div>'
      + '<div class="ck-stat"><span>Already handled</span><b>' + (handled.length + doneToday.length) + ' items</b></div>'
      + '<div class="ck-stat"><span>Next deadline</span><b>' + (next ? esc(next.time ? clock(next.time) : (dayDiff(next.date) === 0 ? 'Today' : shortDay(next.date))) : 'None') + '</b></div></div>'
      + dayCard(ctx)
      + '<section class="ck-section"><div class="ck-sh"><h2>Needs your decision</h2><span class="muted">One row per obligation</span></div>'
      + '<div class="ck-queue" data-ck-rows>' + queue(rows) + '</div></section>'
      + (handled.length || doneToday.length ? '<details class="ck-handled"><summary>Already handled · ' + (handled.length + doneToday.length) + '</summary><ul>'
        + handled.map((i) => '<li><span class="ok">' + icon('check', 16) + '</span><span>' + esc(i.title) + '</span><span class="muted">' + esc(i.handled_by_name ? 'by ' + i.handled_by_name : '') + '</span></li>').join('')
        + doneToday.map((t) => '<li><span class="ok">' + icon('check', 16) + '</span><span>' + esc(t.title) + '</span><span class="muted">done</span></li>').join('') + '</ul></details>' : '')
      + '<section class="ck-section"><div class="ck-sh"><h2>Coming up</h2><span class="muted">Calendar + accepted obligations</span></div>'
      + (upcoming.length ? '<div class="ck-cards">' + upcoming.slice(0, 6).map(comingCard).join('') + '</div>' : '<p class="ck-empty">Nothing dated in the next ten days.</p>') + '</section>'
      + (noticed.length ? '<section class="ck-section"><div class="ck-sh"><h2>FamilyOS noticed</h2></div><div class="stack" style="gap:12px">' + noticed.map(insightCard).join('') + '</div></section>' : '');

    wireHome(main);
    main.querySelector('[data-report]').addEventListener('click', () => reportCall());
    main.querySelectorAll('[data-fix]').forEach((b) => b.addEventListener('click', () => openAsk(b.dataset.fix)));
    wireRows(main, rows);
  }

  function wireRows(main, rows) {
    const box = main.querySelector('[data-ck-rows]');
    if (!box) return;
    const recount = () => {
      box.querySelectorAll('[data-ck-group]').forEach((g) => { g.hidden = !g.querySelector('[data-ck-row]:not([hidden])'); });
      const n = box.querySelectorAll('[data-ck-row]:not([hidden])').length;
      const stat = main.querySelector('[data-ck-stat="need"] b');
      if (stat) stat.textContent = n + (n === 1 ? ' decision' : ' decisions');
      store.needCount = n; paintBadge();
      if (!n && !box.querySelector('.ck-empty')) box.insertAdjacentHTML('beforeend', '<p class="ck-empty">Nothing is waiting on you.</p>');
    };
    box.querySelectorAll('[data-ck-decide]').forEach((b) => b.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const row = b.closest('[data-ck-row]');
      const id = row.dataset.oid, status = b.dataset.ckDecide;
      const title = (row.querySelector('h3') || {}).textContent || 'That date';
      deferred(status === 'accepted' ? '“' + title + '” accepted. It goes on the calendar.' : '“' + title + '” dismissed.',
        () => api('/obligations/' + id + '/decision', { method: 'POST', json: { status } }).then(() => { badgeAt = 0; }),
        () => { row.hidden = true; recount(); },
        () => { row.hidden = false; recount(); });
    }));
    box.querySelectorAll('[data-ck-all]').forEach((b) => b.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const group = b.closest('[data-ck-group]');
      const mine = Array.from(group.querySelectorAll('[data-ck-row][data-oid]:not([hidden])')).filter((row) => row.querySelector('[data-ck-decide]'));
      if (!mine.length) return;
      deferred('Accepted ' + mine.length + ' dates. They go on the calendar.',
        () => Promise.all(mine.map((row) => api('/obligations/' + row.dataset.oid + '/decision', { method: 'POST', json: { status: 'accepted' } }))).then(() => { badgeAt = 0; }),
        () => { mine.forEach((row) => { row.hidden = true; }); recount(); },
        () => { mine.forEach((row) => { row.hidden = false; }); recount(); });
    }));
    box.querySelectorAll('[data-ck-dealt]').forEach((b) => b.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const row = b.closest('[data-ck-row]'), id = b.dataset.ckDealt;
      deferred('Marked as dealt with.', () => api('/artifacts/' + id + '/handled', { method: 'POST', json: { note: 'looked like a scam; dealt with' } }).then(() => { badgeAt = 0; }),
        () => { row.hidden = true; recount(); }, () => { row.hidden = false; recount(); });
    }));
    // Selecting a row opens its evidence beside the page, as the Review button does.
    box.querySelectorAll('[data-ck-row]').forEach((row) => row.addEventListener('click', (ev) => {
      if (ev.target.closest('a, button, summary')) return;
      const a = row.querySelector('[data-review]'); if (a) a.click();
    }));
  }


  /* ── Inbox: triage, so a decision needs no opening ───────────── */

  const QUIET_CATS = { promo: 1, newsletter: 1, developer: 1, banking: 1 };

  function dueChip(date) {
    if (!date) return '';
    const d = dayDiff(date);
    const label = d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : d === -1 ? 'Yesterday' : d < 0 ? (-d) + ' days ago' : d < 7 ? weekday(date) : shortDay(date);
    return '<span class="ck-due' + (d < 0 ? ' late' : d === 0 ? ' soon' : '') + '">' + esc(label) + '</span>';
  }

  function triageRow(r, proposedBy) {
    const shared = r.visibility === 'shared';
    const hue = spaceOfNotice(r);
    const kids = (r.subject_member_ids || []).map(memberName).filter(Boolean);
    const who = memberName(r.assigned_to);
    const mine = proposedBy[r.id] || [];
    const via = channelLabel(r.channel);
    const from = r.from_label && !norm(via).includes(norm(r.from_label)) && !norm(r.from_label).includes(norm(via)) ? r.from_label + ' · ' + via : (r.from_label || via);
    return '<article class="ck-row ck-tri" data-ck-row="' + esc(r.id) + '" tabindex="-1">'
      + '<span class="ck-ic ' + esc(hue) + '">' + icon(ICON_PATHS[hue] ? hue : 'doc', 22) + '</span>'
      + '<div class="ck-body"><h3>' + esc(r.headline || r.filename || 'Notice') + '</h3>'
      + '<p class="ck-meta"><span>' + esc(from) + '</span>' + (kids.length ? '<span>' + esc(kids.join(', ')) + '</span>' : '')
      + (who ? '<span>handled by ' + esc(who) + '</span>' : '')
      + '<span class="ck-vis ' + (shared ? 'shared' : 'private') + '">' + icon(shared ? 'family' : 'shield', 16) + (shared ? 'Shared' : 'Private') + '</span>'
      + '<span>' + esc(ago(r.received_at)) + '</span></p>'
      + (r.preview && r.preview.length ? '<p class="ck-src">' + esc(r.preview[0]) + '</p>' : '') + '</div>'
      + '<div class="ck-acts">' + (r.open ? '<span class="ck-todo">' + r.open + ' to decide</span>' : '') + dueChip(r.next_date)
      + (mine.length ? '<button class="btn" type="button" data-ck-approve-row="' + esc(r.id) + '">Approve' + (mine.length > 1 ? ' ' + mine.length : '') + '</button>' : '')
      + '<a class="btn ghost" data-review href="#/notices/' + esc(r.id) + '">Open</a></div></article>';
  }

  async function inbox(main) {
    main.classList.remove('chat-main');
    const [rows, proposed] = await Promise.all([api('/inbox?days=120&limit=300'), api('/obligations?status=proposed&limit=200').catch(() => [])]);
    const proposedBy = {}; proposed.forEach((o) => { (proposedBy[o.artifact_id] = proposedBy[o.artifact_id] || []).push(o); });
    const calm = rows.filter((r) => !QUIET_CATS[r.category]);
    const quiet = rows.length - calm.length;
    const filters = {
      todo: { label: 'Needs action', test: (r) => r.state === 'todo' },
      assigned: { label: 'Assigned', test: (r) => !!r.assigned_to && !r.handled_at },
      done: { label: 'Handled', test: (r) => r.state === 'done' },
      all: { label: 'All', test: () => true },
    };
    let want = store.ckInbox && filters[store.ckInbox] ? store.ckInbox : 'todo';
    let showQuiet = false, term = '';
    const need = calm.filter(filters.todo.test).length;
    main.innerHTML = '<div class="ck-head"><div><h1>Inbox</h1><p class="day">' + calm.length + ' notices · ' + need + ' ' + (need === 1 ? 'has' : 'have') + ' dates to decide</p></div>'
      + '<div class="ck-headbtns"><button class="btn ghost" type="button" data-reportgap>Something missing?</button><button class="btn" type="button" data-add>Add notice</button></div></div>'
      + '<label class="ck-search">' + icon('search', 20) + '<input type="search" data-ck-q placeholder="Search notices" aria-label="Search notices" autocomplete="off"></label>'
      + '<div class="ck-pills" role="group" aria-label="Filter">' + Object.entries(filters).map(([k, f]) =>
        '<button type="button" class="ck-pill" data-ck-f="' + k + '" aria-pressed="' + (k === want) + '">' + f.label + ' <span>' + calm.filter(f.test).length + '</span></button>').join('') + '</div>'
      + '<div class="ck-rows" data-ck-list></div>'
      + '<p class="ck-quiet" data-ck-quiet></p>'
      + uploadDialog() + gapDialog();
    const list = main.querySelector('[data-ck-list]');
    const paint = () => {
      const pool = showQuiet ? rows : calm;
      const t = term.trim().toLowerCase();
      const shown = pool.filter(filters[want].test).filter((r) => !t || [r.headline, r.filename, r.from_label, (r.preview || []).join(' ')].join(' ').toLowerCase().includes(t));
      list.innerHTML = shown.length ? shown.map((r) => triageRow(r, proposedBy)).join('')
        : '<p class="ck-empty">' + ({ todo: 'Nothing needs a decision. Every date that arrived has been decided.', assigned: 'Nothing is handed to anyone.', done: 'Nothing handled yet.', all: 'Nothing yet. Forward a notice, or paste one.' })[want] + '</p>';
      const q = main.querySelector('[data-ck-quiet]');
      q.innerHTML = quiet ? (showQuiet ? 'Showing ' + quiet + ' promotion, newsletter and bank alert' + (quiet > 1 ? 's' : '') + '. <button class="linklike" type="button" data-ck-hide>Hide them</button>'
        : quiet + ' promotion, newsletter and bank alert' + (quiet > 1 ? 's are' : ' is') + ' kept out of the way. <button class="linklike" type="button" data-ck-show>Show them</button>') : '';
      q.querySelectorAll('[data-ck-show]').forEach((b) => b.addEventListener('click', () => { showQuiet = true; paint(); }));
      q.querySelectorAll('[data-ck-hide]').forEach((b) => b.addEventListener('click', () => { showQuiet = false; paint(); }));
      wireTriage();
    };
    const wireTriage = () => {
      list.querySelectorAll('[data-ck-approve-row]').forEach((b) => b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const row = b.closest('[data-ck-row]'), id = b.dataset.ckApproveRow, os = proposedBy[id] || [];
        const title = (row.querySelector('h3') || {}).textContent || 'That notice';
        deferred('“' + title + '” approved. ' + (os.length > 1 ? os.length + ' dates go' : 'It goes') + ' on the calendar.',
          () => Promise.all(os.map((o) => api('/obligations/' + o.id + '/decision', { method: 'POST', json: { status: 'accepted' } }))).then(() => { badgeAt = 0; }),
          () => { row.hidden = true; }, () => { row.hidden = false; });
      }));
      list.querySelectorAll('[data-ck-row]').forEach((row) => row.addEventListener('click', (ev) => {
        if (ev.target.closest('a, button')) return;
        const a = row.querySelector('[data-review]'); if (a) a.click();
      }));
    };
    paint();
    main.querySelectorAll('[data-ck-f]').forEach((b) => b.addEventListener('click', () => {
      want = b.dataset.ckF; store.ckInbox = want;
      main.querySelectorAll('[data-ck-f]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      paint();
    }));
    main.querySelector('[data-ck-q]').addEventListener('input', (ev) => { term = ev.target.value; paint(); });
    const dlg = main.querySelector('dialog[data-upload]') || main.querySelector('dialog');
    wireUpload(dlg);
    wireWays(main, dlg);
    wireGaps(main);
  }

  /* ── Notice: the original and the facts read from it, together ── */

  const KIND_DECISION = { payment: 'Payment', form: 'Form to sign', deadline: 'Deadline', event: 'Event', amendment: 'A change', instruction: 'Instruction' };

  async function notice(main, args) {
    main.classList.remove('chat-main');
    await noticeView(main, args);
    const id = args[0];
    let x = null, proposed = [];
    try { const e = await api('/artifacts/' + id + '/extraction'); x = e && e.extraction; } catch (e) { /* no reading yet */ }
    try { proposed = (await api('/obligations?status=proposed&limit=200')).filter((o) => o.artifact_id === id); } catch (e) { /* none */ }
    const claims = (x && x.claims) || [];
    const dated = claims.filter((c) => c.date).sort((a, b) => a.date.localeCompare(b.date));
    const first = dated[0];
    const withAmount = claims.find((c) => c.amount_text || c.amount);
    const grounded = claims.filter((c) => c.location && c.location.match).length;
    const requires = [...new Set(claims.flatMap((c) => c.requires || []).map((r) => String(r).replace(/_/g, ' ').toLowerCase()))].slice(0, 3);
    const people = [...new Set(claims.map((c) => c.subject_name || c.applies_to).filter((n) => n && !/^(all|everyone|everybody|parents?)$/i.test(String(n).trim())))].slice(0, 3);
    const card = (k, v) => '<div class="ck-fact"><span>' + esc(k) + '</span><b>' + v + '</b></div>';
    const cards = [];
    if (proposed.length || requires.length || claims.length) {
      cards.push(card('Decision', esc(requires.length ? requires.join(', ').replace(/, ([^,]*)$/, ' and $1').replace(/^./, (c) => c.toUpperCase()) + ' required'
        : proposed.length ? (proposed.length === 1 ? proposed[0].title : proposed.length + ' dates to decide') : 'Nothing asked of you')));
    }
    if (first) cards.push(card('Deadline', esc(when(first.date, (first.time_text || '').match(/\d{1,2}[:.]\d{2}/) ? first.time_text.replace('.', ':').match(/\d{1,2}:\d{2}/)[0] : '').replace(/^(Due|Was due) /, ''))));
    if (withAmount) cards.push(card('Amount', esc(withAmount.amount_text || money(withAmount.amount, withAmount.currency))));
    if (people.length) cards.push(card('For', esc(people.join(' · '))));
    if (claims.length) cards.push(card('Source confidence', grounded === claims.length ? 'All facts grounded in highlighted text'
      : grounded + ' of ' + claims.length + ' facts grounded; the rest quote no words'));
    const side = main.querySelector('[data-side]');
    if (side && cards.length) side.insertAdjacentHTML('afterbegin', '<section class="ck-facts" aria-label="What was read">' + cards.join('') + '</section>');
    // Approve: every date this notice proposes, with the same six seconds to take it back.
    const bar = main.querySelector('.head > .row');
    if (bar && proposed.length) {
      const done = bar.querySelector('[data-handled]'); if (done) done.classList.add('ghost');
      bar.insertAdjacentHTML('afterbegin', '<button class="btn" type="button" data-ck-approve>Review and approve' + (proposed.length > 1 ? ' ' + proposed.length : '') + '</button>');
      bar.querySelector('[data-ck-approve]').addEventListener('click', () => {
        const btn = bar.querySelector('[data-ck-approve]');
        deferred('Approved. ' + (proposed.length > 1 ? proposed.length + ' dates go' : 'It goes') + ' on the calendar.',
          () => Promise.all(proposed.map((o) => api('/obligations/' + o.id + '/decision', { method: 'POST', json: { status: 'accepted' } }))).then(() => { badgeAt = 0; return render(); }),
          () => { btn.hidden = true; }, () => { btn.hidden = false; });
      });
    }
  }

  /* ── Family: the people and the offers, then the week and the money ── */

  async function family(main) {
    main.classList.remove('chat-main');
    await familyView(main);
    // The week, what is being done, the spend and the bills used to sit on three
    // other pages; they come under the people, so the family is one place.
    const parents = (store.household && store.household.members || []).filter((x) => x.circle_role === 'parent');
    if (parents.length) main.insertAdjacentHTML('afterbegin', '<section class="ck-section"><div class="ck-sh"><h2>Care</h2><a class="muted" href="#/constitution">Rules and access</a></div><div class="ck-cards">'
      + parents.map((x) => '<a class="ck-card" data-hue="health" href="#/care/' + esc(x.id) + '" style="text-decoration:none;color:inherit"><span class="ck-when">The parent</span><b>' + esc(x.display_name) + '</b><span class="ck-when">Papers, bills, appointments, warnings</span></a>').join('') + '</div></section>');
    const rest = document.createElement('main');
    await lifeView(rest);
    rest.querySelectorAll('.head, .askbar').forEach((n) => n.remove());
    const bills = await api('/billers').catch(() => []);
    main.insertAdjacentHTML('beforeend', '<h2 class="ck-h" style="margin-top:36px">The week and the money</h2>');
    const wrap = document.createElement('div'); wrap.className = 'ck-famrest';
    while (rest.firstChild) wrap.appendChild(rest.firstChild);
    main.appendChild(wrap);
    if (bills.length) wrap.insertAdjacentHTML('beforeend', '<div class="ck-bills">' + billsCard(bills) + '</div>');
  }

  /* ── Plan: owned next steps ──────────────────────────────────── */

  async function plan(main, args) {
    main.classList.remove('chat-main');
    await planView(main, args);
    let pl; try { pl = await api('/plans/' + args[0]); } catch (e) { return; }
    const todos = pl.todos || [];
    const head = main.querySelector('.head');
    if (!todos.length || !head) return;
    const done = todos.filter((t) => t.done_at).length;
    const row = (t) => '<label class="ck-task' + (t.done_at ? ' done' : '') + '"><input type="checkbox" data-ck-task="' + esc(t.id) + '"' + (t.done_at ? ' checked' : '') + ' aria-label="Done: ' + esc(t.title) + '">'
      + '<span class="ck-box">' + icon('check', 18) + '</span><span class="grow"><b>' + esc(t.title) + '</b>'
      + '<span class="muted">' + (t.done_at ? 'Done' : (t.due_date ? when(t.due_date, t.due_time).replace(/^Due /, 'By ') : 'No date'))
      + (t.assigned_to ? ' · ' + esc(memberName(t.assigned_to) || '') : ' · not yet owned') + '</span></span></label>';
    head.insertAdjacentHTML('afterend', '<section class="ck-plan"><div class="ck-stat hero"><span>' + esc(pl.title) + '</span><b>' + done + ' of ' + todos.length + ' tasks done</b></div>'
      + '<div class="ck-rows">' + todos.slice().sort((a, b) => (a.done_at ? 1 : 0) - (b.done_at ? 1 : 0) || String(a.due_date || '9').localeCompare(String(b.due_date || '9'))).map(row).join('') + '</div></section>');
    main.classList.add('ck-planpage');
    main.querySelectorAll('[data-ck-task]').forEach((cb) => cb.addEventListener('change', async () => {
      try { await api('/todos/' + cb.dataset.ckTask, { method: 'PATCH', json: { done: cb.checked } }); } catch (err) { cb.checked = !cb.checked; fail(err); return; }
      const tid = cb.dataset.ckTask, on = cb.checked;
      reversible(on ? 'Marked done.' : 'Marked not done.', () => api('/todos/' + tid, { method: 'PATCH', json: { done: !on } }));
      render().catch(() => {});
    }));
  }

  /* ── Ask: a grounded answer shows what it stands on ──────────── */

  function sources(t) {
    const cites = (t && t.citations || []).filter((c) => c.artifact_id);
    if (!cites.length) return '';
    return '<div class="ck-sources"><span class="ck-srcnote">' + cites.length + ' household source' + (cites.length > 1 ? 's' : '') + ' · tap to inspect</span>'
      + cites.slice(0, 4).map((c) => '<a class="ck-srccard" href="#/notices/' + esc(c.artifact_id) + '"><b>' + esc(String(c.text || 'Notice').slice(0, 80)) + '</b><span>' + esc(c.ref) + '</span></a>').join('') + '</div>';
  }


  /* ── Report a call: said once, answered always ───────────────── */

  function reportCall(about) {
    document.querySelectorAll('.ck-dialog').forEach((d) => d.remove());
    const adults = (store.household && store.household.members || []).filter((m) => m.role !== 'child');
    const dlg = document.createElement('dialog'); dlg.className = 'ck-dialog';
    dlg.innerHTML = '<form class="stack" data-form="scam" method="dialog" style="gap:14px"><h2>Report a call or a message</h2>'
      + '<p class="muted">Say what they said, in a few words. FamilyOS reads it for the shapes of a scam and tells you what to do. Nothing is blocked or reported for you.</p>'
      + '<label>What did they say?<textarea name="text" rows="5" required minlength="8" maxlength="4000" placeholder="A man said he was from the CBI and that Appa’s Aadhaar was used in a crime…"></textarea></label>'
      + '<div class="row wrap" style="gap:14px"><label class="grow">Who called or wrote (optional)<input name="caller" maxlength="60" placeholder="+91 98…"></label>'
      + '<label class="grow">It was about<select name="about"><option value="">Nobody in particular</option>'
      + adults.map((m) => '<option value="' + esc(m.id) + '"' + (m.id === about ? ' selected' : '') + '>' + esc(m.display_name) + '</option>').join('') + '</select></label></div>'
      + '<div data-scam-result></div>'
      + '<div class="row" style="gap:10px;justify-content:flex-end"><button class="btn ghost" type="button" data-close>Close</button><button class="btn" type="submit">Check it</button></div></form>';
    document.body.appendChild(dlg); dlg.showModal();
    dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());
    dlg.addEventListener('close', () => dlg.remove());
    dlg.querySelector('form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const f = new FormData(ev.target), out = dlg.querySelector('[data-scam-result]'), btn = ev.target.querySelector('[type="submit"]');
      btn.disabled = true;
      try {
        const r = await api('/scam/reports', { method: 'POST', json: { text: String(f.get('text')).trim(), caller: String(f.get('caller')).trim() || null, about_member_id: String(f.get('about')) || null } });
        const head = r.level === 'high' ? ['This matches a scam.', 'high'] : r.level === 'medium' ? ['Worth a second look.', 'medium'] : ['Nothing here matches a known scam.', 'none'];
        out.innerHTML = '<div class="ck-verdict ' + head[1] + '"><b>' + head[0] + '</b>'
          + (r.reasons.length ? '<ul>' + r.reasons.map((x) => '<li>It ' + esc(x) + '.</li>').join('') + '</ul>' : '')
          + '<p><b>What to do</b></p><ul>' + r.advice.map((x) => '<li>' + esc(x) + '</li>').join('') + '</ul>'
          + (r.level === 'high' ? '<p class="muted">The guardians have been told. Nothing was blocked or reported for you.</p>' : '') + '</div>';
        btn.textContent = 'Check another';
        ev.target.reset();
      } catch (err) { fail(err); } finally { btn.disabled = false; }
    });
  }

  /* ── Rules and access: the constitution ───────────────────────── */

  const CIRCLE = [['', 'No role yet'], ['parent', 'The parent'], ['sibling', 'A sibling'], ['spouse', 'A spouse'], ['caregiver', 'A caregiver'], ['other', 'In the circle']];

  async function constitution(main) {
    main.classList.remove('chat-main');
    const [c, grants] = await Promise.all([api('/household/constitution'), Promise.resolve(null)]);
    const guardian = store.me && store.me.role === 'guardian';
    const members = c.people.filter((x) => x.role !== 'child');
    const person = (x) => '<article class="ck-person card" data-person-card="' + esc(x.member_id) + '"><div class="ck-person-h"><span class="avatar">' + esc(initial(x.display_name)) + '</span>'
      + '<div class="grow"><h3>' + esc(x.display_name) + '</h3><span class="muted">' + esc(x.role) + (x.circle_words ? ' · ' + esc(x.circle_words) : '') + '</span></div>'
      + (guardian && x.role !== 'child' ? '<select data-circle-role="' + esc(x.member_id) + '" aria-label="Role of ' + esc(x.display_name) + '">' + CIRCLE.map(([k, l]) => '<option value="' + k + '"' + ((x.circle_role || '') === k ? ' selected' : '') + '>' + l + '</option>').join('') + '</select>' : '')
      + '</div><ul class="ck-sees">' + x.sees.map((t) => '<li>' + esc(t) + '</li>').join('') + '</ul>'
      + (x.grants.length ? '<div class="ck-grants">' + x.grants.map((g) => '<div class="ck-grant"><span>' + esc(g.actions.join(', ')) + ' about ' + esc(g.subject_name || 'anyone') + ' · until ' + esc(fmtDate(String(g.expires_at).slice(0, 10)).replace(/,.*$/, '')) + '</span>'
        + (guardian ? '<button class="btn ghost" type="button" data-revoke="' + esc(g.id) + '">End it</button>' : '') + '</div>').join('') + '</div>' : '')
      + (guardian && x.role !== 'child' && x.member_id !== store.me.id ? '<button class="btn ghost" type="button" data-hand="' + esc(x.member_id) + '">Hand something over…</button>' : '')
      + '</article>';
    main.innerHTML = '<div class="ck-head"><div><h1>Rules and access</h1><p class="day">What this household has decided, in words, and who sees what because of it.</p></div></div>'
      + '<section class="ck-section"><div class="ck-sh"><h2>Always true</h2><span class="muted">nothing here can be switched off</span></div><ul class="ck-walls">'
      + c.walls.map((w) => '<li>' + icon('shield', 18) + '<span>' + esc(w) + '</span></li>').join('') + '</ul></section>'
      + '<section class="ck-section"><div class="ck-sh"><h2>The circle</h2><span class="muted">read from what actually decides it</span></div><div class="ck-people">'
      + members.map(person).join('') + '</div></section>'
      + '<section class="ck-section">' + rulesCard() + '</section>'
      + '<dialog class="ck-dialog" data-hand-dialog><form class="stack" data-form="hand" method="dialog" style="gap:14px"><h2 data-hand-title>Hand something over</h2>'
      + '<p class="muted">They will see only these dated things, for a while, and the reason is written where the family can read it. It is never more than you can see yourself.</p>'
      + '<label>What<select name="preset">' + c.presets.map((p2) => '<option value="' + esc(p2.key) + '">' + esc(p2.label) + '</option>').join('') + '</select></label>'
      + '<label>About<select name="subject"><option value="">Anyone</option>' + c.people.map((x) => '<option value="' + esc(x.member_id) + '">' + esc(x.display_name) + '</option>').join('') + '</select></label>'
      + '<label>For how many days<input type="number" name="days" min="1" max="365" value="30"></label>'
      + '<label>Why (written where the family can read it)<input name="reason" required maxlength="200" placeholder="She takes Amma to the clinic"></label>'
      + '<div class="row" style="gap:10px;justify-content:flex-end"><button class="btn ghost" type="button" data-close>Cancel</button><button class="btn" type="submit">Hand it over</button></div></form></dialog>';
    wireRules(main);
    main.querySelectorAll('[data-circle-role]').forEach((sel) => sel.addEventListener('change', async () => {
      try { await api('/members/' + sel.dataset.circleRole + '/circle-role', { method: 'PUT', json: { circle_role: sel.value || null } }); store.household = await api('/household'); flash('Saved.'); render().catch(() => {}); }
      catch (err) { fail(err); render().catch(() => {}); }
    }));
    main.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', async () => {
      try { await api('/grants/' + b.dataset.revoke, { method: 'DELETE' }); flash('Ended.'); render().catch(() => {}); } catch (err) { fail(err); }
    }));
    const dlg = main.querySelector('[data-hand-dialog]');
    let to = null;
    dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());
    main.querySelectorAll('[data-hand]').forEach((b) => b.addEventListener('click', () => {
      to = b.dataset.hand; const who = c.people.find((x) => x.member_id === to);
      dlg.querySelector('[data-hand-title]').textContent = 'Hand something to ' + (who ? who.display_name : 'them');
      dlg.showModal();
    }));
    dlg.querySelector('form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const f = new FormData(ev.target); const preset = c.presets.find((x) => x.key === f.get('preset'));
      try {
        await api('/grants', { method: 'POST', json: { grantee_member_id: to, actions: preset.actions, subject_member_id: String(f.get('subject')) || null, days: Number(f.get('days')) || preset.days, reason: String(f.get('reason')).trim() } });
        dlg.close(); flash('Handed over. They see only that.'); render().catch(() => {});
      } catch (err) { fail(err); }
    });
  }

  /* ── Care: one person's papers, bills, appointments, warnings ── */

  const DOC_STATE = { expired: ['Expired', 'late'], expiring: ['Expiring', 'warn'], ok: ['Valid', 'ok'], undated: ['No date', ''] };

  async function care(main, args) {
    main.classList.remove('chat-main');
    const id = args[0];
    const c = await api('/members/' + id + '/care');
    const m = c.member, name = m.display_name.split(' ')[0];
    const soon = c.documents.filter((d) => d.status === 'expiring' || d.status === 'expired');
    const open = c.scams.filter((x) => !x.handled_at);
    const row = (icon_, title, meta, extra) => '<div class="ck-lite"><span class="ck-ic" data-hue="money">' + icon(icon_, 20) + '</span><div class="grow"><b>' + esc(title) + '</b><span class="muted">' + meta + '</span></div>' + (extra || '') + '</div>';
    main.innerHTML = '<div class="ck-head"><div><h1>' + esc(m.display_name) + '</h1><p class="day">' + esc(({ parent: 'The parent', sibling: 'A sibling', spouse: 'A spouse', caregiver: 'A caregiver' })[m.circle_role] || m.role)
      + ' · papers, bills, appointments and anything that looked wrong, in one place.</p></div>'
      + '<div class="ck-headbtns"><button class="btn" type="button" data-report>Report a call</button><a class="btn ghost" href="#/constitution">Who sees what</a></div></div>'
      + '<div class="ck-stats"><div class="ck-stat' + (open.length ? ' hero' : '') + '"><span>Looked wrong</span><b>' + open.length + (open.length === 1 ? ' message' : ' messages') + '</b></div>'
      + '<div class="ck-stat"><span>Papers needing attention</span><b>' + soon.length + (soon.length === 1 ? ' document' : ' documents') + '</b></div>'
      + '<div class="ck-stat"><span>Bills coming</span><b>' + c.bills.length + (c.bills.length === 1 ? ' bill' : ' bills') + '</b></div></div>'
      + (open.length ? '<section class="ck-section"><div class="ck-sh"><h2>Looked like a scam</h2><span class="muted">nothing was done about them</span></div><div class="ck-lites">'
        + open.map((x) => row('shield', (x.suspicion.level === 'high' ? 'Matches a scam: ' : 'Worth a second look: ') + (x.headline || 'a message'),
          esc((x.suspicion.reasons || [])[0] || '') + ' · ' + esc(ago(x.received_at)), '<a class="btn ghost" data-review href="#/notices/' + esc(x.artifact_id) + '">Open</a>')).join('') + '</div></section>' : '')
      + '<section class="ck-section"><div class="ck-sh"><h2>Papers</h2><span class="muted">warned ' + 'before they run out</span></div>'
      + (c.documents.length ? '<div class="ck-lites">' + c.documents.map((d) => { const st = DOC_STATE[d.status] || ['', ''];
        return row('doc', (d.label || 'Document').replace(/^./, (x) => x.toUpperCase()) + (d.identifier_tail ? ' …' + d.identifier_tail : ''),
          d.expires_on ? 'expires ' + esc(fmtDate(d.expires_on).replace(/,.*$/, '')) + (d.days_left != null ? ' · ' + (d.days_left < 0 ? -d.days_left + ' days ago' : d.days_left + ' days left') : '') : 'no date read',
          '<span class="ck-state ' + st[1] + '">' + st[0] + '</span><a class="btn ghost" data-review href="#/notices/' + esc(d.artifact_id) + '">Open</a>'); }).join('') + '</div>'
        : '<p class="ck-empty">No papers of ' + esc(name) + '’s read yet. Send a photo of a passport, a policy or a licence and it is kept with its dates.</p>') + '</section>'
      + '<section class="ck-section"><div class="ck-sh"><h2>Bills</h2></div>' + (c.bills.length ? '<div class="ck-lites">' + c.bills.map((b) => row('money', b.title, esc(when(b.due_date, b.due_time)),
        (b.pay_url ? payLinks(b.pay_url, 'btn') : '') + '<a class="btn ghost" data-review href="#/notices/' + esc(b.artifact_id) + '">Open</a>')).join('') + '</div>' : '<p class="ck-empty">No bills for ' + esc(name) + ' are waiting.</p>')
      + (c.unusual.length ? '<div class="ck-lites" style="margin-top:12px">' + c.unusual.map((u) => row('bell', u.title, esc(u.why), '')).join('') + '</div>' : '') + '</section>'
      + '<section class="ck-section"><div class="ck-sh"><h2>Medicines</h2><span class="muted">the doctor’s words, as written; not advice</span></div>'
      + ((c.medications || []).length ? '<div class="ck-lites">' + c.medications.map((md) => row('heart', md.drug + (md.dose_text ? ' · ' + md.dose_text : ''),
        esc([md.times_per_day ? md.times_per_day + ' a day' : '', md.prescriber || '', md.ends_on ? 'supply to ' + fmtDate(md.ends_on).replace(/,.*$/, '') + (md.days_left != null && md.days_left >= 0 ? ' · ' + md.days_left + ' days left' : '') : '', md.from_picture ? 'read from handwriting: check the name on the paper' : ''].filter(Boolean).join(' · ')),
        '<span class="ck-state ' + ({ refill: 'warn', finished: 'bad', active: 'ok' }[md.status] || '') + '">' + ({ refill: 'refill due', finished: 'finished', active: 'active', ongoing: 'ongoing' }[md.status] || '') + '</span><a class="btn ghost" data-review href="#/notices/' + esc(md.artifact_id) + '">Open</a>')).join('') + '</div>'
        : '<p class="ck-empty">No prescription of ' + esc(name) + '’s has been read yet. Share a photo of one and each medicine is kept with its dose and the last day of the supply; a refill is proposed before it runs out.</p>') + '</section>'
      + '<section class="ck-section"><div class="ck-sh"><h2>Standing payments</h2><span class="muted">rent and the like: reminded, never paid</span></div>'
      + ((c.standing || []).length ? '<div class="ck-lites">' + c.standing.map((sp) => row('money', sp.title + ' · ' + sp.payee, esc(money(sp.amount, sp.currency) + ' on the ' + sp.day_of_month + ordinal(sp.day_of_month) + ' · next ' + fmtDate(sp.next_due).replace(/,.*$/, '')),
        '<button class="btn ghost" type="button" data-stop-standing="' + esc(sp.id) + '">Stop</button>')).join('') + '</div>' : '')
      + '<form class="ck-lite" data-standing-form style="flex-wrap:wrap;gap:8px"><input name="title" placeholder="Rent" aria-label="What" required maxlength="120" style="flex:1 1 90px">'
      + '<input name="payee" placeholder="Paid to" aria-label="Paid to" required maxlength="120" style="flex:1 1 120px"><input name="amount" type="number" min="1" step="0.01" placeholder="Amount" aria-label="Amount" required style="flex:1 1 90px">'
      + '<input name="day_of_month" type="number" min="1" max="28" placeholder="Day" aria-label="Day of the month" required style="flex:0 1 70px"><button class="btn" type="submit">Add</button></form></section>'
      + '<section class="ck-section"><div class="ck-sh"><h2>Appointments</h2><span class="muted">next 45 days</span></div>' + (c.appointments.length ? '<div class="ck-lites">' + c.appointments.map((a) => row('calendar', a.title, esc(when(a.due_date, a.due_time)),
        '<a class="btn ghost" data-review href="#/notices/' + esc(a.artifact_id) + '">Open</a>')).join('') + '</div>' : '<p class="ck-empty">Nothing dated for ' + esc(name) + ' in the next six weeks.</p>') + '</section>'
      + (c.handed_over.length ? '<section class="ck-section"><div class="ck-sh"><h2>Handed over</h2></div><div class="ck-lites">' + c.handed_over.map((g) => row('family', g.grantee_name + ' sees ' + g.actions.join(', '), esc(g.reason)
        + ' · until ' + esc(fmtDate(String(g.expires_at).slice(0, 10)).replace(/,.*$/, '')), '')).join('') + '</div></section>' : '');
    main.querySelector('[data-report]').addEventListener('click', () => reportCall(id));
    const form = main.querySelector('[data-standing-form]');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = new FormData(form);
      try {
        await api('/standing', { method: 'POST', json: { title: f.get('title'), payee: f.get('payee'), amount: Number(f.get('amount')), day_of_month: Number(f.get('day_of_month')), subject_member_id: id } });
        care(main, args);
      } catch (err) { flash(err.message || 'Could not save it.', true); }
    });
    main.querySelectorAll('[data-stop-standing]').forEach((b) => b.addEventListener('click', async () => {
      try { await api('/standing/' + b.dataset.stopStanding, { method: 'DELETE' }); care(main, args); } catch (err) { flash(err.message || 'Could not stop it.', true); }
    }));
  }
  const ordinal = (n) => (n % 10 === 1 && n !== 11 ? 'st' : n % 10 === 2 && n !== 12 ? 'nd' : n % 10 === 3 && n !== 13 ? 'rd' : 'th');

  window.COCKPIT_UI = { chrome, today, more, gate, askBar, after, reversible, deferred, inbox, notice, plan, family, sources, constitution, care, reportCall };
})();
