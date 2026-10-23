// Family hub (AGENT_CORE_AND_FAMILY.md §4.4): orbit header, completion
// summary, one card per member (owner first, then oldest), and a fixed
// "+ Add family member" button. Hosts the Add / Edit sheets, the long-press
// menu and the remove dialog.
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown, LinearTransition } from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';
import { ChevronLeft, Plus } from 'lucide-react-native';
import type { FamilyMember } from '../../services/interfaces';
import { completeCount, displayName, sectionsNeedingUpdate, sectionsNotStarted, todoText } from '../../family/model';
import { AGENT_IDS, colors, radii } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { type as T } from '../../theme/typography';
import type { ScreenProps } from '../../navigation/types';
import { useFamily } from '../../store/useFamily';
import { OnboardingBackdrop } from '../../graphics/OnboardingBackdrop';
import { TaskRing, useCountUp } from '../../graphics/Charts';
import { AppText } from '../../components/AppText';
import { SectionLabel } from '../../components/Labels';
import { Pressy } from '../../components/Pressy';
import { ToastHost } from '../../components/Toast';
import { FamilyOrbit } from './FamilyOrbit';
import { MemberCard, MemberMenu } from './MemberCard';
import { MemberBasicsSheet } from './MemberBasicsSheet';
import { RemoveDialog } from './RemoveDialog';

const UNDERLINE = AGENT_IDS.map((id) => colors.agents[id]) as unknown as [string, string, ...string[]];

function SummaryCard({ members }: { members: FamilyMember[] }) {
  const done = members.filter((m) => completeCount(m) === 5).length;
  const todo = members.reduce((n, m) => n + sectionsNeedingUpdate(m).length, 0);
  const blank = members.reduce((n, m) => n + sectionsNotStarted(m).length, 0);
  const pct = members.length ? members.reduce((s, m) => s + completeCount(m), 0) / (members.length * 5) : 0;
  const shown = Math.round(useCountUp(pct * 100));
  return (
    <View style={styles.summary} accessible accessibilityLabel={`${done} of ${members.length} profiles complete. ${todoText(todo, blank) ?? 'Everyone’s details are up to date'}.`}>
      <View style={styles.ring}>
        <TaskRing pct={pct} color={todo || blank ? '#FFB23F' : '#4DD98C'} size={76} />
        <AppText style={[T.stat, styles.ringText]}>{shown}%</AppText>
      </View>
      <View style={styles.summaryText}>
        <AppText style={T.bodyStrong}>
          {done} of {members.length} profiles complete
        </AppText>
        <AppText style={[T.small, styles.summarySub]}>
          {todo ? `${todo} ${todo === 1 ? 'section still needs' : 'sections still need'} updating` : (todoText(0, blank) ?? 'Everyone’s details are up to date')}
        </AppText>
      </View>
    </View>
  );
}

export function FamilyHubScreen({ navigation, route }: ScreenProps<'Family'>) {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const fam = useFamily();
  const [adding, setAdding] = useState(!!route.params?.openAdd);
  // "Add family member" from the Profile menu can also arrive while the hub is open.
  const [seenAdd, setSeenAdd] = useState(route.params?.openAdd);
  if (route.params?.openAdd !== seenAdd) {
    setSeenAdd(route.params?.openAdd);
    if (route.params?.openAdd) setAdding(true);
  }
  const [editing, setEditing] = useState<FamilyMember | null>(null);
  const [menu, setMenu] = useState<FamilyMember | null>(null);
  const [removing, setRemoving] = useState<FamilyMember | null>(null);

  useEffect(() => {
    void fam.load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Entry points: "Add family member" from the Profile menu; a removal confirmed on a profile.
  useEffect(() => {
    if (route.params?.openAdd) navigation.setParams({ openAdd: undefined });
    const r = route.params?.remove;
    if (r) {
      navigation.setParams({ remove: undefined });
      setTimeout(() => void fam.remove(r.id, r.reassign), 350);
    }
  }, [route.params, navigation, fam]);
  useEffect(() => {
    if (!fam.highlight) return;
    const id = setTimeout(fam.clearHighlight, 1800);
    return () => clearTimeout(id);
  }, [fam.highlight, fam.clearHighlight]);

  const members = fam.members;
  const n = members.length;
  const todo = members.reduce((k, m) => k + sectionsNeedingUpdate(m).length, 0);
  const blank = members.reduce((k, m) => k + sectionsNotStarted(m).length, 0);
  const onlyOwner = n <= 1;

  return (
    <View style={styles.root}>
      <OnboardingBackdrop />
      {/* Starts below the status bar so cards never scroll under the clock. */}
      <ScrollView style={{ marginTop: insets.top }} contentContainerStyle={[styles.body, { paddingTop: 6, paddingBottom: insets.bottom + 110 }]} showsVerticalScrollIndicator={false}>
        <Pressy onPress={() => navigation.goBack()} style={styles.back} accessibilityLabel="Back">
          <ChevronLeft size={20} color={colors.ink} />
        </Pressy>
        <AppText style={[T.agentTitle, styles.title]} accessibilityRole="header">
          Family
        </AppText>
        <LinearGradient colors={UNDERLINE} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.underline} />
        <AppText style={[T.small, styles.subtitle]}>
          {!fam.loaded ? ' ' : todo || blank ? `${n} members · ${todoText(todo, blank)}` : 'Everyone’s details are up to date'}
        </AppText>

        <View style={styles.orbit}>
          <FamilyOrbit members={members} width={width - 32} />
        </View>

        {/* Wait for the stored family, so the empty state never flashes and the cards enter once. */}
        {!fam.loaded ? null : onlyOwner ? (
          <AppText style={[T.small, styles.empty]}>Add your family so your agents can plan for everyone.</AppText>
        ) : (
          <SummaryCard members={members} />
        )}

        <SectionLabel style={styles.section}>YOUR FAMILY</SectionLabel>
        {fam.loaded
          ? members.map((m, i) => (
              // Reflow and entrance on separate views: on Android a reflow that lands
              // mid-entrance can leave a card stuck at its entering opacity of 0.
              <Animated.View key={m.id} layout={LinearTransition.springify().damping(22).stiffness(120).mass(1)}>
                <Animated.View entering={FadeInDown.delay(i * durations.stagger).duration(320)}>
                  <MemberCard
                    member={m}
                    glow={fam.highlight === m.id}
                    removing={fam.removing.includes(m.id)}
                    onOpen={() => navigation.navigate('MemberProfile', { id: m.id })}
                    onEdit={() => setEditing(m)}
                    onRemove={() => setRemoving(m)}
                    onLongPress={() => setMenu(m)}
                  />
                </Animated.View>
              </Animated.View>
            ))
          : null}
      </ScrollView>

      <LinearGradient colors={['rgba(0,0,0,0)', 'rgba(0,0,0,0.92)']} locations={[0, 0.45]} style={[styles.fade, { height: insets.bottom + 110 }]} pointerEvents="none" />
      <View style={[styles.footer, { bottom: insets.bottom + 14 }]}>
        <Pressy onPress={() => setAdding(true)} style={styles.add} accessibilityLabel="Add family member">
          <Plus size={18} color={colors.pillPrimaryInk} strokeWidth={2.4} />
          <AppText style={[T.bodyStrong, styles.addText]}>Add family member</AppText>
        </Pressy>
      </View>

      {menu ? (
        <MemberMenu
          member={menu}
          onClose={() => setMenu(null)}
          onEdit={() => {
            setEditing(menu);
            setMenu(null);
          }}
          onRemove={() => {
            setRemoving(menu);
            setMenu(null);
          }}
        />
      ) : null}
      <MemberBasicsSheet
        visible={adding}
        onClose={() => setAdding(false)}
        onSubmit={async (b, later) => {
          const m = await fam.add(b);
          setAdding(false);
          if (!later) navigation.navigate('MemberWizard', { id: m.id, section: 'basic' });
        }}
      />
      <MemberBasicsSheet
        visible={!!editing}
        member={editing ?? undefined}
        onClose={() => setEditing(null)}
        onSubmit={async (b) => {
          if (editing) await fam.updateBasics(editing.id, b);
          setEditing(null);
        }}
      />
      {removing ? (
        <RemoveDialog
          member={removing}
          members={members}
          onCancel={() => setRemoving(null)}
          onConfirm={(reassign) => {
            const id = removing.id;
            setRemoving(null);
            void fam.remove(id, reassign);
          }}
        />
      ) : null}
      <ToastHost bottom={insets.bottom + 84} />
    </View>
  );
}

export const hubA11yName = (m: FamilyMember) => displayName(m);

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  body: { paddingHorizontal: 16 },
  back: { width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.08)', borderWidth: 1, borderColor: colors.glassBorder, alignItems: 'center', justifyContent: 'center' },
  title: { marginTop: 14 },
  underline: { width: 64, height: 3, borderRadius: 2, marginTop: 8 },
  subtitle: { marginTop: 10 },
  orbit: { marginTop: 4, alignItems: 'center' },
  empty: { textAlign: 'center', marginHorizontal: 24, marginBottom: 6 },
  summary: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder },
  ring: { width: 76, height: 76, alignItems: 'center', justifyContent: 'center' },
  ringText: { position: 'absolute', fontSize: 16 },
  summaryText: { flex: 1, marginLeft: 16 },
  summarySub: { marginTop: 4 },
  section: { marginTop: 22 },
  fade: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  footer: { position: 'absolute', left: 16, right: 16 },
  add: { height: 54, borderRadius: 27, backgroundColor: colors.pillPrimaryBg, flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  addText: { color: colors.pillPrimaryInk, marginLeft: 8 },
});
