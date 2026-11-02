// Family-member derived values and section metadata (AGENT_CORE_AND_FAMILY.md
// §4.2, §4.7, §4.10; design.md §13.5–§13.6). Nothing here is stored: age,
// stage, completion and "needs update" counts are always computed.
import type { FamilyMember, Relationship, SectionId, SectionStatus } from '../services/interfaces';
import { avatarForAge, stageAccent, type AvatarStage } from '../graphics/avatars';

export const SECTION_IDS: SectionId[] = ['basic', 'contact', 'ids', 'health', 'banking'];

/** Relationships offered when adding someone ("Self" is the owner only). */
export const RELATIONSHIPS: Relationship[] = [
  'Spouse', 'Partner', 'Son', 'Daughter', 'Father', 'Mother', 'Brother', 'Sister',
  'Grandfather', 'Grandmother', 'Grandson', 'Granddaughter', 'Uncle', 'Aunt',
  'Nephew', 'Niece', 'Cousin', 'In-law', 'Other',
];

export type AgeGroup = 'child' | 'teen' | 'adult';

export interface SectionMeta {
  id: SectionId;
  title: string;
  /** Short label for amber "needs update" tags. */
  tag: string;
  color: string;
  /** Which agents use it, and why (shown at the top of the wizard step). */
  why: string;
  sensitive: boolean;
}

const SECTIONS: Record<SectionId, SectionMeta> = {
  basic: {
    id: 'basic',
    title: 'Basic information',
    tag: 'Basic info',
    color: '#61B8FF',
    why: 'Every agent uses this to know who is who, and to plan around ages and schedules.',
    sensitive: false,
  },
  contact: {
    id: 'contact',
    title: 'Contact and address',
    tag: 'Contact',
    color: '#6BF294',
    why: 'Used by Household and Calendar to coordinate visits, deliveries and reminders.',
    sensitive: false,
  },
  ids: {
    id: 'ids',
    title: 'Government ID and documents',
    tag: 'IDs & documents',
    color: '#BD9EFF',
    why: 'Used by Finance and Education for school forms, travel and official paperwork.',
    sensitive: true,
  },
  health: {
    id: 'health',
    title: 'Health',
    tag: 'Health',
    color: '#FF6B9A',
    why: 'Used by your agents to plan appointments and remind you about medicines.',
    sensitive: true,
  },
  banking: {
    id: 'banking',
    title: 'Banking and payments',
    tag: 'Banking',
    color: '#1FC7B8',
    why: 'Used by Finance and Grocery to pay bills and approve purchases within your limits.',
    sensitive: true,
  },
};

/** Section metadata, with the child/teen variant of banking (§13.6). */
export function sectionMeta(id: SectionId, group: AgeGroup): SectionMeta {
  if (id === 'banking' && group !== 'adult') {
    return {
      ...SECTIONS.banking,
      title: 'Allowance and payments',
      tag: 'Allowance',
      why: 'Used by Finance to manage pocket money and approve spending.',
    };
  }
  return SECTIONS[id];
}

export const REVIEW_COLOR = '#FFFFFF';

/** Whole years between an ISO date of birth and `now`. */
export function ageOf(dateOfBirth: string, now = new Date()): number {
  const [y, m, d] = dateOfBirth.split('-').map(Number);
  if (!y || !m || !d) return 0;
  let age = now.getFullYear() - y;
  if (now.getMonth() + 1 < m || (now.getMonth() + 1 === m && now.getDate() < d)) age -= 1;
  return Math.max(0, age);
}

/** Age for meta lines: babies read "Under 1" rather than "0". */
export function ageText(age: number): string {
  return age < 1 ? 'Under 1' : String(age);
}

/** "Under 1 year" / "1 year" / "N years". */
export function yearsText(age: number): string {
  return age < 1 ? 'Under 1 year' : age === 1 ? '1 year' : `${age} years`;
}

export function ageGroupOf(age: number): AgeGroup {
  if (age < 13) return 'child';
  if (age < 18) return 'teen';
  return 'adult';
}

export function stageOf(member: Pick<FamilyMember, 'dateOfBirth'>): AvatarStage & { accent: string } {
  const st = avatarForAge(ageOf(member.dateOfBirth));
  return { ...st, accent: stageAccent[st.stage] };
}

/** Relationship as shown ("Son", or the custom text for "Other"; "You" for the owner). */
export function relationshipLabel(m: Pick<FamilyMember, 'relationship' | 'relationshipOther' | 'isOwner'>): string {
  if (m.isOwner) return 'You';
  if (m.relationship === 'Other') return m.relationshipOther?.trim() || 'Other';
  return m.relationship;
}

export function displayName(m: Pick<FamilyMember, 'fullName' | 'preferredName'>): string {
  return m.preferredName?.trim() || m.fullName.trim().split(/\s+/)[0] || m.fullName;
}

export function completionOf(m: FamilyMember): number {
  return SECTION_IDS.filter((s) => m.sections[s].status === 'complete').length / SECTION_IDS.length;
}

export function completeCount(m: FamilyMember): number {
  return SECTION_IDS.filter((s) => m.sections[s].status === 'complete').length;
}

export function sectionsNeedingUpdate(m: FamilyMember): SectionId[] {
  return SECTION_IDS.filter((s) => m.sections[s].status === 'needsUpdate');
}

export function sectionsNotStarted(m: FamilyMember): SectionId[] {
  return SECTION_IDS.filter((s) => m.sections[s].status === 'notStarted');
}

/** Short card / summary wording for the sections still to do. */
export function todoText(needs: number, notStarted: number): string | null {
  if (needs) return `${needs} ${needs === 1 ? 'section' : 'sections'} to update`;
  if (notStarted) return `${notStarted} ${notStarted === 1 ? 'section' : 'sections'} not started`;
  return null;
}

export function emptySections(status: SectionStatus = 'notStarted'): FamilyMember['sections'] {
  return {
    basic: { status, data: {} },
    contact: { status, data: {} },
    ids: { status, data: {} },
    health: { status, data: {} },
    banking: { status, data: {} },
  };
}

/** Owner first, then oldest to youngest (§4.4). */
export function sortMembers(list: FamilyMember[]): FamilyMember[] {
  return [...list].sort((a, b) => {
    if (a.isOwner !== b.isOwner) return a.isOwner ? -1 : 1;
    return a.dateOfBirth.localeCompare(b.dateOfBirth);
  });
}

/** Adults who can pay a child's allowance. */
export function adultsOf(list: FamilyMember[]): FamilyMember[] {
  return list.filter((m) => ageOf(m.dateOfBirth) >= 18);
}

/** Children whose allowance is paid from `adultId`. */
export function dependentsOf(list: FamilyMember[], adultId: string): FamilyMember[] {
  return list.filter((m) => m.id !== adultId && ageOf(m.dateOfBirth) < 18 && m.sections.banking.data.paidFrom === adultId);
}

/** ISO date for a Date in local time. */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function dateFromIso(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
