// Finance dashboard, desktop sections (MASTER_AGENT.md §4 Finance ↔ Money +
// Investments, §7 Phase 4; FamilyOS.mp4 3:30 Money, 3:40 Investments):
// the Money ↔ Investments tabs; stat cards (spent last 30 days · charges,
// bills due this week, subscriptions next round, to order again); Recurring ·
// N merchants that charge again (kind chip, cadence, last / next, amount, ↗
// to the merchant's own page); Bills due this week with honest state lines;
// rail Due soon and What this is. Nothing here pays or changes anything.
import { useMemo } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { ArrowUpRight, CalendarClock, Receipt, Repeat, ShoppingBasket, type LucideIcon } from 'lucide-react';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import { StatusChip } from '../shell/DeskPage';
import { ExtrasLayout, Explainer, MoneyTabs, Section, Timeline } from './SpaceParts';
import { DueSoonCard } from './RailParts';
import { billsThisWeek, moneyStats } from './spaceModel';
import { useTimeline } from './useSpace';
import { SPACE_COLORS } from './spaceIcons';
import { extrasCopy } from './copy';

const X = extrasCopy;

/** "due today", "next tomorrow", "next Saturday", "next Nov 7", or "was due Oct 26". */
function nextLine(next: string, today: string, rel: string): string {
  if (next < today) return X.wasDue(fmtShortDay(next));
  if (next === today) return X.dueToday;
  return `next ${rel === 'Tomorrow' ? 'tomorrow' : rel}`;
}

function Stat({ icon: Icon, value, label, to }: { icon: LucideIcon; value: string; label: string; to?: string }) {
  const body = (
    <>
      <span className="sp-icon" aria-hidden>
        <Icon size={15} strokeWidth={1.9} />
      </span>
      <span className="sp-stat__text">
        <span className={T.stat}>{value}</span>
        <span className={T.small}>{label}</span>
      </span>
    </>
  );
  return <li>{to ? <Link to={to} className="sp-stat card sp-stat--link">{body}</Link> : <div className="sp-stat card">{body}</div>}</li>;
}

export function FinanceExtras({ now }: { now: Date }) {
  const f = useDeskFormat(now);
  const recurring = useDesk((s) => s.recurring);
  const orderAgain = useDesk((s) => s.orderAgain);
  const tz = useDesk((s) => s.settings.timezone);
  const stats = useMemo(() => moneyStats(recurring, now, tz), [recurring, now, tz]);
  const week = useTimeline('all', now, 0, 6);
  const bills = useMemo(() => billsThisWeek(week), [week]);
  const rows = useMemo(() => [...recurring].sort((a, b) => a.next.localeCompare(b.next) || b.amount - a.amount), [recurring]);

  const main = (
    <>
      <Section title={X.recurring} sub={X.recurringSub(rows.length)}>
        <ul className="sp-rec">
          {rows.map((r) => (
            <li key={r.id} className="sp-rec__row">
              <span className="sp-avatar sp-avatar--sq" style={{ color: SPACE_COLORS[r.spaceId] }} aria-hidden>
                {r.merchant.charAt(0)}
              </span>
              <Link to={`/inbox/${r.noticeId}`} className="sp-row-link sp-rec__text">
                <span className="sp-rec__name">
                  <span className={T.smallStrong}>{r.merchant}</span>
                  <StatusChip tone="neutral">{X.kind[r.kind]}</StatusChip>
                </span>
                <span className={T.small}>
                  {X.cadence[r.cadence]} · last {fmtShortDay(r.last)} {f.money(r.amount)}
                </span>
              </Link>
              <span className="sp-rec__amt">
                <span className={T.smallStrong}>{f.money(r.amount)}</span>
                <span className={clsx(T.small, 'sp-rec__next')}>{nextLine(r.next, f.today, f.day(r.next))}</span>
              </span>
              <a className="sp-iconbtn" href={r.url} target="_blank" rel="noopener noreferrer" aria-label={X.openSite(r.merchant)} title={X.openSite(r.merchant)}>
                <ArrowUpRight size={14} aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      </Section>
      <Section title={X.bills} sub={bills.length ? String(bills.length) : undefined}>
        <Timeline entries={bills} now={now} empty={X.billsEmpty} label={X.bills} />
      </Section>
    </>
  );

  return (
    <ExtrasLayout
      head={
        <>
          <MoneyTabs current="money" />
          <ul className="sp-stats" aria-label="Money at a glance">
            <Stat icon={Receipt} value={f.money(stats.spent.total)} label={X.statSpent(stats.spent.count)} />
            <Stat icon={CalendarClock} value={String(bills.length)} label={X.statBills(bills.length)} />
            <Stat icon={Repeat} value={f.money(stats.subscriptionsNext)} label={X.statSubs} />
            <Stat icon={ShoppingBasket} value={String(orderAgain.length)} label={X.statReorder} to="/agents/grocery" />
          </ul>
        </>
      }
      main={main}
      rail={
        <>
          <DueSoonCard now={now} />
          <Explainer title={X.what}>
            {X.whatText.map((p) => (
              <p key={p} className={T.small}>
                {p}
              </p>
            ))}
          </Explainer>
        </>
      }
    />
  );
}
