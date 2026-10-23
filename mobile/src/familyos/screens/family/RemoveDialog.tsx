// Remove-member dialog (AGENT_CORE_AND_FAMILY.md §4.9): centred glass dialog
// over a dimmed background. If the member pays any child's allowance, those
// children are listed and the user picks another adult or "Decide later".
import { useEffect, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeOut, ZoomIn } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import type { FamilyMember } from '../../services/interfaces';
import { adultsOf, dependentsOf, displayName } from '../../family/model';
import { colors, radii } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import { AppText } from '../../components/AppText';
import { MemberAvatar } from '../../components/family/MemberBits';
import { ChoiceChips } from '../../components/form/Choices';
import { Pressy } from '../../components/Pressy';

interface Props {
  member: FamilyMember;
  members: FamilyMember[];
  /** reassign: undefined = no dependents; an adult id; or null = decide later. */
  onConfirm: (reassign?: string | null) => void;
  onCancel: () => void;
}

const LATER = 'Decide later';

export function RemoveDialog({ member, members, onConfirm, onCancel }: Props) {
  const deps = dependentsOf(members, member.id);
  const others = adultsOf(members).filter((a) => a.id !== member.id);
  const [choice, setChoice] = useState<string>(others[0] ? displayName(others[0]) : LATER);
  const name = displayName(member);

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onCancel();
      return true;
    });
    return () => sub.remove();
  }, [onCancel]);

  const confirm = () => {
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    if (deps.length === 0) return onConfirm(undefined);
    const a = others.find((x) => displayName(x) === choice);
    onConfirm(a ? a.id : null);
  };

  return (
    <Animated.View entering={FadeIn.duration(180)} exiting={FadeOut.duration(160)} style={StyleSheet.absoluteFill}>
      <Pressable style={[StyleSheet.absoluteFill, styles.scrim]} onPress={onCancel} accessibilityLabel="Cancel" />
      <View style={styles.center} pointerEvents="box-none">
        <Animated.View entering={ZoomIn.springify().damping(18).stiffness(220).mass(1)} style={styles.card} accessibilityViewIsModal>
          <MemberAvatar member={member} size={64} style={styles.avatar} />
          <AppText style={[T.sheetTitle, styles.title]} accessibilityRole="header">
            Remove {name} from your family?
          </AppText>
          <AppText style={[T.small, styles.body]}>
            Their profile and saved details will be deleted from this device. Your agents will stop planning for them.
          </AppText>
          {deps.length > 0 ? (
            <View style={styles.deps}>
              <AppText style={[T.small, styles.depsText]}>
                {name} pays the allowance for {deps.map(displayName).join(' and ')}. Who should pay it now?
              </AppText>
              <ChoiceChips
                label="New payer"
                options={[...others.map(displayName), LATER]}
                value={choice}
                onChange={(v) => setChoice(v as string)}
                accent={colors.danger}
              />
            </View>
          ) : null}
          <View style={styles.buttons}>
            <Pressy onPress={onCancel} style={[styles.btn, styles.cancel]} accessibilityLabel="Cancel">
              <AppText style={T.bodyStrong}>Cancel</AppText>
            </Pressy>
            <Pressy onPress={confirm} style={[styles.btn, styles.remove]} accessibilityLabel={`Remove ${name} from family`}>
              <AppText style={[T.bodyStrong, { color: '#FFFFFF' }]}>Remove</AppText>
            </Pressy>
          </View>
        </Animated.View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: 'rgba(0,0,0,0.66)' },
  center: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 22 },
  card: {
    width: '100%', maxWidth: 380, borderRadius: radii.sheet, backgroundColor: 'rgba(30,33,42,0.97)',
    borderWidth: 1, borderColor: colors.glassBorder, padding: 22, alignItems: 'center',
  },
  avatar: { marginTop: 6, marginBottom: 14 },
  title: { textAlign: 'center' },
  body: { textAlign: 'center', marginTop: 8 },
  deps: { alignSelf: 'stretch', marginTop: 16, padding: 12, borderRadius: 14, backgroundColor: 'rgba(255,178,63,0.08)', borderWidth: 1, borderColor: 'rgba(255,178,63,0.3)' },
  depsText: { color: colors.ink, marginBottom: 10 },
  buttons: { flexDirection: 'row', marginTop: 20, alignSelf: 'stretch' },
  btn: { flex: 1, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  cancel: { backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder, marginRight: 10 },
  remove: { backgroundColor: colors.danger },
});
