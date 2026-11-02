// FamilyOS collecting layer on Android: the native reads (android/…/FamilyosCollectModule.kt). On iPhone, or in a
// build without the module, every read is empty: iOS gives an app no SMS, call log or other apps' notifications.
import { Platform } from 'react-native';
import { requireOptionalNativeModule } from 'expo';

export interface InstalledApp {
  package: string;
  label: string;
}
/** Every field the collector app read (SmsReader.kt); one-time codes included. */
export interface Sms {
  id: string;
  sender: string;
  body: string;
  date: number;
  threadId: string;
  dateSent: number;
  type: number;
  read: number;
  seen: number;
  subject: string | null;
  serviceCenter: string | null;
  person: string | null;
  protocol: number;
}
export interface Call {
  number: string;
  type: 'incoming' | 'outgoing' | 'missed' | 'other';
  date: number;
  duration: number;
}
export interface Fix {
  lat: number;
  lng: number;
  accuracy: number;
  time: number;
}
export interface Photo {
  id: string;
  name: string;
  size: number;
  mimeType: string;
  date: number;
}
export interface PhoneNotification {
  package: string;
  title: string;
  text: string;
  postTime: number;
}

/** What the phone agent sees (FamilyosAgentService.kt): sent to the backend as it is, for the next action. */
export interface Screen {
  currentApp: string;
  tree: Record<string, unknown>[];
  screenshot: string;
  width: number;
  height: number;
}
/** One action from the backend (familyos/collect/phone_agent.py valid_action). */
export type AgentAction = { action: string } & Record<string, unknown>;

interface Native {
  listApps(): Promise<InstalledApp[]>;
  readSms(sinceMs: number, limit: number): Promise<Sms[]>;
  readCallLog(sinceMs: number, limit: number): Promise<Call[]>;
  lastLocation(): Promise<Fix | null>;
  recentPhotos(sinceSeconds: number, limit: number): Promise<Photo[]>;
  notificationAccess(): boolean;
  openNotificationAccessSettings(): void;
  drainNotifications(): PhoneNotification[];
  agentAccess(): boolean;
  openAccessibilitySettings(): void;
  observe(): Promise<Screen>;
  act(action: AgentAction): Promise<boolean>;
  settle(ms: number): Promise<void>;
  bringToFront(): void;
  setSession(baseUrl: string, token: string): void;
  clearSession(): void;
  startLiveSms(): void;
  stopLiveSms(): void;
  liveSmsRunning(): boolean;
}

const native = Platform.OS === 'android' ? requireOptionalNativeModule<Native>('FamilyosCollect') : null;

/** True where the phone can collect at all (Android with this module built in). */
export const canCollect = !!native;

export const listApps = () => native?.listApps() ?? Promise.resolve([]);
export const readSms = (sinceMs: number, limit = 500) => native?.readSms(sinceMs, limit) ?? Promise.resolve([]);
export const readCallLog = (sinceMs: number, limit = 500) => native?.readCallLog(sinceMs, limit) ?? Promise.resolve([]);
export const lastLocation = () => native?.lastLocation() ?? Promise.resolve(null);
export const recentPhotos = (sinceSeconds: number, limit = 500) => native?.recentPhotos(sinceSeconds, limit) ?? Promise.resolve([]);
export const notificationAccess = () => native?.notificationAccess() ?? false;
export const openNotificationAccessSettings = () => native?.openNotificationAccessSettings();
export const drainNotifications = () => native?.drainNotifications() ?? [];

// The phone agent's eyes and hands; the loop is services/phoneAgent.ts.
export const agentAccess = () => native?.agentAccess() ?? false;
export const openAccessibilitySettings = () => native?.openAccessibilitySettings();
export const observe = (): Promise<Screen> => native?.observe() ?? Promise.reject(new Error('This phone cannot run the phone agent.'));
export const act = (action: AgentAction) => native?.act(action) ?? Promise.resolve(false);
export const settle = (ms: number) => native?.settle(ms) ?? new Promise<void>((r) => setTimeout(r, ms));
export const bringToFront = () => native?.bringToFront();

// Live SMS (CollectSmsService.kt): new SMS sent within seconds, by the phone itself, while SMS is switched on.
export const setSession = (baseUrl: string, token: string) => native?.setSession(baseUrl, token);
export const clearSession = () => native?.clearSession();
export const startLiveSms = () => native?.startLiveSms();
export const stopLiveSms = () => native?.stopLiveSms();
export const liveSmsRunning = () => native?.liveSmsRunning() ?? false;
