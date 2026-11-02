// Ask, the answer builder (MASTER_AGENT.md §7 Phase 3 "Ask", §3.3.2
// "Every answer cites"; FamilyOS.mp4 4:50–5:30, frames f_059–f_068): text,
// citation chips numbered r1, r2… in order (one per notice, and never a
// notice the asker cannot see), and action cards that only run on Confirm.
import type { AskCtx, AskData } from './askSearch';
import { memberOf, whenPhrase } from './askSearch';
import type { Proposal } from '../../desk/types';
import { isMissed } from '../../desk/selectors';

export type Seg = { t: string } | { cite: number };
export interface Citation {
  n: number;
  noticeId: string;
  title: string;
  sender: string;
}
export type ActionKind = 'accept' | 'dismiss' | 'tick' | 'addTodo';
export interface AskAction {
  id: string;
  kind: ActionKind;
  /** Proposal or to-do id (absent for a new to-do). */
  target?: string;
  title: string;
  detail: string;
  noticeId?: string;
}
export interface Answer {
  segs: Seg[];
  cites: Citation[];
  actions: AskAction[];
  /** Questions to try instead (when nothing matched). */
  suggest?: string[];
}

export const SUGGESTIONS = ['What needs someone this week?', 'What do we pay every month?', 'When is Mia’s recital?', 'What is still undecided?'];

/** Collects the answer: text, numbered citations (deduplicated by notice) and action cards. */
export class Composer {
  private segs: Seg[] = [];
  private cites: Citation[] = [];
  private acts: AskAction[] = [];
  private suggest?: string[];
  constructor(
    readonly d: AskData,
    readonly ctx: AskCtx,
  ) {}
  say(t: string) {
    const last = this.segs[this.segs.length - 1];
    if (last && 't' in last) last.t += t;
    else this.segs.push({ t });
    return this;
  }
  /** Cite the notice behind a fact; a notice the asker cannot see is never cited. */
  cite(noticeId?: string) {
    const n = noticeId ? this.d.notices.find((x) => x.id === noticeId) : undefined;
    if (!n) return this;
    let c = this.cites.find((x) => x.noticeId === n.id);
    if (!c) {
      c = { n: this.cites.length + 1, noticeId: n.id, title: n.title, sender: n.sender };
      this.cites.push(c);
    }
    this.segs.push({ cite: c.n });
    return this;
  }
  /** Offer to accept an undecided proposal (missed ones can only be let go, so they get no card). */
  offerAccept(p: Proposal) {
    if ((p.state !== 'proposed' && p.state !== 'changed') || isMissed(p, this.ctx.now, this.ctx.tz) || this.acts.some((a) => a.target === p.id)) return this;
    return this.act({ id: `accept:${p.id}`, kind: 'accept', target: p.id, title: p.title, detail: this.proposalDetail(p), noticeId: p.noticeId });
  }
  act(a: AskAction) {
    this.acts.push(a);
    return this;
  }
  suggestInstead(s: string[]) {
    this.suggest = s;
    return this;
  }
  proposalDetail(p: Proposal) {
    const who = memberOf(this.d, p.forMemberId);
    return `${p.kind}${p.due ? `, due ${whenPhrase(p.due, p.dueKind, this.ctx)}` : ', no date'}${who ? `, for ${who}` : ''}`;
  }
  get actions() {
    return this.acts;
  }
  done(): Answer {
    const segs = this.segs.map((s) => ('t' in s ? { t: s.t } : s));
    return { segs, cites: this.cites, actions: this.acts, suggest: this.suggest };
  }
}
