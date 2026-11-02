// Profile-menu destinations that have no real screen yet (AGENT.md §8.5).
import { StyleSheet, View } from 'react-native';
import { copy } from '../mocks/data';
import { colors, radii } from '../theme/tokens';
import { type as T } from '../theme/typography';
import type { ScreenProps } from '../navigation/types';
import { MiniGem } from '../graphics/MiniGem';
import { AppText } from '../components/AppText';
import { ScreenShell } from '../components/ScreenShell';

export function PlaceholderScreen({ navigation, route }: ScreenProps<'Placeholder'>) {
  const { title } = route.params;
  return (
    <ScreenShell title={title} onBack={() => navigation.goBack()}>
      <View style={styles.card}>
        <MiniGem size={120} />
        <AppText style={[T.small, styles.text]}>{copy.placeholder(title)}</AppText>
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: 'center',
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    padding: 24,
    marginTop: 20,
  },
  text: { textAlign: 'center', marginTop: 12 },
});
