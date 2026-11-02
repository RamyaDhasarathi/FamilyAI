// Errand helpers for the Errands pages (MASTER_AGENT.md §3.2 Errands
// 5:50–6:10, §7 Phase 5, §11 "Errand approval voids if any written-down
// field changes"; FamilyOS.mp4 frames f_069–f_074). Pure functions: the
// edit form keeps a Draft of strings, `parseDraft` turns it into terms, and
// `draftEffect` says — live, before anything is saved — which terms change,
// the new fingerprint, and whether a guardian's approval would stop applying.
import type { Errand, ErrandStatus, ErrandTerms } from '../../desk/types';
import { approvalHolds, fingerprint } from '../../desk/fingerprint';

export type TermKey = keyof ErrandTerms;
export type Draft = Record<TermKey, string>;

/** "What was written down", in the reference's order. */
export const TERM_ROWS: { key: TermKey; label: string; placeholder: string }[] = [
  { key: 'what', label: 'What', placeholder: 'Exactly what is booked or bought' },
  { key: 'when', label: 'When', placeholder: 'A date, or a deadline' },
  { key: 'where', label: 'Where', placeholder: 'The site, and who is signed in' },
  { key: 'atMost', label: 'At most', placeholder: '48.00' },
  { key: 'paidBy', label: 'Paid', placeholder: 'How it is paid' },
  { key: 'card', label: 'Card', placeholder: 'Visa ending 4417 (last four digits only)' },
  { key: 'stopsIf', label: 'Stops if', placeholder: 'When it must stop and ask' },
];

export const TERM_LABEL = Object.fromEntries(TERM_ROWS.map((r) => [r.key, r.label])) as Record<TermKey, string>;

/** Worst first: what needs a guardian, then what will run, then history. */
export const STATUS_ORDER: ErrandStatus[] = ['proposed', 'approved', 'done', 'cancelled'];

export function sortErrands(list: Errand[]): Errand[] {
  return [...list].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || b.createdAt.localeCompare(a.createdAt));
}

/** "homesupply.example, signed in as Michael" → "homesupply.example". */
export const siteOf = (where: string) => where.split(',')[0].trim();

const amountText = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

export const toDraft = (t: ErrandTerms): Draft => ({
  what: t.what, when: t.when, where: t.where, atMost: amountText(t.atMost), paidBy: t.paidBy, card: t.card, stopsIf: t.stopsIf,
});

/** "$48", "48.50", "1,200" → 48 / 48.5 / 1200; null when it is not an amount. */
export function parseAmount(s: string): number | null {
  const clean = s.replace(/[^\d.,]/g, '').replace(/,/g, '');
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Number(clean);
}

/**
 * Only the last four digits of a card are ever kept: "4111 1111 1111 4417"
 * → "Card ending 4417", "Mastercard 5555…1111" → "Mastercard ending 1111".
 * Text with no digits ("none — FamilyOS holds no card") stays as written;
 * one to three digits is not enough to say which card (null).
 */
export function safeCard(s: string): string | null {
  const text = s.trim();
  const digits = text.replace(/\D/g, '');
  if (!digits) return text;
  if (digits.length < 4) return null;
  const lead = text.split(/\d/)[0].replace(/\b(ending|ends|in|card|number|no)\b\.?/gi, ' ').replace(/[^A-Za-z ]/g, ' ').trim().replace(/\s+/g, ' ');
  return `${lead || 'Card'} ending ${digits.slice(-4)}`;
}

export type DraftErrors = Partial<Record<TermKey, string>>;

/** The draft as terms (trimmed, card reduced to its last four), or the reasons it can't be saved. */
export function parseDraft(d: Draft): { terms: ErrandTerms | null; errors: DraftErrors } {
  const errors: DraftErrors = {};
  for (const k of ['what', 'when', 'where', 'paidBy', 'stopsIf'] as const) if (!d[k].trim()) errors[k] = 'Write this down; it cannot be left open.';
  const atMost = parseAmount(d.atMost);
  if (atMost === null) errors.atMost = 'An amount, like 48 or 48.50.';
  const card = safeCard(d.card);
  if (card === null) errors.card = 'The last four digits, or “none”.';
  else if (!card) errors.card = 'Write this down; it cannot be left open.';
  if (Object.keys(errors).length) return { terms: null, errors };
  return {
    terms: { what: d.what.trim(), when: d.when.trim(), where: d.where.trim(), atMost: atMost!, paidBy: d.paidBy.trim(), card: card!, stopsIf: d.stopsIf.trim() },
    errors,
  };
}

/** Terms that differ (amounts to the cent, text ignoring outer spaces). */
export function changedTerms(a: ErrandTerms, b: ErrandTerms): TermKey[] {
  return TERM_ROWS.map((r) => r.key).filter((k) => (k === 'atMost' ? a.atMost.toFixed(2) !== b.atMost.toFixed(2) : String(a[k]).trim() !== String(b[k]).trim()));
}

/** Only the changed terms, for `editErrand`. */
export function patchOf(e: ErrandTerms, t: ErrandTerms): Partial<ErrandTerms> {
  return Object.fromEntries(changedTerms(e, t).map((k) => [k, t[k]])) as Partial<ErrandTerms>;
}

export interface DraftEffect {
  changed: TermKey[];
  fingerprint: string;
  /** Saving would void a guardian's approval that holds today. */
  voids: boolean;
}

/** What saving these terms would do, shown live while the form is open. */
export function draftEffect(e: Errand, terms: ErrandTerms): DraftEffect {
  const changed = changedTerms(e, terms);
  const fp = changed.length ? fingerprint(terms) : e.fingerprint;
  return { changed, fingerprint: fp, voids: e.status === 'approved' && approvalHolds(e) && fp !== e.approvedFingerprint };
}

export const canEdit = (e: Errand) => e.status === 'proposed' || e.status === 'approved';
export const canCancel = canEdit;
/** Only a guardian approves, and only an errand that is waiting. */
export const canApprove = (e: Errand, role?: string) => e.status === 'proposed' && role === 'guardian';
