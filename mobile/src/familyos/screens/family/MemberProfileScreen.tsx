// Member profile (AGENT_CORE_AND_FAMILY.md §4.6): floating avatar hero in
// stage-tinted dust, completion, one row per details section, Edit basics and
// Remove from family.
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Canvas, Fill, Shader } from '@shopify/react-native-skia';
import Animated, { useAnimatedStyle, useDerivedValue, useFrameCallback, useReducedMotion, useSharedValue, withSequence, withSpring, withTiming } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { ChevronLeft, ChevronRight, ClipboardCheck, Ellipsis, HeartPulse, IdCard, Landmark, MapPin, PiggyBank, User, type LucideIcon } from 'lucide-react-native';
import type { SectionId } from '../../services/interfaces';
import { SECTION_IDS, ageGroupOf, ageOf, ageText, completeCount, displayName, relationshipLabel, sectionMeta, stageOf } from '../../family/model';
import { sectionSummary } from '../../family/summary';
import { colors, hexToRgb, radii, withAlpha } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import type { ScreenProps } from '../../navigation/types';
import { useFamily } from '../../store/useFamily';
import { ambientEffect } from '../../graphics/ambientShader';
import { JELLY_SPRING } from '../../graphics/coreMotion';
import { OnboardingBackdrop } from '../../graphics/OnboardingBackdrop';
import { AppText } from '../../components/AppText';
import { SectionLabel } from '../../components/Labels';
import { Pressy } from '../../components/Pressy';
import { ToastHost } from '../../components/Toast';
import { AMBER, CompletionRing, GREEN, MemberAvatar, StatusPill } from '../../components/family/MemberBits';
import { MemberBasicsSheet } from './MemberBasicsSheet';
import { MemberMenu } from './MemberCard';
import { RemoveDialog } from './RemoveDialog';

export const SECTION_ICONS: Record<SectionId, LucideIcon> = { basic: User, contact: MapPin, ids: IdCard, health: HeartPulse, banking: Landmark };
export const ReviewIcon = ClipboardCheck;
const HERO = 140;
const DUST = 260;

export function MemberProfileScreen({ navigation, route }: ScreenProps<'MemberProfile'>) {
  const insets = useSafeAreaInsets();
  const reduced = useReducedMotion();
  const members = useFamily((s) => s.members);
  const updateBasics = useFamily((s) => s.updateBasics);
  const m = members.find((x) => x.id === route.params.id);
  const owner = members.find((x) => x.isOwner);
  const [editing, setEditing] = useState(false);
  const [menu, setMenu] = useState(false);
  const [removing, setRemoving] = useState(false);

  // Slow bob of the hero, its dust, and the jelly squash on tap.
  const clock = useSharedValue(0);
  const squash = useSharedValue(1);
  const cb = useFrameCallback((f) => {
    clock.set(clock.get() + Math.min(f.timeSincePreviousFrame ?? 16, 50) / 1000);
  }, false);
  useEffect(() => {
    cb.setActive(!reduced);
    return () => cb.setActive(false);
  }, [cb, reduced]);
  const accent = m ? stageOf(m).accent : '#7FA8FF';
  const tint = hexToRgb(accent);
  const uniforms = useDerivedValue(() => ({
    res: [DUST, DUST], ph: (clock.value / 72) * Math.PI * 2, center: [DUST / 2, DUST / 2], radius: HERO / 2 + 6,
    tint: [0, 0, 0], corner: [0, 0, 0], halo: tint, haloAmt: 0.55, dustAmt: 1.4, dustCol: [tint[0] * 0.7 + 0.25, tint[1] * 0.7 + 0.25, tint[2] * 0.7 + 0.25],
    starAmt: 0, sats: new Array(10).fill(-99), satCols: new Array(15).fill(0), satR: 1, satAmt: 0, lowPower: 1, clearBg: 1, pushDir: [1, 0], pushAmt: 0,
  }));
  const hero = useAnimatedStyle(() => ({
    transform: [{ translateY: 5 * Math.sin(clock.value * 1.1) }, { scaleX: 2 - squash.value }, { scaleY: squash.value }],
  }));

  if (!m) return <View style={styles.root} />;
  const age = ageOf(m.dateOfBirth);
  const group = ageGroupOf(age);
  const st = stageOf(m);
  const done = completeCount(m);

  return (
    <View style={styles.root}>
      <OnboardingBackdrop />
      <ScrollView style={{ marginTop: insets.top }} contentContainerStyle={[styles.body, { paddingTop: 6, paddingBottom: insets.bottom + 40 }]} showsVerticalScrollIndicator={false}>
        <View style={styles.bar}>
          <Pressy onPress={() => navigation.goBack()} style={styles.round} accessibilityLabel="Back">
            <ChevronLeft size={20} color={colors.ink} />
          </Pressy>
          <Pressy onPress={() => setMenu(true)} style={styles.round} accessibilityLabel="More options">
            <Ellipsis size={20} color={colors.ink} />
          </Pressy>
        </View>

        <View style={styles.hero}>
          <Canvas style={styles.dust} pointerEvents="none">
            <Fill>
              <Shader source={ambientEffect} uniforms={uniforms} />
            </Fill>
          </Canvas>
          <Pressable
            onPress={() => {
              void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              squash.set(reduced ? withSequence(withTiming(0.96, { duration: 90 }), withTiming(1, { duration: 200 })) : withSequence(withTiming(0.88, { duration: 90 }), withSpring(1, JELLY_SPRING)));
            }}
            accessibilityRole="imagebutton"
            accessibilityLabel={`${displayName(m)}'s avatar, stage ${st.stage}, ${st.name}`}
          >
            <Animated.View style={hero}>
              <MemberAvatar member={m} size={HERO} animated />
            </Animated.View>
          </Pressable>
        </View>
        <AppText style={[T.greeting, styles.center]} accessibilityRole="header">
          {m.fullName}
        </AppText>
        <AppText style={[T.small, styles.center, styles.sub]}>
          {relationshipLabel(m)} · {ageText(age)}
        </AppText>
        <View style={[styles.stageChip, { borderColor: withAlpha(accent, 0.5) }]}>
          <AppText style={[T.chip, { color: accent }]}>
            Stage {st.stage} · {st.name}
          </AppText>
        </View>

        <View style={styles.completion} accessible accessibilityLabel={`${done} of 5 sections complete`}>
          <CompletionRing value={done / 5} size={44} stroke={4} color={done === 5 ? GREEN : AMBER} />
          <AppText style={[T.bodyStrong, styles.completionText]}>{done} of 5 sections complete</AppText>
        </View>

        <SectionLabel style={styles.section}>DETAILS</SectionLabel>
        {SECTION_IDS.map((sid) => {
          const meta = sectionMeta(sid, group);
          const Icon = sid === 'banking' && group !== 'adult' ? PiggyBank : SECTION_ICONS[sid];
          const sec = m.sections[sid];
          return (
            <Pressy
              key={sid}
              onPress={() => navigation.navigate('MemberWizard', { id: m.id, section: sid })}
              pressScale={0.98}
              style={styles.row}
              accessibilityLabel={`${meta.title}, ${sec.status === 'complete' ? 'complete' : sec.status === 'needsUpdate' ? 'needs update' : 'not started'}`}
              accessibilityHint="Opens this section"
            >
              <View style={[styles.icon, { backgroundColor: withAlpha(meta.color, 0.16), borderColor: withAlpha(meta.color, 0.45) }]}>
                <Icon size={18} color={meta.color} />
              </View>
              <View style={styles.rowText}>
                <AppText style={T.bodyStrong}>{meta.title}</AppText>
                <AppText style={[T.small, styles.rowSub]} numberOfLines={1}>
                  {sectionSummary(m, sid, members, owner)}
                </AppText>
                <View style={styles.pillRow}>
                  <StatusPill status={sec.status} />
                </View>
              </View>
              <ChevronRight size={18} color={colors.muted} />
            </Pressy>
          );
        })}

        {!m.isOwner ? (
          <Pressy onPress={() => setRemoving(true)} style={styles.removeBtn} accessibilityLabel={`Remove ${displayName(m)} from family`}>
            <AppText style={[T.bodyStrong, { color: colors.danger }]}>Remove from family</AppText>
          </Pressy>
        ) : null}
      </ScrollView>

      {menu ? (
        <MemberMenu
          member={m}
          onClose={() => setMenu(false)}
          onEdit={() => {
            setMenu(false);
            setEditing(true);
          }}
          onRemove={() => {
            setMenu(false);
            setRemoving(true);
          }}
        />
      ) : null}
      <MemberBasicsSheet
        visible={editing}
        member={m}
        onClose={() => setEditing(false)}
        onSubmit={async (b) => {
          await updateBasics(m.id, b);
          setEditing(false);
        }}
      />
      {removing ? (
        <RemoveDialog
          member={m}
          members={members}
          onCancel={() => setRemoving(false)}
          onConfirm={(reassign) => {
            setRemoving(false);
            // Back to the hub first; the removal animates there (§4.9).
            navigation.popTo('Family', { remove: { id: m.id, reassign } });
          }}
        />
      ) : null}
      <ToastHost bottom={insets.bottom + 24} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  body: { paddingHorizontal: 16 },
  bar: { flexDirection: 'row', justifyContent: 'space-between' },
  round: { width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.08)', borderWidth: 1, borderColor: colors.glassBorder, alignItems: 'center', justifyContent: 'center' },
  hero: { height: 200, alignItems: 'center', justifyContent: 'center' },
  dust: { position: 'absolute', width: DUST, height: DUST, left: '50%', marginLeft: -DUST / 2, top: 100 - DUST / 2 },
  center: { textAlign: 'center' },
  sub: { marginTop: 4 },
  stageChip: { alignSelf: 'center', marginTop: 10, paddingHorizontal: 12, height: 28, borderRadius: 14, borderWidth: 1, justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.05)' },
  completion: { flexDirection: 'row', alignItems: 'center', marginTop: 22, padding: 14, borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder },
  completionText: { marginLeft: 14 },
  section: { marginTop: 22 },
  row: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder, marginBottom: 10 },
  icon: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  rowText: { flex: 1, marginLeft: 14, marginRight: 8 },
  rowSub: { marginTop: 2, fontSize: 12.5 },
  pillRow: { flexDirection: 'row' },
  removeBtn: { alignSelf: 'center', marginTop: 18, paddingHorizontal: 20, height: 44, justifyContent: 'center' },
});
