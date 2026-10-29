(function () {
  var KEY = 'familyos.kid';
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } }
  var hash = location.hash.slice(1);
  if (/^kid_/.test(hash)) { store(KEY, hash); history.replaceState(null, '', location.pathname); }
  var token = store(KEY);
  var app = document.getElementById('app'), helpBtn = document.getElementById('help');
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function api(path, opts) {
    opts = opts || {};
    return fetch('/v1' + path, { method: opts.method || 'GET', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: opts.json ? JSON.stringify(opts.json) : undefined })
      .then(function (r) { return r.text().then(function (t) { var d = null; try { d = t ? JSON.parse(t) : null; } catch (e) {} if (!r.ok) { var err = new Error((d && d.detail) || 'Something went wrong'); err.status = r.status; throw err; } return d; }); });
  }
  function say(msg) { var n = document.createElement('div'); n.textContent = msg; n.style.cssText = 'position:fixed;left:50%;top:16px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:10px 18px;border-radius:999px;z-index:9;font-weight:700'; document.body.appendChild(n); setTimeout(function () { n.remove(); }, 2600); }
  function item(it) { return '<button class="item' + (it.done ? ' done' : '') + '" data-key="' + esc(it.key) + '" data-done="' + (it.done ? '1' : '') + '"><span class="box">✓</span>' + (it.icon ? '<span class="ic">' + esc(it.icon) + '</span>' : '') + '<span class="t">' + esc(it.label || it.text) + '</span></button>'; }
  function render(d) {
    var asked = (d.asked || []).map(function (a) { return '<div class="entry"><div>' + esc(a.text) + '</div>' + (a.answer ? '<span class="pill ' + (a.answer === 'yes' ? 'yes' : a.answer === 'no' ? 'no' : '') + '">' + ({ yes: 'Yes', no: 'No', later: 'Later' }[a.answer]) + '</span>' + (a.note ? ' <span class="sub">' + esc(a.note) + '</span>' : '') : '<span class="pill">waiting for an answer</span>') + '</div>'; }).join('');
    var goals = (d.goals || []).map(function (g) { return '<div class="entry"><b>' + esc(g.title) + '</b><div class="sub">' + Math.round(g.saved).toLocaleString() + ' of ' + Math.round(g.target).toLocaleString() + '</div><div class="bar"><i style="width:' + g.percent + '%"></i></div></div>'; }).join('');
    var when = new Date(d.date + 'T00:00:00').toLocaleDateString('en', { weekday: 'long', day: 'numeric', month: 'long' });
    app.innerHTML = '<div><p class="sub">' + esc(when) + '</p><h1>Hi ' + esc(d.name) + ' 👋</h1></div>'
      + (d.morning.length ? '<section class="card"><h2>🌅 Morning</h2>' + d.morning.map(item).join('') + '</section>' : '')
      + ((d.today || []).length ? '<section class="card"><h2>📅 Coming up</h2>' + d.today.map(function (t) { return '<div class="entry"><b>' + esc(t.title) + '</b><div class="sub">' + esc(t.when) + (t.time ? ' · ' + esc(t.time) : '') + '</div></div>'; }).join('') + '</section>' : '')
      + ((d.bring || []).length ? '<section class="card"><h2>🎒 To bring or wear</h2>' + d.bring.map(item).join('') + '</section>' : '')
      + (d.evening.length ? '<section class="card"><h2>🌙 Evening</h2>' + d.evening.map(item).join('') + '</section>' : '')
      + '<section class="card"><h2>🙋 Ask a parent</h2><div class="row"><input id="ask" maxlength="200" placeholder="Can I…?" aria-label="Ask a parent"><button class="btn" id="askgo">Ask</button></div>' + asked + '</section>'
      + (goals ? '<section class="card"><h2>🐷 My savings</h2>' + goals + '</section>' : '')
      + '<section class="card"><h2>📓 My journal</h2><p class="sub">Only you can read this. You can choose to share one note.</p><textarea id="jt" rows="3" maxlength="2000" placeholder="Write anything…" aria-label="Journal"></textarea><div class="row" style="margin-top:8px"><button class="btn" id="jgo">Save</button><button class="btn quiet" id="jshow">Show my notes</button></div><div id="jlist"></div></section>';
    helpBtn.hidden = false;
    app.querySelectorAll('.item').forEach(function (b) { b.addEventListener('click', function () {
      var done = !b.dataset.done; api('/kid/check', { method: 'POST', json: { key: b.dataset.key, done: done } }).then(function () { b.dataset.done = done ? '1' : ''; b.classList.toggle('done', done); }, function (e) { say(e.message); }); }); });
    document.getElementById('askgo').addEventListener('click', function () { var v = document.getElementById('ask').value.trim(); if (!v) return; api('/kid/ask', { method: 'POST', json: { text: v } }).then(function () { say('Asked! They will answer soon.'); load(); }, function (e) { say(e.message); }); });
    document.getElementById('jgo').addEventListener('click', function () { var v = document.getElementById('jt').value.trim(); if (!v) return; api('/kid/journal', { method: 'POST', json: { text: v } }).then(function () { document.getElementById('jt').value = ''; say('Saved. Only you can see it.'); showJ(); }, function (e) { say(e.message); }); });
    document.getElementById('jshow').addEventListener('click', showJ);
  }
  function showJ() {
    api('/kid/journal').then(function (rows) {
      var box = document.getElementById('jlist');
      box.innerHTML = rows.length ? rows.map(function (r) { return '<div class="entry"><div>' + esc(r.text) + '</div><div class="sub">' + new Date(r.at).toLocaleDateString('en', { day: 'numeric', month: 'short' }) + (r.shared ? ' · shared with your grown-ups' : '') + '</div>' + (r.shared ? '' : '<button class="btn quiet" data-share="' + esc(r.id) + '">Share this one</button>') + '</div>'; }).join('') : '<p class="sub">No notes yet.</p>';
      box.querySelectorAll('[data-share]').forEach(function (b) { b.addEventListener('click', function () { api('/kid/journal/' + b.dataset.share + '/share', { method: 'POST' }).then(function () { say('Shared.'); showJ(); }, function (e) { say(e.message); }); }); });
    }, function (e) { say(e.message); });
  }
  helpBtn.addEventListener('click', function () { if (!confirmed) { confirmed = true; helpBtn.textContent = 'Tap again to tell them'; setTimeout(function () { confirmed = false; helpBtn.textContent = 'I need a grown-up'; }, 4000); return; } confirmed = false; helpBtn.textContent = 'I need a grown-up'; api('/kid/help', { method: 'POST' }).then(function () { say('They have been told. Stay where you are.'); }, function (e) { say(e.message); }); });
  var confirmed = false;
  function load() { if (!token) { app.innerHTML = '<section class="card"><h2>Ask a grown-up for your link</h2><p class="sub">This page needs the special link they have.</p></section>'; return; } api('/kid/day').then(render, function (e) { app.innerHTML = '<section class="card"><h2>' + (e.status === 401 ? 'This link does not work any more' : 'Could not open your day') + '</h2><p class="sub">Ask a grown-up for a new one.</p></section>'; if (e.status === 401) store(KEY, null); }); }
  load();
})();
