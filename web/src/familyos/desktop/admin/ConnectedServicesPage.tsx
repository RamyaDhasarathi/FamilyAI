// Connected services, /services: the sites the browser agent may sign in to for you (Amazon, Flipkart …), decided
// 30 Oct 2026. Search the list, add a site with its username and password, remove it. The password goes to the Keychain
// of the Mac running FamilyOS (/v1/collect/services, familyos/collect/vault.py); this page never shows one back.
// Each connected site can be collected by the browser agent (familyos/collect/browser_agent.py): it signs in and reads the
// orders, bookings or bills, never buying or changing anything; "Sign in yourself" opens a window on that Mac for a
// one-time code. What it read shows under the site.
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import clsx from 'clsx';
import { KeyRound } from 'lucide-react';
import { T } from '../../theme/typography';
import { Pressable } from '../../components/Pressable';
import { useFamilyOS } from '../../store/useFamilyOS';
import { API_ENABLED, request } from '../../services/api';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { Field } from './AdminBits';
import './admin.css';

interface Site {
  id: string;
  name: string;
  host: string | null;
  kind: string;
}
interface Connected {
  service: string;
  name: string;
  username: string;
  host: string;
  added_at: string;
  running: boolean;
  items: number;
  last_run: { finished_at: string; counts: { kept?: number; cost_usd?: number }; errors: { outcome?: string; note?: string } } | null;
}
interface Item {
  id: string;
  title: string;
  amount: string | null;
  status: string | null;
  happened: string | null;
}

/** The last run, in one line. */
function lastRun(c: Connected): string {
  if (c.running) return 'Collecting now…';
  const r = c.last_run;
  if (!r) return 'Not collected yet.';
  const cost = r.counts.cost_usd != null ? ` · $${r.counts.cost_usd.toFixed(3)}` : '';
  if (r.errors.outcome === 'needs_sign_in') return `Needs you to sign in once (${r.errors.note ?? 'a code'}): use Sign in yourself.`;
  if (r.errors.outcome) return `${r.errors.outcome === 'failed' ? 'Failed' : 'Stopped'}: ${r.errors.note ?? ''}${cost}`;
  return `Read ${r.counts.kept ?? 0} on ${new Date(r.finished_at).toLocaleString()}${cost}`;
}

export default function ConnectedServicesPage() {
  const toast = useFamilyOS((s) => s.toast);
  const [catalog, setCatalog] = useState<Site[]>([]);
  const [connected, setConnected] = useState<Connected[]>([]);
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<Site | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [host, setHost] = useState('');
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const [open, setOpen] = useState<{ service: string; items: Item[] } | null>(null);

  const read = useCallback(() => request<{ catalog: Site[]; connected: Connected[]; agent?: { model: string | null } }>('GET', '/collect/services'), []);
  const apply = useCallback((d: { catalog: Site[]; connected: Connected[]; agent?: { model: string | null } }) => {
    setCatalog(d.catalog);
    setConnected(d.connected);
    setModel(d.agent?.model ?? null);
  }, []);
  useEffect(() => {
    if (!API_ENABLED) return;
    let live = true;
    void read()
      .then((d) => live && apply(d))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [read, apply]);

  // While the agent is on a site, look again every few seconds.
  const running = connected.some((c) => c.running);
  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => void read().then(apply, () => undefined), 5000);
    return () => clearTimeout(t);
  }, [running, connected, read, apply]);

  const collect = async (c: Connected) => {
    try {
      await request('POST', `/collect/services/${c.service}/run`);
      toast(`Collecting from ${c.name}. A browser window opens on the Mac while it works.`);
      apply(await read());
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not start.', { duration: 5000 });
    }
  };

  const signInYourself = async (c: Connected) => {
    try {
      await request('POST', `/collect/services/${c.service}/sign-in`);
      toast(`A window with ${c.name} is open on the Mac running FamilyOS. Sign in there, then close it.`, { duration: 6000 });
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not open it.', { duration: 5000 });
    }
  };

  const show = async (c: Connected) => {
    if (open?.service === c.service) return setOpen(null);
    try {
      setOpen({ service: c.service, items: await request<Item[]>('GET', `/collect/services/${c.service}/items`) });
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not read them.', { duration: 5000 });
    }
  };

  const have = new Set(connected.map((c) => c.service));
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.filter((s) => !have.has(s.id) || s.id === 'other').filter((s) => !q || s.name.toLowerCase().includes(q) || (s.host ?? '').includes(q));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, connected, query]);

  const pick = (s: Site) => {
    setPicked(s);
    setUsername('');
    setPassword('');
    setHost('');
  };

  const save = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!picked) return;
    setBusy(true);
    try {
      await request('POST', '/collect/services', { service: picked.id, username, password, host: picked.id === 'other' ? host : undefined });
      setPassword('');
      setPicked(null);
      toast(`${picked.name} connected. Its password is in this Mac's Keychain.`);
      apply(await read());
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not connect it.', { duration: 5000 });
    }
    setBusy(false);
  };

  const remove = async (c: Connected) => {
    try {
      await request('DELETE', `/collect/services/${c.service}`);
      toast(`${c.name} removed, and its password with it.`);
      apply(await read());
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not remove it.', { duration: 5000 });
    }
  };

  return (
    <DeskPage
      className="adm-page"
      icon={KeyRound}
      title="Connected services"
      description="Sites FamilyOS's browser agent may sign in to for you, to collect orders, bills and bookings. Passwords stay in this Mac's Keychain."
      rail={
        <DeskCard title="Your connected sites" sub={connected.length ? `${connected.length}` : undefined}>
          {connected.length ? (
            <ul className="adm-list">
              {connected.map((c) => (
                <li key={c.service} className="adm-row cs-site">
                  <span className="adm-row__main">
                    <span className={clsx(T.smallStrong, 'adm-row__title')}>{c.name}</span>
                    <span className={clsx(T.small, 'adm-row__sub')}>
                      {c.username} · {c.host}
                    </span>
                    <span className={clsx(T.small, 'adm-row__sub')}>{lastRun(c)}</span>
                  </span>
                  <span className="cs-actions">
                    <Pressable className="pill pill--primary" disabled={c.running || !model} onClick={() => void collect(c)} aria-label={`Collect from ${c.name}`}>
                      {c.running ? 'Collecting…' : 'Collect now'}
                    </Pressable>
                    <Pressable className="pill" disabled={c.running} onClick={() => void signInYourself(c)} aria-label={`Sign in to ${c.name} yourself`}>
                      Sign in yourself
                    </Pressable>
                    {c.items ? (
                      <Pressable className="pill" onClick={() => void show(c)} aria-expanded={open?.service === c.service} aria-label={`What was read from ${c.name}`}>
                        {open?.service === c.service ? 'Hide' : `Read (${c.items})`}
                      </Pressable>
                    ) : null}
                    <Pressable className="pill" onClick={() => void remove(c)} aria-label={`Remove ${c.name}`}>
                      Remove
                    </Pressable>
                  </span>
                  {open?.service === c.service ? (
                    <ul className="adm-list cs-items">
                      {open.items.map((it) => (
                        <li key={it.id} className={T.small}>
                          <strong>{it.title}</strong>
                          {[it.happened, it.amount, it.status].filter(Boolean).length ? ` · ${[it.happened, it.amount, it.status].filter(Boolean).join(' · ')}` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className={T.small}>None yet. Pick a site and add its sign-in.</p>
          )}
          <p className={clsx(T.small, 'adm-row__sub')}>FamilyOS never shows a saved password. Removing a site deletes it from the Keychain.</p>
          <p className={clsx(T.small, 'adm-row__sub')}>
            {model
              ? `The browser agent (${model}) only reads: it never buys, books or changes anything, and never sees the password.`
              : 'The browser agent needs a Claude key on the server.'}
          </p>
        </DeskCard>
      }
    >
      {!API_ENABLED ? (
        <DeskCard>
          <p className={T.small}>This page needs the FamilyOS server: it is empty on the demo data.</p>
        </DeskCard>
      ) : picked ? (
        <DeskCard title={`Connect ${picked.name}`} sub={picked.host ?? 'any site'}>
          <form className="adm-form" onSubmit={save} aria-label={`Connect ${picked.name}`}>
            {picked.id === 'other' ? (
              <Field label="The site's address">
                {({ id }) => <input id={id} className="adm-input" value={host} placeholder="portal.school.example" autoCapitalize="none" spellCheck={false} onChange={(e) => setHost(e.target.value)} />}
              </Field>
            ) : null}
            <Field label="Username, email or phone">
              {({ id }) => <input id={id} className="adm-input" value={username} autoComplete="off" autoCapitalize="none" spellCheck={false} onChange={(e) => setUsername(e.target.value)} />}
            </Field>
            <Field label="Password">
              {({ id }) => <input id={id} className="adm-input" type="password" value={password} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />}
            </Field>
            <p className={T.small}>Kept in the Keychain of the Mac running FamilyOS, used only when the browser agent signs in to {picked.name}. A one-time code still comes to you.</p>
            <div className="adm-actions">
              <Pressable type="submit" className="pill pill--primary" disabled={busy || !username.trim() || !password || (picked.id === 'other' && !host.trim())}>
                {busy ? 'Saving…' : 'Connect'}
              </Pressable>
              <Pressable className="pill" onClick={() => setPicked(null)}>
                Cancel
              </Pressable>
            </div>
          </form>
        </DeskCard>
      ) : (
        <DeskCard title="Add a site">
          <Field label="Search">
            {({ id }) => <input id={id} className="adm-input" value={query} placeholder="Amazon, Swiggy, IRCTC…" onChange={(e) => setQuery(e.target.value)} />}
          </Field>
          <ul className="adm-list">
            {shown.map((s) => (
              <li key={s.id} className="adm-row">
                <span className="adm-row__main">
                  <span className={clsx(T.smallStrong, 'adm-row__title')}>{s.name}</span>
                  <span className={clsx(T.small, 'adm-row__sub')}>{s.host ?? 'any site, by its address'}</span>
                </span>
                <StatusChip tone="neutral">{s.kind}</StatusChip>
                <Pressable className="pill" onClick={() => pick(s)} aria-label={`Connect ${s.name}`}>
                  Connect
                </Pressable>
              </li>
            ))}
          </ul>
        </DeskCard>
      )}
    </DeskPage>
  );
}
