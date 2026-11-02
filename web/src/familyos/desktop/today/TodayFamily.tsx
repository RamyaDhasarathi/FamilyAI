// Today, reference rows (MASTER_AGENT.md §7 Phase 2.4; FamilyOS.mp4 1:50):
// the member cards (status dot + one line, "+ Add"), the "FamilyOS noticed"
// clash card — Fix for me shows a proposal that changes nothing until
// Confirm; Show me highlights both items — and "Needs someone · worst first".
import { useState } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { Check, Plus, Sparkle } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { Dot } from '../../components/Labels';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { useDesk } from '../../desk/store';
import { NEED_LABELS, type NeedCard } from '../../desk/selectors';
import type { Conflict, Member, MemberStatus } from '../../desk/types';
import { StatusChip } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { deskCopy } from '../copy';

const C = deskCopy.today;
/** "yesterday" in a sentence, but "Oct 26" stays a date. */
const relWord = (d: string) => (/^(Today|Tomorrow|Yesterday)$/.test(d) ? d.toLowerCase() : d);
const STATUS_COLOR: Record<MemberStatus, string> = { busy: colors.severity.urgent, free: colors.done, home: colors.agents.calendar, away: colors.severity.headsup };

export function MemberCards({ members }: { members: Member[] }) {
  return (
    <section aria-label={C.members}>
      <ul className="dt-members">
        {members.map((m) => (
          <li key={m.id}>
            <Link to={`/family/${m.id}`} className="dt-member card" aria-label={`${m.name}: ${m.status ? C.status[m.status] : ''}. ${m.statusLine ?? ''}`}>
              <span className="dt-member__avatar" style={{ borderColor: m.status ? STATUS_COLOR[m.status] : undefined }} aria-hidden>
                {m.initial}
              </span>
              <span className={clsx(T.smallStrong, 'dt-member__name')}>{m.name}</span>
              {m.status ? (
                <span className={clsx(T.small, 'dt-member__status')}>
                  <Dot color={STATUS_COLOR[m.status]} size={6} />
                  {C.status[m.status]}
                </span>
              ) : null}
              <span className={clsx(T.small, 'dt-member__line')}>{m.statusLine}</span>
            </Link>
          </li>
        ))}
        <li>
          <Link to="/family?add=1" className="dt-member dt-member--add card" aria-label="Add family member">
            <span className="dt-member__avatar dt-member__avatar--add" aria-hidden>
              <Plus size={16} />
            </span>
            <span className={clsx(T.smallStrong, 'dt-member__name')}>{C.addMember}</span>
          </Link>
        </li>
      </ul>
    </section>
  );
}

/** The newest open clash, or the one just sorted (so its Undo stays in reach). */
export function NoticedCard({ conflict }: { conflict: Conflict }) {
  const [fixing, setFixing] = useState(false);
  const reduced = useReducedMotion();
  const resolve = useDesk((s) => s.resolveConflict);
  const undo = useDesk((s) => s.undoConflict);
  const flashIds = useDeskUI((s) => s.flashIds);
  const fix = conflict.fixes[0];
  const showMe = () => {
    flashIds([conflict.aId, conflict.bId]);
    document.querySelector(`[data-desk-id="${conflict.aId}"]`)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' });
  };
  const confirm = () => {
    if (!resolve(conflict.id, fix.id)) return;
    setFixing(false);
    useFamilyOS.getState().toast(C.resolvedToast, { action: { label: 'Undo', onPress: () => undo(conflict.id) }, duration: 5000 });
  };
  return (
    <section className={clsx('dt-noticed card', conflict.resolvedAt && 'is-resolved')} aria-labelledby="dt-noticed-title">
      <p className={clsx(T.section, 'dt-noticed__label')}>
        <Sparkle size={11} aria-hidden /> {C.noticed}
      </p>
      {conflict.resolvedAt ? (
        <>
          <h2 id="dt-noticed-title" className={T.bodyStrong}>
            <Check size={15} aria-hidden className="dt-noticed__check" /> {C.fixed(fix.label.split('.')[0])}
          </h2>
          <div className="dt-noticed__actions">
            <PillButton label="Undo" onClick={() => undo(conflict.id)} />
            <PillButton label={C.showMe} onClick={showMe} />
          </div>
        </>
      ) : (
        <>
          <h2 id="dt-noticed-title" className={T.bodyStrong}>
            {conflict.title}
          </h2>
          <p className={clsx(T.small, 'dt-noticed__msg')}>{conflict.message}</p>
          {fixing ? (
            <div className="dt-proposal" role="group" aria-label="Proposed change">
              <p className={T.meta}>{C.proposalLabel}</p>
              <p className={T.bodyStrong}>{fix.label}</p>
              <div className="dt-noticed__actions">
                <PillButton label={C.confirm} variant="primary" onClick={confirm} />
                <PillButton label={C.notNow} onClick={() => setFixing(false)} />
              </div>
            </div>
          ) : (
            <div className="dt-noticed__actions">
              <PillButton label={C.fix} variant="primary" onClick={() => setFixing(true)} />
              <PillButton label={C.showMe} onClick={showMe} />
            </div>
          )}
        </>
      )}
    </section>
  );
}

interface NeedsProps {
  cards: NeedCard[];
  memberName: (id?: string) => string;
  day: (w: string) => string;
  slot: (w: string, k?: NeedCard['dueKind']) => string;
  text: (s: string) => string;
}

export function NeedsSomeone({ cards, memberName, day, slot, text }: NeedsProps) {
  const shown = cards.slice(0, 8);
  return (
    <section aria-labelledby="dt-needs">
      <h2 id="dt-needs" className="dt-h2">
        <span className={T.bodyStrong}>{C.needs}</span> <span className={T.small}>{C.needsSub}</span>
      </h2>
      {shown.length === 0 ? (
        <p className={clsx(T.small, 'desk-empty')}>{C.needsEmpty}</p>
      ) : (
        <ul className="dt-needs">
          {shown.map((c) => (
            <li key={c.id}>
              <Link to={`/inbox/${c.noticeId}`} className="dt-need card" aria-label={`${NEED_LABELS[c.tone]}: ${text(c.title)}. ${c.line}. Opens the notice`}>
                <span className="dt-need__top">
                  <StatusChip tone={c.tone}>{NEED_LABELS[c.tone]}</StatusChip>
                  {c.due ? <span className={T.small}>{c.tone === 'changed' || c.tone === 'today' ? `${day(c.due)} · ${slot(c.due, c.dueKind)}` : relWord(day(c.due))}</span> : null}
                  {c.memberId ? <StatusChip tone="neutral">{memberName(c.memberId)}</StatusChip> : null}
                </span>
                <span className={clsx(T.bodyStrong, 'dt-need__title')}>{text(c.title)}</span>
                <span className={T.small}>{c.line}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {cards.length ? (
        <Link to="/waiting" className="desk-link dt-needs__all">
          {C.needsAll} ›
        </Link>
      ) : null}
    </section>
  );
}
