// Small centred glass confirmation ("Discard this new member?").
import { useEffect } from 'react';
import { BackHandler, Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeOut, ZoomIn } from 'react-native-reanimated';
import { colors, radii } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import { AppText } from '../../components/AppText';
import { Pressy } from '../../components/Pressy';

export function ConfirmDialog({ title, body, confirm, cancel, destructive = true, onConfirm, onCancel }: {
  title: string; body?: string; confirm: string; cancel: string; destructive?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onCancel();
      return true;
    });
    return () => sub.remove();
  }, [onCancel]);
  return (
    <Animated.View entering={FadeIn.duration(160)} exiting={FadeOut.duration(140)} style={[StyleSheet.absoluteFill, styles.z]}>
      <Pressable style={[StyleSheet.absoluteFill, styles.scrim]} onPress={onCancel} accessibilityLabel={cancel} />
      <View style={styles.center} pointerEvents="box-none">
        <Animated.View entering={ZoomIn.springify().damping(18).stiffness(220).mass(1)} style={styles.card} accessibilityViewIsModal>
          <AppText style={[T.bodyStrong, styles.title]} accessibilityRole="header">
            {title}
          </AppText>
          {body ? <AppText style={[T.small, styles.body]}>{body}</AppText> : null}
          <View style={styles.row}>
            <Pressy onPress={onCancel} style={[styles.btn, styles.cancel]} accessibilityLabel={cancel}>
              <AppText style={T.smallStrong}>{cancel}</AppText>
            </Pressy>
            <Pressy onPress={onConfirm} style={[styles.btn, destructive ? styles.danger : styles.primary]} accessibilityLabel={confirm}>
              <AppText style={[T.smallStrong, { color: destructive ? '#FFFFFF' : colors.pillPrimaryInk }]}>{confirm}</AppText>
            </Pressy>
          </View>
        </Animated.View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  z: { zIndex: 100, elevation: 100 },
  scrim: { backgroundColor: 'rgba(0,0,0,0.6)' },
  center: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 },
  card: { width: '100%', maxWidth: 340, borderRadius: radii.card, backgroundColor: 'rgba(30,33,42,0.98)', borderWidth: 1, borderColor: colors.glassBorder, padding: 20 },
  title: { textAlign: 'center', fontSize: 16 },
  body: { textAlign: 'center', marginTop: 6 },
  row: { flexDirection: 'row', marginTop: 18 },
  btn: { flex: 1, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  cancel: { backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder, marginRight: 10 },
  danger: { backgroundColor: colors.danger },
  primary: { backgroundColor: colors.pillPrimaryBg },
});
