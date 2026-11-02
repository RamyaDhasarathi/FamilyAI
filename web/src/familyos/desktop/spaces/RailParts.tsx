// Right-rail cards of the space template (MASTER_AGENT.md §7 Phase 4;
// FamilyOS.mp4 2:20 Spent here / Charges again, 2:40 The children, 3:30 Due
// soon, 3:50 Dates spotted ✓ / ✕). Money rows link to their notices; the
// only actions are Accept / Dismiss, each a person's click, each with Undo
// and each writing an audit row in the store.
import { useMemo } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { Check, Receipt, X } from 'lucide-react';
import { T } from '../../theme/typography';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import type { Proposal, RecurringMerchant } from '../../desk/types';
import { DeskCard, StatusChip } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { chargesAgain, dueSoon, spentHere, type Scope } from './spaceModel';
import { spaceCopy, extrasCopy } from './copy';

const C = spaceCopy;

function MoneyRows({ rows, date, money }: { rows: RecurringMerchant[]; date: (r: RecurringMerchant) => string; money: (n: number) => string }) {
  return (
    <ul className="sp-money">
      {rows.map((r) => (
        <li key={r.id}>
          <Link to={`/inbox/${r.noticeId}`} className="sp-row-link sp-money__row">
            <span className={clsx(T.small, 'sp-money__name')}>{r.merchant}</span>
            <span className={clsx(T.small, 'sp-money__date')}>{date(r)}</span>
            <span className={clsx(T.smallStrong, 'sp-money__amt')}>{money(r.amount)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Spent here: what mail saw charged in this space over the last 30 days. */
export function SpentHereCard({ scope, now, max = 6 }: { scope: Scope; now: Date; max?: number }) {
  const recurring = useDesk((s) => s.recurring);
  const tz = useDesk((s) => s.settings.timezone);
  const f = useDeskFormat(now);
  const c = useMemo(() => spentHere(recurring, scope, now, tz), [recurring, scope, now, tz]);
  return (
    <DeskCard title={C.spent} className="sp-spent">
      {c.count ? (
        <>
          <p className="sp-spent__total">
            <span className="sp-icon" aria-hidden>
              <Receipt size={15} strokeWidth={1.9} />
            </span>
            <span className="sp-spent__text">
              <span className={T.stat}>{f.money(c.total)}</span>
              <span className={T.small}>{C.spentSub(c.count)}</span>
            </span>
          </p>
          <MoneyRows rows={c.rows.slice(0, max)} date={(r) => fmtShortDay(r.last)} money={f.money} />
        </>
      ) : (
        <p className={T.small}>{C.spentEmpty}</p>
      )}
    </DeskCard>
  );
}

/** Charges again: the next charge of each recurring merchant, soonest first. */
export function ChargesAgainCard({ scope, now, max = 6 }: { scope: Scope; now: Date; max?: number }) {
  const recurring = useDesk((s) => s.recurring);
  const tz = useDesk((s) => s.settings.timezone);
  const f = useDeskFormat(now);
  const rows = useMemo(() => chargesAgain(recurring, scope, now, tz), [recurring, scope, now, tz]);
  return (
    <DeskCard title={C.chargesAgain} sub={rows.length ? C.plural(rows.length, 'merchant') : undefined}>
      {rows.length ? <MoneyRows rows={rows.slice(0, max)} date={(r) => f.day(r.next)} money={f.money} /> : <p className={T.small}>{C.chargesEmpty}</p>}
    </DeskCard>
  );
}

/** Due soon (Money rail): next charges within two weeks. */
export function DueSoonCard({ now }: { now: Date }) {
  const recurring = useDesk((s) => s.recurring);
  const tz = useDesk((s) => s.settings.timezone);
  const f = useDeskFormat(now);
  const rows = useMemo(() => dueSoon(recurring, now, tz), [recurring, now, tz]);
  return (
    <DeskCard title={extrasCopy.dueSoon}>
      {rows.length ? <MoneyRows rows={rows} date={(r) => f.day(r.next)} money={f.money} /> : <p className={T.small}>{extrasCopy.dueSoonEmpty}</p>}
    </DeskCard>
  );
}

/** The children (School): name, school, grade, homeroom; opens their profile. */
export function ChildrenCard() {
  const children = useDesk((s) => s.children);
  const members = useDesk((s) => s.members);
  return (
    <DeskCard title={C.children}>
      <ul className="sp-people">
        {children.map((c) => {
          const m = members.find((x) => x.id === c.memberId);
          return (
            <li key={c.memberId}>
              <Link to={`/family/${c.memberId}`} className="sp-row-link sp-person">
                <span className="sp-avatar" aria-hidden>
                  {m?.initial ?? '?'}
                </span>
                <span className="sp-person__text">
                  <span className={T.smallStrong}>{m?.fullName ?? c.memberId}</span>
                  <span className={T.small}>{C.childLine(c.school, c.grade)}</span>
                  <span className={clsx(T.small, 'sp-person__more')}>{C.childMore(c.homeroom, c.teacher)}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </DeskCard>
  );
}

/** Dates spotted / To decide: undecided proposals with ✓ Accept and ✕ Dismiss. */
export function DecideCard({ title, items, missed, now, empty }: { title: string; items: Proposal[]; missed: number; now: Date; empty: string }) {
  const f = useDeskFormat(now);
  const members = useDesk((s) => s.members);
  const accept = useDesk((s) => s.acceptProposal);
  const dismiss = useDesk((s) => s.dismissProposal);
  const undo = useDesk((s) => s.undoProposal);
  const flash = useDeskUI((s) => s.flash);
  const decide = (p: Proposal, yes: boolean) => {
    const title = f.text(p.title);
    if (!(yes ? accept(p.id) : dismiss(p.id))) return;
    useFamilyOS.getState().toast(yes ? C.accepted(title) : C.dismissed(title), { action: { label: C.undo, onPress: () => undo(p.id) }, duration: 5000 });
  };
  return (
    <DeskCard title={title} sub={items.length ? extrasCopy.datesSub(items.length) : undefined} className="sp-decide">
      {items.length ? (
        <ul>
          {items.map((p) => {
            const title = f.text(p.title);
            const who = p.forMemberId ? C.forWho(memberName({ members }, p.forMemberId)) : '';
            return (
              <li key={p.id} className={clsx('sp-decide__row', flash.includes(p.id) && 'desk-flash')} data-desk-id={p.id}>
                <Link to={`/inbox/${p.noticeId}`} className="sp-row-link sp-decide__link">
                  <span className="sp-decide__when">
                    <span className={T.smallStrong}>{p.due ? f.day(p.due) : C.noDate}</span>
                    {p.due ? <span className={T.small}>{f.slot(p.due, p.dueKind)}</span> : null}
                  </span>
                  <span className="sp-decide__text">
                    <span className={T.smallStrong}>{title}</span>
                    <span className={clsx(T.small, 'sp-decide__meta')}>
                      {p.state === 'changed' ? <StatusChip tone="changed">{C.tone.changed}</StatusChip> : null}
                      <span>{[C.kindLabel[p.kind], who].filter(Boolean).join(' · ')}</span>
                    </span>
                  </span>
                </Link>
                <span className="sp-decide__btns">
                  <button type="button" className="sp-iconbtn sp-iconbtn--yes" aria-label={`${C.accept} “${title}”`} title={C.accept} onClick={() => decide(p, true)}>
                    <Check size={14} strokeWidth={2.4} aria-hidden />
                  </button>
                  <button type="button" className="sp-iconbtn" aria-label={`${C.dismiss} “${title}”`} title={C.dismiss} onClick={() => decide(p, false)}>
                    <X size={14} strokeWidth={2.4} aria-hidden />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className={clsx(T.small, 'sp-decide__empty')}>{empty}</p>
      )}
      {missed ? (
        <Link to="/waiting" className="desk-link sp-decide__missed">
          {C.wentBy(missed)} · {C.waitingLink} ›
        </Link>
      ) : null}
    </DeskCard>
  );
}
