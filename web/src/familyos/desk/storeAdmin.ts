// Desk store, second slice: notices and quarantine, plans, revisions,
// household settings and connections, Download everything and Erase
// everything (MASTER_AGENT.md §7 Phases 3–5). Same rules as store.ts: every
// action appends one audit row; the audit has no edit or delete.
import type { DeskData, Notice } from './types';
import type { DeskActions, DeskExport, DeskGet, DeskSet } from './store';
import { auditRow, deskClock, newId, q, revisionRow, updateIn } from './storeKit';

type AdminActions = Pick<
  DeskActions,
  | 'addNotice' | 'flagNotice' | 'openOriginal' | 'releaseQuarantine' | 'deleteQuarantine' | 'setPlanStatus' | 'markBooked' | 'revertRevision'
  | 'setSetting' | 'setToggle' | 'connectMailbox' | 'disconnectMailbox' | 'newPhoneToken' | 'revokeToken' | 'stopWatcher' | 'withdrawConsent'
  | 'signOutEverywhere' | 'openSitting' | 'exportAll' | 'eraseConfirmPhrase' | 'eraseAll'
>;

/** The data keys (everything exportAll writes). */
const DATA_KEYS: (keyof DeskData)[] = [
  'settings', 'members', 'children', 'spaces', 'notices', 'quarantine', 'proposals', 'agenda', 'todos', 'conflicts', 'errands', 'plans',
  'recurring', 'statements', 'orderAgain', 'revisions', 'audit', 'mailboxes', 'phoneTokens', 'watchers', 'toggles', 'consents', 'telegram', 'sittings', 'weather',
];

export function adminActions(set: DeskSet, get: DeskGet): AdminActions {
  const name = (id: string) => (id === 'FamilyOS' ? 'FamilyOS' : (get().members.find((m) => m.id === id)?.name ?? 'Someone'));
  const who = () => name(get().actor);
  const log = (sentence: string, code: string, raw?: Record<string, unknown>, extra: Partial<DeskData> = {}) =>
    set((s) => ({ ...extra, audit: [...s.audit, auditRow(s.actor, sentence, code, raw)] }));
  const now = () => deskClock.now().toISOString();
  const notice = (id: string) => get().notices.find((n) => n.id === id);

  return {
    addNotice({ title, body, source = 'paste', sender, spaceId, attachments }) {
      const n: Notice = { id: newId('n'), source, sender: sender ?? `${who()} (${source === 'paste' ? 'pasted' : source})`, receivedAt: now(), title, summary: body.slice(0, 120), body, category: 'family', spaceId, attachments };
      log(`${who()} added ${q(title)}`, 'notice.received', { noticeId: n.id, via: source }, { notices: [...get().notices, n] });
      return n.id;
    },

    flagNotice(noticeId, note) {
      const n = notice(noticeId);
      if (!n) return;
      const notices = updateIn(get().notices, noticeId, (x) => ({ ...x, flags: [...(x.flags ?? []), { at: now(), by: get().actor, note }] }));
      log(`${who()} said ${q(n.title)} was not read right`, 'notice.flagged', { noticeId, note }, { notices });
    },

    openOriginal(noticeId) {
      const n = notice(noticeId);
      if (n) log(`${who()} opened the original of ${q(n.title)}`, 'artifact.original_read', { noticeId });
    },

    releaseQuarantine(id) {
      const item = get().quarantine.find((x) => x.id === id);
      const n = item && notice(item.noticeId);
      if (!item || !n) return;
      const notices = updateIn(get().notices, n.id, (x) => ({ ...x, quarantined: false }));
      log(`${who()} released ${q(n.title)} from Quarantine`, 'quarantine.released', { noticeId: n.id, sender: n.senderAddress ?? n.sender }, { notices, quarantine: get().quarantine.filter((x) => x.id !== id) });
    },

    deleteQuarantine(id) {
      const item = get().quarantine.find((x) => x.id === id);
      const n = item && notice(item.noticeId);
      if (!item || !n) return;
      log(`${who()} deleted ${q(n.title)} from Quarantine`, 'quarantine.deleted', { noticeId: n.id }, {
        notices: get().notices.filter((x) => x.id !== n.id),
        quarantine: get().quarantine.filter((x) => x.id !== id),
      });
    },

    setPlanStatus(planId, status) {
      const p = get().plans.find((x) => x.id === planId);
      if (!p || p.status === status) return;
      const rv = revisionRow(get().actor, 'plan', planId, p.title, 'status', p.status, status);
      const verb = status === 'done' ? 'marked done' : status === 'dropped' ? 'dropped' : 'reopened';
      log(`${who()} ${verb} the plan ${q(p.title)}`, 'plan.status', { planId, from: p.status, to: status }, {
        plans: updateIn(get().plans, planId, (x) => ({ ...x, status })),
        revisions: [...get().revisions, rv],
      });
    },

    markBooked(planId, bookingId, booked) {
      const p = get().plans.find((x) => x.id === planId);
      const b = p?.bookings.find((x) => x.id === bookingId);
      if (!p || !b || b.booked === booked) return;
      const plans = updateIn(get().plans, planId, (x) => ({ ...x, bookings: updateIn(x.bookings, bookingId, (y) => ({ ...y, booked })) }));
      log(`${who()} marked ${q(b.option)} as ${booked ? 'booked' : 'not booked'}`, 'plan.booking_marked', { planId, bookingId, booked }, { plans });
    },

    revertRevision(id) {
      const s = get();
      const r = s.revisions.find((x) => x.id === id);
      if (!r || !r.revertible || r.revertedAt) return false;
      const key = ({ agenda: 'agenda', todo: 'todos', plan: 'plans', member: 'members', errand: 'errands' } as const)[r.recordType];
      const list = s[key] as { id: string }[];
      if (!list.some((x) => x.id === r.recordId)) return false;
      const patched = updateIn(list, r.recordId, (x) => ({ ...x, [r.field]: r.before }));
      const back = { ...revisionRow(s.actor, r.recordType, r.recordId, r.recordLabel, r.field, r.after, r.before, false), revertOf: r.id };
      const revisions = [...updateIn(s.revisions, id, (x) => ({ ...x, revertedAt: now() })), back];
      log(`${who()} reverted ${r.field} on ${q(r.recordLabel)}`, 'revision.reverted', { revisionId: id, recordType: r.recordType, recordId: r.recordId, field: r.field }, { [key]: patched, revisions } as Partial<DeskData>);
      return true;
    },

    setSetting(key, value) {
      const before = get().settings[key];
      if (before === value) return;
      log(`${who()} changed ${key} from ${before} to ${value}`, 'setting.changed', { key, from: before, to: value }, { settings: { ...get().settings, [key]: value } });
    },

    setToggle(id, on) {
      const t = get().toggles.find((x) => x.id === id);
      if (!t || t.on === on) return;
      log(`${who()} turned ${on ? 'on' : 'off'} ${q(t.label)}`, 'setting.toggled', { toggle: id, on }, { toggles: updateIn(get().toggles, id, (x) => ({ ...x, on })) });
    },

    connectMailbox(address) {
      const mb = { id: newId('mb'), address, ownerId: get().actor, connectedAt: now(), status: 'connected' as const };
      log(`${who()} connected the mailbox ${address}`, 'mailbox.connected', { mailboxId: mb.id }, { mailboxes: [...get().mailboxes, mb] });
    },

    disconnectMailbox(id) {
      const mb = get().mailboxes.find((x) => x.id === id);
      if (!mb || mb.status === 'disconnected') return;
      log(`${who()} disconnected the mailbox ${mb.address}`, 'mailbox.disconnected', { mailboxId: id }, { mailboxes: updateIn(get().mailboxes, id, (x) => ({ ...x, status: 'disconnected' as const })) });
    },

    newPhoneToken(device) {
      const t = { id: newId('tk'), device, ownerId: get().actor, createdAt: now() };
      log(`${who()} made a phone token for ${device}`, 'phone_token.created', { tokenId: t.id }, { phoneTokens: [...get().phoneTokens, t] });
      return t.id;
    },

    revokeToken(id) {
      const t = get().phoneTokens.find((x) => x.id === id);
      if (!t || t.revokedAt) return;
      log(`${who()} revoked the phone token for ${t.device}`, 'phone_token.revoked', { tokenId: id }, { phoneTokens: updateIn(get().phoneTokens, id, (x) => ({ ...x, revokedAt: now() })) });
    },

    stopWatcher(id) {
      const w = get().watchers.find((x) => x.id === id);
      if (!w || w.status === 'stopped') return;
      log(`${who()} stopped watching ${q(w.label)}`, 'watcher.stopped', { watcherId: id }, { watchers: updateIn(get().watchers, id, (x) => ({ ...x, status: 'stopped' as const })) });
    },

    withdrawConsent(childId) {
      const c = get().consents.find((x) => x.childId === childId);
      if (!c || c.withdrawnAt) return;
      const consents = get().consents.map((x) => (x.childId === childId ? { ...x, withdrawnAt: now() } : x));
      log(`${who()} withdrew consent for ${name(childId)}; an erasure of ${name(childId)}’s notices starts`, 'consent.withdrawn', { childId }, { consents });
    },

    signOutEverywhere(memberId) {
      log(`${who()} signed ${name(memberId)} out everywhere`, 'member.signed_out_everywhere', { memberId });
    },

    openSitting({ purpose, site, minutes }) {
      const st = { id: newId('st'), purpose, site, minutes, openedAt: now(), openedBy: get().actor };
      log(`${who()} opened a ${minutes}-minute sitting on ${site}`, 'sitting.opened', { sittingId: st.id, site }, { sittings: [...get().sittings, st] });
      return st.id;
    },

    exportAll() {
      log(`${who()} downloaded everything`, 'export.downloaded');
      const s = get();
      const data = Object.fromEntries(DATA_KEYS.map((k) => [k, s[k]])) as unknown as DeskData;
      const payload: DeskExport = { format: 'familyos.desk.v1', exportedAt: now(), household: s.settings.name, data };
      if (typeof document !== 'undefined' && typeof URL !== 'undefined' && 'createObjectURL' in URL) {
        const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
        const a = document.createElement('a');
        a.href = url;
        a.download = `familyos-${s.settings.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${payload.exportedAt.slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      return payload;
    },

    eraseConfirmPhrase() {
      return `erase ${get().settings.name}`;
    },

    eraseAll(typed) {
      const s = get();
      if (typed !== s.eraseConfirmPhrase()) return false;
      // The only purge of the audit log: everything goes, then the erasure itself is recorded.
      set({
        notices: [], quarantine: [], proposals: [], agenda: [], todos: [], conflicts: [], errands: [], plans: [], recurring: [], statements: [],
        orderAgain: [], revisions: [], mailboxes: [], phoneTokens: [], watchers: [], sittings: [], consents: [],
        telegram: { ...s.telegram, devices: [] },
        audit: [auditRow(s.actor, `${who()} erased the household’s data`, 'household.erased')],
      });
      return true;
    },
  };
}
