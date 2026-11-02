// Phase 3 additions to the one desk store (MASTER_AGENT.md §7 Phase 3,
// FamilyOS.mp4 3:50–4:20 "Handling · open notices", "Schools · add portal").
// Built on desk/storeKit.ts and written into useDesk itself, so there is no
// second copy of anything: export and erase cover these records too.
//
//  • Who handles a notice: the notice's optional `handledBy` ('' means
//    "nobody yet" after someone cleared it). A few open
//    notices start with a handler (SEED_HANDLERS) so the rail is not empty.
//  • A school portal is a read-only page watcher in `watchers`.
// Both are a person's click and append one audit row, like every store action.
import { useDesk } from '../store';
import { auditRow, deskClock, newId, q, updateIn } from '../storeKit';
import type { DeskData, Notice, Watcher } from '../types';
import { MEMBER_IDS } from '../data';
import { API_ENABLED } from '../../services/api';
import { serverAssign, serverPortal } from '../api/server';

/** Who started out handling which open notice (fictional seed, by notice id). */
export const SEED_HANDLERS: Record<string, string> = {
  n_insurance: MEMBER_IDS.michael,
  n_recital: MEMBER_IDS.sarah,
  n_trip: MEMBER_IDS.sarah,
  n_pharmacy: MEMBER_IDS.linda,
};

/** The member handling a notice, or null for "nobody yet". */
export function handlerOf(n: Notice): string | null {
  const h = n.handledBy;
  if (h !== undefined) return h || null;
  return SEED_HANDLERS[n.id] ?? null;
}

const nameIn = (s: Pick<DeskData, 'members'>, id: string) => s.members.find((m) => m.id === id)?.name ?? 'Someone';

/** Ask a member to handle a notice (null = nobody). One audit row. */
export function assignNotice(noticeId: string, memberId: string | null): boolean {
  const s = useDesk.getState();
  const n = s.notices.find((x) => x.id === noticeId);
  if (!n || handlerOf(n) === memberId) return false;
  const who = nameIn(s, s.actor);
  const notices = updateIn(s.notices, noticeId, (x) => ({ ...x, handledBy: memberId ?? '' }));
  const sentence = memberId
    ? memberId === s.actor
      ? `${who} took on ${q(n.title)}`
      : `${who} asked ${nameIn(s, memberId)} to handle ${q(n.title)}`
    : `${who} cleared who handles ${q(n.title)}`;
  useDesk.setState({ notices, audit: [...s.audit, auditRow(s.actor, sentence, 'notice.assigned', { noticeId, to: memberId, from: handlerOf(n) })] });
  if (API_ENABLED) serverAssign(noticeId, memberId);
  return true;
}

/** A link a person can type: https:// is added when missing; null if it is not a web address. */
export function normalizeUrl(input: string): string | null {
  const t = input.trim();
  if (!t || /\s/.test(t)) return null;
  const withScheme = /^https?:\/\//i.test(t) ? t : `https://${t}`;
  try {
    const u = new URL(withScheme);
    return u.hostname.includes('.') ? u.toString() : null;
  } catch {
    return null;
  }
}

/** Add a school's portal as a read-only page watcher. Returns the watcher id, or null if the address is not usable. */
export function addPortal(school: string, address: string): string | null {
  const url = normalizeUrl(address);
  if (!url) return null;
  const s = useDesk.getState();
  const w: Watcher = { id: newId('w'), label: `${school} · portal`, url, spaceId: 'education', since: deskClock.now().toISOString(), status: 'watching' };
  const sentence = `${nameIn(s, s.actor)} added the ${school} portal (${new URL(url).hostname}); FamilyOS only reads it`;
  useDesk.setState({ watchers: [...s.watchers, w], audit: [...s.audit, auditRow(s.actor, sentence, 'watcher.added', { watcherId: w.id, school, url })] });
  if (API_ENABLED) serverPortal(school, url);
  return w.id;
}

/** The pages watched for a school (its portals and calendars). */
export const schoolPages = (watchers: Watcher[], school: string) =>
  watchers.filter((w) => w.status === 'watching' && w.label.toLowerCase().startsWith(school.toLowerCase()));
