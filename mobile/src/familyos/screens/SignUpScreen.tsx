// Create a family: the Log in screen's look, three fields. The person becomes
// the new household's guardian and is signed in (services/apiService.ts signUp).
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, radii } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { copy } from '../mocks/data';
import { useFamilyOS } from '../store/useFamilyOS';
import { API_ENABLED } from '../services/api';
import type { ScreenProps } from '../navigation/types';
import { OnboardingBackdrop } from '../graphics/OnboardingBackdrop';
import { MiniGem } from '../graphics/MiniGem';
import { AppText } from '../components/AppText';
import { Pressy } from '../components/Pressy';
import { ToastHost } from '../components/Toast';
import { Field } from './LoginScreen';

export function SignUpScreen({ navigation, route }: ScreenProps<'SignUp'>) {
  const insets = useSafeAreaInsets();
  const signUp = useFamilyOS((s) => s.signUp);
  const [name, setName] = useState('');
  // From Google: the address it verified (Google's ticket is for exactly this one).
  const [email, setEmail] = useState(route.params?.email ?? '');
  const [family, setFamily] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    const ok = await signUp({ name, email, family, founding: route.params?.founding });
    setBusy(false);
    if (ok) navigation.reset({ index: 0, routes: [{ name: 'Loading' }] });
  };

  return (
    <View style={styles.root}>
      <OnboardingBackdrop />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <ScrollView contentContainerStyle={[styles.body, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled">
          <View style={styles.gem}>
            <MiniGem size={96} />
          </View>
          <AppText style={[T.greeting, styles.center]} accessibilityRole="header">
            {copy.signUp.title}
          </AppText>
          <AppText style={[T.small, styles.center, styles.sub]}>{copy.signUp.subtitle}</AppText>
          <Field label={copy.signUp.name} value={name} onChange={setName} words />
          <Field label={copy.signUp.email} value={email} onChange={setEmail} email />
          <Field label={copy.signUp.family} value={family} onChange={setFamily} words />
          <Pressy onPress={submit} style={[styles.primary, busy && { opacity: 0.6 }]} accessibilityLabel={copy.signUp.submit} disabled={busy}>
            <AppText style={[T.bodyStrong, { color: '#fff' }]}>{busy ? '…' : copy.signUp.submit}</AppText>
          </Pressy>
          <Pressy onPress={() => navigation.goBack()} style={styles.link} accessibilityLabel={copy.signUp.logIn}>
            <AppText style={[T.smallStrong, { color: '#A99FFF' }]}>{copy.signUp.logIn}</AppText>
          </Pressy>
          {API_ENABLED ? <AppText style={[T.small, styles.center, styles.note]}>{copy.signUp.noteServer}</AppText> : null}
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
  primary: { height: 52, marginTop: 8, borderRadius: radii.pill, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  link: { alignSelf: 'center', marginTop: 18, padding: 6 },
  note: { marginTop: 18, fontSize: 12, color: colors.dim },
});
