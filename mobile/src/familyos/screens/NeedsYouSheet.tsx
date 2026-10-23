// Needs you (AGENT.md §8.4, video 2:05): live count, tinted by the most
// severe item, swipeable cards. Empties → sheet closes, Home goes calm.
import { ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Animated, { FadeOut, LinearTransition } from 'react-native-reanimated';
import { copy } from '../mocks/data';
import { useFamilyOS, useMood } from '../store/useFamilyOS';
import { scenarioThemes } from '../theme/stateThemes';
import { type as T } from '../theme/typography';
import { AppText } from '../components/AppText';
import { ModalCard } from '../components/ModalCard';
import { SwipeCard } from '../components/SwipeCard';

export function NeedsYouSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const needs = useFamilyOS((s) => s.needs);
  const resolve = useFamilyOS((s) => s.resolve);
  const snooze = useFamilyOS((s) => s.snooze);
  const mood = useMood();
  const { width } = useWindowDimensions();
  const header = (
    <View style={styles.header}>
      <AppText style={[T.smallStrong, styles.title]} accessibilityRole="header">
        {copy.needsTitle(needs.length)}
      </AppText>
    </View>
  );
  return (
    <ModalCard visible={visible} onClose={onClose} header={header} tint={scenarioThemes[mood].sheetTint} maxFrac={0.8}>
      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        {needs.map((n) => (
          <Animated.View key={n.id} layout={LinearTransition.duration(280)} exiting={FadeOut.duration(180)}>
            <SwipeCard item={n} onDone={resolve} onLater={snooze} width={width - 32 - 28} />
          </Animated.View>
        ))}
      </ScrollView>
    </ModalCard>
  );
}

const styles = StyleSheet.create({
  header: { paddingTop: 16, paddingBottom: 12, alignItems: 'center' },
  title: { color: '#FFFFFF' },
  body: { paddingHorizontal: 14, paddingBottom: 6 },
});
