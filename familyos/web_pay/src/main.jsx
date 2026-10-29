// The guardian's screens for the payment provider: save a card, and verify an allowance for an approved purchase.
// The provider's own components draw the card form and the verification step inside their own frames, so a card
// number never reaches FamilyOS or this page. Everything else here is FamilyOS's own API.
import React, { useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CrossmintProvider, CrossmintPaymentMethodManagement, OrderIntentVerification } from '@crossmint/client-sdk-react-ui';

// The session is the console's HttpOnly cookie, sent with every same-origin request; the header is the proof the call came from our own page.
async function api(method, path, body) {
  const r = await fetch('/v1' + path, { method, headers: { 'X-FamilyOS-CSRF': '1', 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  let data = null; try { data = text ? JSON.parse(text) : null; } catch (e) { /* not JSON */ }
  if (!r.ok) { const err = new Error((data && (data.detail || data.error)) || 'Something went wrong (' + r.status + ')'); err.status = r.status; throw err; }
  return data;
}
const money = (p) => p.amount.toLocaleString(undefined, { style: 'currency', currency: p.currency.trim() });

function Purchase({ p, session, reload }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [asked, setAsked] = useState(false);       // the network's screen opens only when asked, never on a refresh
  const intent = p.provider_state && p.provider_state.order_intent;
  const rail = intent && (intent.rails || []).find((r) => r.rail === 'agentic-token');
  const needsVerification = p.status === 'ready' && intent && rail && rail.status === 'pending_verification';
  const verified = p.status === 'ready' && intent && !needsVerification;
  const run = async (fn) => { setBusy(true); setErr(null); try { await fn(); await reload(); } catch (e) { setErr(e.message); } finally { setBusy(false); } };
  return (
    <div className="row">
      <div>
        <strong>{p.title}</strong><div className="muted">{p.merchant_name} · {money(p)} · {p.status}</div>
        {p.note && <div className="muted">{p.note}</div>}
        {err && <div className="warn">{err}</div>}
      </div>
      <div>
        {p.status === 'requested' && <><button disabled={busy} onClick={() => run(() => api('POST', '/purchases/' + p.id + '/decision', { approve: true }))}>Approve</button> <button className="quiet" disabled={busy} onClick={() => run(() => api('POST', '/purchases/' + p.id + '/decision', { approve: false }))}>Decline</button></>}
        {p.status === 'approved' && <button disabled={busy} onClick={() => run(() => api('POST', '/purchases/' + p.id + '/allowance'))}>Make the allowance</button>}
        {needsVerification && !asked && <button disabled={busy} onClick={() => setAsked(true)}>Verify with the card network</button>}
        {needsVerification && asked && (
          <OrderIntentVerification orderIntent={intent} displayName="FamilyOS"
            onVerificationComplete={() => run(async () => { setAsked(false); await api('POST', '/purchases/' + p.id + '/refresh'); })}
            onVerificationError={(e) => { setAsked(false); setErr(String((e && e.message) || e)); }} />
        )}
        {verified && <span className="ok">Verified</span>}
        {p.status === 'ready' && <button className="quiet" disabled={busy} onClick={() => run(() => api('POST', '/purchases/' + p.id + '/refresh'))}>Check</button>}
        {['requested', 'approved', 'ready'].includes(p.status) && <button className="quiet" disabled={busy} onClick={() => run(() => api('DELETE', '/purchases/' + p.id))}>Cancel</button>}
      </div>
    </div>
  );
}

function Ask({ reload, currency }) {
  const [f, setF] = useState({ title: '', merchant_name: '', merchant_url: 'https://', amount: '' });
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    try { await api('POST', '/purchases', { ...f, amount: Number(f.amount), currency }); setF({ title: '', merchant_name: '', merchant_url: 'https://', amount: '' }); await reload(); } catch (x) { setErr(x.message); }
  };
  const box = { font: 'inherit', padding: '10px 12px', borderRadius: 10, border: '1px solid var(--line)', background: 'var(--paper)', color: 'var(--ink)', minHeight: 44, width: '100%', boxSizing: 'border-box' };
  return (
    <form className="card" onSubmit={submit} style={{ display: 'grid', gap: 8 }}>
      <h2>Ask for a purchase</h2>
      <input style={box} placeholder="What for" value={f.title} onChange={set('title')} required />
      <input style={box} placeholder="Merchant" value={f.merchant_name} onChange={set('merchant_name')} required />
      <input style={box} placeholder="Merchant website" value={f.merchant_url} onChange={set('merchant_url')} required />
      <input style={box} placeholder={'Amount in ' + currency} inputMode="decimal" value={f.amount} onChange={set('amount')} required />
      {err && <div className="warn">{err}</div>}
      <div><button type="submit">Ask</button></div>
      <div className="muted">A guardian approves each purchase before anything is made.</div>
    </form>
  );
}

function App() {
  const [state, setState] = useState({ loading: true });
  const load = useCallback(async () => {
    try {
      const [status, purchases] = await Promise.all([api('GET', '/payments'), api('GET', '/purchases')]);
      let session = null, problem = null;
      try { session = await api('POST', '/payments/session'); } catch (e) { problem = e.message; }
      setState({ status, purchases, session, problem });
    } catch (e) { setState(e.status === 401 ? { signedOut: true } : { error: e.message }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (state.loading) return <p className="muted">Loading</p>;
  if (state.signedOut) return <div className="card"><h1>FamilyOS payments</h1><p>Sign in to the console first, then come back here.</p><p><a href="/app/">Open the console</a></p></div>;
  if (state.error) return <div className="card"><h1>FamilyOS payments</h1><p className="warn">{state.error}</p></div>;
  const { status, purchases, session, problem } = state;
  const waiting = purchases.filter((p) => ['requested', 'approved', 'ready'].includes(p.status));
  return (
    <>
      <div><h1>Payments</h1><p className="muted">{status.enabled ? 'On' : 'Off'} for this household{status.environment ? ' · ' + status.environment + ' mode' : ''}. Nothing is bought without a guardian approving that one purchase. FamilyOS never sees a card number.</p></div>
      {problem && <div className="card"><p className="warn">{problem}</p></div>}
      {status.enabled && <Ask reload={load} currency={status.currency} />}
      {session && (
        <CrossmintProvider apiKey={session.client_key}>
          <div className="card">
            <h2>Your card</h2>
            {status.has_card ? <p className="ok">A card is saved for you.</p> : <p className="muted">Save the card an approved purchase may use. It is held by the provider; FamilyOS keeps only an id.</p>}
            <CrossmintPaymentMethodManagement jwt={session.jwt} allowedMethods={['card']}
              onPaymentMethodSelected={async (m) => { try { await api('PUT', '/payments/card', { payment_method_id: m.paymentMethodId }); await load(); } catch (e) { setState((s) => ({ ...s, problem: e.message })); } }} />
          </div>
          <div className="card">
            <h2>Waiting for you</h2>
            {waiting.length === 0 && <p className="muted">No approved purchase is waiting.</p>}
            {waiting.map((p) => <Purchase key={p.id} p={p} session={session} reload={load} />)}
          </div>
        </CrossmintProvider>
      )}
      <div className="card">
        <h2>All purchases</h2>
        {purchases.length === 0 && <p className="muted">None yet.</p>}
        {purchases.map((p) => <div className="row" key={p.id}><div><strong>{p.title}</strong><div className="muted">{p.merchant_name} · {money(p)}</div></div><span className="muted">{p.status}</span></div>)}
      </div>
    </>
  );
}

createRoot(document.getElementById('root')).render(<App />);
