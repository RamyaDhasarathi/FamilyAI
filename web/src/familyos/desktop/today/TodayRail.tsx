// Today, right rail (MASTER_AGENT.md §7 Phase 2.4; FamilyOS.mp4 1:50–2:00):
// "Coming up" grouped by day (time, or all day / EOD / not specified;
// undecided proposals marked), and Grocery's "Order again · from your
// receipts" (item, store, last date, price, Order ↗ to the store's page —
// nothing is ordered from here). Every row links to its notice.
import { Link } from 'react-router';
import clsx from 'clsx';
import { ArrowUpRight } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { Dot } from '../../components/Labels';
import type { ComingDay } from '../../desk/selectors';
import type { OrderAgainItem } from '../../desk/types';
import { DeskCard } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { deskCopy } from '../copy';

const C = deskCopy.today;

interface Props {
  days: ComingDay[];
  orderAgain: OrderAgainItem[];
  memberName: (id?: string) => string;
  money: (n: number) => string;
  text: (s: string) => string;
  shortDay: (d: string) => string;
}

/** The first `max` entries across the days, keeping the day groups. */
function firstEntries(days: ComingDay[], max: number): ComingDay[] {
  const out: ComingDay[] = [];
  let left = max;
  for (const d of days) {
    if (left <= 0) break;
    const entries = d.entries.slice(0, left);
    left -= entries.length;
    out.push({ ...d, entries });
  }
  return out;
}

export function TodayRail({ days, orderAgain, memberName, money, text, shortDay }: Props) {
  const flash = useDeskUI((s) => s.flash);
  const shown = firstEntries(days, 12);
  return (
    <>
      <DeskCard title={C.coming} className="dt-coming">
        {days.length === 0 ? <p className={T.small}>{C.comingEmpty}</p> : null}
        {shown.map((d) => {
          const entries = d.entries;
          return (
            <div key={d.day} className="dt-coming__day">
              <p className={clsx(T.section, 'dt-coming__label')}>{d.label}</p>
              <ul>
                {entries.map((e) => {
                  const who = e.memberIds.map((id) => memberName(id)).join(', ');
                  const inner = (
                    <>
                      <span className={clsx(T.small, 'dt-coming__slot')}>{e.slot}</span>
                      <span className="dt-coming__text">
                        <span className={T.smallStrong}>
                          <Dot color={colors.agents[e.agent]} size={6} className="dt-coming__dot" />
                          {text(e.title)}
                        </span>
                        {who || e.undecided ? (
                          <span className={clsx(T.small, 'dt-coming__sub')}>
                            {who}
                            {who && e.undecided ? ' · ' : ''}
                            {e.undecided ? `(${C.undecided})` : ''}
                          </span>
                        ) : null}
                      </span>
                    </>
                  );
                  return (
                    <li key={e.id} data-desk-id={e.id} className={clsx('dt-coming__row', flash.includes(e.id) && 'desk-flash')} style={{ ['--desk-flash-color' as string]: colors.agents[e.agent] }}>
                      {e.noticeId ? (
                        <Link to={`/inbox/${e.noticeId}`} className="dt-coming__link">
                          {inner}
                        </Link>
                      ) : (
                        <span className="dt-coming__link">{inner}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </DeskCard>
      {orderAgain.length ? (
        <DeskCard title={C.orderAgain} sub={C.orderAgainSub} className="dt-order">
          <ul>
            {orderAgain.map((o) => (
              <li key={o.id} className="dt-order__row">
                <span className="dt-order__text">
                  <span className={T.smallStrong}>{text(o.item)}</span>
                  <span className={T.small}>
                    <Link to={`/inbox/${o.noticeId}`} className="dt-order__store">
                      {o.store}
                    </Link>{' '}
                    · {C.lastOrdered(shortDay(o.lastDate))} · {money(o.price)}
                  </span>
                </span>
                <a className="pill pill--secondary dt-order__btn" href={o.url} target="_blank" rel="noopener noreferrer" aria-label={`${C.order} ${o.item} again at ${o.store} (opens the store’s page)`}>
                  {C.order}
                  <ArrowUpRight size={13} aria-hidden />
                </a>
              </li>
            ))}
          </ul>
        </DeskCard>
      ) : null}
    </>
  );
}
