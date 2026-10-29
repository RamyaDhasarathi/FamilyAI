// Member details wizard (AGENT_CORE_AND_FAMILY.md §4.7): a full-height glass
// sheet stepping through the five sections and a review. Six tappable
// progress segments in each section's colour; content slides between steps
// and the sheet's glow cross-fades to the next colour. "Skip for now" marks
// a section "needs update"; "Save and continue" validates first; Close saves.
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentRef } from 'react';
import { BackHandler, Keyboard, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeIn, FadeOut, SlideInLeft, SlideInRight, useAnimatedKeyboard, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import { ShieldCheck } from 'lucide-react-native';
import type { MemberBasics, SectionId, SectionStatus } from '../../services/interfaces';
import { REVIEW_COLOR, SECTION_IDS, adultsOf, ageGroupOf, ageOf, displayName, sectionMeta } from '../../family/model';
import { fieldValue, fieldsFor, isEmpty, validateField } from '../../family/fields';
import { colors, radii, withAlpha } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import type { ScreenProps } from '../../navigation/types';
import { useFamily } from '../../store/useFamily';
import { AppText } from '../../components/AppText';
import { ClosePill, PillButton } from '../../components/Pills';
import { Pressy } from '../../components/Pressy';
import { MemberAvatar, AMBER } from '../../components/family/MemberBits';
import { ToastHost } from '../../components/Toast';
import { SECTION_ICONS, ReviewIcon } from './MemberProfileScreen';
import { WizardFields, draftAge } from './WizardFields';
import { WizardReview } from './WizardReview';

type Step = SectionId | 'review';
const STEPS: Step[] = [...SECTION_IDS, 'review'];
const sameDraft = (a: Record<string, unknown>, b: Record<string, unknown>) =>
  [...new Set([...Object.keys(a), ...Object.keys(b)])].every((k) => (isEmpty(a[k]) && isEmpty(b[k])) || JSON.stringify(a[k]) === JSON.stringify(b[k]));

function Segment({ color, state, current, onPress, label }: { color: string; state: SectionStatus | 'review'; current: boolean; onPress: () => void; label: string }) {
  const pulse = useSharedValue(1);
  useEffect(() => {
    pulse.set(current ? withRepeat(withTiming(0.45, { duration: 700 }), -1, true) : withTiming(1, { duration: 200 }));
  }, [current, pulse]);
  const st = useAnimatedStyle(() => ({ opacity: pulse.value }));
  const fill = current ? color : state === 'complete' ? color : state === 'needsUpdate' ? AMBER : 'rgba(255,255,255,0.14)';
  return (
    <Pressy onPress={onPress} style={styles.segHit} accessibilityLabel={label} accessibilityState={{ selected: current }} pressScale={0.9}>
      <Animated.View style={[styles.seg, { backgroundColor: fill }, st]} />
    </Pressy>
  );
}

export function MemberWizardScreen({ navigation, route }: ScreenProps<'MemberWizard'>) {
  const insets = useSafeAreaInsets();
  const members = useFamily((s) => s.members);
  const saveSection = useFamily((s) => s.saveSection);
  const updateBasics = useFamily((s) => s.updateBasics);
  const member = members.find((m) => m.id === route.params.id);
  const [step, setStep] = useState<Step>(route.params.section ?? 'basic');
  // 0 until the first step change: the sheet slides up, so the first step needs no slide of its own.
  const [dir, setDir] = useState(0);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [base, setBase] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const ys = useRef<Record<string, number>>({});
  const fieldsTop = useRef(0);
  const scrollY = useRef(0);
  const viewH = useRef(0);
  const focused = useRef<string | null>(null);
  const busy = useRef(false);

  // Keep the footer and the focused field above the keyboard (Android draws
  // edge to edge, so the window does not resize for it).
  const kb = useAnimatedKeyboard();
  const kbPad = useAnimatedStyle(() => ({ paddingBottom: Math.max(0, kb.height.value - insets.bottom) }));
  /** Scroll a field into view: always for errors, only when hidden for focus. */
  const reveal = useCallback((k: string, always = false) => {
    const y = fieldsTop.current + (ys.current[k] ?? 0);
    if (!always && y >= scrollY.current && y + 76 <= scrollY.current + viewH.current) return;
    scroll.current?.scrollTo({ y: Math.max(0, y - 16), animated: true });
  }, []);
  useEffect(() => {
    const sub = Keyboard.addListener('keyboardDidShow', () => {
      if (focused.current) reveal(focused.current, true);
    });
    return () => sub.remove();
  }, [reveal]);

  const age = member ? draftAge(draft.dateOfBirth, ageOf(member.dateOfBirth)) : 0;
  const group = ageGroupOf(age);
  const fields = useMemo(() => (member && step !== 'review' ? fieldsFor(step, { ...member, ...(draft as object) }, age, group) : []), [member, step, draft, age, group]);
  const adults = member ? adultsOf(members).filter((a) => a.id !== member.id) : [];

  // Fresh draft whenever the step changes (adjusted during render, not in an effect).
  const [draftFor, setDraftFor] = useState<string | null>(null);
  const key = member ? `${member.id}:${step}` : null;
  if (member && key !== draftFor) {
    setDraftFor(key);
    if (step !== 'review') {
      const d: Record<string, unknown> = { ...member.sections[step].data };
      for (const f of fieldsFor(step, member, ageOf(member.dateOfBirth), ageGroupOf(ageOf(member.dateOfBirth)))) d[f.key] = fieldValue(f, member, member.sections[step].data);
      setDraft(d);
      setBase(d);
    }
    setErrors({});
  }
  useEffect(() => {
    ys.current = {};
    scroll.current?.scrollTo({ y: 0, animated: false });
  }, [step]);

  const visible = useCallback(() => fields.filter((f) => !f.when || f.when(draft, { ...member!, ...(draft as object) })), [fields, draft, member]);
  const check = useCallback(() => {
    const e: Record<string, string | null> = {};
    for (const f of visible()) e[f.key] = validateField(f, draft[f.key]);
    return e;
  }, [visible, draft]);

  /** Write the current step: basics to the member, the rest to the section. */
  const persist = async (status: SectionStatus) => {
    if (!member || step === 'review') return;
    const patch: Partial<MemberBasics> = {};
    const data: Record<string, unknown> = { ...member.sections[step].data };
    for (const f of fields) {
      if (f.basics) {
        const v = draft[f.key];
        if (v !== (member as unknown as Record<string, unknown>)[f.basics]) (patch as Record<string, unknown>)[f.basics] = typeof v === 'string' ? v.trim() || undefined : v;
      } else data[f.key] = draft[f.key];
    }
    if (Object.keys(patch).length) await updateBasics(member.id, patch);
    await saveSection(member.id, step, data, status);
  };

  const go = (to: Step) => {
    setDir(STEPS.indexOf(to) >= STEPS.indexOf(step) ? 1 : -1);
    setStep(to);
  };

  const next = () => go(STEPS[Math.min(STEPS.length - 1, STEPS.indexOf(step) + 1)]);

  const saveAndContinue = async () => {
    if (busy.current) return;
    const e = check();
    setErrors(e);
    const first = visible().find((f) => e[f.key]);
    if (first) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      reveal(first.key, true);
      return;
    }
    busy.current = true;
    await persist('complete');
    busy.current = false;
    next();
  };

  const skip = async () => {
    if (busy.current) return;
    busy.current = true;
    await persist('needsUpdate');
    busy.current = false;
    next();
  };

  /** Keep edits when leaving a step without its buttons (Close, back, a progress
   *  segment): complete if valid, otherwise needing an update. Untouched steps keep their status. */
  const saveCurrent = useCallback(async () => {
    if (!member || step === 'review' || busy.current || sameDraft(draft, base)) return;
    busy.current = true;
    const e = check();
    await persist(visible().every((f) => !e[f.key]) ? 'complete' : 'needsUpdate');
    busy.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member, step, check, visible, draft, base]);

  const close = useCallback(async () => {
    await saveCurrent();
    navigation.goBack();
  }, [saveCurrent, navigation]);

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      void close();
      return true;
    });
    return () => sub.remove();
  }, [close]);

  if (!member) return null;
  const meta = step === 'review' ? null : sectionMeta(step, group);
  const color = meta?.color ?? REVIEW_COLOR;
  const Icon = step === 'review' ? ReviewIcon : SECTION_ICONS[step];
  const idx = STEPS.indexOf(step);
  const title = meta?.title ?? 'Review';

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <Animated.View style={[styles.sheet, kbPad]}>
        <Animated.View key={color} entering={FadeIn.duration(450)} exiting={FadeOut.duration(450)} style={StyleSheet.absoluteFill} pointerEvents="none">
          <LinearGradient colors={[withAlpha(color, 0.2), withAlpha(color, 0)]} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 0.6 }} style={StyleSheet.absoluteFill} />
        </Animated.View>
        <View style={styles.header}>
          <MemberAvatar member={member} size={40} />
          <View style={styles.headerText}>
            <AppText style={T.bodyStrong} numberOfLines={1}>
              {displayName(member)}
            </AppText>
            <AppText style={[T.small, styles.stepText]} numberOfLines={1}>
              Step {idx + 1} of 6 · {title}
            </AppText>
          </View>
          <ClosePill onPress={() => void close()} />
        </View>
        <View style={styles.progress}>
          {STEPS.map((s) => {
            const c = s === 'review' ? REVIEW_COLOR : sectionMeta(s, group).color;
            return (
              <Segment
                key={s}
                color={c}
                state={s === 'review' ? 'review' : member.sections[s].status}
                current={s === step}
                onPress={() => {
                  void saveCurrent();
                  go(s);
                }}
                label={`Go to ${s === 'review' ? 'Review' : sectionMeta(s, group).title}`}
              />
            );
          })}
        </View>

        <ScrollView
          ref={scroll}
          style={styles.flex}
          contentContainerStyle={styles.body}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          scrollEventThrottle={32}
          onScroll={(e) => (scrollY.current = e.nativeEvent.contentOffset.y)}
          onLayout={(e) => (viewH.current = e.nativeEvent.layout.height)}
        >
          <Animated.View key={step} entering={dir === 0 ? undefined : (dir > 0 ? SlideInRight : SlideInLeft).springify().damping(22).stiffness(120).mass(1)}>
            <View style={styles.intro}>
              <View style={[styles.icon, { backgroundColor: withAlpha(color, 0.16), borderColor: withAlpha(color, 0.5) }]}>
                <Icon size={22} color={color} />
              </View>
              <AppText style={[T.sheetTitle, styles.introTitle]} accessibilityRole="header">
                {title}
              </AppText>
              <AppText style={[T.small, styles.why]}>{meta?.why ?? 'Check each section, then finish. You can come back any time.'}</AppText>
            </View>
            {meta?.sensitive ? (
              <View style={[styles.note, { borderColor: withAlpha(color, 0.5) }]}>
                <ShieldCheck size={16} color={color} />
                <AppText style={[T.small, styles.noteText]}>Demo app: these details are stored only on this device.</AppText>
              </View>
            ) : null}
            {step === 'review' ? (
              <WizardReview member={member} members={members} group={group} onEdit={go} />
            ) : (
              <View onLayout={(e) => (fieldsTop.current = e.nativeEvent.layout.y)}>
                <WizardFields
                  fields={fields}
                  draft={draft}
                  member={member}
                  adults={adults}
                  errors={errors}
                  accent={color}
                  onChange={(k, v) => {
                    const d = { ...draft, [k]: v };
                    setDraft(d);
                    if (errors[k]) {
                      const f = fields.find((x) => x.key === k);
                      if (f) setErrors({ ...errors, [k]: validateField(f, v) });
                    }
                  }}
                  onLayoutY={(k, y) => {
                    ys.current[k] = y;
                  }}
                  onFocusField={(k) => {
                    focused.current = k;
                    if (Keyboard.isVisible()) reveal(k);
                  }}
                />
              </View>
            )}
          </Animated.View>
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + 12 }]}>
          {step === 'review' ? (
            <PillButton label="Done" variant="primary" onPress={() => navigation.goBack()} style={styles.full} />
          ) : (
            <>
              <PillButton label="Skip for now" onPress={() => void skip()} style={styles.half} />
              <PillButton label="Save and continue" variant="primary" onPress={() => void saveAndContinue()} style={[styles.half, styles.right]} />
            </>
          )}
        </View>
      </Animated.View>
      <ToastHost bottom={insets.bottom + 90} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: {
    flex: 1, borderTopLeftRadius: radii.sheet, borderTopRightRadius: radii.sheet, backgroundColor: 'rgba(22,25,33,0.98)',
    borderWidth: 1, borderBottomWidth: 0, borderColor: colors.glassBorder, overflow: 'hidden',
  },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 16 },
  headerText: { flex: 1, marginLeft: 12, marginRight: 10 },
  stepText: { marginTop: 2, fontSize: 12.5 },
  progress: { flexDirection: 'row', paddingHorizontal: 12, marginTop: 14 },
  segHit: { flex: 1, height: 22, justifyContent: 'center', paddingHorizontal: 3 },
  seg: { height: 4, borderRadius: 2 },
  flex: { flex: 1 },
  body: { paddingHorizontal: 16, paddingBottom: 30 },
  intro: { marginTop: 14 },
  icon: { width: 46, height: 46, borderRadius: 23, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  introTitle: { marginTop: 12 },
  why: { marginTop: 6 },
  note: { flexDirection: 'row', alignItems: 'center', marginTop: 14, padding: 12, borderRadius: 14, borderWidth: 1, borderStyle: 'dashed' },
  noteText: { flex: 1, marginLeft: 10, color: colors.ink, fontSize: 12.5 },
  footer: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
  half: { flex: 1, height: 48, borderRadius: 24 },
  right: { marginLeft: 10 },
  full: { flex: 1, height: 48, borderRadius: 24 },
});
