// Data sources, /sources: our collecting layer (famos-notes/COLLECTION_PLAN.md). Google first: what it may read (given
// at Google sign-in), how much is collected, the last run and what went wrong, Collect now, and the latest mail, dates
// and tasks. Everything shown is from the local cache on the computer running FamilyOS (GET /v1/collect/…), not the
// family's shared database. On the mocks (no backend) the page says so.
import { useCallback, useEffect, useState } from 'react';
import clsx from 'clsx';
import { DatabaseZap } from 'lucide-react';
import { T } from '../../theme/typography';
import { Pressable } from '../../components/Pressable';
import { useFamilyOS } from '../../store/useFamilyOS';
import { API_ENABLED, request } from '../../services/api';
import { googleSignInUrl } from '../../services/apiService';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import './admin.css';

interface GoogleStatus {
  connected: boolean;
  email: string | null;
  scopes: string[];
  connected_at?: string | null;
  last_run_at?: string | null;
  last_errors: Record<string, string>;
  counts: Partial<Record<Kind, number>>;
  running: boolean;
}
type Kind = 'gmail' | 'calendar' | 'tasks';
interface Mail { id: string; sender: string | null; subject: string | null; snippet: string | null; sent_at: string | null }
interface Event { id: string; summary: string | null; starts: string | null; all_day: number; location: string | null }
interface Task { id: string; title: string | null; due: string | null; status: string | null; list_title: string | null }

const READS: { kind: Kind; label: string; scope: string }[] = [
  { kind: 'gmail', label: 'Gmail', scope: 'gmail.readonly' },
  { kind: 'calendar', label: 'Calendar', scope: 'calendar.readonly' },
  { kind: 'tasks', label: 'Tasks', scope: 'tasks.readonly' },
];

const name = (from: string | null) => (from ?? '').replace(/<.*>/, '').replace(/"/g, '').trim() || from || 'Someone';

export default function DataSourcesPage() {
  const toast = useFamilyOS((s) => s.toast);
  const now = useNow(30000);
  const f = useDeskFormat(now);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [mail, setMail] = useState<Mail[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  // One read of the status and the latest items; applied by the caller, so effects only set state in a callback.
  const load = useCallback(async () => {
    const s = await request<{ google: GoogleStatus }>('GET', '/collect/status').catch(() => null);
    if (!s?.google.connected) return { google: s?.google ?? null, mail: [], events: [], tasks: [] };
    const [m, e, t] = await Promise.all([
      request<Mail[]>('GET', '/collect/google/gmail?limit=25').catch(() => []),
      request<Event[]>('GET', '/collect/google/calendar?limit=25').catch(() => []),
      request<Task[]>('GET', '/collect/google/tasks?limit=25').catch(() => []),
    ]);
    return { google: s.google, mail: m, events: e, tasks: t };
  }, []);
  const apply = useCallback((d: Awaited<ReturnType<typeof load>>) => {
    setGoogle(d.google);
    setMail(d.mail);
    setEvents(d.events);
    setTasks(d.tasks);
  }, []);
  const refresh = useCallback(() => load().then(apply), [load, apply]);

  useEffect(() => {
    if (!API_ENABLED) return;
    let live = true;
    void load().then((d) => live && apply(d));
    return () => {
      live = false;
    };
  }, [load, apply]);
  // While a run is going, look again every few seconds.
  useEffect(() => {
    if (!google?.running) return;
    const t = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(t);
  }, [google?.running, refresh]);

  const collectNow = async () => {
    try {
      await request('POST', '/collect/google/run');
      toast('Collecting from Google…');
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not start collecting.', { duration: 5000 });
    }
  };
  const connect = async () => {
    const url = await googleSignInUrl();
    if (url) window.location.assign(url);
    else toast("Google isn't set up on this server yet.", { duration: 5000 });
  };

  const errors = Object.entries(google?.last_errors ?? {});
  return (
    <DeskPage
      className="adm-page"
      icon={DatabaseZap}
      title="Data sources"
      description="Where FamilyOS collects from, with your permission. What it collects is kept on this computer only for now; nothing is sent to your family's shared account."
      rail={
        <DeskCard title="How this works">
          <div className="adm-prose">
            <p className={T.small}>When you sign in with Google you can let FamilyOS read your Gmail, Calendar and Tasks. It only reads: it never sends, deletes or changes anything there.</p>
            <p className={T.small}>What it reads stays in a local store on the computer running FamilyOS. Your phone's messages, apps and other services come next.</p>
            <p className={T.small}>To stop, remove FamilyOS at myaccount.google.com → Security → Third-party connections.</p>
          </div>
        </DeskCard>
      }
    >
      {!API_ENABLED ? (
        <DeskCard>
          <p className={T.small}>This page needs the FamilyOS server: it is empty on the demo data.</p>
        </DeskCard>
      ) : (
        <>
          <DeskCard
            title="Google"
            sub={google?.connected ? google.email : 'not connected'}
            action={
              google?.connected ? (
                <Pressable className="pill pill--primary" onClick={() => void collectNow()} disabled={google.running}>
                  {google.running ? 'Collecting…' : 'Collect now'}
                </Pressable>
              ) : (
                <Pressable className="pill pill--primary" onClick={() => void connect()}>
                  Connect Google
                </Pressable>
              )
            }
          >
            {google?.connected ? (
              <>
                <ul className="adm-list">
                  {READS.map((r) => {
                    const allowed = google.scopes.some((s) => s.endsWith(r.scope));
                    return (
                      <li key={r.kind} className="adm-row">
                        <span className="adm-row__main">
                          <span className={clsx(T.smallStrong, 'adm-row__title')}>{r.label}</span>
                          <span className={clsx(T.small, 'adm-row__sub')}>
                            {allowed ? `${google.counts[r.kind] ?? 0} collected` : 'not allowed at sign-in'}
                            {google.last_errors[r.kind] ? ' · last run had a problem' : ''}
                          </span>
                        </span>
                        <StatusChip tone={!allowed ? 'neutral' : google.last_errors[r.kind] ? 'overdue' : 'done'}>
                          {!allowed ? 'off' : google.last_errors[r.kind] ? 'problem' : 'reading'}
                        </StatusChip>
                      </li>
                    );
                  })}
                </ul>
                <p className={clsx(T.small, 'adm-row__sub')}>
                  {google.last_run_at ? `Last collected ${f.ago(google.last_run_at)}.` : 'Not collected yet.'} Kept on this computer only.
                </p>
                {errors.length ? (
                  <div className="adm-note" role="status">
                    {errors.map(([k, v]) => (
                      <p key={k} className={T.small}>
                        {v}
                      </p>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <p className={T.small}>Sign in with Google and allow Gmail, Calendar and Tasks, and FamilyOS starts collecting at once.</p>
            )}
          </DeskCard>

          {google?.connected ? (
            <>
              <DeskCard title="Latest mail" sub={`${google.counts.gmail ?? 0} in the last 30 days`}>
                {mail.length ? (
                  <ul className="adm-list">
                    {mail.map((m) => (
                      <li key={m.id} className="adm-row adm-row--top">
                        <span className="adm-row__main">
                          <span className={clsx(T.smallStrong, 'adm-row__title')}>{m.subject || '(no subject)'}</span>
                          <span className={clsx(T.small, 'adm-row__sub')}>
                            {name(m.sender)} · {m.sent_at ? f.ago(m.sent_at) : ''} · {m.snippet}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={T.small}>No mail collected yet.</p>
                )}
              </DeskCard>
              <DeskCard title="Calendar" sub="a week back to two months ahead">
                {events.length ? (
                  <ul className="adm-list">
                    {events.map((e) => (
                      <li key={e.id} className="adm-row">
                        <span className="adm-row__main">
                          <span className={clsx(T.smallStrong, 'adm-row__title')}>{e.summary || '(no title)'}</span>
                          <span className={clsx(T.small, 'adm-row__sub')}>
                            {e.starts ? (e.all_day ? e.starts : new Date(e.starts).toLocaleString()) : ''}
                            {e.location ? ` · ${e.location}` : ''}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={T.small}>No events collected yet.</p>
                )}
              </DeskCard>
              <DeskCard title="Tasks">
                {tasks.length ? (
                  <ul className="adm-list">
                    {tasks.map((t) => (
                      <li key={t.id} className="adm-row">
                        <span className="adm-row__main">
                          <span className={clsx(T.smallStrong, 'adm-row__title')}>{t.title || '(no title)'}</span>
                          <span className={clsx(T.small, 'adm-row__sub')}>
                            {t.list_title}
                            {t.due ? ` · due ${t.due.slice(0, 10)}` : ''}
                          </span>
                        </span>
                        <StatusChip tone={t.status === 'completed' ? 'done' : 'proposed'}>{t.status === 'completed' ? 'done' : 'open'}</StatusChip>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={T.small}>No tasks collected yet.</p>
                )}
              </DeskCard>
            </>
          ) : null}
        </>
      )}
    </DeskPage>
  );
}
