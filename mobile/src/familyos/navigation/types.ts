import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { AgentId } from '../theme/tokens';

export type RootStackParamList = {
  Loading: undefined;
  Login: undefined;
  Home: undefined;
  /** `via: 'reveal'` = arrived through the satellite's expanding circle (fade in). */
  Agent: { agent: AgentId; via?: 'reveal' };
  Settings: undefined;
  Family: undefined;
  Placeholder: { title: string };
};

export type ScreenProps<K extends keyof RootStackParamList> = NativeStackScreenProps<RootStackParamList, K>;
