// Data sources (from the profile menu): our collecting layer on the phone (famos-notes/COLLECTION_PLAN.md). Google
// (read at Google sign-in, collected on the server), this phone's own sources, each asked of Android only when switched
// on, and the installed apps with a "collect from this app" switch (notifications are kept only from those). All of it
// is kept in a local cache on the computer running FamilyOS, not in the family's shared database. Off by default.
// Each app switched on shows the decision layer's answer (familyos/collect/decide.py): which methods may collect from
// it, best first, each with a status the backend's registry decided; tap the app to see all six, run the phone agent on
// it (services/phoneAgent.ts: it opens the app and reads, never buys or sends) and see what it read.
import { useCallback, useEffect, useState } from 'react';
import { AppState, StyleSheet, Switch, View } from 'react-native';
import { colors, radii } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { useFamilyOS } from '../store/useFamilyOS';
import type { ScreenProps } from '../navigation/types';
import { AppText } from '../components/AppText';
import { SectionLabel } from '../components/Labels';
import { Pressy } from '../components/Pressy';
import { ScreenShell } from '../components/ScreenShell';
import { API_ENABLED, request } from '../services/api';
import { googleLogIn } from '../services/apiService';
import * as Collect from '../services/collect';
import { scheduleCollect } from '../services/collectTask';
import * as Agent from '../services/phoneAgent';

interface Status {
  google: { connected: boolean; email: string | null; counts: Record<string, number>; last_errors: Record<string, string>; running: boolean; last_run_at?: string | null };
  device: Record<string, number>;
}

interface Method {
  method: string;
  status: string;
  reason: string;
  priority: number;
}
interface Decision {
  package: string;
  status: 'none' | 'pending' | 'completed' | 'failed';
  methods: Method[];
  error: string | null;
}

const METHOD_LABEL: Record<string, string> = {
  api: 'Service API',
  mcp: 'MCP server',
  email: 'Email',
  phone_data: 'Notifications',
  mobile_use: 'Phone agent',
  browser_use: 'Browser agent',
};
const STATUS_LABEL: Record<string, string> = {
  available: 'ready',
  unverified: 'not confirmed',
  requires_connection: 'needs connecting',
  requires_permission: 'needs permission',
  unsupported: 'not possible',
  temporarily_unavailable: 'try again later',
};

/** One line for the app list: what is ready, else the first thing to do. */
function summary(d: Decision | undefined): string {
  if (!d || d.status === 'none' || d.status === 'pending') return 'Deciding how to collect…';
  if (d.status === 'failed') return d.error ?? 'Could not decide. Tap to try again.';
  const ready = d.methods.filter((m) => m.status === 'available');
  if (ready.length) return `Ready: ${ready.map((m) => METHOD_LABEL[m.method]).join(', ')}`;
  const todo = d.methods.find((m) => m.status === 'requires_connection' || m.status === 'requires_permission');
  return todo ? `Nothing ready yet. ${todo.reason}` : 'Nothing ready yet.';
}

const SOURCES: { id: Collect.SourceId; label: string; what: string }[] = [
  { id: 'sms', label: 'Messages (SMS)', what: 'Every inbox text, one-time codes included — new ones within seconds, sorted on the Mac.' },
  { id: 'notifications', label: 'Notifications', what: 'From the apps you switch on below.' },
  { id: 'calls', label: 'Call log', what: 'Number, time and length of calls.' },
  { id: 'locations', label: 'Location', what: 'Where the phone last was, when you collect.' },
  { id: 'files', label: 'Photos', what: 'Names and sizes of new photos — never the pictures.' },
];

const switchColors = { false: 'rgba(255,255,255,0.12)', true: colors.violet };

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function DataSourcesScreen({ navigation }: ScreenProps<'DataSources'>) {
  const toast = useFamilyOS((s) => s.toast);
  const [settings, setSettings] = useState<Collect.CollectSettings | null>(null);
  const [apps, setApps] = useState<Collect.AppSwitch[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [notifAccess, setNotifAccess] = useState(false);
  const [live, setLive] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [agent, setAgent] = useState<{ pkg: string; line: string } | null>(null);
  const [readItems, setReadItems] = useState<Record<string, Awaited<ReturnType<typeof Agent.appItems>>>>({});

  // One read of everything; applied by the caller, so effects only set state in a callback.
  const read = useCallback(async () => {
    const [s, st, dec] = await Promise.all([
      Collect.loadSettings(),
      API_ENABLED ? request<Status>('GET', '/collect/status').catch(() => null) : null,
      API_ENABLED ? request<{ apps: Decision[] }>('GET', '/collect/decide').catch(() => null) : null,
    ]);
    const list = Collect.canCollect ? await Collect.appsWithSwitches(s) : [];
    return { s, st, list, dec: Object.fromEntries((dec?.apps ?? []).map((d) => [d.package, d])), access: Collect.notificationAccess() };
  }, []);
  const apply = useCallback((d: Awaited<ReturnType<typeof read>>) => {
    setSettings(d.s);
    setStatus(d.st);
    setApps(d.list);
    setNotifAccess(d.access);
    setDecisions(d.dec);
    // Live SMS starts with the schedule; look again once Android has it running.
    void scheduleCollect(d.s)
      .catch(() => undefined)
      .then(() => setTimeout(() => setLive(Collect.liveSmsRunning()), 2000));
  }, []);
  const refresh = useCallback(() => read().then(apply), [read, apply]);

  useEffect(() => {
    let live = true;
    void read().then((d) => live && apply(d));
    // Back from Android's Settings (notification access): look again.
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        setNotifAccess(Collect.notificationAccess());
        setLive(Collect.liveSmsRunning());
      }
    });
    return () => {
      live = false;
      sub.remove();
    };
  }, [read, apply]);

  // While a decision is being made (about 10-25 seconds an app on this Mac's model), look again. An app switched on
  // that the backend has no decision for (switched on before it was told) is sent once, so it gets one.
  const deciding = apps.some((a) => a.collect && ['none', 'pending'].includes(decisions[a.package]?.status ?? 'none'));
  const [told, setTold] = useState(false);
  useEffect(() => {
    if (!API_ENABLED || !deciding) return;
    const undecided = apps.some((a) => a.collect && !decisions[a.package]);
    const t = setTimeout(() => {
      if (undecided && !told) {
        setTold(true);
        void Collect.sendApps(apps).then(refresh, () => undefined);
      } else void refresh();
    }, undecided && !told ? 0 : 10000);
    return () => clearTimeout(t);
  }, [deciding, decisions, apps, told, refresh]);

  const save = async (next: Collect.CollectSettings) => {
    setSettings(next);
    await Collect.saveSettings(next);
    // About every 15 minutes by itself while any source is on.
    await scheduleCollect(next).catch(() => undefined);
  };

  const flip = async (id: Collect.SourceId, on: boolean) => {
    if (!settings) return;
    if (on && !(await Collect.allow(id))) {
      if (id === 'notifications') toast('Allow FamilyOS under Notification access, then come back and switch it on.', { duration: 5000 });
      else toast('Android did not allow it, so it stays off.', { duration: 4000 });
      return;
    }
    await save({ ...settings, sources: { ...settings.sources, [id]: on } });
  };

  const flipApp = async (pkg: string, on: boolean) => {
    if (!settings) return;
    await save({ ...settings, apps: { ...settings.apps, [pkg]: on } });
    const next = apps.map((a) => (a.package === pkg ? { ...a, collect: on } : a));
    setApps(next);
    // The backend decides for an app as soon as it is switched on.
    if (API_ENABLED) void Collect.sendApps(next).then(refresh, () => undefined);
  };

  const decideAgain = async (pkg: string) => {
    try {
      await request('POST', `/collect/decide/${encodeURIComponent(pkg)}`);
      setDecisions((d) => ({ ...d, [pkg]: { ...(d[pkg] ?? { package: pkg, methods: [], error: null }), status: 'pending' } }));
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not start.', { duration: 4000 });
    }
  };

  const loadItems = async (pkg: string) => {
    if (!API_ENABLED) return;
    const got = await Agent.appItems(pkg).catch(() => null);
    if (got) setReadItems((r) => ({ ...r, [pkg]: got }));
  };

  const toggleApp = (pkg: string, shown: boolean) => {
    setOpen(shown ? null : pkg);
    if (!shown) void loadItems(pkg);
  };

  const runAgent = async (pkg: string, label: string, engine: Agent.Engine = 'claude') => {
    if (!Agent.agentAllowed()) {
      toast('Allow “FamilyOS phone agent” under Accessibility, then come back and run it again.', { duration: 6000 });
      Agent.openAgentSettings();
      return;
    }
    setAgent({ pkg, line: 'Starting…' });
    try {
      const run = await Agent.runPhoneAgent(pkg, (r, doing) => setAgent({ pkg, line: `Step ${r.steps}: ${doing}` }), engine);
      const via = run.fallback ? ` (on the Mac's models: ${run.fallback})` : engine === 'local' ? " (on the Mac's models)" : '';
      toast(
        run.status === 'done'
          ? `Read ${run.kept} from ${label}${via}.`
          : run.status === 'needs_sign_in'
            ? `${label} needs you to sign in on the phone first.`
            : `Stopped: ${run.note}`,
        { duration: 6000 },
      );
    } catch (e) {
      toast(e instanceof Error ? e.message : 'The phone agent could not run.', { duration: 5000 });
    }
    setAgent(null);
    await loadItems(pkg);
  };

  const collectPhone = async () => {
    if (!settings) return;
    setBusy(true);
    try {
      await Collect.sendApps(apps);
      const r = await Collect.collectNow(settings);
      const kept = Object.values(r.kept).reduce((n, k) => n + (k ?? 0), 0);
      const failed = Object.keys(r.failed);
      toast(failed.length ? `Collected ${kept}. Could not send: ${failed.join(', ')}.` : `Collected ${kept} new item${kept === 1 ? '' : 's'}.`, { duration: 4500 });
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not collect.', { duration: 5000 });
    }
    setBusy(false);
    await refresh();
  };

  const collectGoogle = async () => {
    try {
      await request('POST', '/collect/google/run');
      toast('Collecting from Google…');
      setTimeout(() => void refresh(), 15000);
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not start.', { duration: 5000 });
    }
  };

  const connectGoogle = async () => {
    const r = await googleLogIn();
    if (r.ok === true) {
      toast('Google connected. Collecting now.');
      setTimeout(() => void refresh(), 15000);
    } else if (r.ok === false) toast(r.message, { duration: 5000 });
  };

  const g = status?.google;
  const errors = Object.values(g?.last_errors ?? {});
  return (
    <ScreenShell title="Data sources" onBack={() => navigation.goBack()}>
      <AppText style={[T.small, styles.lead]}>
        What FamilyOS may read, with your permission. It is kept on the computer running FamilyOS for now, not in your family&apos;s shared account.
      </AppText>

      <SectionLabel>Google</SectionLabel>
      <Card>
        <View style={styles.row}>
          <View style={styles.flex}>
            <AppText style={T.menu}>{g?.connected ? g.email ?? 'Connected' : 'Not connected'}</AppText>
            <AppText style={[T.small, styles.hint]}>
              {g?.connected
                ? `Gmail ${g.counts.gmail ?? 0} · Calendar ${g.counts.calendar ?? 0} · Tasks ${g.counts.tasks ?? 0}`
                : 'Sign in with Google and allow Gmail, Calendar and Tasks.'}
            </AppText>
          </View>
          <Pressy onPress={() => void (g?.connected ? collectGoogle() : connectGoogle())} style={styles.pill} accessibilityLabel={g?.connected ? 'Collect from Google now' : 'Connect Google'}>
            <AppText style={T.chip}>{g?.connected ? (g.running ? 'Collecting…' : 'Collect now') : 'Connect'}</AppText>
          </Pressy>
        </View>
        {errors.map((e) => (
          <AppText key={e} style={[T.small, styles.problem]}>
            {e}
          </AppText>
        ))}
      </Card>

      <SectionLabel style={styles.gap}>On this phone</SectionLabel>
      {!Collect.canCollect ? (
        <Card>
          <AppText style={[T.small, styles.pad]}>This phone cannot share its messages, calls or apps with FamilyOS (iPhone allows none of it). Google above still works.</AppText>
        </Card>
      ) : (
        <Card>
          {SOURCES.map((src, i) => (
            <View key={src.id} style={[styles.row, i > 0 && styles.divider]}>
              <View style={styles.flex}>
                <AppText style={T.menu}>{src.label}</AppText>
                <AppText style={[T.small, styles.hint]}>
                  {src.what}
                  {status?.device?.[src.id] ? ` · ${status.device[src.id]} kept` : ''}
                  {src.id === 'notifications' && settings?.sources.notifications && !notifAccess ? ' · needs Notification access' : ''}
                  {src.id === 'sms' && settings?.sources.sms ? (live ? ' · live' : ' · live SMS starting…') : ''}
                </AppText>
              </View>
              <Switch
                value={!!settings?.sources[src.id]}
                onValueChange={(v) => void flip(src.id, v)}
                trackColor={switchColors}
                thumbColor="#fff"
                accessibilityLabel={src.label}
              />
            </View>
          ))}
          <Pressy onPress={() => void collectPhone()} style={[styles.primary, busy && { opacity: 0.6 }]} disabled={busy} accessibilityLabel="Collect from this phone now">
            <AppText style={[T.bodyStrong, { color: '#fff' }]}>{busy ? 'Collecting…' : 'Collect from this phone now'}</AppText>
          </Pressy>
          <AppText style={[T.small, styles.foot]}>
            {Object.values(settings?.sources ?? {}).some(Boolean) ? 'Collects by itself about every 15 minutes.' : 'Switch a source on to collect.'}
            {settings?.lastRun ? ` Last collected ${new Date(settings.lastRun).toLocaleString()}.` : ''}
          </AppText>
        </Card>
      )}

      {Collect.canCollect ? (
        <>
          <SectionLabel style={styles.gap}>{`Apps (${apps.filter((a) => a.collect).length} of ${apps.length} on)`}</SectionLabel>
          <Card>
            {apps.map((a, i) => {
              const d = decisions[a.package];
              const shown = open === a.package && d?.status === 'completed';
              return (
                <View key={a.package} style={i > 0 && styles.divider}>
                  <View style={styles.row}>
                    <Pressy
                      style={styles.flex}
                      disabled={!a.collect || !API_ENABLED}
                      onPress={() => (d?.status === 'failed' ? void decideAgain(a.package) : toggleApp(a.package, shown))}
                      accessibilityLabel={`${a.label}: how FamilyOS can collect`}
                    >
                      <AppText style={T.menu}>{a.label}</AppText>
                      <AppText style={[T.small, styles.hint]}>
                        {agent?.pkg === a.package ? agent.line : a.collect && API_ENABLED ? summary(d) : a.package}
                      </AppText>
                    </Pressy>
                    <Switch value={a.collect} onValueChange={(v) => void flipApp(a.package, v)} trackColor={switchColors} thumbColor="#fff" accessibilityLabel={`Collect from ${a.label}`} />
                  </View>
                  {shown ? (
                    <View style={styles.methods}>
                      {d.methods.map((m) => (
                        <AppText key={m.method} style={[T.small, styles.method, m.status === 'available' && styles.ready]}>
                          {`${m.priority}. ${METHOD_LABEL[m.method] ?? m.method} — ${STATUS_LABEL[m.status] ?? m.status}. ${m.reason}`}
                        </AppText>
                      ))}
                      <View style={styles.actions}>
                        {Agent.canRunAgent ? (
                          <Pressy
                            onPress={() => void runAgent(a.package, a.label)}
                            disabled={!!agent}
                            style={[styles.pill, styles.pillStrong, !!agent && { opacity: 0.6 }]}
                            accessibilityLabel={`Read ${a.label} with the phone agent`}
                          >
                            <AppText style={T.chip}>{agent?.pkg === a.package ? 'Reading…' : 'Read with phone agent'}</AppText>
                          </Pressy>
                        ) : null}
                        {Agent.canRunAgent ? (
                          <Pressy
                            onPress={() => void runAgent(a.package, a.label, 'local')}
                            disabled={!!agent}
                            style={[styles.pill, !!agent && { opacity: 0.6 }]}
                            accessibilityLabel={`Read ${a.label} with the Mac's own models`}
                          >
                            <AppText style={T.chip}>On the Mac&apos;s models</AppText>
                          </Pressy>
                        ) : null}
                        <Pressy onPress={() => void decideAgain(a.package)} style={styles.pill} accessibilityLabel={`Check ${a.label} again`}>
                          <AppText style={T.chip}>Check again</AppText>
                        </Pressy>
                      </View>
                      <AppText style={[T.small, styles.method]}>
                        The phone agent opens {a.label} and reads it on its own: Claude decides each step, or the Mac&apos;s own Qwen + MAI-UI. Coming back to FamilyOS stops it. It never buys, sends or changes anything.
                      </AppText>
                      {readItems[a.package]?.items.length ? (
                        <>
                          <AppText style={[T.small, styles.readHead]}>{`What it read (${readItems[a.package].items.length})`}</AppText>
                          {readItems[a.package].items.slice(0, 10).map((it) => (
                            <AppText key={it.id} style={[T.small, styles.method]}>
                              {[it.title, it.happened, it.amount, it.status].filter(Boolean).join(' · ')}
                            </AppText>
                          ))}
                        </>
                      ) : readItems[a.package]?.last_run ? (
                        <AppText style={[T.small, styles.method]}>
                          {`Last run: ${readItems[a.package].last_run?.errors.note ?? 'nothing read'}`}
                        </AppText>
                      ) : null}
                    </View>
                  ) : null}
                </View>
              );
            })}
          </Card>
        </>
      ) : null}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  lead: { marginBottom: 18, color: colors.muted },
  card: { borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder, overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, minHeight: 58, paddingVertical: 10 },
  flex: { flex: 1, marginRight: 12 },
  hint: { marginTop: 4, fontSize: 12.5 },
  gap: { marginTop: 22 },
  pad: { padding: 16 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
  pill: { paddingHorizontal: 14, height: 34, borderRadius: 999, justifyContent: 'center', backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  primary: { margin: 14, height: 48, borderRadius: radii.pill, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  foot: { textAlign: 'center', marginBottom: 14, color: colors.dim },
  methods: { paddingHorizontal: 16, paddingBottom: 12 },
  method: { marginTop: 6, fontSize: 12.5, color: colors.muted },
  ready: { color: colors.ink },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  pillStrong: { backgroundColor: colors.violet, borderColor: colors.violet },
  readHead: { marginTop: 12, color: colors.ink },
  problem: { paddingHorizontal: 16, paddingBottom: 12, color: colors.muted },
});
