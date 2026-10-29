// One member on the Family hub (AGENT_CORE_AND_FAMILY.md §4.4). Tap opens the
// profile; swipe left (the Needs-you SwipeCard feel) reveals Edit and Remove;
// long-press opens a small menu. The owner has no Remove. A just-added card
// glows; a removed one dissolves into particles and collapses.
import { useEffect } from 'react';
import { BackHandler, Pressable, StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { interpolate, useAnimatedStyle, useSharedValue, withSequence, withSpring, withTiming } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Pencil, Trash2 } from 'lucide-react-native';
import type { FamilyMember } from '../../services/interfaces';
import { SECTION_IDS, ageOf, ageText, completionOf, displayName, relationshipLabel, sectionMeta, sectionsNeedingUpdate, sectionsNotStarted, ageGroupOf, stageOf } from '../../family/model';
import { colors, radii, withAlpha } from '../../theme/tokens';
import { springs } from '../../theme/motion';
import { type as T } from '../../theme/typography';
import { AppText } from '../../components/AppText';
import { AMBER, CompletionRing, GREEN, MemberAvatar, Tag } from '../../components/family/MemberBits';
import { Pressy } from '../../components/Pressy';
import { Dissolve } from './Dissolve';

/** How far the card slides to show its actions: two buttons, or Edit alone (the owner). */
const OPEN = 132;
const OPEN_ONE = 70;

interface Props {
  member: FamilyMember;
  glow: boolean;
  removing: boolean;
  onOpen: () => void;
  onEdit: () => void;
  onRemove: () => void;
  onLongPress: () => void;
}

export function memberA11y(m: FamilyMember) {
  const n = sectionsNeedingUpdate(m).length;
  const blank = sectionsNotStarted(m).length;
  const rel = m.isOwner ? 'you' : relationshipLabel(m).toLowerCase();
  const state = n ? `${n === 1 ? 'one section needs' : `${n} sections need`} updating` : blank ? `${blank === 1 ? 'one section' : `${blank} sections`} not started` : 'all details up to date';
  return `${displayName(m)}, ${rel}, ${ageText(ageOf(m.dateOfBirth))}, ${state}`;
}

export function MemberCard({ member: m, glow, removing, onOpen, onEdit, onRemove, onLongPress }: Props) {
  const tx = useSharedValue(0);
  const shine = useSharedValue(0);
  const gone = useSharedValue(0);
  const age = ageOf(m.dateOfBirth);
  const st = stageOf(m);
  const todo = sectionsNeedingUpdate(m);
  const blank = sectionsNotStarted(m).length;
  const group = ageGroupOf(age);
  const canRemove = !m.isOwner;
  const open = canRemove ? OPEN : OPEN_ONE;

  useEffect(() => {
    if (glow) shine.set(withSequence(withTiming(1, { duration: 260 }), withTiming(0, { duration: 1400 })));
  }, [glow, shine]);
  useEffect(() => {
    if (removing) {
      tx.set(withSpring(0, springs.snappy));
      gone.set(withTiming(1, { duration: 480 }));
    } else gone.set(withTiming(0, { duration: 220 }));
  }, [removing, gone, tx]);

  const close = () => {
    tx.set(withSpring(0, springs.snappy));
  };
  const pan = Gesture.Pan()
    .activeOffsetX([-12, 12])
    .failOffsetY([-12, 12])
    .onChange((e) => {
      tx.set(Math.min(0, Math.max(-open - 30, tx.get() + e.changeX)));
    })
    .onEnd((e) => {
      tx.set(withSpring(tx.get() < -open / 2 || e.velocityX < -500 ? -open : 0, springs.snappy));
    });

  const card = useAnimatedStyle(() => ({
    transform: [{ translateX: tx.value }, { scale: 1 - 0.04 * gone.value }],
    opacity: 1 - gone.value,
  }));
  const wrap = useAnimatedStyle(() => ({ opacity: 1 - gone.value * 0.2 }));
  const glowSt = useAnimatedStyle(() => ({ opacity: shine.value }));
  const actions = useAnimatedStyle(() => ({ opacity: interpolate(tx.value, [-open, -20, 0], [1, 0.3, 0], 'clamp') }));

  const meta = `${m.isOwner ? 'You' : relationshipLabel(m)} · ${ageText(age)} · ${st.name}`;
  return (
    <Animated.View style={[styles.wrap, wrap]}>
      <Animated.View style={[styles.actions, actions]}>
        <Pressy onPress={() => { close(); onEdit(); }} style={[styles.round, styles.edit]} accessibilityLabel={`Edit ${displayName(m)}`}>
          <Pencil size={18} color={colors.ink} />
        </Pressy>
        {canRemove ? (
          <Pressy onPress={() => { close(); onRemove(); }} style={[styles.round, styles.remove]} accessibilityLabel={`Remove ${displayName(m)} from family`}>
            <Trash2 size={18} color="#FFFFFF" />
          </Pressy>
        ) : null}
      </Animated.View>
      <GestureDetector gesture={pan}>
        <Animated.View style={card}>
          <Pressable
            onPress={() => {
              if (tx.get() < -4) close();
              else onOpen();
            }}
            onLongPress={() => {
              void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
              onLongPress();
            }}
            delayLongPress={420}
            style={styles.card}
            accessibilityRole="button"
            accessibilityLabel={memberA11y(m)}
            accessibilityHint="Opens their profile"
            accessibilityActions={[
              { name: 'activate', label: 'Open profile' },
              { name: 'edit', label: 'Edit details' },
              ...(canRemove ? [{ name: 'remove', label: 'Remove from family' }] : []),
            ]}
            onAccessibilityAction={(e) => {
              const a = e.nativeEvent.actionName;
              if (a === 'edit') onEdit();
              else if (a === 'remove') onRemove();
              else onOpen();
            }}
          >
            {glow ? (
              <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.glow, { borderColor: st.accent, shadowColor: st.accent }, glowSt]} />
            ) : null}
            <MemberAvatar member={m} size={56} animated={m.isOwner} />
            <View style={styles.text}>
              <View style={styles.nameRow}>
                <AppText style={[T.bodyStrong, styles.name]} numberOfLines={1}>
                  {m.fullName}
                </AppText>
                {m.isOwner ? (
                  <View style={styles.you}>
                    <AppText style={[T.chip, styles.youText]}>You</AppText>
                  </View>
                ) : null}
              </View>
              <AppText style={[T.small, styles.meta]} numberOfLines={1}>
                {meta}
              </AppText>
              <View style={styles.tags}>
                {todo.length ? (
                  todo.map((s) => <Tag key={s} text={sectionMeta(s, group).tag} color={AMBER} />)
                ) : blank ? (
                  <Tag text={blank === SECTION_IDS.length ? 'Details not started' : `${blank} ${blank === 1 ? 'section' : 'sections'} not started`} color={colors.dim} />
                ) : (
                  <Tag text="All details up to date" color={GREEN} />
                )}
              </View>
            </View>
            <CompletionRing value={completionOf(m)} size={28} stroke={3} color={todo.length ? AMBER : blank ? colors.muted : GREEN} />
          </Pressable>
        </Animated.View>
      </GestureDetector>
      {removing ? <Dissolve color={st.accent} /> : null}
    </Animated.View>
  );
}

/** Small glass context menu for long-press (Edit details / Remove from family). */
export function MemberMenu({ member, onEdit, onRemove, onClose }: { member: FamilyMember; onEdit: () => void; onRemove: () => void; onClose: () => void }) {
  // Android back closes the menu before it pops the screen.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onClose();
      return true;
    });
    return () => sub.remove();
  }, [onClose]);
  return (
    <View style={StyleSheet.absoluteFill}>
      <Pressable style={[StyleSheet.absoluteFill, styles.scrim]} onPress={onClose} accessibilityLabel="Close menu" />
      <View style={styles.menuWrap} pointerEvents="box-none">
        <View style={styles.menu}>
          <AppText style={[T.smallStrong, styles.menuTitle]}>{displayName(member)}</AppText>
          <Pressy onPress={onEdit} style={styles.menuRow} pressScale={0.98} accessibilityLabel="Edit details">
            <Pencil size={16} color={colors.ink} />
            <AppText style={[T.menu, styles.menuText]}>Edit details</AppText>
          </Pressy>
          {!member.isOwner ? (
            <Pressy onPress={onRemove} style={styles.menuRow} pressScale={0.98} accessibilityLabel={`Remove ${displayName(member)} from family`}>
              <Trash2 size={16} color={colors.danger} />
              <AppText style={[T.menu, styles.menuText, { color: colors.danger }]}>Remove from family</AppText>
            </Pressy>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: 10 },
  actions: { position: 'absolute', right: 8, top: 0, bottom: 0, flexDirection: 'row', alignItems: 'center' },
  round: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', marginLeft: 10 },
  edit: { backgroundColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderColor: colors.glassBorder },
  remove: { backgroundColor: colors.danger },
  card: {
    flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: radii.card,
    backgroundColor: 'rgba(28,31,40,0.96)', borderWidth: 1, borderColor: colors.glassBorder,
  },
  glow: { borderRadius: radii.card, borderWidth: 1.5, backgroundColor: withAlpha('#FFFFFF', 0.04) },
  text: { flex: 1, marginLeft: 14, marginRight: 10 },
  nameRow: { flexDirection: 'row', alignItems: 'center' },
  name: { flexShrink: 1 },
  you: { marginLeft: 8, paddingHorizontal: 7, height: 18, borderRadius: 9, backgroundColor: 'rgba(255,255,255,0.12)', justifyContent: 'center' },
  youText: { fontSize: 10 },
  meta: { marginTop: 2, fontSize: 12.5 },
  tags: { flexDirection: 'row', flexWrap: 'wrap' },
  scrim: { backgroundColor: 'rgba(0,0,0,0.5)' },
  menuWrap: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  menu: { width: 260, borderRadius: radii.card, backgroundColor: 'rgba(34,37,46,0.97)', borderWidth: 1, borderColor: colors.glassBorder, paddingVertical: 8 },
  menuTitle: { color: colors.muted, paddingHorizontal: 18, paddingVertical: 8 },
  menuRow: { flexDirection: 'row', alignItems: 'center', height: 46, paddingHorizontal: 18 },
  menuText: { marginLeft: 12 },
});
