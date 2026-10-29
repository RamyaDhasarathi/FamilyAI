import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { AgentId } from '../theme/tokens';
import type { SectionId } from '../services/interfaces';

export type RootStackParamList = {
  Loading: undefined;
  Login: undefined;
  Home: undefined;
  /** `via: 'reveal'` = arrived through the satellite's expanding circle (fade in). */
  Agent: { agent: AgentId; via?: 'reveal' };
  Settings: undefined;
  /** openAdd: open the Add sheet at once. remove: animate a removal confirmed on a profile. */
  Family: { openAdd?: boolean; remove?: { id: string; reassign?: string | null } } | undefined;
  MemberProfile: { id: string };
  MemberWizard: { id: string; section?: SectionId | 'review' };
  Placeholder: { title: string };
};

export type ScreenProps<K extends keyof RootStackParamList> = NativeStackScreenProps<RootStackParamList, K>;
