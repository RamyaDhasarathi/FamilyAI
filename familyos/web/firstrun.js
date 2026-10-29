/* First run: the few calm screens a new home sees once, before the console (docs/first-run.md).
 *
 * One question a screen, a "why" fold-out on the personal ones, Skip on everything but the name. The server says when it is due
 * (GET /household/onboarding -> wizard) and answering the name step ends it for good, so a refresh never starts it over.
 * Loaded before app.js; it uses that file's api, esc, flash, fail, root and store when it runs.
 */
'use strict';

const FR_STEPS = ['name', 'family', 'channel', 'mail', 'done'];

/* Called from render(): true when the first-run screens took over the page. Asked once per page load. */
async function firstRunDue() {
  if (store.firstRunChecked) return false;
  store.firstRunChecked = true;
  let status;
  try { status = await api('/household/onboarding'); } catch (e) { return false; }
  if (!status || !status.wizard) return false;
  firstRun(status);
  return true;
}

function firstRun(status) {
  const me = store.me || {};
  const household = store.household || {};
  const state = {
    at: 0,
    status,
    home: household.name || '',
    kids: [{ name: '', age: '' }],
    adult: { name: '', email: '' },
    added: [],
    telegram: !!household.telegram_bot,           // a way in only where one is set up
    linked: false,
    opened: false,
  };
  // The channel step is left out where no bot is configured; the mail step stays (it says so itself if Google is not set up).
  const order = FR_STEPS.filter((k) => k !== 'channel' || state.telegram);

  const first = (me.display_name || '').split(' ')[0] || '';
  const suggest = first ? 'The ' + (me.display_name || '').split(' ').slice(-1)[0] + ' family' : 'Our family';

  function frame(body, opts) {
    const o = opts || {};
    const pct = Math.round(((state.at + 1) / order.length) * 100);
    root.className = '';
    root.innerHTML = '<div class="fr"><div class="fr-in">'
      + '<div class="fr-top">' + (state.at > 0 && order[state.at] !== 'done' ? '<button class="fr-back" type="button" data-back aria-label="Back">&larr;</button>' : '<span></span>')
      + '<div class="fr-bar" role="progressbar" aria-valuemin="0" aria-valuemax="' + order.length + '" aria-valuenow="' + (state.at + 1) + '"><i style="width:' + pct + '%"></i></div></div>'
      + body
      + '<div class="fr-foot">' + (o.primary ? '<button class="btn fr-primary" type="button" data-primary>' + esc(o.primary) + '</button>' : '')
      + (o.skip ? '<button class="fr-skip" type="button" data-skip>' + esc(o.skip) + '</button>' : '') + '</div>'
      + '</div></div>';
    const back = root.querySelector('[data-back]');
    if (back) back.addEventListener('click', () => { state.at -= 1; draw(); });
    return {
      primary: (fn) => { const b = root.querySelector('[data-primary]'); if (b) b.addEventListener('click', () => fn(b)); },
      skip: (fn) => { const b = root.querySelector('[data-skip]'); if (b) b.addEventListener('click', () => fn(b)); },
    };
  }

  function why(text) {
    return '<details class="fr-why"><summary>Why I ask</summary><p>' + esc(text) + '</p></details>';
  }

  function next() { state.at = Math.min(state.at + 1, order.length - 1); draw(); }

  const screens = {
    name() {
      const w = frame('<h1>Welcome' + (first ? ', ' + esc(first) : '') + '.</h1>'
        + '<p class="fr-sub">What is your family called? It is only a label for the top of the page and the morning brief.</p>'
        + '<label class="fr-field"><span>Family name</span><input type="text" data-home maxlength="100" value="' + esc(state.home || suggest) + '" autocomplete="off"></label>'
        + why('So the brief reads "the Iyer family" and not an email address. You can change it any time.'),
        { primary: 'Continue' });
      w.primary(async (btn) => {
        const name = root.querySelector('[data-home]').value.trim();
        if (!name) { flash('Give the family a name to go on.', true); return; }
        try {
          if (name !== household.name) store.household = await api('/household', { method: 'PATCH', json: { name } });
          state.home = name;
          // Answering this step is what ends the first-run screens for good.
          await api('/household/onboarding/named', { method: 'POST' });
          next();
        } catch (err) { fail(err); }
      });
    },

    family() {
      const kidRows = state.kids.map((k, i) => '<div class="fr-row"><input type="text" data-kid-name="' + i + '" placeholder="First name" maxlength="100" value="' + esc(k.name) + '" aria-label="Child ' + (i + 1) + ' first name">'
        + '<select data-kid-age="' + i + '" aria-label="Child ' + (i + 1) + ' age"><option value="">Age</option>'
        + Array.from({ length: 19 }, (_, a) => '<option value="' + a + '"' + (String(k.age) === String(a) ? ' selected' : '') + '>' + a + '</option>').join('')
        + '</select>' + (state.kids.length > 1 ? '<button class="fr-x" type="button" data-kid-del="' + i + '" aria-label="Remove child ' + (i + 1) + '">&times;</button>' : '') + '</div>').join('');
      const done = state.added.length ? '<p class="fr-added">Added: ' + state.added.map(esc).join(', ') + '</p>' : '';
      const w = frame('<h1>Tell me about your family.</h1>'
        + '<p class="fr-sub">Names and ages help me work out whose school mail is whose.</p>'
        + '<div class="fr-group"><b>Children</b>' + kidRows + '<button class="fr-add" type="button" data-kid-add>+ Add another</button></div>'
        + '<div class="fr-group"><b>Partner or another adult</b><p class="fr-sub">They get a sign-in link by email. They do not need to connect a mailbox.</p>'
        + '<div class="fr-row"><input type="text" data-adult-name placeholder="First name" maxlength="100" value="' + esc(state.adult.name) + '" aria-label="Adult first name">'
        + '<input type="email" data-adult-email placeholder="their@email" value="' + esc(state.adult.email) + '" aria-label="Adult email"></div></div>'
        + done
        + why('Children are matched to their school and class so a circular lands with the right person. Only a first name and an age are kept for a child, and nothing else is asked.'),
        { primary: 'Continue', skip: 'Skip for now' });
      const readRows = () => {
        state.kids = state.kids.map((_, i) => ({ name: root.querySelector('[data-kid-name="' + i + '"]').value, age: root.querySelector('[data-kid-age="' + i + '"]').value }));
        state.adult = { name: root.querySelector('[data-adult-name]').value, email: root.querySelector('[data-adult-email]').value };
      };
      root.querySelector('[data-kid-add]').addEventListener('click', () => { readRows(); state.kids.push({ name: '', age: '' }); draw(); });
      root.querySelectorAll('[data-kid-del]').forEach((b) => b.addEventListener('click', () => { readRows(); state.kids.splice(Number(b.dataset.kidDel), 1); draw(); }));
      w.skip(() => next());
      w.primary(async () => {
        readRows();
        const year = new Date().getFullYear();
        try {
          for (const k of state.kids.filter((x) => x.name.trim())) {
            if (k.age === '') { flash('How old is ' + k.name.trim() + '?', true); return; }
            // An age is kept as a mid-year birth date, so it is right for the year without asking for a birthday.
            await api('/household/members', { method: 'POST', json: { display_name: k.name.trim(), role: 'child', date_of_birth: (year - Number(k.age)) + '-07-01' } });
            state.added.push(k.name.trim());
          }
          state.kids = [{ name: '', age: '' }];
          const a = state.adult;
          if (a.email.trim()) {
            if (!a.name.trim()) { flash('What should I call them?', true); return; }
            const made = await api('/household/members', { method: 'POST', json: { display_name: a.name.trim(), role: 'adult', email: a.email.trim() } });
            const id = made.member ? made.member.id : made.id;
            try { await api('/members/' + id + '/invite', { method: 'POST' }); } catch (e) { flash('Added, but the invitation did not send. Invite them from Family.', true); }
            state.added.push(a.name.trim());
            state.adult = { name: '', email: '' };
          }
          next();
        } catch (err) { fail(err); }
      });
    },

    channel() {
      const w = frame('<h1>Message me from your phone.</h1>'
        + '<p class="fr-sub">Your morning brief, the school note you would have missed, a reminder before it is too late. You can answer right there.</p>'
        + '<div class="fr-mock"><p class="in">Morning. Your day is clear until pickup at 3. One thing needs you: the lunch order closes at noon.</p><p class="out">Doing it now, thank you</p></div>'
        + (state.linked ? '<p class="fr-added">Linked. I said hello on Telegram.</p>' : '')
        + why('Telegram is where I can message you first. I only ever write to you, never to anyone else, and you can unlink it from Settings.'),
        { primary: state.linked ? 'Continue' : 'Open Telegram', skip: state.linked ? '' : 'Skip for now' });
      w.primary(async (btn) => {
        if (state.linked) { next(); return; }
        try {
          if (!state.opened) {
            const link = await api('/telegram/link', { method: 'POST' });
            window.open(link.url, '_blank', 'noopener');
            state.opened = true;
            flash('Telegram opened. Press Start there, then come back.');
            btn.textContent = 'I pressed Start';
            return;
          }
          const s = await api('/household/onboarding');
          const ch = (s.steps || []).find((x) => x.key === 'channel');
          if (ch && ch.done) { state.linked = true; draw(); } else { flash('Not linked yet. Press Start in Telegram first.', true); }
        } catch (err) { fail(err); }
      });
      w.skip(async () => { try { await api('/household/onboarding/skip_channel', { method: 'POST' }); } catch (e) { /* later, from the checklist */ } next(); });
    },

    mail() {
      const w = frame('<h1>Connect your mail and calendar.</h1>'
        + '<p class="fr-sub">Family life runs through your inbox. I read it for what each message asks of you, so nothing slips through.</p>'
        + '<ul class="fr-asks"><li><b>Asked</b><span>Read your mail and your calendar</span></li>'
        + '<li><b>Not asked</b><span>Sending mail, or changing anything. Anything I would send, you approve first.</span></li></ul>'
        + why('Google will show its own permission screen next. You can disconnect, and delete what was read, at any time in Settings.'),
        { primary: 'Connect Google', skip: 'Skip for now' });
      w.primary(async () => {
        try { const begun = await api('/google/mailboxes/authorize', { method: 'POST' }); window.location.href = begun.url; }
        catch (err) { fail(err); }
      });
      w.skip(async () => { try { await api('/household/onboarding/skip_mail', { method: 'POST' }); } catch (e) { /* later, from the checklist */ } next(); });
    },

    done() {
      const w = frame('<h1>That is the start.</h1>'
        + '<p class="fr-sub">' + (state.added.length ? esc(state.added.join(', ')) + ' ' + (state.added.length > 1 ? 'are' : 'is') + ' in. ' : '')
        + 'Forward a school mail or share a screenshot to see it work. What is left, such as making the home private, waits on your Today page.</p>',
        { primary: 'Go to Today' });
      w.primary(() => { window.location.hash = '#/today'; render(); });
    },
  };

  function draw() { screens[order[state.at]](); const f = root.querySelector('input,select'); if (f) f.focus({ preventScroll: true }); }
  draw();
}
