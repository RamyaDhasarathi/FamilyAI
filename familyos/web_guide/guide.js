/* The guide page: sign in with the console's token (same origin), pick a
   plan, stream its page line by line and render each line as it lands.
   The renderer and the component library come from the OpenUI browser
   bundle; the model may use only that library, and the server forwards
   only lines that name it. A button opens an option's own page or hands a
   sentence to Ask; nothing here books, pays or changes the record. */
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let token = null;
  try { token = localStorage.getItem('familyos.token'); } catch (e) { token = null; }

  async function api(path, opts) {
    const o = opts || {}; const headers = Object.assign({}, o.headers);
    if (token) headers.Authorization = 'Bearer ' + token;
    let body = o.body;
    if (o.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(o.json); }
    const res = await fetch('/v1' + path, { method: o.method || 'GET', headers, body });
    if (!res.ok) { let d = null; try { d = await res.json(); } catch (e) { /* no body */ } throw new Error((d && (d.detail || d.error)) || ('HTTP ' + res.status)); }
    return res.status === 204 ? null : res.json();
  }

  /* A link on the address: spend it, keep the token, take it out of the bar. */
  async function takeLink() {
    const q = new URLSearchParams(location.search); const link = q.get('link');
    if (!link) return;
    q.delete('link'); history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : '') + location.hash);
    const out = await api('/sign-in/redeem', { method: 'POST', json: { link } });
    token = out.token; try { localStorage.setItem('familyos.token', token); } catch (e) { /* this tab only */ }
  }

  const OU = window.__OpenUI;
  const lib = OU && OU.openuiChatLibrary && (OU.openuiChatLibrary.library || OU.openuiChatLibrary);
  let root = null, code = '', streaming = false, planId = null, plan = null;

  function render() {
    if (!root) root = OU.createRoot($('#root'));
    root.render(OU.React.createElement(OU.Renderer, { response: code || null, library: lib, isStreaming: streaming, onAction: onAction }));
    $('#code').textContent = code; $('#codeBox').hidden = !code;
  }

  /* The two things a button may do. ToAssistant hands the words to Ask in
     the console; OpenUrl the bundle handles itself (a new tab). */
  function onAction(ev) {
    const text = ev && (ev.message || ev.text || (ev.payload && (ev.payload.message || ev.payload.text)) || (ev.args && ev.args[0]));
    const kind = ev && (ev.type || ev.kind || ev.name || '');
    if (/assistant/i.test(String(kind)) || (text && !/url/i.test(String(kind)))) {
      try { sessionStorage.setItem('familyos.ask', String(text || '').slice(0, 500)); } catch (e) { /* storage off */ }
      location.href = '/app/#/chat';
    }
  }

  async function compose() {
    if (!planId) return;
    code = ''; streaming = true; render();
    $('#status').innerHTML = '<b>Composing…</b> the page arrives line by line.';
    $('#bar').hidden = false; $('#again').disabled = true;
    const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token };
    const t0 = performance.now(); let lines = 0, first = null;
    try {
      const res = await fetch('/v1/plans/' + planId + '/guide', { method: 'POST', headers });
      if (!res.ok || !res.body) throw new Error('HTTP ' + res.status);
      const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        buf += done ? dec.decode() : dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const raw = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1); if (!raw) continue;
          let ev; try { ev = JSON.parse(raw); } catch (e) { continue; }
          if (ev.type === 'line') { lines += 1; if (first === null) first = performance.now() - t0; code += (code ? '\n' : '') + ev.text; render(); }
          else if (ev.type === 'done') $('#status').innerHTML = 'Composed: <b>' + lines + ' lines</b>, first in ' + Math.round(first || 0) + ' ms, all in ' + Math.round(performance.now() - t0) + ' ms' + (ev.dropped ? ' · ' + ev.dropped + ' line' + (ev.dropped === 1 ? '' : 's') + ' the library does not know were dropped' : '') + '.';
          else if (ev.type === 'error') $('#status').innerHTML = '<b>Could not compose:</b> ' + esc(ev.detail);
        }
        if (done) break;
      }
    } catch (err) { $('#status').innerHTML = '<b>Could not compose:</b> ' + esc(err.message); }
    streaming = false; render(); $('#again').disabled = false;
  }

  async function pick() {
    const plansList = await api('/plans');
    const box = $('#picker'); box.hidden = false;
    box.innerHTML = '<p class="sub">Which plan?</p>' + plansList.map((p) => '<button data-id="' + esc(p.id) + '"><b>' + esc(p.title) + '</b><small>' + esc([p.shape, p.status, p.starts_on ? p.starts_on + ' to ' + p.ends_on : ''].filter(Boolean).join(' · ')) + '</small></button>').join('');
    box.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { const q = new URLSearchParams(location.search); q.set('plan', b.dataset.id); location.search = q.toString(); }));
  }

  async function boot() {
    if (!OU || !lib) { $('#status').innerHTML = '<b>The component library did not load.</b> The page needs the OpenUI bundle from the CDN.'; return; }
    try { await takeLink(); } catch (e) { $('#status').textContent = 'That link did not work: ' + e.message; }
    if (!token) { $('#gate').style.display = 'block'; return; }
    $('#gate').style.display = 'none';
    planId = new URLSearchParams(location.search).get('plan');
    if (!planId) return pick();
    try { plan = await api('/plans/' + planId); } catch (e) { $('#status').textContent = e.message; return pick(); }
    document.title = 'FamilyOS · ' + plan.title;
    $('header h1').textContent = plan.title;
    $('#again').addEventListener('click', compose);
    $('#askBtn').addEventListener('click', () => { try { sessionStorage.setItem('familyos.ask', 'About the plan "' + plan.title + '": what still has to be confirmed before anything is booked?'); } catch (e) { /* fine */ } location.href = '/app/#/chat'; });
    compose();
  }
  $('#gateForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const link = $('#gateLink').value.trim(); if (!link) return;
    try { const out = await api('/sign-in/redeem', { method: 'POST', json: { link } }); token = out.token; try { localStorage.setItem('familyos.token', token); } catch (e) { /* fine */ } boot(); }
    catch (e) { $('#status').textContent = e.message; }
  });
  boot();
})();
