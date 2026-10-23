// Shell for secondary screens (Settings, Family, placeholders): black with
// a faint top glow, glass back button, title, scrolling body.
import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { ChevronLeft } from 'lucide-react-native';
import { colors } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';
import { Pressy } from './Pressy';
import { ToastHost } from './Toast';

export function ScreenShell({ title, onBack, children, glow = 'rgba(128,115,255,0.16)' }: { title: string; onBack: () => void; children: ReactNode; glow?: string }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.root}>
      <LinearGradient colors={[glow, 'rgba(0,0,0,0)']} style={styles.glow} pointerEvents="none" />
      <View style={[styles.bar, { paddingTop: insets.top + 8 }]}>
        <Pressy onPress={onBack} style={styles.back} accessibilityLabel="Back">
          <ChevronLeft size={20} color={colors.ink} />
        </Pressy>
        <AppText style={[T.sheetTitle, styles.title]} accessibilityRole="header">
          {title}
        </AppText>
      </View>
      <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 32 }]} showsVerticalScrollIndicator={false}>
        {children}
      </ScrollView>
      <ToastHost bottom={insets.bottom + 24} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  glow: { position: 'absolute', left: 0, right: 0, top: 0, height: 320 },
  bar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 10 },
  back: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { marginLeft: 14 },
  body: { paddingHorizontal: 16, paddingTop: 12 },
});
