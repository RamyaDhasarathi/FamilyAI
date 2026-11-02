// The phone's part of the collecting layer (famos-notes/COLLECTION_PLAN.md). Each source the person switched on is
// read since its own mark (modules/familyos-collect) and sent to our backend (/v1/collect/device/…), which keeps it in
// its local cache. A mark moves only after the backend said yes, so nothing is lost while it is unreachable (the user's
// own collector app works the same way). First read: SMS 5 days, calls 48 hours, photos 7 days, as there.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { PermissionsAndroid, Platform, type Permission } from 'react-native';
import * as Native from '../../../modules/familyos-collect';
import { API_BASE, loadToken, request } from './api';

export type SourceId = 'sms' | 'calls' | 'notifications' | 'locations' | 'files';

export interface AppSwitch {
  package: string;
  label: string;
  collect: boolean;
}

export interface CollectSettings {
  sources: Record<SourceId, boolean>;
  apps: Record<string, boolean>;
  lastRun?: string;
}

const KEY = 'familyos.collect.v1';
const MARK = (s: SourceId) => `familyos.collect.mark.${s}`;
const BACKFILL_MS: Partial<Record<SourceId, number>> = { sms: 5 * 864e5, calls: 2 * 864e5, files: 7 * 864e5 };

export const canCollect = Native.canCollect;

const OFF: CollectSettings = { sources: { sms: false, calls: false, notifications: false, locations: false, files: false }, apps: {} };

export async function loadSettings(): Promise<CollectSettings> {
  const raw = await AsyncStorage.getItem(KEY).catch(() => null);
  const s = raw ? (JSON.parse(raw) as CollectSettings) : OFF;
  return { ...OFF, ...s, sources: { ...OFF.sources, ...s.sources } };
}

export async function saveSettings(s: CollectSettings): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(s));
}

/** What Android must allow for a source; asked the moment the person switches it on. */
const PERMISSIONS: Partial<Record<SourceId, Permission[]>> = {
  sms: [PermissionsAndroid.PERMISSIONS.READ_SMS],
  calls: [PermissionsAndroid.PERMISSIONS.READ_CALL_LOG],
  locations: [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION, PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION],
  files: [Number(Platform.Version) >= 33 ? PermissionsAndroid.PERMISSIONS.READ_MEDIA_IMAGES : PermissionsAndroid.PERMISSIONS.READ_EXTERNAL_STORAGE],
};

/** Ask Android for a source's permission; true when it may be read. Notifications are allowed in Settings instead. */
export async function allow(source: SourceId): Promise<boolean> {
  if (source === 'notifications') {
    if (Native.notificationAccess()) return true;
    Native.openNotificationAccessSettings();
    return false;
  }
  const wanted = PERMISSIONS[source] ?? [];
  // Live SMS shows a notification while it runs; Android 13+ asks before an app may show one (it runs either way).
  const extra = source === 'sms' && Number(Platform.Version) >= 33 ? [PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS] : [];
  const got = await PermissionsAndroid.requestMultiple([...wanted, ...extra]);
  return wanted.some((p) => got[p] === PermissionsAndroid.RESULTS.GRANTED);
}

/** Live SMS on while SMS is switched on and someone is signed in, off otherwise (CollectSmsService). */
export async function syncLiveSms(s: CollectSettings): Promise<void> {
  if (!Native.canCollect) return;
  const t = await loadToken();
  if (s.sources.sms && t && API_BASE) {
    Native.setSession(API_BASE, t);
    Native.startLiveSms();
  } else Native.stopLiveSms();
}

export const liveSmsRunning = () => Native.liveSmsRunning();

export const notificationAccess = () => Native.notificationAccess();

/** The installed apps with this person's switch for each, newest list from the phone. */
export async function appsWithSwitches(s: CollectSettings): Promise<AppSwitch[]> {
  const apps = await Native.listApps();
  return apps.map((a) => ({ ...a, collect: !!s.apps[a.package] }));
}

/** Send the app list and its switches (the backend keeps notifications only from switched-on apps). */
export async function sendApps(apps: AppSwitch[]): Promise<void> {
  await request('PUT', '/collect/device/apps', { apps });
}

async function mark(source: SourceId, fallbackMs: number): Promise<number> {
  const v = Number(await AsyncStorage.getItem(MARK(source)).catch(() => null));
  return v > 0 ? v : fallbackMs;
}

async function send(kind: SourceId, items: object[]): Promise<number> {
  if (!items.length) return 0;
  const r = await request<{ kept: number }>('POST', `/collect/device/${kind}`, { items });
  return r.kept;
}

export interface RunResult {
  kept: Partial<Record<SourceId, number>>;
  failed: Partial<Record<SourceId, string>>;
}

/** Read every switched-on source since its mark and send it; one failing source never stops the others. */
export async function collectNow(s: CollectSettings): Promise<RunResult> {
  const out: RunResult = { kept: {}, failed: {} };
  if (!Native.canCollect) return out;
  const now = Date.now();
  const step = async (source: SourceId, run: () => Promise<{ items: object[]; next: number | null }>) => {
    if (!s.sources[source]) return;
    try {
      const { items, next } = await run();
      out.kept[source] = await send(source, items);
      if (next) await AsyncStorage.setItem(MARK(source), String(next));
    } catch (e) {
      out.failed[source] = e instanceof Error ? e.message : String(e);
    }
  };
  await step('sms', async () => {
    const items = await Native.readSms(await mark('sms', now - BACKFILL_MS.sms!));
    return { items, next: items.length ? Math.max(...items.map((x) => x.date)) : null };
  });
  await step('calls', async () => {
    const items = await Native.readCallLog(await mark('calls', now - BACKFILL_MS.calls!));
    return { items, next: items.length ? Math.max(...items.map((x) => x.date)) : null };
  });
  await step('files', async () => {
    const sinceSeconds = (await mark('files', now - BACKFILL_MS.files!)) / 1000;
    const items = await Native.recentPhotos(sinceSeconds);
    return { items, next: items.length ? Math.max(...items.map((x) => x.date)) * 1000 : null };
  });
  await step('locations', async () => {
    const fix = await Native.lastLocation();
    return { items: fix ? [fix] : [], next: null };
  });
  await step('notifications', async () => ({ items: Native.drainNotifications(), next: null }));
  await saveSettings({ ...s, lastRun: new Date().toISOString() });
  return out;
}
