import React, { useEffect } from 'react';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useAuthStore } from '../src/state/authStore';

function RootNavigation() {
  const { isAuthenticated, isLoading, loadStoredAuth } = useAuthStore();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    loadStoredAuth();
  }, []);

  useEffect(() => {
    if (isLoading) return;

    const currentScreen = segments[0] || '';
    const isAuthScreen = currentScreen === 'login';

    if (!isAuthenticated && !isAuthScreen) {
      router.replace('/login');
    } else if (isAuthenticated && isAuthScreen) {
      router.replace('/purchase');
    }
  }, [isAuthenticated, isLoading, segments]);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="login" />
      <Stack.Screen name="purchase" />
      <Stack.Screen name="travel" />
      <Stack.Screen name="governance" />
      <Stack.Screen name="task/[taskId]" />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <RootNavigation />
    </SafeAreaProvider>
  );
}
