// Family members (AGENT.md §8.5): each member with the avatar stage for their
// age (design.md §6), from the design pack's animated renders.
import { StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { copy } from '../mocks/data';
import { colors, radii } from '../theme/tokens';
import { durations } from '../theme/motion';
import { type as T } from '../theme/typography';
import { useFamilyOS } from '../store/useFamilyOS';
import type { ScreenProps } from '../navigation/types';
import { avatarForAge } from '../graphics/avatars';
import { AppText } from '../components/AppText';
import { SectionLabel } from '../components/Labels';
import { ScreenShell } from '../components/ScreenShell';

export function FamilyScreen({ navigation }: ScreenProps<'Family'>) {
  const family = useFamilyOS((s) => s.family);
  const lowPower = useFamilyOS((s) => s.lowPower);
  return (
    <ScreenShell title={copy.family.title} onBack={() => navigation.goBack()} glow="rgba(31,199,184,0.14)">
      <SectionLabel>{copy.family.section}</SectionLabel>
      {family.map((m, i) => {
        const stage = avatarForAge(m.age);
        return (
          <Animated.View key={m.id} entering={FadeInDown.delay(i * durations.stagger * 2).duration(320)} style={styles.card}>
            <Image
              source={lowPower ? stage.png : stage.gif}
              style={styles.avatar}
              contentFit="cover"
              accessibilityLabel={`${m.name}'s avatar, ${stage.name}`}
            />
            <View style={styles.text}>
              <AppText style={T.bodyStrong}>{m.name}</AppText>
              <AppText style={[T.small, styles.line]}>{copy.family.age(m.relationship, m.age)}</AppText>
              <AppText style={[T.small, styles.stage]}>{copy.family.stage(stage.stage, stage.name)}</AppText>
            </View>
          </Animated.View>
        );
      })}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    padding: 12,
    marginBottom: 10,
  },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: '#000' },
  text: { flex: 1, marginLeft: 14 },
  line: { marginTop: 2 },
  stage: { marginTop: 2, fontSize: 12, color: colors.dim },
});
