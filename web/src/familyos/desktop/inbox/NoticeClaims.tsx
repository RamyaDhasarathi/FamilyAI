// Notice drawer, the two read-outs (MASTER_AGENT.md §7 Phase 3, §3.3.2
// "Provenance everywhere"; FamilyOS.mp4 2:55, 9:50, frames f_121–f_122):
//  • Read from this notice · N claims · N grounded — the text as it came,
//    each claim's source highlighted and numbered, then one card per claim
//    with its quote; a quote not found in the text says so plainly.
//  • Proposed for the family — Accept / ✕ for what is undecided (each a
//    click, Undo in the toast), and an honest line for what was decided.
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useDesk } from '../../desk/store';
import { useFamilyOS } from '../../store/useFamilyOS';
import { memberName } from '../../desk/selectors';
import type { DeskData, Notice, Proposal } from '../../desk/types';
import { StatusChip } from '../shell/DeskPage';
import { DismissButton, KindIcon } from '../waiting/WaitingRow';
import { acceptWithUndo, dismissWithUndo } from '../waiting/decide';
import { stateLines } from '../waiting/waitingModel';
import { markQuotes } from './inboxModel';

interface Fmt {
  text: (s: string) => string;
  when: (w: string, k?: Proposal['dueKind']) => string;
  tz: string;
}

export function ReadFromNotice({ notice, proposals, f }: { notice: Notice; proposals: Proposal[]; f: Fmt }) {
  const claims = proposals.map((p, i) => ({ n: i + 1, quote: p.quote }));
  const { segs, found, missing } = markQuotes(notice.body, claims);
  const body = f.text(notice.body);
  return (
    <section className="ib-read" aria-labelledby="ib-read-title">
      <p className="ib-label">
        <span id="ib-read-title" className={T.bodyStrong}>Read from this notice</span>
        <span className={T.small}>
          {proposals.length} {proposals.length === 1 ? 'claim' : 'claims'} · {found.size} grounded
        </span>
      </p>
      <p className={clsx(T.body, 'ib-body')}>
        {segs.map((s, i) =>
          s.n ? (
            <mark key={i} className="ib-mark">
              <span className="ib-mark__n" aria-label={`claim ${s.n}:`}>{s.n}</span>
              {f.text(s.text)}
            </mark>
          ) : (
            <span key={i}>{f.text(s.text)}</span>
          ),
        )}
      </p>
      <ol className="ib-claims">
        {proposals.map((p, i) => {
          const n = i + 1;
          const quote = p.quote ? f.text(p.quote) : '';
          const at = quote ? body.indexOf(quote) : -1;
          return (
            <li key={p.id} className="ib-claim">
              <span className="ib-claim__n" aria-hidden>{n}</span>
              <div className="ib-claim__main">
                <p className="ib-claim__title">
                  <StatusChip tone="neutral">{p.kind}</StatusChip> <span className={T.bodyStrong}>{f.text(p.title)}</span>
                </p>
                <p className={T.small}>{p.due ? f.when(p.due, p.dueKind) : 'no date given'}</p>
                {quote ? <blockquote className={clsx(T.small, 'ib-quote')}>“{quote}”</blockquote> : null}
                <p className={clsx(T.small, 'ib-claim__meta')}>
                  {missing.includes(n) || at < 0 ? 'Check before relying on it: these words are not in the notice.' : `in the notice · chars ${at + 1}–${at + quote.length}`}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** "accepted · on the calendar · Mia" (MASTER §10), "dismissed by Sarah". */
function decidedLine(p: Proposal, s: Pick<DeskData, 'members' | 'todos'>): string {
  const name = (id?: string) => memberName(s, id);
  if (p.state === 'dismissed') return `dismissed${p.decidedBy ? ` by ${name(p.decidedBy)}` : ''}`;
  const todo = p.created?.todoId ? s.todos.find((t) => t.id === p.created!.todoId) : undefined;
  if (todo) return `accepted · on the to-dos · ${name(todo.ownerId)}${todo.done ? ' · done' : ''}`;
  const who = p.forMemberId ? ` · ${name(p.forMemberId)}` : '';
  return `accepted · on the calendar${who}`;
}

export function ProposedList({ proposals, f, now }: { proposals: Proposal[]; f: Fmt; now: Date }) {
  const undo = useDesk((s) => s.undoProposal);
  const members = useDesk((s) => s.members);
  const todos = useDesk((s) => s.todos);
  const undoClick = (id: string) => {
    if (undo(id)) useFamilyOS.getState().toast('Undone. Nothing else changed.');
  };
  return (
    <section className="ib-proposed" aria-labelledby="ib-proposed-title">
      <p className="ib-label">
        <span id="ib-proposed-title" className={T.bodyStrong}>Proposed for the family</span>
        <span className={T.small}>nothing is accepted until someone says so</span>
      </p>
      {proposals.length === 0 ? <p className={T.small}>Nothing proposed from this notice.</p> : null}
      <ul className="ib-props">
        {proposals.map((p) => {
          const title = f.text(p.title);
          const open = p.state === 'proposed' || p.state === 'changed';
          const lines = open || p.state === 'missed' ? stateLines(p, now, f.tz) : [decidedLine(p, { members, todos })];
          return (
            <li key={p.id} className="ib-prop" data-desk-id={p.id}>
              <KindIcon kind={p.kind} agent={p.agent} size={14} />
              <div className="wt-row__main">
                <p className={clsx(T.smallStrong, 'wt-row__title')}>
                  {title}
                  {p.state === 'changed' ? <StatusChip tone="changed">Changed</StatusChip> : null}
                  {p.state === 'missed' ? <StatusChip tone="missed">Missed</StatusChip> : null}
                  {p.state === 'accepted' ? <StatusChip tone="approved">Accepted</StatusChip> : null}
                  {p.state === 'dismissed' ? <StatusChip tone="done">Dismissed</StatusChip> : null}
                </p>
                <p className={T.small}>
                  {p.kind} · {p.due ? f.when(p.due, p.dueKind) : 'no date'}
                  {p.forMemberId ? ` · for ${memberName({ members }, p.forMemberId)}` : ''}
                </p>
                {lines.map((l) => (
                  <p key={l} className={clsx(T.small, 'wt-row__line')}>{l}</p>
                ))}
              </div>
              <span className="wt-row__actions">
                {open ? <PillButton label={p.state === 'changed' ? 'Accept change' : 'Accept'} variant="primary" aria-label={`Accept ${title}`} onClick={() => acceptWithUndo(p.id)} /> : null}
                {open || p.state === 'missed' ? <DismissButton label={`Dismiss ${title}`} onClick={() => dismissWithUndo(p.id)} /> : null}
                {(p.state === 'accepted' || p.state === 'dismissed') && p.prevState ? <PillButton label="Undo" aria-label={`Undo the decision on ${title}`} onClick={() => undoClick(p.id)} /> : null}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
