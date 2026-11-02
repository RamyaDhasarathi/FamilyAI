// Ask, the conversation (MASTER_AGENT.md §7 Phase 3 "Ask"; FamilyOS.mp4
// 4:50–5:40). Lives for the visit, like the desk store, so leaving /ask and
// coming back keeps it; Clear empties it. A question shows the typing dots
// for 600–1200 ms, then the answer built from the desk data at that moment.
// Action cards run only from confirm() — a person's click — and each result
// (done / nothing to do) is kept on the card, with Undo where the store has one.
import { create } from 'zustand';
import { useDesk } from '../../desk/store';
import { useFamilyOS } from '../../store/useFamilyOS';
import { acceptWithUndo, dismissWithUndo, placeOf } from '../waiting/decide';
import { answer, type Answer, type AskAction } from './answer';

export interface AskMsg {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  answer?: Answer;
}

export interface CardResult {
  state: 'done' | 'stale';
  line: string;
  /** Undo is offered (accept / dismiss / tick / a to-do just added). */
  undo: boolean;
  /** The to-do a "remind me" card added, so Undo can take it away again. */
  todoId?: string;
}

interface AskState {
  msgs: AskMsg[];
  /** Answers still being "typed". */
  pending: number;
  /** The navigation (location key) whose ?q= was already asked, so Back or a re-render never asks twice. */
  handled: string | null;
  results: Record<string, CardResult>;
  ask(q: string): void;
  askOnce(key: string, q: string): void;
  clear(): void;
  confirm(msgId: string, a: AskAction): void;
  undo(msgId: string, a: AskAction): void;
}

let seq = 0;
const timers = new Set<number>();
const nextId = (p: string) => `${p}${++seq}`;
const cardKey = (msgId: string, a: AskAction) => `${msgId}:${a.id}`;
/** 600–1200 ms, as the brief asks (tests replace it). */
export const askTiming = { delay: () => 600 + Math.round(Math.random() * 600) };

export const useAsk = create<AskState>()((set, get) => ({
  msgs: [],
  pending: 0,
  handled: null,
  results: {},

  ask(q) {
    const text = q.trim();
    if (!text) return;
    set((s) => ({ msgs: [...s.msgs, { id: nextId('u'), role: 'user', text }], pending: s.pending + 1 }));
    const t = window.setTimeout(() => {
      timers.delete(t);
      const d = useDesk.getState();
      const a = answer(text, d, { now: new Date(), tz: d.settings.timezone, actor: d.actor });
      set((s) => ({ msgs: [...s.msgs, { id: nextId('a'), role: 'assistant', text: a.segs.map((x) => ('t' in x ? x.t : `[r${x.cite}]`)).join(''), answer: a }], pending: Math.max(0, s.pending - 1) }));
    }, askTiming.delay());
    timers.add(t);
  },

  askOnce(key, q) {
    if (get().handled === key) return;
    set({ handled: key });
    get().ask(q);
  },

  clear() {
    timers.forEach((t) => window.clearTimeout(t));
    timers.clear();
    set({ msgs: [], pending: 0, results: {} });
  },

  confirm(msgId, a) {
    const key = cardKey(msgId, a);
    if (get().results[key]?.state === 'done') return;
    const desk = useDesk.getState();
    let result: CardResult;
    if (a.kind === 'accept') {
      result = acceptWithUndo(a.target!) ? { state: 'done', line: `Accepted. ${placeOf(a.target!)}`, undo: true } : { state: 'stale', line: 'Already decided, so nothing changed.', undo: false };
    } else if (a.kind === 'dismiss') {
      result = dismissWithUndo(a.target!) ? { state: 'done', line: 'Dismissed. Nothing else changed.', undo: true } : { state: 'stale', line: 'Already decided, so nothing changed.', undo: false };
    } else if (a.kind === 'tick') {
      const t = desk.todos.find((x) => x.id === a.target);
      if (t && !t.done) {
        desk.toggleTodo(t.id);
        result = { state: 'done', line: 'Ticked off.', undo: true };
      } else result = { state: 'stale', line: 'Already done, so nothing changed.', undo: false };
    } else {
      const todoId = desk.addTodo({ title: a.title, ownerId: desk.actor });
      useFamilyOS.getState().toast(`Added “${a.title}” to your to-dos.`);
      result = { state: 'done', line: 'Added to your to-dos. Tick it off on Waiting on you.', undo: true, todoId };
    }
    set((s) => ({ results: { ...s.results, [key]: result } }));
  },

  undo(msgId, a) {
    const key = cardKey(msgId, a);
    const desk = useDesk.getState();
    const added = get().results[key]?.todoId;
    let ok: boolean;
    if (added) ok = desk.removeTodo(added);
    else if (a.kind === 'tick') {
      const t = desk.todos.find((x) => x.id === a.target);
      ok = !!t?.done;
      if (ok) desk.toggleTodo(t!.id);
    } else ok = desk.undoProposal(a.target!);
    if (!ok) return;
    useFamilyOS.getState().toast('Undone. Nothing else changed.');
    set((s) => {
      const results = { ...s.results };
      delete results[key];
      return { results };
    });
  },
}));

export const resultKey = cardKey;
