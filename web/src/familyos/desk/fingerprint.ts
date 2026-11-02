// Errand fingerprint (MASTER_AGENT.md §3.2 Errands 5:50, §7 Phase 5): a short
// hash of exactly the written-down terms. A guardian's approval stores the
// fingerprint it saw; if any term changes, the fingerprint changes and the
// approval no longer applies.
import type { ErrandTerms } from './types';

const SEP = '␟';

/** Canonical text of the terms, in a fixed order (amount to the cent). */
export function termsText(t: ErrandTerms): string {
  return [t.what, t.when, t.where, t.atMost.toFixed(2), t.paidBy, t.card, t.stopsIf].map((s) => s.trim()).join(SEP);
}

/** FNV-1a 32-bit over the terms, shown as two groups of hex: "fp 3a9c·e104". */
export function fingerprint(t: ErrandTerms): string {
  let h = 0x811c9dc5;
  const s = termsText(t);
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  const hex = h.toString(16).padStart(8, '0');
  return `fp ${hex.slice(0, 4)}·${hex.slice(4)}`;
}

/** An approval holds only while the fingerprint it approved is still the errand's. */
export const approvalHolds = (e: ErrandTerms & { approvedFingerprint?: string }) =>
  !!e.approvedFingerprint && e.approvedFingerprint === fingerprint(e);
