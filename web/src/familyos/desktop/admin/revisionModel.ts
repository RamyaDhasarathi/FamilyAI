// Revisions view helpers (MASTER_AGENT.md §7 Phase 5 "Revisions: history of
// edits to records (who, what changed, when, Revert where allowed)"; the
// reference links Revisions from Audit, FamilyOS.mp4 ≈7:15, frame f_084).
// Values are shown in the household's own terms: amounts in its currency,
// dates and times in its timezone.
import type { AgendaItem, Revision, Todo } from '../../desk/types';
import { dayKey, fmtShortDay, fmtText, fmtTime, isDay } from '../../desk/format';

export const RECORD_LABEL: Record<Revision['recordType'], string> = { agenda: 'calendar', todo: 'to-do', plan: 'plan', member: 'person', errand: 'errand' };

const FIELD_LABEL: Record<string, string> = {
  when: 'time', due: 'due date', atMost: 'at most', paidBy: 'paid', stopsIf: 'stops if', statusLine: 'status line', estCost: 'estimated cost',
};
export const fieldLabel = (f: string) => FIELD_LABEL[f] ?? f.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();

const MONEY_FIELDS = new Set(['budget', 'atMost', 'amount', 'estCost', 'price']);
const INSTANT = /^\d{4}-\d{2}-\d{2}T/;

/** One side of a change, as a person would say it: "$2,800", "Oct 25", "Oct 30, 11 am", "nothing". */
export function fmtValue(field: string, v: Revision['before'], ctx: { currency: string; tz: string; money: (n: number) => string }): string {
  if (v === null || v === undefined || v === '') return 'nothing';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'number') return MONEY_FIELDS.has(field) ? ctx.money(v) : String(v);
  if (isDay(v)) return fmtShortDay(v);
  if (INSTANT.test(v) && !Number.isNaN(Date.parse(v))) return `${fmtShortDay(dayKey(v, ctx.tz))}, ${fmtTime(v, ctx.tz, true)}`;
  return fmtText(v, ctx.currency);
}

/** Newest first. */
export const sortRevisions = (list: readonly Revision[]) => [...list].sort((a, b) => b.at.localeCompare(a.at));

export const canRevert = (r: Revision) => r.revertible && !r.revertedAt;

/** Why a row has no Revert, in one honest line. */
export function whyNoRevert(r: Revision): string | null {
  if (canRevert(r)) return null;
  if (r.revertedAt) return null;
  if (r.revertOf) return 'This is itself a revert.';
  if (r.recordType === 'errand') return 'Errand terms change on the errand itself, where any change voids the approval.';
  if (r.actor === 'FamilyOS') return 'This followed the notice it was read from; it changes when the notice does.';
  return 'This change cannot be reverted here.';
}

/** Where the record lives, so every row points to its source. */
export function recordHref(r: Revision, d: { agenda: readonly AgendaItem[]; todos: readonly Todo[] }): string | undefined {
  switch (r.recordType) {
    case 'errand':
      return `/errands/${r.recordId}`;
    case 'plan':
      return `/plans/${r.recordId}`;
    case 'member':
      return `/family/${r.recordId}`;
    case 'agenda': {
      const a = d.agenda.find((x) => x.id === r.recordId);
      return a ? `/agents/${a.agent}` : undefined;
    }
    case 'todo': {
      const t = d.todos.find((x) => x.id === r.recordId);
      if (!t) return undefined;
      return t.planId ? `/plans/${t.planId}` : '/waiting';
    }
  }
}
