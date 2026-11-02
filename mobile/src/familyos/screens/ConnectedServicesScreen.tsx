// Connected services (from the profile menu), the phone's copy of the web page /services: the sites the browser agent may
// sign in to for you (Amazon, Flipkart …). Add a site with its username and password -- the password goes to the Keychain
// of the Mac running FamilyOS (/v1/collect/services, familyos/collect/vault.py) and is never shown back -- run the browser
// agent on it (it works in a window on that Mac and only reads), and see what it read.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { colors, radii } from '../theme/tokens';
import { fonts, type as T } from '../theme/typography';
import { useFamilyOS } from '../store/useFamilyOS';
import type { ScreenProps } from '../navigation/types';
import { AppText } from '../components/AppText';
import { SectionLabel } from '../components/Labels';
import { Pressy } from '../components/Pressy';
import { ScreenShell } from '../components/ScreenShell';
import { API_ENABLED, request } from '../services/api';
import { Field } from './LoginScreen';

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
type Listing = { catalog: Site[]; connected: Connected[]; agent?: { model: string | null } };

/** The last run, in one line (as on the web page). */
function lastRun(c: Connected): string {
  if (c.running) return 'Collecting now, on the Mac…';
  const r = c.last_run;
  if (!r) return 'Not collected yet.';
  const cost = r.counts.cost_usd != null ? ` · $${r.counts.cost_usd.toFixed(3)}` : '';
  if (r.errors.outcome === 'needs_sign_in') return `Needs you to sign in once (${r.errors.note ?? 'a code'}): use Sign in on the Mac.`;
  if (r.errors.outcome) return `${r.errors.outcome === 'failed' ? 'Failed' : 'Stopped'}: ${r.errors.note ?? ''}${cost}`;
  return `Read ${r.counts.kept ?? 0} on ${new Date(r.finished_at).toLocaleString()}${cost}`;
}

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function ConnectedServicesScreen({ navigation }: ScreenProps<'ConnectedServices'>) {
  const toast = useFamilyOS((s) => s.toast);
  const [data, setData] = useState<Listing | null>(null);
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<Site | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [host, setHost] = useState('');
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<{ service: string; items: Item[] } | null>(null);

  const read = useCallback(() => request<Listing>('GET', '/collect/services'), []);
  const refresh = useCallback(() => read().then(setData, () => undefined), [read]);
  useEffect(() => {
    if (!API_ENABLED) return;
    let live = true;
    void read().then((d) => live && setData(d), () => undefined);
    return () => {
      live = false;
    };
  }, [read]);

  // While the agent is on a site, look again every few seconds.
  const running = !!data?.connected.some((c) => c.running);
  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => void refresh(), 5000);
    return () => clearTimeout(t);
  }, [running, data, refresh]);

  const have = useMemo(() => new Set((data?.connected ?? []).map((c) => c.service)), [data]);
  const shownSites = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.catalog ?? []).filter((s) => !have.has(s.id) || s.id === 'other').filter((s) => !q || s.name.toLowerCase().includes(q) || (s.host ?? '').includes(q));
  }, [data, have, query]);

  const pick = (s: Site) => {
    setPicked(s);
    setUsername('');
    setPassword('');
    setHost('');
    setShown(false);
  };

  const save = async () => {
    if (!picked) return;
    setBusy(true);
    try {
      await request('POST', '/collect/services', { service: picked.id, username, password, host: picked.id === 'other' ? host : undefined });
      toast(`${picked.name} connected. Its password is in the Mac's Keychain.`);
      setPassword('');
      setPicked(null);
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not connect it.', { duration: 5000 });
    }
    setBusy(false);
  };

  const act = async (c: Connected, what: 'run' | 'sign-in' | 'remove') => {
    try {
      if (what === 'remove') {
        await request('DELETE', `/collect/services/${c.service}`);
        toast(`${c.name} removed, and its password with it.`);
      } else {
        await request('POST', `/collect/services/${c.service}/${what}`);
        toast(what === 'run' ? `Collecting from ${c.name} in a window on the Mac.` : `${c.name} is open in a window on the Mac: sign in there, then close it.`, {
          duration: 5000,
        });
      }
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not do that.', { duration: 5000 });
    }
  };

  const showItems = async (c: Connected) => {
    if (open?.service === c.service) return setOpen(null);
    try {
      setOpen({ service: c.service, items: await request<Item[]>('GET', `/collect/services/${c.service}/items`) });
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not read them.', { duration: 5000 });
    }
  };

  const model = data?.agent?.model ?? null;
  return (
    <ScreenShell title="Connected services" onBack={() => (picked ? setPicked(null) : navigation.goBack())}>
      <AppText style={[T.small, styles.lead]}>
        Sites FamilyOS&apos;s browser agent may sign in to for you, to read orders, bills and bookings. Passwords stay in the Keychain of the Mac running
        FamilyOS and are never shown back.
      </AppText>

      {!API_ENABLED ? (
        <Card>
          <AppText style={[T.small, styles.pad]}>This needs the FamilyOS server: it is empty on the demo data.</AppText>
        </Card>
      ) : picked ? (
        <Card>
          <View style={styles.pad}>
            <AppText style={[T.menu, styles.formHead]}>{`Connect ${picked.name}`}</AppText>
            {picked.id === 'other' ? <Field label="The site's address" value={host} onChange={setHost} /> : null}
            <Field label="Username, email or phone" value={username} onChange={setUsername} email />
            <Field label="Password" value={password} onChange={setPassword} secure toggle={() => setShown((v) => !v)} shown={shown} />
            <AppText style={[T.small, styles.hint]}>
              {`Kept in the Mac's Keychain, used only when the browser agent signs in to ${picked.name}. A one-time code still comes to you.`}
            </AppText>
            <View style={styles.actions}>
              <Pressy
                onPress={() => void save()}
                disabled={busy || !username.trim() || !password || (picked.id === 'other' && !host.trim())}
                style={[styles.pill, styles.pillStrong, (busy || !username.trim() || !password) && { opacity: 0.5 }]}
                accessibilityLabel={`Connect ${picked.name}`}
              >
                <AppText style={T.chip}>{busy ? 'Saving…' : 'Connect'}</AppText>
              </Pressy>
              <Pressy onPress={() => setPicked(null)} style={styles.pill} accessibilityLabel="Cancel">
                <AppText style={T.chip}>Cancel</AppText>
              </Pressy>
            </View>
          </View>
        </Card>
      ) : (
        <>
          <SectionLabel>{`Your sites${data?.connected.length ? ` (${data.connected.length})` : ''}`}</SectionLabel>
          <Card>
            {data?.connected.length ? (
              data.connected.map((c, i) => (
                <View key={c.service} style={[styles.site, i > 0 && styles.divider]}>
                  <AppText style={T.menu}>{c.name}</AppText>
                  <AppText style={[T.small, styles.hint]}>{`${c.username} · ${c.host}`}</AppText>
                  <AppText style={[T.small, styles.hint]}>{lastRun(c)}</AppText>
                  <View style={styles.actions}>
                    <Pressy
                      onPress={() => void act(c, 'run')}
                      disabled={c.running || !model}
                      style={[styles.pill, styles.pillStrong, (c.running || !model) && { opacity: 0.5 }]}
                      accessibilityLabel={`Collect from ${c.name}`}
                    >
                      <AppText style={T.chip}>{c.running ? 'Collecting…' : 'Collect now'}</AppText>
                    </Pressy>
                    <Pressy onPress={() => void act(c, 'sign-in')} disabled={c.running} style={styles.pill} accessibilityLabel={`Sign in to ${c.name} on the Mac`}>
                      <AppText style={T.chip}>Sign in on the Mac</AppText>
                    </Pressy>
                    {c.items ? (
                      <Pressy onPress={() => void showItems(c)} style={styles.pill} accessibilityLabel={`What was read from ${c.name}`}>
                        <AppText style={T.chip}>{open?.service === c.service ? 'Hide' : `Read (${c.items})`}</AppText>
                      </Pressy>
                    ) : null}
                    <Pressy onPress={() => void act(c, 'remove')} style={styles.pill} accessibilityLabel={`Remove ${c.name}`}>
                      <AppText style={T.chip}>Remove</AppText>
                    </Pressy>
                  </View>
                  {open?.service === c.service
                    ? open.items.map((it) => (
                        <AppText key={it.id} style={[T.small, styles.item]}>
                          {[it.title, it.happened, it.amount, it.status].filter(Boolean).join(' · ')}
                        </AppText>
                      ))
                    : null}
                </View>
              ))
            ) : (
              <AppText style={[T.small, styles.pad]}>None yet. Pick a site below and add its sign-in.</AppText>
            )}
          </Card>
          <AppText style={[T.small, styles.foot]}>
            {model
              ? `The browser agent (${model}) only reads: it never buys, books or changes anything, and never sees the password.`
              : 'The browser agent needs a Claude key on the server.'}
          </AppText>

          <SectionLabel style={styles.gap}>Add a site</SectionLabel>
          <Card>
            <View style={styles.searchBox}>
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder="Amazon, Swiggy, IRCTC…"
                placeholderTextColor={colors.dim}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.search}
                accessibilityLabel="Search sites"
              />
            </View>
            {shownSites.map((s) => (
              <View key={s.id} style={[styles.row, styles.divider]}>
                <View style={styles.flex}>
                  <AppText style={T.menu}>{s.name}</AppText>
                  <AppText style={[T.small, styles.hint]}>{`${s.host ?? 'any site, by its address'} · ${s.kind}`}</AppText>
                </View>
                <Pressy onPress={() => pick(s)} style={styles.pill} accessibilityLabel={`Connect ${s.name}`}>
                  <AppText style={T.chip}>Connect</AppText>
                </Pressy>
              </View>
            ))}
          </Card>
        </>
      )}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  lead: { marginBottom: 18, color: colors.muted },
  card: { borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder, overflow: 'hidden' },
  pad: { padding: 16 },
  formHead: { marginBottom: 14 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, minHeight: 58, paddingVertical: 10 },
  site: { paddingHorizontal: 16, paddingVertical: 12 },
  flex: { flex: 1, marginRight: 12 },
  hint: { marginTop: 4, fontSize: 12.5 },
  item: { marginTop: 6, fontSize: 12.5, color: colors.muted },
  gap: { marginTop: 22 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  pill: { paddingHorizontal: 14, height: 34, borderRadius: 999, justifyContent: 'center', backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  pillStrong: { backgroundColor: colors.violet, borderColor: colors.violet },
  foot: { textAlign: 'center', marginTop: 10, color: colors.dim },
  searchBox: { margin: 12, paddingHorizontal: 14, height: 42, borderRadius: 12, backgroundColor: colors.glassFill, justifyContent: 'center' },
  search: { color: colors.ink, fontFamily: fonts.medium, fontSize: 15, paddingVertical: 0 },
});
