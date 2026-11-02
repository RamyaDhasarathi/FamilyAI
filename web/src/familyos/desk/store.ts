// The one desk store (MASTER_AGENT.md §9 "one store, no parallel copies").
// It starts from buildDeskData() dated around the moment the app loads, and
// lives in memory for the visit (refresh = a fresh demo household).
//
// Rules every action follows:
//  • Nothing changes without a person's click: actions are called from a
//    Confirm / Accept / ✕ / toggle, never from an effect.
//  • Every mutation appends one AuditEntry (actor = `actor`, the signed-in
//    member). The audit list has no edit or delete action; only a household
//    erasure purges it (eraseAll), and that erasure is itself recorded.
//  • Accept moves a proposal to its agent: calendar / reminder → an agenda
//    item, task / payment / errand → a to-do. Undo puts it back exactly.
//
// This file: proposals, conflicts, to-dos, errands. storeAdmin.ts: notices,
// quarantine, plans, revisions, settings, export and erase.
import { create } from 'zustand';
import type { AgendaItem, DeskData, ErrandTerms, Todo, ToggleId, HouseholdSettings, Errand, NoticeSource, SpaceId, AgentId, When, DueKind } from './types';
import { buildDeskData, MEMBER_IDS } from './data';
import { fingerprint } from './fingerprint';
import { dayKey, fmtTime, isDay } from './format';
import { auditRow, deskClock, newId, q, revisionRow, updateIn } from './storeKit';
import { adminActions } from './storeAdmin';
import { API_ENABLED } from '../services/api';
import { bindServer } from './api/server';

export { deskClock } from './storeKit';

export interface DeskActions {
  setActor(memberId: string): void;
  acceptProposal(id: string): boolean;
  dismissProposal(id: string): boolean;
  undoProposal(id: string): boolean;
  resolveConflict(conflictId: string, fixId: string): boolean;
  undoConflict(conflictId: string): boolean;
  toggleTodo(id: string): void;
  /** Undo of an addTodo; one audit row. False when it is gone already. */
  removeTodo(id: string): boolean;
  addTodo(input: { title: string; ownerId: string; due?: When; dueKind?: DueKind; agent?: AgentId; planId?: string; noticeId?: string }): string;
  approveErrand(id: string): boolean;
  editErrand(id: string, patch: Partial<ErrandTerms>): boolean;
  cancelErrand(id: string, reason?: string): boolean;
  requestErrand(input: ErrandTerms & { title: string; agent: AgentId; noticeId?: string }): string;
  // storeAdmin.ts
  addNotice(input: { title: string; body: string; source?: NoticeSource; sender?: string; spaceId?: SpaceId; attachments?: number }): string;
  flagNotice(noticeId: string, note: string): void;
  openOriginal(noticeId: string): void;
  releaseQuarantine(id: string): void;
  deleteQuarantine(id: string): void;
  setPlanStatus(planId: string, status: 'draft' | 'done' | 'dropped'): void;
  markBooked(planId: string, bookingId: string, booked: boolean): void;
  revertRevision(id: string): boolean;
  setSetting<K extends keyof HouseholdSettings>(key: K, value: HouseholdSettings[K]): void;
  setToggle(id: ToggleId, on: boolean): void;
  connectMailbox(address: string): void;
  disconnectMailbox(id: string): void;
  newPhoneToken(device: string): string;
  revokeToken(id: string): void;
  stopWatcher(id: string): void;
  withdrawConsent(childId: string): void;
  signOutEverywhere(memberId: string): void;
  openSitting(input: { purpose: string; site: string; minutes: number }): string;
  exportAll(): DeskExport;
  eraseConfirmPhrase(): string;
  eraseAll(typed: string): boolean;
}

export interface DeskExport {
  format: 'familyos.desk.v1';
  exportedAt: string;
  household: string;
  data: DeskData;
}

export type DeskState = DeskData & { actor: string } & DeskActions;
export type DeskSet = (partial: Partial<DeskState> | ((s: DeskState) => Partial<DeskState>)) => void;
export type DeskGet = () => DeskState;

/** Who did it, for sentences: "Michael", "Sarah"… */
export const nameOf = (s: Pick<DeskData, 'members'>, id: string) => (id === 'FamilyOS' ? 'FamilyOS' : (s.members.find((m) => m.id === id)?.name ?? 'Someone'));

/** Errand fields in household words, for audit sentences. */
const TERM_LABEL: Record<keyof ErrandTerms, string> = { what: 'what', when: 'when', where: 'where', atMost: 'at most', paidBy: 'how it is paid', card: 'the card', stopsIf: 'stops if' };

/** "When" row text after a move: "3:30 – 4:30 pm" style. */
function whenRow(details: [string, string][] | undefined, when: When, end: string | undefined, tz: string) {
  if (!details || isDay(when)) return details;
  const text = end ? `${fmtTime(when, tz)} – ${fmtTime(end, tz)}` : fmtTime(when, tz);
  return details.map(([k, v]) => (k === 'When' ? [k, text] : [k, v]) as [string, string]);
}

export const useDesk = create<DeskState>()((set, get) => {
  const log = (sentence: string, code: string, raw?: Record<string, unknown>, extra: Partial<DeskState> = {}) =>
    set((s) => ({ ...extra, audit: [...s.audit, auditRow(s.actor, sentence, code, raw)] }));
  const who = () => nameOf(get(), get().actor);

  return {
    ...buildDeskData(),
    actor: MEMBER_IDS.michael,

    setActor(memberId) {
      set({ actor: memberId });
    },

    acceptProposal(id) {
      const s = get();
      const p = s.proposals.find((x) => x.id === id);
      if (!p || (p.state !== 'proposed' && p.state !== 'changed')) return false;
      const now = deskClock.now().toISOString();
      const tz = s.settings.timezone;
      let agenda = s.agenda;
      let todos = s.todos;
      const decision: NonNullable<typeof p.lastDecision> = {};
      const existing = p.created?.agendaId ? s.agenda.find((a) => a.id === p.created!.agendaId) : undefined;
      if (existing && p.due) {
        // A changed notice: move what is already on the calendar to the new time.
        decision.moved = { agendaId: existing.id, when: existing.when, end: existing.end };
        const shift = existing.end && !isDay(existing.when) && !isDay(p.due) ? new Date(existing.end).getTime() - new Date(existing.when).getTime() : 0;
        const end = shift ? new Date(new Date(p.due).getTime() + shift).toISOString() : existing.end;
        agenda = updateIn(agenda, existing.id, (a) => ({ ...a, when: p.due!, dueKind: p.dueKind ?? a.dueKind, end, details: whenRow(a.details, p.due!, end, tz) }));
      } else if (p.kind === 'calendar' || p.kind === 'reminder') {
        const item: AgendaItem = {
          id: newId('a'), agent: p.agent, spaceId: p.spaceId, kind: p.kind === 'reminder' ? 'reminder' : 'event', title: p.title,
          when: p.due ?? dayKey(deskClock.now(), tz), dueKind: p.due ? (p.dueKind ?? 'allDay') : 'allDay', memberIds: p.forMemberId ? [p.forMemberId] : [],
          createdAt: now, noticeId: p.noticeId, proposalId: p.id, remindsOf: p.kind === 'reminder' && p.due ? (isDay(p.due) ? p.due : dayKey(p.due, tz)) : undefined,
        };
        agenda = [...agenda, item];
        decision.createdAgendaId = item.id;
      } else {
        const todo: Todo = {
          id: newId('t'), title: p.title, due: p.due, dueKind: p.dueKind, ownerId: s.actor, done: false, agent: p.agent, spaceId: p.spaceId,
          proposalId: p.id, noticeId: p.noticeId, createdAt: now, onCalendar: false,
        };
        todos = [...todos, todo];
        decision.createdTodoId = todo.id;
      }
      const proposals = updateIn(s.proposals, id, (x) => ({
        ...x, prevState: x.state, state: 'accepted' as const, decidedAt: now, decidedBy: s.actor, lastDecision: decision,
        created: { ...x.created, agendaId: x.created?.agendaId ?? decision.createdAgendaId, todoId: x.created?.todoId ?? decision.createdTodoId },
      }));
      const where = decision.createdTodoId ? 'to the to-dos' : decision.moved ? 'and moved it on the calendar' : 'to the calendar';
      log(`${who()} accepted ${q(p.title)} ${where}`, 'proposal.accepted', { proposalId: id, noticeId: p.noticeId, ...decision }, { proposals, agenda, todos });
      return true;
    },

    dismissProposal(id) {
      const p = get().proposals.find((x) => x.id === id);
      if (!p || p.state === 'accepted' || p.state === 'dismissed') return false;
      const now = deskClock.now().toISOString();
      const proposals = updateIn(get().proposals, id, (x) => ({ ...x, prevState: x.state, state: 'dismissed' as const, decidedAt: now, decidedBy: get().actor, lastDecision: {} }));
      log(`${who()} dismissed ${q(p.title)}`, 'proposal.dismissed', { proposalId: id, noticeId: p.noticeId }, { proposals });
      return true;
    },

    undoProposal(id) {
      const s = get();
      const p = s.proposals.find((x) => x.id === id);
      if (!p || (p.state !== 'accepted' && p.state !== 'dismissed') || !p.prevState) return false;
      const d = p.lastDecision ?? {};
      let agenda = s.agenda.filter((a) => a.id !== d.createdAgendaId);
      if (d.moved) agenda = updateIn(agenda, d.moved.agendaId, (a) => ({ ...a, when: d.moved!.when, end: d.moved!.end, details: whenRow(a.details, d.moved!.when, d.moved!.end, s.settings.timezone) }));
      const todos = s.todos.filter((t) => t.id !== d.createdTodoId);
      const created = { ...p.created };
      if (d.createdAgendaId && created.agendaId === d.createdAgendaId) delete created.agendaId;
      if (d.createdTodoId && created.todoId === d.createdTodoId) delete created.todoId;
      const proposals = updateIn(s.proposals, id, (x) => ({ ...x, state: x.prevState!, prevState: undefined, decidedAt: undefined, decidedBy: undefined, lastDecision: undefined, created }));
      log(`${who()} undid the decision on ${q(p.title)}`, 'proposal.undone', { proposalId: id, was: p.state, now: p.prevState }, { proposals, agenda, todos });
      return true;
    },

    resolveConflict(conflictId, fixId) {
      const s = get();
      const c = s.conflicts.find((x) => x.id === conflictId);
      const fix = c?.fixes.find((f) => f.id === fixId);
      const a = fix && s.agenda.find((x) => x.id === fix.agendaId);
      if (!c || !fix || !a || c.resolvedAt) return false;
      const tz = s.settings.timezone;
      const now = deskClock.now().toISOString();
      const agenda = updateIn(s.agenda, a.id, (x) => ({ ...x, when: fix.newWhen, end: fix.newEnd ?? x.end, details: whenRow(x.details, fix.newWhen, fix.newEnd ?? x.end, tz) }));
      const conflicts = updateIn(s.conflicts, c.id, (x) => ({ ...x, resolvedAt: now, resolvedBy: s.actor, undo: { agendaId: a.id, when: a.when, end: a.end } }));
      const rv = revisionRow(s.actor, 'agenda', a.id, a.title, 'when', a.when, fix.newWhen);
      const to = isDay(fix.newWhen) ? fix.newWhen : fmtTime(fix.newWhen, tz, true);
      log(`${who()} confirmed: moved ${q(a.title)} to ${to}`, 'conflict.resolved', { conflictId, fixId, agendaId: a.id, from: a.when, to: fix.newWhen }, { agenda, conflicts, revisions: [...s.revisions, rv] });
      return true;
    },

    undoConflict(conflictId) {
      const s = get();
      const c = s.conflicts.find((x) => x.id === conflictId);
      if (!c?.resolvedAt || !c.undo) return false;
      const u = c.undo;
      const a = s.agenda.find((x) => x.id === u.agendaId);
      const agenda = updateIn(s.agenda, u.agendaId, (x) => ({ ...x, when: u.when, end: u.end, details: whenRow(x.details, u.when, u.end, s.settings.timezone) }));
      const conflicts = updateIn(s.conflicts, c.id, (x) => ({ ...x, resolvedAt: undefined, resolvedBy: undefined, undo: undefined }));
      log(`${who()} undid the move of ${q(a?.title ?? 'an event')}`, 'conflict.reopened', { conflictId, agendaId: u.agendaId }, { agenda, conflicts });
      return true;
    },

    toggleTodo(id) {
      const t = get().todos.find((x) => x.id === id);
      if (!t) return;
      const done = !t.done;
      const todos = updateIn(get().todos, id, (x) => ({ ...x, done, doneAt: done ? deskClock.now().toISOString() : undefined }));
      log(`${who()} ${done ? 'ticked' : 'reopened'} ${q(t.title)}`, done ? 'todo.done' : 'todo.reopened', { todoId: id }, { todos });
    },

    addTodo(input) {
      const s = get();
      const todo: Todo = { id: newId('t'), done: false, createdAt: deskClock.now().toISOString(), ...input };
      const plans = input.planId ? updateIn(s.plans, input.planId, (p) => ({ ...p, todoIds: [...p.todoIds, todo.id] })) : s.plans;
      log(`${who()} added the to-do ${q(input.title)}`, 'todo.created', { todoId: todo.id, planId: input.planId }, { todos: [...s.todos, todo], plans });
      return todo.id;
    },

    removeTodo(id) {
      const s = get();
      const t = s.todos.find((x) => x.id === id);
      if (!t) return false;
      const plans = t.planId ? updateIn(s.plans, t.planId, (p) => ({ ...p, todoIds: p.todoIds.filter((x) => x !== id) })) : s.plans;
      log(`${who()} removed the to-do ${q(t.title)}`, 'todo.removed', { todoId: id, planId: t.planId }, { todos: s.todos.filter((x) => x.id !== id), plans });
      return true;
    },

    approveErrand(id) {
      const s = get();
      const e = s.errands.find((x) => x.id === id);
      const guardian = s.members.find((m) => m.id === s.actor)?.role === 'guardian';
      if (!e || e.status !== 'proposed' || !guardian) return false;
      const fp = fingerprint(e);
      const errands = updateIn(s.errands, id, (x) => ({ ...x, status: 'approved' as const, fingerprint: fp, approvedFingerprint: fp, approvedBy: s.actor, approvedAt: deskClock.now().toISOString() }));
      log(`${who()} approved ${q(e.title)}`, 'errand.approved', { errandId: id, fingerprint: fp }, { errands });
      return true;
    },

    editErrand(id, patch) {
      const s = get();
      const e = s.errands.find((x) => x.id === id);
      if (!e || e.status === 'done' || e.status === 'cancelled') return false;
      const next: Errand = { ...e, ...patch };
      const fp = fingerprint(next);
      const changed = (Object.keys(patch) as (keyof ErrandTerms)[]).filter((k) => patch[k] !== undefined && patch[k] !== e[k]);
      if (!changed.length) return false;
      const voided = e.status === 'approved' && fp !== e.approvedFingerprint;
      const errand: Errand = voided
        ? { ...next, fingerprint: fp, status: 'proposed', approvedFingerprint: undefined, approvedBy: undefined, approvedAt: undefined }
        : { ...next, fingerprint: fp };
      const revs = changed.map((k) => revisionRow(s.actor, 'errand', id, e.title, k, e[k], next[k], false));
      const rows = [auditRow(s.actor, `${who()} changed ${changed.map((k) => TERM_LABEL[k]).join(', ')} on ${q(e.title)}`, 'errand.updated', { errandId: id, fields: changed, fingerprint: fp })];
      if (voided) rows.push(auditRow('FamilyOS', `The approval for ${q(e.title)} no longer applies: what was written down changed`, 'errand.approval_voided', { errandId: id, was: e.approvedFingerprint, now: fp }));
      set((st) => ({ errands: updateIn(st.errands, id, () => errand), revisions: [...st.revisions, ...revs], audit: [...st.audit, ...rows] }));
      return true;
    },

    cancelErrand(id, reason) {
      const e = get().errands.find((x) => x.id === id);
      if (!e || e.status === 'done' || e.status === 'cancelled') return false;
      const errands = updateIn(get().errands, id, (x) => ({ ...x, status: 'cancelled' as const, cancelledReason: reason }));
      log(`${who()} cancelled ${q(e.title)}`, 'errand.cancelled', { errandId: id, reason }, { errands });
      return true;
    },

    requestErrand(input) {
      const s = get();
      const { title, agent, noticeId, ...terms } = input;
      const e: Errand = { id: newId('e'), title, agent, noticeId, ...terms, status: 'proposed', fingerprint: fingerprint(terms), requestedBy: s.actor, createdAt: deskClock.now().toISOString(), steps: [] };
      log(`${who()} asked for an errand: ${q(title)}`, 'errand.requested', { errandId: e.id, fingerprint: e.fingerprint }, { errands: [...s.errands, e] });
      return e.id;
    },

    ...adminActions(set, get),
  };
});

// On the backend the desk starts empty, fills from the server once signed in, and every action also reaches it
// (desk/api/server.ts). The mock household above stays for `npm run dev` and the tests.
if (API_ENABLED) bindServer(useDesk);
