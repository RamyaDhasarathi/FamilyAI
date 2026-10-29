import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { bootstrapApi } from '../src/api/auth';
import { ErrorBanner } from '../src/components/ErrorBanner';
import { useAuthStore } from '../src/state/authStore';
import { ApiError } from '../src/types';

export default function LoginScreen() {
  const router = useRouter();
  const { login } = useAuthStore();

  const [email, setEmail] = useState('admin@familyos.local');
  const [password, setPassword] = useState('AdminPass123!');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | string | null>(null);

  // Bootstrap modal state
  const [showBootstrap, setShowBootstrap] = useState(false);
  const [bootstrapToken, setBootstrapToken] = useState('REPLACE_WITH_ONE_TIME_BOOTSTRAP_TOKEN');
  const [familyDisplayName, setFamilyDisplayName] = useState('Family Admin');
  const [familyName, setFamilyName] = useState('My Family');
  const [bootstrapSuccess, setBootstrapSuccess] = useState<string | null>(null);

  const handleLogin = async () => {
    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.replace('/purchase');
    } catch (err: unknown) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  };

  const handleBootstrap = async () => {
    setLoading(true);
    setError(null);
    setBootstrapSuccess(null);
    try {
      await bootstrapApi({
        bootstrap_token: bootstrapToken,
        email: email.trim(),
        password,
        display_name: familyDisplayName,
        family_name: familyName,
      });
      setBootstrapSuccess('Family & Administrator created successfully! Now signing in...');
      // Auto-login
      await login(email.trim(), password);
      router.replace('/purchase');
    } catch (err: unknown) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  };

  const apiBase = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://10.0.2.2:8000';

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Brand */}
        <View style={styles.brandContainer}>
          <Text style={styles.logoIcon}>🛡️</Text>
          <Text style={styles.brandTitle}>FAMILY OS</Text>
          <Text style={styles.brandSubtitle}>Private, Governance-First Family AI</Text>
        </View>

        {/* Backend Info Pill */}
        <View style={styles.backendPill}>
          <Text style={styles.backendText}>Connected to: {apiBase}</Text>
        </View>

        {/* Form Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>
            {showBootstrap ? 'Initialize Family OS' : 'Sign In'}
          </Text>

          <ErrorBanner error={error} onDismiss={() => setError(null)} />

          {bootstrapSuccess ? (
            <View style={styles.successBanner}>
              <Text style={styles.successText}>{bootstrapSuccess}</Text>
            </View>
          ) : null}

          {showBootstrap ? (
            <>
              <Text style={styles.inputLabel}>Family Name</Text>
              <TextInput
                style={styles.input}
                value={familyName}
                onChangeText={setFamilyName}
                placeholder="e.g. The Smiths"
                autoCapitalize="words"
              />

              <Text style={styles.inputLabel}>Admin Display Name</Text>
              <TextInput
                style={styles.input}
                value={familyDisplayName}
                onChangeText={setFamilyDisplayName}
                placeholder="e.g. John Doe"
                autoCapitalize="words"
              />

              <Text style={styles.inputLabel}>Bootstrap Token</Text>
              <TextInput
                style={styles.input}
                value={bootstrapToken}
                onChangeText={setBootstrapToken}
                placeholder="BOOTSTRAP_TOKEN from .env"
                autoCapitalize="none"
              />
            </>
          ) : null}

          <Text style={styles.inputLabel}>Email Address</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            placeholder="admin@familyos.local"
          />

          <Text style={styles.inputLabel}>Password</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="Enter password"
          />

          {/* Primary Action Button */}
          <TouchableOpacity
            style={[styles.primaryButton, loading && styles.buttonDisabled]}
            onPress={showBootstrap ? handleBootstrap : handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#ffffff" />
            ) : (
              <Text style={styles.primaryButtonText}>
                {showBootstrap ? 'Initialize & Sign In' : 'Sign In'}
              </Text>
            )}
          </TouchableOpacity>

          {/* Mode Switcher */}
          <TouchableOpacity
            style={styles.switchButton}
            onPress={() => {
              setShowBootstrap(!showBootstrap);
              setError(null);
            }}
          >
            <Text style={styles.switchButtonText}>
              {showBootstrap
                ? '← Already initialized? Sign In'
                : 'First-time setup? Initialize Family & Admin'}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a2e',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
  },
  brandContainer: {
    alignItems: 'center',
    marginBottom: 20,
  },
  logoIcon: {
    fontSize: 44,
    marginBottom: 8,
  },
  brandTitle: {
    color: '#ffffff',
    fontSize: 26,
    fontWeight: 'bold',
    letterSpacing: 3,
  },
  brandSubtitle: {
    color: '#a0a0b8',
    fontSize: 13,
    marginTop: 4,
  },
  backendPill: {
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    paddingVertical: 5,
    paddingHorizontal: 12,
    borderRadius: 16,
    alignSelf: 'center',
    marginBottom: 20,
  },
  backendText: {
    color: '#cbd5e1',
    fontSize: 11,
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 8,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#475569',
    marginTop: 10,
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  input: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: '#0f172a',
    backgroundColor: '#f8fafc',
  },
  primaryButton: {
    backgroundColor: '#3b82f6',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 20,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  switchButton: {
    marginTop: 16,
    alignItems: 'center',
  },
  switchButtonText: {
    color: '#3b82f6',
    fontSize: 13,
    fontWeight: '500',
  },
  successBanner: {
    backgroundColor: '#d1fae5',
    borderColor: '#10b981',
    borderWidth: 1,
    borderRadius: 6,
    padding: 10,
    marginBottom: 12,
  },
  successText: {
    color: '#065f46',
    fontSize: 13,
  },
});
