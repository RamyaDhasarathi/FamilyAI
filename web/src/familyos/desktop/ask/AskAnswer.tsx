// Ask, one answer (MASTER_AGENT.md §7 Phase 3 "Ask"; FamilyOS.mp4 4:50–5:30,
// frames f_059, f_063, f_066, f_068): our "theirs" chat bubble with citation
// chips r1, r2… (each opens the notice it came from), then any change as an
// action card — "Accept {title} — task, due …" + Confirm. Nothing happens
// before Confirm; afterwards the card says what happened, with Undo.
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { Check } from 'lucide-react';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import type { Answer, AskAction } from './answer';
import { resultKey, useAsk } from './askStore';

const VERB: Record<AskAction['kind'], string> = { accept: 'Accept', dismiss: 'Dismiss', tick: 'Tick off', addTodo: 'Add the to-do' };

interface Props {
  msgId: string;
  answer: Answer;
  text: (s: string) => string;
  onCite: (noticeId: string) => void;
  onAsk: (q: string) => void;
}

export function AskAnswer({ msgId, answer, text, onCite, onAsk }: Props) {
  return (
    <motion.li className="bubble bubble--theirs ak-answer" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.26 }}>
      <span className="sr-only">FamilyOS: </span>
      <p className="ak-answer__text">
        {answer.segs.map((s, i) => {
          if ('t' in s) return <span key={i}>{text(s.t)}</span>;
          const c = answer.cites[s.cite - 1];
          return (
            <button key={i} type="button" className="ak-cite" onClick={() => onCite(c.noticeId)} aria-label={`Source r${c.n}: ${text(c.title)}, from ${c.sender}. Opens the notice`} title={`${text(c.title)} · ${c.sender}`}>
              r{c.n}
            </button>
          );
        })}
      </p>
      {answer.suggest?.length ? (
        <span className="ak-suggest" role="group" aria-label="Try instead">
          {answer.suggest.map((q) => (
            <button key={q} type="button" className="chip chip--small" onClick={() => onAsk(q)}>
              {q}
            </button>
          ))}
        </span>
      ) : null}
      {answer.actions.length ? (
        <div className="ak-actions">
          <p className={clsx(T.meta, 'ak-actions__label')}>Proposed · nothing changes until you confirm</p>
          {answer.actions.map((a) => (
            <ActionCard key={a.id} msgId={msgId} a={a} text={text} onCite={onCite} />
          ))}
        </div>
      ) : null}
    </motion.li>
  );
}

function ActionCard({ msgId, a, text, onCite }: { msgId: string; a: AskAction; text: (s: string) => string; onCite: (id: string) => void }) {
  const result = useAsk((s) => s.results[resultKey(msgId, a)]);
  const confirm = useAsk((s) => s.confirm);
  const undo = useAsk((s) => s.undo);
  const title = text(a.title);
  return (
    <div className={clsx('ak-card', result?.state === 'done' && 'is-done')} role="group" aria-label={`${VERB[a.kind]} ${title}`}>
      <p className="ak-card__what">
        <span className={T.small}>{VERB[a.kind]}</span> <strong className="ak-card__title">{title}</strong> <span className={T.small}>— {text(a.detail)}</span>
        {a.noticeId ? (
          <>
            {' '}
            <button type="button" className="ak-card__src desk-link" onClick={() => onCite(a.noticeId!)}>
              the notice
            </button>
          </>
        ) : null}
      </p>
      {result ? (
        <span className="ak-card__result" role="status">
          {result.state === 'done' ? <Check size={14} strokeWidth={2.6} aria-hidden className="ak-card__check" /> : null}
          <span className={T.small}>{result.line}</span>
          {result.undo ? <PillButton label="Undo" aria-label={`Undo: ${VERB[a.kind]} ${title}`} onClick={() => undo(msgId, a)} /> : null}
        </span>
      ) : (
        <PillButton label="Confirm" variant="primary" aria-label={`Confirm: ${VERB[a.kind]} ${title}`} onClick={() => confirm(msgId, a)} />
      )}
    </div>
  );
}
