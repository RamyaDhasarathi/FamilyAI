// Add family member / Edit basics (AGENT_CORE_AND_FAMILY.md §4.5, §4.6): a
// keyboard-aware glass sheet with a live avatar preview for the age entered,
// name, relationship chips (no "Self"), date of birth, and (when editing)
// preferred name and photo. Closing with unsaved input asks first.
import { useRef, useState, type ComponentRef } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import type { FamilyMember, MemberBasics, Relationship } from '../../services/interfaces';
import { RELATIONSHIPS, ageOf, yearsText } from '../../family/model';
import { avatarForAge, stageAccent } from '../../graphics/avatars';
import { colors, radii } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import { useFamilyOS } from '../../store/useFamilyOS';
import { AppText } from '../../components/AppText';
import { ModalCard } from '../../components/ModalCard';
import { ClosePill, PillButton } from '../../components/Pills';
import { ChoiceChips, FieldFrame } from '../../components/form/Choices';
import { DateField } from '../../components/form/PickerFields';
import { TextField } from '../../components/form/TextField';
import { Dissolve } from './Dissolve';
import { ConfirmDialog } from './ConfirmDialog';

const ACCENT = '#61B8FF';
const yearsAgo = (n: number) => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - n);
  return d;
};

interface Props {
  visible: boolean;
  /** Edit mode when a member is given. */
  member?: FamilyMember;
  onClose: () => void;
  /** finishLater: "Add now, finish later" (add mode only). */
  onSubmit: (basics: MemberBasics, finishLater: boolean) => Promise<void>;
}

type Errors = Partial<Record<'fullName' | 'relationship' | 'relationshipOther' | 'dateOfBirth', string>>;

function validate(b: Partial<MemberBasics>, owner: boolean): Errors {
  const e: Errors = {};
  if (!b.fullName?.trim()) e.fullName = 'Required';
  else if (!/^[\p{L} .'-]{2,60}$/u.test(b.fullName.trim())) e.fullName = 'Use 2–60 letters, spaces or . \' -';
  if (!owner && !b.relationship) e.relationship = 'Choose one';
  if (b.relationship === 'Other' && !b.relationshipOther?.trim()) e.relationshipOther = 'Required';
  if (!b.dateOfBirth) e.dateOfBirth = 'Required';
  return e;
}

export function MemberBasicsSheet({ visible, member, onClose, onSubmit }: Props) {
  const edit = !!member;
  const initial: Partial<MemberBasics> = member
    ? { fullName: member.fullName, preferredName: member.preferredName, relationship: member.relationship, relationshipOther: member.relationshipOther, dateOfBirth: member.dateOfBirth, photoUri: member.photoUri }
    : {};
  const [b, setB] = useState<Partial<MemberBasics>>(initial);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const ys = useRef<Record<string, number>>({});
  const toast = useFamilyOS((s) => s.toast);
  // Reset the form each time the sheet opens.
  const [openKey, setOpenKey] = useState(visible);
  if (visible !== openKey) {
    setOpenKey(visible);
    if (visible) {
      setB(initial);
      setErrors({});
    }
  }

  const age = b.dateOfBirth ? ageOf(b.dateOfBirth) : null;
  const stage = age !== null ? avatarForAge(age) : null;
  const dirty = JSON.stringify(b) !== JSON.stringify(initial);
  const set = (patch: Partial<MemberBasics>) => {
    const next = { ...b, ...patch };
    setB(next);
    // Messages clear as soon as the field is fixed.
    if (Object.keys(errors).length) setErrors(validate(next, !!member?.isOwner));
  };

  const requestClose = () => (dirty ? setConfirm(true) : onClose());

  const submit = async (finishLater: boolean) => {
    const e = validate(b, !!member?.isOwner);
    setErrors(e);
    const first = (['fullName', 'relationship', 'relationshipOther', 'dateOfBirth'] as const).find((k) => e[k]);
    if (first) {
      scroll.current?.scrollTo({ y: Math.max(0, (ys.current[first] ?? 0) - 12), animated: true });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      return;
    }
    setBusy(true);
    try {
      await onSubmit(
        {
          fullName: b.fullName!.trim(),
          preferredName: b.preferredName?.trim() || undefined,
          relationship: (b.relationship ?? 'Self') as Relationship,
          relationshipOther: b.relationship === 'Other' ? b.relationshipOther?.trim() : undefined,
          dateOfBirth: b.dateOfBirth!,
          photoUri: b.photoUri,
        },
        finishLater
      );
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } finally {
      setBusy(false);
    }
  };

  const pickPhoto = async (camera: boolean) => {
    try {
      if (camera) {
        const p = await ImagePicker.requestCameraPermissionsAsync();
        if (!p.granted) return toast('Camera access is off for FamilyOS');
      }
      const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.8 };
      const r = camera ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
      if (!r.canceled && r.assets[0]) set({ photoUri: r.assets[0].uri });
    } catch {
      toast(camera ? 'No camera available here' : 'Couldn’t open your photos');
    }
  };

  const header = (
    <View style={styles.header}>
      <AppText style={T.sheetTitle} accessibilityRole="header">
        {edit ? 'Edit details' : 'Add family member'}
      </AppText>
      <ClosePill onPress={requestClose} />
    </View>
  );

  return (
    <>
      <ModalCard visible={visible} onClose={requestClose} header={header} closeAbove={false} fixedFrac={0.9} keyboardAware opaque>
        <ScrollView ref={scroll} contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <View style={styles.preview} accessible accessibilityLabel={stage ? `Avatar: stage ${stage.stage}, ${stage.name}` : 'Avatar appears once a date of birth is set'}>
            <View style={styles.previewImg}>
              {b.photoUri ? (
                <Image source={{ uri: b.photoUri }} style={styles.img} contentFit="cover" />
              ) : stage ? (
                <Animated.View key={stage.stage} entering={FadeIn.duration(380)} exiting={FadeOut.duration(220)} style={StyleSheet.absoluteFill}>
                  <Image source={stage.gif} style={styles.img} contentFit="cover" />
                </Animated.View>
              ) : (
                <View style={styles.orb} />
              )}
              {stage ? <Dissolve key={`s${stage.stage}`} color={stageAccent[stage.stage]} cx={36} cy={36} size={72} reverse /> : null}
            </View>
            <View style={styles.previewText}>
              <AppText style={[T.bodyStrong, { color: stage ? stageAccent[stage.stage] : colors.muted }]}>
                {stage ? `Stage ${stage.stage} · ${stage.name}` : 'Avatar'}
              </AppText>
              <AppText style={[T.small, styles.previewSub]}>
                {stage ? `Ages ${stage.ages}${age !== null ? ` · ${yearsText(age)}` : ''}` : 'Appears when you add a date of birth'}
              </AppText>
            </View>
          </View>

          <View onLayout={(e) => (ys.current.fullName = e.nativeEvent.layout.y)} style={styles.gap}>
            <TextField label="Full name" required value={b.fullName ?? ''} onChange={(v) => set({ fullName: v })} accent={ACCENT} error={errors.fullName} autoCapitalize="words" />
          </View>
          {edit ? (
            <View style={styles.gap}>
              <TextField label="Preferred name" value={b.preferredName ?? ''} onChange={(v) => set({ preferredName: v })} accent={ACCENT} autoCapitalize="words" />
            </View>
          ) : null}
          {!member?.isOwner ? (
            <View onLayout={(e) => (ys.current.relationship = e.nativeEvent.layout.y)} style={styles.gap}>
              <FieldFrame label="Relationship" required error={errors.relationship}>
                <ChoiceChips label="Relationship" options={RELATIONSHIPS} value={b.relationship} onChange={(v) => set({ relationship: v as Relationship })} accent={ACCENT} />
              </FieldFrame>
            </View>
          ) : null}
          {b.relationship === 'Other' ? (
            <View onLayout={(e) => (ys.current.relationshipOther = e.nativeEvent.layout.y)} style={styles.gap}>
              <TextField label="Relationship (other)" required value={b.relationshipOther ?? ''} onChange={(v) => set({ relationshipOther: v })} accent={ACCENT} error={errors.relationshipOther} />
            </View>
          ) : null}
          <View onLayout={(e) => (ys.current.dateOfBirth = e.nativeEvent.layout.y)} style={styles.gap}>
            <DateField label="Date of birth" required value={b.dateOfBirth} onChange={(v) => set({ dateOfBirth: v })} accent={ACCENT} error={errors.dateOfBirth} maxDate={new Date()} minDate={yearsAgo(120)} ageNote />
          </View>
          {edit ? (
            <View style={[styles.gap, styles.photoRow]}>
              <PillButton label="Choose photo" onPress={() => void pickPhoto(false)} />
              <PillButton label="Take photo" onPress={() => void pickPhoto(true)} style={styles.pillGap} />
              {b.photoUri ? <PillButton label="Remove photo" onPress={() => set({ photoUri: undefined })} style={styles.pillGap} /> : null}
            </View>
          ) : null}

          <View style={styles.actions}>
            {edit ? (
              <PillButton label={busy ? 'Saving…' : 'Save'} variant="primary" onPress={() => void submit(false)} style={styles.primary} />
            ) : (
              <>
                <PillButton label={busy ? 'Adding…' : 'Add and fill details'} variant="primary" onPress={() => void submit(false)} style={styles.primary} />
                <PillButton label="Add now, finish later" onPress={() => void submit(true)} style={styles.secondary} />
              </>
            )}
          </View>
        </ScrollView>
      </ModalCard>
      {confirm ? (
        <ConfirmDialog
          title={edit ? 'Discard your changes?' : 'Discard this new member?'}
          confirm="Discard"
          cancel="Keep editing"
          onConfirm={() => {
            setConfirm(false);
            onClose();
          }}
          onCancel={() => setConfirm(false)}
        />
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 8 },
  body: { paddingHorizontal: 16, paddingBottom: 24 },
  preview: { flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder, marginBottom: 6 },
  previewImg: { width: 72, height: 72, borderRadius: 36, overflow: 'visible' },
  img: { width: 72, height: 72, borderRadius: 36 },
  orb: { width: 72, height: 72, borderRadius: 36, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderColor: colors.glassBorder, borderStyle: 'dashed' },
  previewText: { flex: 1, marginLeft: 14 },
  previewSub: { marginTop: 3, fontSize: 12.5 },
  gap: { marginTop: 14 },
  photoRow: { flexDirection: 'row', flexWrap: 'wrap' },
  pillGap: { marginLeft: 8 },
  actions: { marginTop: 22 },
  primary: { alignSelf: 'stretch', height: 50, borderRadius: 25 },
  secondary: { alignSelf: 'stretch', height: 46, borderRadius: 23, marginTop: 10 },
});
