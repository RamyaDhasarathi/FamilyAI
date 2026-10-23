// Mobile-only navigator. Native stack → iOS edge-swipe back and Android
// hardware back for free (AGENT.md §8.7, §11.1).
import { DarkTheme, NavigationContainer, type Theme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { colors } from '../theme/tokens';
import type { RootStackParamList } from './types';
import { LoadingScreen } from '../screens/LoadingScreen';
import { LoginScreen } from '../screens/LoginScreen';
import { HomeOrbitScreen } from '../screens/HomeOrbitScreen';
import { AgentDetailScreen } from '../screens/AgentDetailScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { FamilyScreen } from '../screens/FamilyScreen';
import { PlaceholderScreen } from '../screens/PlaceholderScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();

const theme: Theme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.bg, card: colors.bg, text: colors.ink, border: colors.glassBorder, primary: colors.violet },
};

export function FamilyOSNavigator() {
  return (
    <NavigationContainer theme={theme}>
      <Stack.Navigator
        initialRouteName="Loading"
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.bg },
          animation: 'slide_from_right',
          gestureEnabled: true,
          fullScreenGestureEnabled: true,
        }}
      >
        <Stack.Screen name="Loading" component={LoadingScreen} options={{ animation: 'fade', gestureEnabled: false }} />
        <Stack.Screen name="Login" component={LoginScreen} options={{ animation: 'fade' }} />
        <Stack.Screen name="Home" component={HomeOrbitScreen} options={{ animation: 'fade', gestureEnabled: false }} />
        <Stack.Screen
          name="Agent"
          component={AgentDetailScreen}
          options={({ route }) => ({ animation: route.params.via === 'reveal' ? 'fade' : 'slide_from_right' })}
        />
        <Stack.Screen name="Settings" component={SettingsScreen} />
        <Stack.Screen name="Family" component={FamilyScreen} />
        <Stack.Screen name="Placeholder" component={PlaceholderScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
