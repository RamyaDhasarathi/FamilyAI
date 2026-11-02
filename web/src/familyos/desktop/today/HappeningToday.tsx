// "HAPPENING TODAY" (MASTER_AGENT.md §7 Phase 1 "Today dashboard" right
// column): filter pills All + the five agents (with dots), one list by time
// (time · dot · SMALL-CAPS agent · title), untimed rows under "Anytime
// today", each row with Details ▾ (key / value, Ask about this, Open
// {Agent}, the notice it came from), and the calm empty state.
import { useId, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import type { AgentId } from '../../theme/tokens';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { agentNames, copy } from '../../mocks/data';
import { scenarioThemes } from '../../theme/stateThemes';
import { Dot } from '../../components/Labels';
import { PillButton } from '../../components/Pills';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import type { DayRow } from '../../desk/selectors';
import { askPath } from '../shell/routes';
import { useDeskUI } from '../shell/useDeskUI';
import { deskCopy } from '../copy';

const C = deskCopy.today;
const FILTERS: AgentId[] = ['household', 'education', 'finance', 'grocery', 'calendar'];

export function HappeningToday({ rows, now, text }: { rows: DayRow[]; now: Date; text: (s: string) => string }) {
  const [filter, setFilter] = useState<AgentId | 'all'>('all');
  const shown = filter === 'all' ? rows : rows.filter((r) => r.agent === filter);
  const timed = shown.filter((r) => r.timed);
  const anytime = shown.filter((r) => !r.timed);
  return (
    <section className="dt-happening card" aria-labelledby="dt-happening">
      <div className="dt-happening__head">
        <h2 id="dt-happening" className={T.section}>
          {C.happening}
        </h2>
        <div className="dt-filters" role="group" aria-label="Show items from">
          <button type="button" className={clsx('dt-filter', filter === 'all' && 'is-on')} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
            {C.filterAll}
          </button>
          {FILTERS.map((a) => (
            <button key={a} type="button" className={clsx('dt-filter', filter === a && 'is-on')} aria-pressed={filter === a} onClick={() => setFilter(a)}>
              <Dot color={colors.agents[a]} size={6} />
              {agentNames[a]}
            </button>
          ))}
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="desk-empty">
          <Dot color={scenarioThemes.calm.dot} size={7} style={{ boxShadow: `0 0 8px ${scenarioThemes.calm.dot}` }} />
          <span className={T.small}>{filter === 'all' ? C.empty : C.emptyFiltered(filter)}</span>
        </p>
      ) : (
        <>
          {timed.length ? (
            <ul className="dt-rows">
              {timed.map((r) => (
                <Row key={r.id} row={r} now={now} text={text} />
              ))}
            </ul>
          ) : null}
          {anytime.length ? (
            <>
              <p className={clsx(T.section, 'dt-anytime')}>{C.anytime}</p>
              <ul className="dt-rows">
                {anytime.map((r) => (
                  <Row key={r.id} row={r} now={now} text={text} />
                ))}
              </ul>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}

function Row({ row, now, text }: { row: DayRow; now: Date; text: (s: string) => string }) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  const navigate = useNavigate();
  const panel = useId();
  const flash = useDeskUI((s) => s.flash.includes(row.id));
  const color = colors.agents[row.agent];
  const past = row.done || (row.timed && new Date(row.end ?? row.at!).getTime() <= now.getTime());
  const title = text(row.title);
  return (
    <li className={clsx('dt-row', past && 'is-past', flash && 'desk-flash')} data-desk-id={row.id} style={{ ['--desk-flash-color' as string]: color }}>
      <button type="button" className="dt-row__head" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)}>
        <span className={clsx(T.smallStrong, 'dt-row__time')}>{row.timed ? row.slot : '—'}</span>
        <Dot color={color} size={7} style={{ boxShadow: `0 0 8px ${color}` }} />
        <span className="dt-row__main">
          <span className={clsx(T.meta, 'dt-row__agent')} style={{ color }}>
            {agentNames[row.agent].toUpperCase()}
            {row.label ? <span className="dt-row__label">{row.label}</span> : null}
            {past ? <span className="sr-only">, done</span> : null}
          </span>
          <span className={clsx(T.body, 'dt-row__title')}>{title}</span>
        </span>
        <span className={clsx(T.small, 'dt-row__more')}>
          {C.details}
          <motion.span className="dt-row__chev" animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown size={13} aria-hidden />
          </motion.span>
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={panel}
            key="details"
            className="dt-row__details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0.1 : 0.24, ease: [0.33, 1, 0.68, 1] }}
          >
            {row.details.length ? (
              <dl className="timeline-item__rows">
                {row.details.map(([k, v]) => (
                  <div key={k} className="timeline-item__row">
                    <dt className={T.small}>{k}</dt>
                    <dd className={T.smallStrong}>{text(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <div className="dt-row__actions">
              <PillButton label={copy.askAboutThis} onClick={() => navigate(askPath(copy.tellMeMore(title)))} />
              <PillButton label={C.open(row.agent)} variant="primary" onClick={() => navigate(`/agents/${row.agent}`)} />
              {row.noticeId ? (
                <Link to={`/inbox/${row.noticeId}`} className="desk-link dt-row__notice">
                  {C.fromNotice} ›
                </Link>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </li>
  );
}
