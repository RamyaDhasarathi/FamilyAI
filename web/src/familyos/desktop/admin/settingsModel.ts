// Settings → Household and Collect helpers (MASTER_AGENT.md §3.2 Settings
// 0:35–1:20 and 7:30–9:30, Collect 6:10, §11 "Erase everything requires typed
// confirmation"; frames f_009–f_017, f_075, f_091–f_115). Pure: the erase
// gate, which toggle sits in which section, and the small validators.
import type { ToggleId } from '../../desk/types';

/** Anchors the avatar menu links to on desktop (HomeOrbit / ProfileMenu: #permissions, #notifications, #privacy). */
export const SECTIONS = [
  ['members', 'Members'],
  ['consent', 'Consent'],
  ['notifications', 'Notifications'],
  ['permissions', 'Agents and permissions'],
  ['place', 'Where we live'],
  ['mailboxes', 'Mailboxes'],
  ['telegram', 'Telegram'],
  ['phone', 'From your phone'],
  ['watching', 'Watching'],
  ['privacy', 'Privacy and data'],
] as const;
export type SectionId = (typeof SECTIONS)[number][0];

/** Who hears what, and when. */
export const NOTIFY_TOGGLES: ToggleId[] = ['childrenNotices', 'weeklyDigest', 'billReminders'];
/** What FamilyOS (and its agents) may do on its own. */
export const PERMISSION_TOGGLES: ToggleId[] = ['calendarSync', 'localModel', 'picturesByModel', 'holidaysAutoAccept', 'receiptsSettleBills'];

/**
 * Erase everything is enabled only when the typed text is exactly the
 * store's phrase (`eraseConfirmPhrase()`, e.g. "erase The Carters"). Case
 * matters; only spaces around it are forgiven.
 */
export const eraseReady = (typed: string, phrase: string) => !!phrase && typed.trim() === phrase;

export const validEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s.trim());

/** "https://portal.example/login" → "portal.example"; null when it isn't a site. */
export function siteHost(s: string): string | null {
  const t = s.trim().replace(/^[a-z]+:\/\//i, '').split(/[/?#]/)[0].toLowerCase();
  return /^(?=.{4,253}$)([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?$/.test(t) ? t : null;
}

/** "How long you need" (Collect from a site). */
export const SITTING_LENGTHS: { minutes: number; label: string }[] = [
  { minutes: 15, label: 'a quarter of an hour' },
  { minutes: 30, label: 'half an hour' },
  { minutes: 60, label: 'an hour' },
  { minutes: 90, label: 'an hour and a half' },
  { minutes: 120, label: 'two hours' },
];

/** Currencies the household formatter knows (desk/format.ts LOCALES). */
export const CURRENCIES: { code: string; label: string }[] = [
  { code: 'USD', label: 'US dollar ($)' },
  { code: 'CAD', label: 'Canadian dollar (CA$)' },
  { code: 'GBP', label: 'Pound sterling (£)' },
  { code: 'EUR', label: 'Euro (€)' },
  { code: 'AUD', label: 'Australian dollar (A$)' },
  { code: 'INR', label: 'Indian rupee (₹)' },
];

/** A few household timezones, plus whatever the household uses now. */
export function timezoneOptions(current: string): string[] {
  const common = ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Anchorage', 'Pacific/Honolulu', 'Europe/London', 'Asia/Kolkata', 'UTC'];
  return common.includes(current) ? common : [current, ...common];
}

/** A phone token or Telegram link code, grouped for reading aloud: "fos-7k2m-q9xd-4tpa". */
export function readableCode(seed: string, prefix = 'fos'): string {
  const s = seed.toLowerCase().replace(/[^a-z0-9]/g, '').padEnd(12, '0').slice(0, 12);
  return [prefix, s.slice(0, 4), s.slice(4, 8), s.slice(8, 12)].join('-');
}
