window.FOS_CONSOLE = '/app/';
(function () {
  var authEl = document.getElementById('auth');
  var authMsg = document.getElementById('auth-msg');

  /* served by the console: sign-in and start-a-household live there; a signed-in visitor goes straight in */
  var BASE = window.FOS_CONSOLE;
  if (BASE) {
    /* A signed-in visitor goes straight in. The session is an HttpOnly cookie, so script cannot look: ask the server (a token kept by an earlier version is traded for the cookie first). */
    var legacy = null; try { legacy = localStorage.getItem('familyos.token'); } catch (e) { /* no storage */ }
    var adopted = legacy ? fetch('/v1/session', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-FamilyOS-CSRF': '1' }, body: JSON.stringify({ token: legacy }) })
      /* Let go of it when the server took it, or said the token itself is dead (r.ok or 401); a rate limit or a server error keeps it. */
      .then(function (r) { if (r.ok || r.status === 401) { try { localStorage.removeItem('familyos.token'); } catch (e) { /* no storage */ } } }, function () { /* keep it, try again next time */ }) : Promise.resolve();
    adopted.then(function () { return fetch('/v1/me'); }).then(function (r) { if (r.ok) window.location.replace(BASE); }, function () { /* show the page */ });
    Array.prototype.forEach.call(document.querySelectorAll('[data-start]'), function (a) { a.setAttribute('href', '#start'); a.addEventListener('click', function (e) { e.preventDefault(); openAuth('new'); }); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-signin]'), function (a) { a.setAttribute('href', '#signin'); a.hidden = false; a.addEventListener('click', function (e) { e.preventDefault(); openAuth('in'); }); });
    wireAuth(BASE);
    if (window.location.hash === '#start') openAuth('new'); else if (window.location.hash === '#signin') openAuth('in');
    var copy = document.getElementById('copy'); if (copy) copy.hidden = true;
    var fl = document.getElementById('final-lede'); if (fl) fl.textContent = 'Create a household in a minute and become its first guardian. Forward one notice and see what it becomes. Invite the rest of the family when you are ready.';
  }

  /* sign in and start a household without leaving the page: the same calls the console makes */
  function say(t, bad) { authMsg.textContent = t || ''; authMsg.classList.toggle('bad', !!bad); }
  function tabAuth(which) {
    Array.prototype.forEach.call(authEl.querySelectorAll('[data-auth-tab]'), function (b) { b.setAttribute('aria-selected', b.getAttribute('data-auth-tab') === which ? 'true' : 'false'); });
    Array.prototype.forEach.call(authEl.querySelectorAll('[data-auth-panel]'), function (p) { p.hidden = p.getAttribute('data-auth-panel') !== which; });
    say('');
  }
  function openAuth(which) {
    tabAuth(which);
    if (!authEl.open) { if (authEl.showModal) authEl.showModal(); else authEl.setAttribute('open', ''); }
    var first = authEl.querySelector('[data-auth-panel]:not([hidden]) input');
    if (first && which === 'new') window.setTimeout(function () { first.focus(); }, 60);
  }
  function api(path, opts) {
    opts = opts || {};
    var headers = { 'Content-Type': 'application/json', 'X-FamilyOS-CSRF': '1' };       /* the server sets the session cookie for a call that carries this */
    return fetch('/v1' + path, { method: opts.method || 'GET', headers: headers, body: opts.json ? JSON.stringify(opts.json) : undefined }).then(function (r) {
      return r.text().then(function (t) {
        var d = null; try { d = t ? JSON.parse(t) : null; } catch (e) { /* not JSON */ }
        if (!r.ok) { var err = new Error((d && (d.detail || d.error)) || 'Something went wrong (' + r.status + ')'); err.status = r.status; throw err; }
        return d;
      });
    });
  }
  function enter(base) { window.location.href = base; }
  function wireAuth(base) {
    Array.prototype.forEach.call(authEl.querySelectorAll('[data-auth-tab]'), function (b) { b.addEventListener('click', function () { tabAuth(b.getAttribute('data-auth-tab')); }); });
    document.getElementById('auth-close').addEventListener('click', function () { authEl.close(); });
    authEl.addEventListener('click', function (e) { if (e.target === authEl) authEl.close(); });
    /* a passkey: the device signs a one-use challenge; only a public key is kept on the server */
    var pk = document.getElementById('auth-passkey');
    function buf(b64u) { var s = b64u.replace(/-/g, '+').replace(/_/g, '/'); s += '==='.slice((s.length + 3) % 4); var raw = atob(s), out = new Uint8Array(raw.length); for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i); return out.buffer; }
    function b64u(ab) { var b = new Uint8Array(ab), s = ''; for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
    if (pk && window.PublicKeyCredential && navigator.credentials) {
      pk.hidden = false; document.getElementById('auth-passkey-note').hidden = false;
      pk.addEventListener('click', function () {
        say('Waiting for your passkey');
        api('/sign-in/passkey/options', { method: 'POST' }).then(function (o) {
          return navigator.credentials.get({ publicKey: { challenge: buf(o.challenge), rpId: o.rpId, timeout: o.timeout, userVerification: o.userVerification || 'preferred', allowCredentials: [] } });
        }).then(function (c) {
          var r = c.response;
          return api('/sign-in/passkey', { method: 'POST', json: { credential: { id: c.id, rawId: b64u(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
            response: { clientDataJSON: b64u(r.clientDataJSON), authenticatorData: b64u(r.authenticatorData), signature: b64u(r.signature), userHandle: r.userHandle ? b64u(r.userHandle) : null } } } });
        }).then(function (done) { enter(base); }, function (err) {
          say(err && err.name === 'NotAllowedError' ? 'No passkey was used. You can try again, or use Google or an email link.' : (err && err.message) || 'Passkey sign-in did not work. Use Google or an email link.', true);
        });
      });
    }
    document.getElementById('auth-google').addEventListener('click', function () {
      say('Opening Google');
      api('/sign-in/google').then(function (w) { window.location.href = w.url; }, function () { say('Google sign-in is not set up here. Use an email link instead.', true); });
    });
    document.getElementById('auth-link').addEventListener('submit', function (e) {
      e.preventDefault();
      var email = new FormData(e.target).get('email').trim(); if (!email) return;
      api('/sign-in/request', { method: 'POST', json: { email: email } }).then(null, function () { /* the answer is the same either way, on purpose */ }).then(function () {
        say('If ' + email + ' can sign in, a link is on its way. It works once and lasts 15 minutes.');
      });
    });
    document.getElementById('auth-token').addEventListener('submit', function (e) {
      e.preventDefault();
      var token = new FormData(e.target).get('token').trim(); if (!token) return;
      api('/session', { method: 'POST', json: { token: token } }).then(function () { enter(base); }, function () { say('That token was not accepted.', true); });
    });
    document.getElementById('auth-new').addEventListener('submit', function (e) {
      e.preventDefault();
      var f = new FormData(e.target);
      say('Creating your household');
      api('/households', { method: 'POST', json: { name: f.get('name').trim(), guardian: { display_name: f.get('display_name').trim(), email: f.get('email').trim() }, founding: '' } })
        .then(function (made) { enter(base); }, function (err) { say(err.message, true); });
    });
  }
})();
