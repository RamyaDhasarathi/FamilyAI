/* The optional family wallet's card (docs/wallet.md). Loaded before app.js and used from Settings, Privacy and security.
 *
 * The card draws nothing for a household that has not chosen the wallet: it asks GET /v1/wallet, and the 404 that answers removes the card.
 * The browser's own wallet (window.ethereum, EIP-1193) does the signing and the sending; FamilyOS holds no key. Test network only.
 * Uses the console's api, esc, flash and fail, which app.js defines in the same page; they are only called after the page has loaded.
 */
'use strict';

function walletHex(text) {
  return '0x' + Array.from(new TextEncoder().encode(text), (b) => b.toString(16).padStart(2, '0')).join('');
}

function walletShort(address) {
  return address ? address.slice(0, 6) + '…' + address.slice(-4) : '';
}

/* The wallet this browser offers, and the account the person lets us see. */
async function walletAccount() {
  const eth = window.ethereum;
  if (!eth || typeof eth.request !== 'function') throw new Error('No wallet found in this browser. Install a browser wallet and reload.');
  const accounts = await eth.request({ method: 'eth_requestAccounts' });
  if (!accounts || !accounts[0]) throw new Error('The wallet did not share an account.');
  return accounts[0];
}

async function walletSign(account, text) {
  return window.ethereum.request({ method: 'personal_sign', params: [walletHex(text), account] });
}

const WALLET_STATUS = {
  proposed: 'waiting for a guardian', approved: 'approved: send it from the family wallet', submitted: 'sent: waiting for the network',
  settled: 'confirmed by the network', rejected: 'turned down', expired: 'lapsed', failed: 'the network does not show it as approved',
};

function walletCard() {
  return '<div class="card pad stack" data-wallet style="gap:10px" hidden><div class="row wrap" style="gap:8px"><h2>Family wallet</h2>'
    + '<span class="tag" data-wallet-net></span></div><div data-wallet-body class="muted">Loading…</div></div>';
}

function walletTransferHtml(t, me, fam) {
  const guardian = me.role === 'guardian';
  let act = '';
  if (t.status === 'proposed' && guardian) act = '<button class="btn sm" type="button" data-wallet-approve="' + esc(t.id) + '">Approve with my wallet</button> <button class="btn sm ghost" type="button" data-wallet-reject="' + esc(t.id) + '">Turn down</button>';
  else if (t.status === 'proposed' && t.proposed_by === me.id) act = '<button class="btn sm ghost" type="button" data-wallet-reject="' + esc(t.id) + '">Withdraw</button>';
  else if (t.status === 'approved' && guardian) act = '<button class="btn sm" type="button" data-wallet-send="' + esc(t.id) + '">Send from the family wallet</button> <button class="btn sm ghost" type="button" data-wallet-reject="' + esc(t.id) + '">Cancel</button>';
  else if (t.status === 'submitted') act = '<button class="btn sm ghost" type="button" data-wallet-check="' + esc(t.id) + '">Check the network</button>';
  return '<div class="item" style="cursor:default"><span class="grow"><span class="title">' + esc(t.amount) + ' ' + esc(t.token) + ' to ' + esc(t.payee_label || walletShort(t.payee_address)) + '</span>'
    + (t.payee_new ? ' <span class="tag amber">new payee</span>' : '')
    + '<span class="muted" style="display:block">' + esc(walletShort(t.payee_address)) + (t.memo ? ' · ' + esc(t.memo) : '') + ' · ' + esc(WALLET_STATUS[t.status] || t.status) + (t.failure_reason ? ' (' + esc(t.failure_reason) + ')' : '') + '</span>'
    + (act ? '<span class="row wrap" style="gap:6px;margin-top:6px">' + act + '</span>' : '') + '</span></div>';
}

async function wireWallet(main) {
  const root = main.querySelector('[data-wallet]'); if (!root) return;
  const body = root.querySelector('[data-wallet-body]');
  const draw = async () => {
    let w;
    try { w = await api('/wallet'); } catch (err) {
      if (err.status === 404) { root.remove(); return; }                 // not offered here, or not chosen by this household: nothing to show
      root.hidden = false; body.textContent = err.message || 'Could not load.'; return;
    }
    const me = store.me, guardian = me.role === 'guardian', fam = w.family_wallet, lim = fam.limits;
    root.hidden = false;
    root.querySelector('[data-wallet-net]').textContent = 'test network · ' + w.network.name;
    body.className = 'stack'; body.style.gap = '12px';
    body.innerHTML = '<p class="muted" style="line-height:1.55;margin:0">Test tokens only, no real money. FamilyOS never holds a key and never sends anything: a guardian approves exactly what is shown by signing with their own wallet, then sends it from the family wallet.</p>'
      + '<div><h3>The family wallet</h3>' + (fam.address
        ? '<p style="margin:4px 0">' + esc(fam.label || 'Family wallet') + ' <code>' + esc(fam.address) + '</code></p>'
          + '<p class="muted" style="margin:0">' + (fam.balance ? 'Balance ' + esc(fam.balance.token) + ' ' + esc(w.network.token) : fam.chain_unavailable ? 'The network did not answer; the balance is not shown.' : '')
          + ' · up to ' + esc(lim.per_transfer) + ' a transfer, ' + esc(lim.per_day) + ' a day, ' + esc(lim.per_month) + ' a month</p>'
        : '<p class="muted" style="margin:4px 0">' + (guardian ? 'Name the wallet the family pays from.' : 'A guardian has not named the family wallet yet.') + '</p>')
      + (guardian ? '<form class="md-form" data-wallet-set><label>Address<input name="address" placeholder="0x…" autocomplete="off" value="' + esc(fam.address || '') + '"></label><label>Name<input name="label" maxlength="60" value="' + esc(fam.label || '') + '"></label>'
        + '<label>One transfer, up to<input name="per_transfer" inputmode="decimal" value="' + esc(lim.per_transfer) + '"></label><label>A day, up to<input name="per_day" inputmode="decimal" value="' + esc(lim.per_day) + '"></label>'
        + '<label>A month, up to<input name="per_month" inputmode="decimal" value="' + esc(lim.per_month) + '"></label><button class="btn sm" type="submit">Save</button></form>' : '') + '</div>'
      + '<div><h3>Your wallets</h3>' + (w.my_links.length ? w.my_links.map((l) => '<div class="row wrap" style="gap:8px;margin:4px 0"><code>' + esc(l.address) + '</code> <button class="btn sm ghost" type="button" data-wallet-unlink="' + esc(l.id) + '">Remove</button></div>').join('')
        : '<p class="muted" style="margin:4px 0">None linked. A linked wallet lets you approve transfers (guardians) and sign in without a password.</p>')
      + '<button class="btn sm" type="button" data-wallet-link>Link a wallet</button></div>'
      + (fam.address ? '<div><h3>Propose a transfer</h3><form class="md-form" data-wallet-propose><label>To address<input name="payee_address" placeholder="0x…" autocomplete="off" required></label><label>Who it is<input name="payee_label" maxlength="60"></label>'
        + '<label>Amount (' + esc(w.network.token) + ')<input name="amount" inputmode="decimal" required></label><label>Note<input name="memo" maxlength="140"></label><button class="btn sm" type="submit">Propose</button></form></div>' : '')
      + '<div><h3>Transfers</h3>' + (w.transfers.length ? '<div class="list">' + w.transfers.map((t) => walletTransferHtml(t, me, fam)).join('') + '</div>' : '<p class="muted" style="margin:4px 0">None yet.</p>') + '</div>'
      + (guardian ? '<details><summary>Delete the wallet’s data</summary><p class="muted" style="line-height:1.55">Removes linked wallets, the family wallet, and every transfer. Turning the wallet off in Rules keeps them. This cannot be undone.</p>'
        + '<form class="md-form" data-wallet-delete><label>Type “delete wallet data”<input name="confirm" autocomplete="off"></label><button class="btn sm danger" type="submit">Delete</button></form></details>' : '');
    wire(w, me);
  };
  const run = (fn, ok) => async (ev) => {
    if (ev && ev.preventDefault) ev.preventDefault();
    try { await fn(ev); if (ok) flash(ok); await draw(); } catch (err) { fail(err.status ? err : { message: (err && err.message) || 'That did not work.' }); }
  };
  const wire = (w, me) => {
    const on = (sel, fn) => body.querySelectorAll(sel).forEach((el) => el.addEventListener(el.tagName === 'FORM' ? 'submit' : 'click', fn(el)));
    on('[data-wallet-set]', (f) => run(() => api('/wallet/family-wallet', { method: 'PUT', json: { address: f.address.value.trim() || null, label: f.label.value.trim() || null,
      per_transfer: f.per_transfer.value.trim(), per_day: f.per_day.value.trim(), per_month: f.per_month.value.trim() } }), 'Saved.'));
    on('[data-wallet-link]', () => run(async () => {
      const account = await walletAccount();
      const m = await api('/wallet/links/message', { method: 'POST', json: { address: account } });
      await api('/wallet/links', { method: 'POST', json: { message: m.message, signature: await walletSign(account, m.message) } });
    }, 'Linked.'));
    on('[data-wallet-unlink]', (b) => run(() => api('/wallet/links/' + b.dataset.walletUnlink, { method: 'DELETE' }), 'Removed.'));
    on('[data-wallet-propose]', (f) => run(() => api('/wallet/transfers', { method: 'POST', json: { payee_address: f.payee_address.value.trim(), payee_label: f.payee_label.value.trim() || null,
      amount: f.amount.value.trim(), memo: f.memo.value.trim() || null } }), 'Proposed. A guardian approves it next.'));
    on('[data-wallet-approve]', (b) => run(async () => {
      const t = await api('/wallet/transfers/' + b.dataset.walletApprove);
      if (!window.confirm(t.approval_text + '\n\nApprove exactly this?')) return;                       // the text the wallet will sign, shown first in full
      const account = await walletAccount();
      await api('/wallet/transfers/' + t.id + '/approve', { method: 'POST', json: { signature: await walletSign(account, t.approval_text) } });
    }, 'Approved. Send it from the family wallet.'));
    on('[data-wallet-reject]', (b) => run(() => api('/wallet/transfers/' + b.dataset.walletReject + '/reject', { method: 'POST' }), 'Done.'));
    on('[data-wallet-send]', (b) => run(async () => {
      const t = await api('/wallet/transfers/' + b.dataset.walletSend);
      if (t.status !== 'approved' || !t.send) throw new Error('This transfer is no longer waiting to be sent.');
      const account = await walletAccount();
      if (account.toLowerCase() !== t.from_address.toLowerCase()) throw new Error('Connect the family wallet (' + walletShort(t.from_address) + ') in your browser wallet to send this.');
      try { await window.ethereum.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: '0x' + t.send.chain_id.toString(16) }] }); } catch (e) { /* the wallet will refuse a wrong network itself */ }
      const hash = await window.ethereum.request({ method: 'eth_sendTransaction', params: [{ from: account, to: t.send.to, data: t.send.data, value: t.send.value }] });
      await api('/wallet/transfers/' + t.id + '/submitted', { method: 'POST', json: { tx_hash: hash } });
    }, 'Sent. The network decides whether it matches.'));
    on('[data-wallet-check]', (b) => run(() => api('/wallet/transfers/' + b.dataset.walletCheck + '/check', { method: 'POST' })));
    on('[data-wallet-delete]', (f) => run(() => api('/wallet/delete-data', { method: 'POST', json: { confirm: f.confirm.value } }), 'Deleted.'));
  };
  draw();
}
