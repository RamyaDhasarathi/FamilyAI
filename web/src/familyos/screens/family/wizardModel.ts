// Pure helpers for the details wizard (mobile MemberWizardScreen.tsx / WizardFields.tsx).
import type { SectionId } from '../../services/interfaces';
import { SECTION_IDS, dateFromIso } from '../../family/model';
import { isEmpty } from '../../family/fields';

export type Step = SectionId | 'review';
export const STEPS: Step[] = [...SECTION_IDS, 'review'];

/** Age from a draft date of birth, if the basic step is changing it. */
export function draftAge(iso: unknown, fallback: number) {
  if (typeof iso !== 'string' || !iso) return fallback;
  const d = dateFromIso(iso);
  const now = new Date();
  let a = now.getFullYear() - d.getFullYear();
  if (now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())) a -= 1;
  return Math.max(0, a);
}

/** Two drafts hold the same values (empty values count as equal). */
export const sameDraft = (a: Record<string, unknown>, b: Record<string, unknown>) =>
  [...new Set([...Object.keys(a), ...Object.keys(b)])].every((k) => (isEmpty(a[k]) && isEmpty(b[k])) || JSON.stringify(a[k]) === JSON.stringify(b[k]));
