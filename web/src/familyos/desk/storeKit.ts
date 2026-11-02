// Shared plumbing for the desk store slices: the clock, the append-only audit
// writer, revision records and immutable list updates.
import type { AuditEntry, DeskData, RecordType, Revision } from './types';

/** The store's clock (tests pin it; the app uses the real time). */
export const deskClock = { now: () => new Date() };

let seq = 0;
/** Unique, time-ordered ids for records the store creates. */
export const newId = (prefix: string) => `${prefix}_${deskClock.now().getTime().toString(36)}${(++seq).toString(36)}`;

export type Patch = Partial<DeskData>;

/** One audit row. Rows are only ever appended (MASTER §3.2 6:20, §11). */
export function auditRow(actor: string, sentence: string, code: string, raw?: Record<string, unknown>): AuditEntry {
  return { id: newId('au'), at: deskClock.now().toISOString(), actor, sentence, code, raw };
}

export function revisionRow(
  actor: string,
  recordType: RecordType,
  recordId: string,
  recordLabel: string,
  field: string,
  before: Revision['before'],
  after: Revision['after'],
  revertible = true
): Revision {
  return { id: newId('rv'), at: deskClock.now().toISOString(), actor, recordType, recordId, recordLabel, field, before, after, revertible };
}

/** Replace the item with `id` in a list (no-op when missing). */
export function updateIn<T extends { id: string }>(list: T[], id: string, fn: (x: T) => T): T[] {
  return list.map((x) => (x.id === id ? fn(x) : x));
}

/** Quote a record title in an audit sentence. */
export const q = (s: string) => `“${s}”`;
