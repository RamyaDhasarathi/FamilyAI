// How the member form's fields meet our backend's columns (MIGRATION_PLAN.md §7, Phase 3). Pure functions, the same
// file in the mobile app and the web app, used by services/apiFamilyService.ts. What has a column goes there; what has
// none stays on the device (famos-notes/GAPS.md §2a).
//
//   Health  → blood group, allergies  members.blood_group, members.allergies  PUT /members/{id}/medical   (guardian)
//   Health  → emergency contact       emergency_profile.contacts[]           PUT /emergency/profile     (guardian)
//             one list for the household; a member's entry is the one whose relation reads "Emergency contact for <name>"
//   Basic   → relationship            members.circle_role                    PUT /members/{id}/circle-role (guardian; adults)
//   Banking → approval limit / "ask an adult above"  members.payment_limit   PUT /members/{id}/payment-limit (guardian)
//   Contact → (the owner's) address   read only from the household's home place: writing a typed address over it would
//             drop the map point the weather and travel times use.
//   Health  → current medicines       read only, from prescriptions (GET /emergency/card): there is no way to type one in.
import type { Relationship } from '../services/interfaces';
import { digits, formatters, phonePrefix } from './region';

// ── Relationship ↔ circle role ──────────────────────────────────────────────

export type CircleRole = 'parent' | 'sibling' | 'spouse' | 'caregiver' | 'other';

/** The backend's five words for who someone is in the circle. Never "caregiver": that one also narrows what they see. */
export function circleFor(rel: Relationship | undefined): CircleRole | null {
  if (!rel) return null;
  if (rel === 'Spouse' || rel === 'Partner') return 'spouse';
  if (rel === 'Mother' || rel === 'Father' || rel === 'Grandmother' || rel === 'Grandfather') return 'parent';
  if (rel === 'Brother' || rel === 'Sister') return 'sibling';
  return 'other';
}

/** What the form shows for a role set on the server, when this device has no word of its own for the person. */
export function relationshipFrom(role: string | null | undefined): { relationship: Relationship; relationshipOther?: string } | null {
  if (role === 'spouse') return { relationship: 'Spouse' };
  if (role === 'parent') return { relationship: 'Other', relationshipOther: 'Parent' };
  if (role === 'sibling') return { relationship: 'Other', relationshipOther: 'Sibling' };
  if (role === 'caregiver') return { relationship: 'Other', relationshipOther: 'Caregiver' };
  return null;
}

// ── Blood group ─────────────────────────────────────────────────────────────

/** The form writes "A−" (a true minus) and "Not sure"; the backend keeps up to five characters, "A-" or nothing. */
export const bloodToServer = (v: unknown): string | null => {
  const s = String(v ?? '').trim();
  if (!s || s === 'Not sure') return null;
  return s.replace(/−/g, '-').toUpperCase();
};

export const bloodFromServer = (v: string | null | undefined): string | undefined => (v ? v.replace(/-/g, '−') : undefined);

// ── Emergency contact ───────────────────────────────────────────────────────

export interface EmergencyContact {
  name: string;
  relation: string;
  phone: string;
}

/** The relation text that marks a member's own entry on the household's emergency card. */
export const emergencyTag = (memberName: string) => `Emergency contact for ${memberName.trim()}`;

/** The household's list with this member's entry replaced (or taken out when `entry` is null); others are kept. */
export function contactsWith(list: EmergencyContact[], memberName: string, entry: { name: string; mobile: string } | null): EmergencyContact[] {
  const tag = emergencyTag(memberName);
  const others = list.filter((c) => c.relation !== tag);
  if (!entry || !entry.name.trim()) return others;
  const phone = digits(entry.mobile) ? `${phonePrefix} ${formatters.phone(entry.mobile)}` : '';
  return [{ name: entry.name.trim(), relation: tag, phone }, ...others];
}

/** This member's entry, as the form's two fields. */
export function contactFor(list: EmergencyContact[], memberName: string): { emergencyName: string; emergencyMobile: string } | null {
  const c = list.find((x) => x.relation === emergencyTag(memberName));
  if (!c) return null;
  const local = c.phone.startsWith(phonePrefix) ? c.phone.slice(phonePrefix.length) : c.phone;
  return { emergencyName: c.name, emergencyMobile: formatters.phone(local) };
}

// ── Money and medicines ─────────────────────────────────────────────────────

/** "1,500.50" → 1500.5; empty → null (the backend's "no personal limit"). */
export function moneyToNumber(v: unknown): number | null {
  const s = String(v ?? '').replace(/[^\d.]/g, '');
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** The emergency card's "Amoxicillin 250 mg, 3 a day" lines as the form's medicine rows (read only). */
export const medicineRows = (lines: string[]) => lines.map((l) => ({ name: l, dose: '', when: '' }));

// ── What the form tells people about where a section is kept ───────────────

/** The note on a sensitive section when the app is on our backend: what goes to the family's account, what stays here. */
export function storageNote(section: string, here: 'this device' | 'this browser'): string {
  if (section === 'health') return `Blood group, allergies and the emergency contact are saved to your family’s account when a guardian saves them; the rest stays only on ${here}.`;
  if (section === 'banking') return `The approval limit is saved to your family’s account when a guardian saves it; bank and card details stay only on ${here}.`;
  return `These details stay only on ${here}: your family’s account has no place for them yet.`;
}
