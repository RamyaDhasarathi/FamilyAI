// Glass toast pill above the bottom bar; auto-hides after 2.2 s (AGENT.md §8.1.8).
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInDown, FadeOutDown } from 'react-native-reanimated';
import { useFamilyOS, type Toast } from '../store/useFamilyOS';
import { durations } from '../theme/motion';
import { colors } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';

function ToastPill({ toast }: { toast: Toast }) {
  const dismiss = useFamilyOS((s) => s.dismissToast);
  useEffect(() => {
    const id = setTimeout(() => dismiss(toast.id), durations.toast);
    return () => clearTimeout(id);
  }, [toast.id, dismiss]);
  return (
    <Animated.View entering={FadeInDown.duration(220)} exiting={FadeOutDown.duration(200)} style={styles.pill}>
      <AppText style={[T.smallStrong, styles.text]} accessibilityLiveRegion="polite">
        {toast.text}
      </AppText>
    </Animated.View>
  );
}

export function ToastHost({ bottom }: { bottom: number }) {
  const toasts = useFamilyOS((s) => s.toasts);
  const last = toasts[toasts.length - 1];
  return (
    <View pointerEvents="none" style={[styles.host, { bottom }]}>
      {last ? <ToastPill key={last.id} toast={last} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  host: { position: 'absolute', left: 16, right: 16, alignItems: 'center', zIndex: 50 },
  pill: {
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: 999,
    backgroundColor: 'rgba(30,33,42,0.94)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  text: { color: colors.ink, textAlign: 'center', fontSize: 12 },
});
