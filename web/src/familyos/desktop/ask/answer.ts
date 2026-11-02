// Ask, the answers (MASTER_AGENT.md §7 Phase 3 "Ask", §3.3 principles 1–2;
// FamilyOS.mp4 4:40–5:40, frames f_058–f_068). Keyword-matched, built only
// from the desk data the asker can see, and every fact cites the notice it
// came from as a chip [r1] [r2] (numbered in order, one per notice). Anything
// that would change something is returned as an action card ("Accept … —
// due …") which runs only when a person presses Confirm; answering never
// touches the store. Money stays as ¤{n} tokens, rendered in the household
// currency by the page.
import type { AskCtx, AskData, Hit } from './askSearch';
import { memberOf, namedMembers, norm, search, statePhrase, visibleData, whenPhrase, words } from './askSearch';
import { Composer, SUGGESTIONS, type Answer } from './askCompose';
import { TOPICS, listUndecided, personSummary } from './answerTopics';
import type { Todo } from '../../desk/types';

export type { Answer, AskAction, ActionKind, Citation, Seg } from './askCompose';
export { SUGGESTIONS } from './askCompose';

const ABOUT = /^(tell me (more )?about|what about|when is|when's|when does|when did|where is|who is|how much (was|is|do we pay for))[: ]*/i;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const clean = (s: string) => s.trim().replace(/[.?!]+$/, '').replace(/^["“]|["”]$/g, '');

/** Answer a question or an instruction. Pure: it reads `data` and never changes it. */
export function answer(question: string, data: AskData, ctx: AskCtx): Answer {
  const d = visibleData(data, ctx.actor);
  const c = new Composer(d, ctx);
  const q = question.trim().replace(/^(please|hey|ok|okay)[, ]+/i, '');
  if (command(q, c)) return c.done();
  // "Tell me more about X", "When is X?": look X up first; broad topics only if nothing matches.
  const about = q.replace(ABOUT, '');
  if (about !== q && lookup(about, c)) return c.done();
  for (const t of TOPICS) if (t.test.test(q) && t.run(c, q)) return c.done();
  if (lookup(about, c)) return c.done();
  const named = namedMembers(about, d.members);
  if (named.length && !words(about).some((w) => !named.some((m) => m.name.toLowerCase().startsWith(w)))) personSummary(c, named[0]);
  else fallback(about, c);
  return c.done();
}

// ── Instructions: accept / dismiss / tick / add a to-do ────────────────

function command(q: string, c: Composer): boolean {
  const add = q.match(/^(?:remind me to|add (?:a )?to-?do(?: to)?|add to (?:the |my )?to-?dos|put on (?:the |my )?to-?dos)[: ]+(.+)$/i);
  if (add) {
    const title = cap(clean(add[1]));
    const me = memberOf(c.d, c.ctx.actor) || 'you';
    c.say(`I can put “${title}” on your to-dos, with no date. Confirm below; nothing is added before you do.`);
    c.act({ id: `todo:${title}`, kind: 'addTodo', title, detail: `for ${me}, no date` });
    return true;
  }
  const decide = q.match(/^(accept|approve|say yes to|dismiss|decline|ignore|reject|let go of)\s+(.+)$/i);
  if (decide) {
    const yes = /^(accept|approve|say yes to)$/i.test(decide[1]);
    const open = c.d.proposals.filter((p) => p.state === 'proposed' || p.state === 'changed' || (!yes && p.state === 'missed'));
    const hit = search({ ...c.d, proposals: open, agenda: [], todos: [], recurring: [], notices: [] }, decide[2])[0];
    if (!hit || hit.type !== 'proposal') {
      c.say(`Nothing undecided matches “${clean(decide[2])}”. `);
      listUndecided(c, 4);
      return true;
    }
    const p = hit.item;
    c.say(`That is “${p.title}”, ${p.due ? whenPhrase(p.due, p.dueKind, c.ctx) : 'with no date'}`).cite(p.noticeId).say(`, and ${statePhrase(p, c.ctx, c.d)}. `);
    if (yes) {
      c.offerAccept(p);
      c.say(c.actions.length ? 'Confirm below to accept it; nothing changes before you do.' : 'There is nothing to accept any more.');
    } else {
      c.act({ id: `dismiss:${p.id}`, kind: 'dismiss', target: p.id, title: p.title, detail: c.proposalDetail(p), noticeId: p.noticeId });
      c.say('Confirm below to dismiss it; nothing changes before you do.');
    }
    return true;
  }
  const tick = q.match(/^(?:tick(?: off)?|check off|mark|finish|done with)\s+(.+?)(?:\s+(?:as\s+)?done)?$/i);
  if (tick) {
    const open = c.d.todos.filter((t) => !t.done);
    const hit = search({ ...c.d, todos: open, proposals: [], agenda: [], recurring: [], notices: [] }, tick[1])[0];
    if (!hit || hit.type !== 'todo') {
      c.say(`No open to-do matches “${clean(tick[1])}”.`);
      return true;
    }
    const t = hit.item;
    c.say(`“${t.title}” is on the to-dos for ${memberOf(c.d, t.ownerId)}`).cite(t.noticeId).say('. Confirm below to tick it off.');
    c.act({ id: `tick:${t.id}`, kind: 'tick', target: t.id, title: t.title, detail: `on the to-dos for ${memberOf(c.d, t.ownerId)}`, noticeId: t.noticeId });
    return true;
  }
  return false;
}

// ── Lookups: the best match, said plainly, plus up to two related ─────

function sayHit(h: Hit, c: Composer, first: boolean) {
  const { ctx, d } = c;
  switch (h.type) {
    case 'proposal': {
      const p = h.item;
      c.say(`“${p.title}” ${p.due ? `is ${whenPhrase(p.due, p.dueKind, ctx)}` : 'has no date'}`).cite(p.noticeId).say(`, and ${statePhrase(p, ctx, d)}.`);
      if (first) c.offerAccept(p);
      return;
    }
    case 'agenda': {
      const a = h.item;
      const who = (a.memberIds ?? []).map((id) => memberOf(d, id)).filter(Boolean);
      const when = whenPhrase(a.when, a.dueKind, ctx);
      // "The mortgage … is due today" already says the day; don't repeat it.
      const said = norm(a.title).split(' ').includes(when.replace(/^on /, '').split(/[ ,]/)[0].toLowerCase());
      c.say(`${a.title.replace(/\.$/, '')}${said ? '' : `: ${when}`}${a.place ? `, ${a.place}` : ''}${who.length ? ` (${who.join(', ')})` : ''}`).cite(a.noticeId).say(', on the calendar.');
      return;
    }
    case 'todo': {
      const t: Todo = h.item;
      c.say(`“${t.title}” is on the to-dos for ${memberOf(d, t.ownerId)}${t.due ? `, ${whenPhrase(t.due, t.dueKind, ctx)}` : ''}${t.done ? ', done' : ''}`).cite(t.noticeId).say('.');
      return;
    }
    case 'recurring': {
      const r = h.item;
      c.say(`${r.merchant} charges ¤{${r.amount}} ${r.cadence === 'monthly' ? 'every month' : r.cadence === 'weekly' ? 'every week' : 'every year'}; next ${whenPhrase(r.next, 'allDay', ctx)}`).cite(r.noticeId).say('.');
      return;
    }
    case 'notice': {
      const n = h.item;
      c.say(`${n.sender} sent “${n.title}” ${whenPhrase(n.receivedAt, 'allDay', ctx).replace(/^on /, 'on ')}`).cite(n.id).say(`: ${n.summary.replace(/\.$/, '')}.`);
    }
  }
}

function lookup(q: string, c: Composer): boolean {
  const hits = search(c.d, q);
  if (!hits.length) return false;
  // A dated record whose title matches (a calendar entry, a proposal, a to-do, a charge) answers better than the raw notice.
  const best = hits.find((h) => h.type !== 'notice' && h.score >= 3) ?? hits[0];
  sayHit(best, c, true);
  hits.splice(hits.indexOf(best), 1);
  hits.unshift(best);
  const seen = new Set([best.noticeId]);
  let more = 0;
  for (const h of hits.slice(1)) {
    if (more >= 2 || h.score < Math.max(2, best.score * 0.6) || seen.has(h.noticeId)) continue;
    seen.add(h.noticeId);
    c.say(more ? ' ' : ' Also: ');
    sayHit(h, c, false);
    more++;
  }
  return true;
}

function fallback(q: string, c: Composer) {
  const w = words(q);
  c.say(w.length ? `I could not find anything about “${w.slice(0, 3).join(' ')}” in what the household has received. ` : 'I did not catch a question there. ');
  c.say('I only see the notices, the dates spotted, the to-dos and what you pay. Try one of these:');
  c.suggestInstead(SUGGESTIONS);
}
