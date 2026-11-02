// Today — left column (MASTER_AGENT.md §7 Phase 1 "Today dashboard"): the
// hero ("{n} things today", the next item in its agent's colour, a done /
// remaining ring), the five agent chips that open each dashboard, the
// weather card and the tomorrow-morning card. Copy reused from the mobile
// Today sheet (mocks/data.ts todayBrief).
import { Link } from 'react-router';
import clsx from 'clsx';
import { ChevronRight } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { agentNames, todayBrief as mockBrief } from '../../mocks/data';
import { useFamilyOS } from '../../store/useFamilyOS';
import { TaskRing } from '../../graphics/Charts';
import { Dot } from '../../components/Labels';
import { agentChips, dayProgress, type ComingDay, type DayRow } from '../../desk/selectors';
import { deskCopy } from '../copy';

const C = deskCopy.today;

interface Props {
  rows: DayRow[];
  now: Date;
  tomorrow?: ComingDay;
  text: (s: string) => string;
  time: (i: string) => string;
}

export function TodayHero({ rows, now, tomorrow, text, time }: Props) {
  // The weather and the leave-by line are the Today brief's: the backend's when it is on (contract a), else the mock.
  const todayBrief = useFamilyOS((s) => s.today) ?? mockBrief;
  const p = dayProgress(rows, now);
  const nextColor = p.next ? colors.agents[p.next.agent] : colors.muted;
  const first = tomorrow?.entries.find((e) => e.source === 'agenda' && e.timed);
  return (
    <div className="dt-left">
      <section className="dt-hero card" aria-label={`${C.heroCount(rows.length)}. ${C.ring(p.done, p.remaining)}`}>
        <div className="dt-hero__top">
          <div className="dt-hero__text">
            <p className={clsx(T.heroSmall, 'dt-hero__count')}>{C.heroCount(rows.length)}</p>
            <p className={T.smallStrong} style={{ color: nextColor }}>
              {p.next ? C.next(time(p.next.at!), text(p.next.title)) : C.nothingNext}
            </p>
          </div>
          <TaskRing pct={p.total ? p.done / p.total : 1} color={p.next ? nextColor : colors.done} size={72} stroke={5}>
            <span className={T.stat} style={{ fontSize: '0.95rem' }} aria-hidden>
              {p.done}/{p.total}
            </span>
          </TaskRing>
        </div>
        <p className={clsx(T.small, 'dt-hero__ring')}>{C.ring(p.done, p.remaining)}</p>
        <ul className="dt-chips">
          {agentChips(rows).map((c) => (
            <li key={c.agent}>
              <Link to={`/agents/${c.agent}`} className="dt-chip" aria-label={`${deskCopy.stones.open(c.agent)}: ${text(c.text)}`}>
                <Dot color={colors.agents[c.agent]} size={7} style={{ boxShadow: `0 0 8px ${colors.agents[c.agent]}` }} />
                <span className={clsx(T.smallStrong, 'dt-chip__name')}>{agentNames[c.agent]}</span>
                <span className={clsx(T.small, 'dt-chip__text')}>{text(c.text)}</span>
                <ChevronRight size={14} className="dt-chip__chev" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <section className="dt-tile card" aria-label={`${todayBrief.weather.label}: ${todayBrief.weather.value}`}>
        <p className={T.meta}>{C.weather}</p>
        <p className={clsx(T.heroSmall, 'dt-tile__value')}>{todayBrief.weather.value}</p>
        <p className={T.small}>{todayBrief.weather.detail}</p>
      </section>
      {todayBrief.commute ? (
        <section className="dt-tile card" aria-label={C.tomorrow}>
          <p className={T.meta}>{C.tomorrow}</p>
          <p className={clsx(T.bodyStrong, 'dt-tile__title')}>{todayBrief.commute.title}</p>
          <p className={T.small}>{todayBrief.commute.detail}</p>
          {first ? <p className={clsx(T.small, 'dt-tile__first')}>{C.firstEvent(first.slot, text(first.title))}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
