// Audit view helpers (MASTER_AGENT.md §3.2 Audit 6:20–7:20, §3.3.6, §11
// "Audit has no edit/delete"; frames f_077–f_088). Read-only views over the
// append-only rows: the raw line under a row ("member.signed_in via
// "google"", "calendar.synced kept 17 dropped 0"), newest-first day groups,
// and the actor / kind / text filters. Nothing here writes to the store.
import type { AuditEntry, Day } from '../../desk/types';
import { dayKey } from '../../desk/format';

const snake = (k: string) => k.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();

function rawValue(v: unknown): string {
  if (typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'number' || typeof v === 'boolean' || v === null) return String(v);
  if (v === undefined) return 'none';
  return JSON.stringify(v);
}

/** The raw row as the reference prints it: the event code, then `key value` pairs. */
export function rawLine(e: Pick<AuditEntry, 'code' | 'raw'>): string {
  const pairs = Object.entries(e.raw ?? {}).map(([k, v]) => `${snake(k)} ${rawValue(v)}`);
  return [e.code, ...pairs].join(' ');
}

/** Kinds, by the first part of the event code. */
const KIND_OF_PREFIX: Record<string, string> = {
  proposal: 'Proposals', conflict: 'Proposals',
  notice: 'Notices', artifact: 'Notices', quarantine: 'Quarantine',
  errand: 'Errands', sitting: 'Errands',
  calendar: 'Calendar', reminder: 'Calendar', todo: 'To-dos', plan: 'Plans', revision: 'Revisions',
  member: 'People', consent: 'People',
  setting: 'Settings', mailbox: 'Connections', phone_token: 'Connections', watcher: 'Connections', telegram: 'Connections',
  export: 'Export and erase', household: 'Export and erase',
};

export function kindOf(code: string): string {
  const prefix = code.split('.')[0];
  return KIND_OF_PREFIX[prefix] ?? prefix.charAt(0).toUpperCase() + prefix.slice(1).replace(/_/g, ' ');
}

export interface AuditFilter {
  /** A member id, 'FamilyOS', or 'all'. */
  actor: string;
  /** A kind label from `kindOf`, or 'all'. */
  kind: string;
  /** Free text, matched against the sentence and the raw line. */
  text: string;
}

export const NO_FILTER: AuditFilter = { actor: 'all', kind: 'all', text: '' };

/** The rows that pass every filter (a new array; the log itself is never touched). */
export function filterAudit(rows: readonly AuditEntry[], f: AuditFilter): AuditEntry[] {
  const q = f.text.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (f.actor === 'all' || r.actor === f.actor) &&
      (f.kind === 'all' || kindOf(r.code) === f.kind) &&
      (!q || r.sentence.toLowerCase().includes(q) || rawLine(r).toLowerCase().includes(q))
  );
}

export const isFiltered = (f: AuditFilter) => f.actor !== 'all' || f.kind !== 'all' || !!f.text.trim();

/** Newest first, grouped by household day. Rows at the same instant keep log order (the later one first). */
export function groupByDay(rows: readonly AuditEntry[], tz: string): { day: Day; rows: AuditEntry[] }[] {
  const order = new Map(rows.map((r, i) => [r.id, i]));
  const sorted = [...rows].sort((a, b) => b.at.localeCompare(a.at) || order.get(b.id)! - order.get(a.id)!);
  const groups: { day: Day; rows: AuditEntry[] }[] = [];
  for (const r of sorted) {
    const day = dayKey(r.at, tz);
    const last = groups[groups.length - 1];
    if (last?.day === day) last.rows.push(r);
    else groups.push({ day, rows: [r] });
  }
  return groups;
}

/** Actors in the log, people first (most rows first), FamilyOS last. */
export function actorOptions(rows: readonly AuditEntry[]): string[] {
  const n = new Map<string, number>();
  for (const r of rows) n.set(r.actor, (n.get(r.actor) ?? 0) + 1);
  return [...n.keys()].sort((a, b) => Number(a === 'FamilyOS') - Number(b === 'FamilyOS') || n.get(b)! - n.get(a)!);
}

/** Kinds present in the log, alphabetically. */
export const kindOptions = (rows: readonly AuditEntry[]) => [...new Set(rows.map((r) => kindOf(r.code)))].sort();
