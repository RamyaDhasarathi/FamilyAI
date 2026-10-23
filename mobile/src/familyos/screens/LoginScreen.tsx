// Log in, restyled (AGENT.md §8.8, design.md §13.3): frosted inputs, violet
// primary button, the existing app's "Continue with Google". Any credentials
// work while the backend is mocked.
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Check, Eye, EyeOff } from 'lucide-react-native';
import { colors, radii } from '../theme/tokens';
import { fonts, MAX_FONT_SCALE, type as T } from '../theme/typography';
import { copy } from '../mocks/data';
import { useFamilyOS } from '../store/useFamilyOS';
import type { ScreenProps } from '../navigation/types';
import { OnboardingBackdrop } from '../graphics/OnboardingBackdrop';
import { MiniGem } from '../graphics/MiniGem';
import { AppText } from '../components/AppText';
import { Pressy } from '../components/Pressy';
import { ToastHost } from '../components/Toast';

function Field({ label, value, onChange, secure, toggle, shown }: { label: string; value: string; onChange: (s: string) => void; secure?: boolean; toggle?: () => void; shown?: boolean }) {
  return (
    <View style={styles.field}>
      <AppText style={[T.statLabel, styles.fieldLabel]}>{label}</AppText>
      <View style={styles.inputBox}>
        <TextInput
          value={value}
          onChangeText={onChange}
          secureTextEntry={secure && !shown}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.input}
          placeholderTextColor={colors.dim}
          selectionColor={colors.violet}
          maxFontSizeMultiplier={MAX_FONT_SCALE}
          accessibilityLabel={label}
        />
        {toggle ? (
          <Pressy onPress={toggle} accessibilityLabel={shown ? 'Hide password' : 'Show password'} style={styles.eye}>
            {shown ? <EyeOff size={18} color={colors.muted} /> : <Eye size={18} color={colors.muted} />}
          </Pressy>
        ) : null}
      </View>
    </View>
  );
}

export function LoginScreen({ navigation }: ScreenProps<'Login'>) {
  const insets = useSafeAreaInsets();
  const logIn = useFamilyOS((s) => s.logIn);
  const toast = useFamilyOS((s) => s.toast);
  const [email, setEmail] = useState('michael@example.com');
  const [password, setPassword] = useState('');
  const [shown, setShown] = useState(false);
  const [keep, setKeep] = useState(true);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    const ok = await logIn(email, password);
    setBusy(false);
    if (ok) navigation.reset({ index: 0, routes: [{ name: 'Loading' }] });
  };

  return (
    <View style={styles.root}>
      <OnboardingBackdrop />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <ScrollView contentContainerStyle={[styles.body, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled">
          <View style={styles.gem}>
            <MiniGem size={120} />
          </View>
          <AppText style={[T.greeting, styles.center]} accessibilityRole="header">
            {copy.login.title}
          </AppText>
          <AppText style={[T.small, styles.center, styles.sub]}>{copy.login.subtitle}</AppText>
          <Field label={copy.login.email} value={email} onChange={setEmail} />
          <Field label={copy.login.password} value={password} onChange={setPassword} secure toggle={() => setShown((s) => !s)} shown={shown} />
          <View style={styles.row}>
            <Pressy onPress={() => setKeep((k) => !k)} style={styles.keep} accessibilityRole="checkbox" accessibilityState={{ checked: keep }} accessibilityLabel={copy.login.keep}>
              <View style={[styles.box, keep && styles.boxOn]}>{keep ? <Check size={12} color="#fff" strokeWidth={3} /> : null}</View>
              <AppText style={[T.small, { color: colors.ink }]}>{copy.login.keep}</AppText>
            </Pressy>
            <Pressy onPress={() => toast(copy.login.forgotToast)} accessibilityLabel={copy.login.forgot}>
              <AppText style={[T.smallStrong, { color: '#A99FFF' }]}>{copy.login.forgot}</AppText>
            </Pressy>
          </View>
          <Pressy onPress={submit} style={[styles.primary, busy && { opacity: 0.6 }]} accessibilityLabel={copy.login.submit} disabled={busy}>
            <AppText style={[T.bodyStrong, { color: '#fff' }]}>{busy ? '…' : copy.login.submit}</AppText>
          </Pressy>
          <Pressy onPress={submit} style={styles.secondary} accessibilityLabel="Continue with Google">
            <AppText style={T.bodyStrong}>Continue with Google</AppText>
          </Pressy>
          <Pressy onPress={() => toast(copy.login.otpToast)} style={styles.link} accessibilityLabel={copy.login.otp}>
            <AppText style={[T.smallStrong, { color: '#A99FFF' }]}>{copy.login.otp}</AppText>
          </Pressy>
          <AppText style={[T.small, styles.center, styles.note]}>{copy.login.note}</AppText>
        </ScrollView>
      </KeyboardAvoidingView>
      <ToastHost bottom={insets.bottom + 24} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  body: { paddingHorizontal: 24 },
  gem: { alignItems: 'center', marginBottom: 8 },
  center: { textAlign: 'center' },
  sub: { marginTop: 6, marginBottom: 26 },
  field: { marginBottom: 14 },
  fieldLabel: { marginBottom: 6, marginLeft: 4 },
  inputBox: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    paddingHorizontal: 16,
  },
  input: { flex: 1, color: colors.ink, fontFamily: fonts.medium, fontSize: 15, paddingVertical: 0 },
  eye: { padding: 6 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4, marginBottom: 22 },
  keep: { flexDirection: 'row', alignItems: 'center' },
  box: { width: 20, height: 20, borderRadius: 6, borderWidth: 1, borderColor: colors.glassBorder, marginRight: 8, alignItems: 'center', justifyContent: 'center' },
  boxOn: { backgroundColor: colors.violet, borderColor: colors.violet },
  primary: { height: 52, borderRadius: radii.pill, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  secondary: {
    height: 52,
    borderRadius: radii.pill,
    marginTop: 12,
    backgroundColor: colors.pillSecondaryBg,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  link: { alignSelf: 'center', marginTop: 18, padding: 6 },
  note: { marginTop: 18, fontSize: 12, color: colors.dim },
});
