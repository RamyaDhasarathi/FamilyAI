// Education (School) and Calendar dashboards, desktop sections
// (MASTER_AGENT.md §4, §7 Phase 4; FamilyOS.mp4 2:40–2:55 and 9:30–10:40
// School, 3:50 Dates spotted). School: "{n} notices · {m} dated", Coming up
// with honest state lines, What arrived, rail Spent here and The children.
// Calendar: Coming up grouped by day, rail Dates spotted (✓ accept / ✕
// dismiss — the only changes, each a click, each with Undo).
import { Link } from 'react-router';
import clsx from 'clsx';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { Dot } from '../../components/Labels';
import { useDesk } from '../../desk/store';
import { useComingUp, useDeskFormat } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import { useDeskUI } from '../shell/useDeskUI';
import { ExtrasLayout, Section, Timeline, WhatArrived } from './SpaceParts';
import { ChildrenCard, DecideCard, SpentHereCard } from './RailParts';
import { useArrived, useDecide, useSpaceCounts, useSpaceMeta, useTimeline } from './useSpace';
import { extrasCopy, spaceCopy } from './copy';

const C = spaceCopy;
const X = extrasCopy;

export function SchoolExtras({ now }: { now: Date }) {
  const meta = useSpaceMeta('education');
  const counts = useSpaceCounts('education');
  const entries = useTimeline('education', now);
  const arrived = useArrived('education');
  const name = meta?.name ?? 'School';
  return (
    <ExtrasLayout
      head={
        <p className="sp-x__counts">
          <span className={T.section}>{name}</span>
          <span className={T.small}>{C.counts(counts.notices, counts.dated)}</span>
        </p>
      }
      main={
        <>
          <Section title={C.coming}>
            <Timeline entries={entries} now={now} empty={C.comingEmpty.education} label={`${C.coming} in ${name}`} />
          </Section>
          <Section title={C.arrived} sub={arrived.length ? C.plural(arrived.length, 'notice') : undefined}>
            <WhatArrived items={arrived} now={now} empty={C.arrivedEmpty(name)} max={8} />
          </Section>
        </>
      }
      rail={
        <>
          <SpentHereCard scope="education" now={now} />
          <ChildrenCard />
        </>
      }
    />
  );
}

export function CalendarExtras({ now }: { now: Date }) {
  const days = useComingUp(now, { days: 14, includeToday: true });
  const { items, missed } = useDecide(now, { datedOnly: true });
  const members = useDesk((s) => s.members);
  const flash = useDeskUI((s) => s.flash);
  const f = useDeskFormat(now);
  return (
    <ExtrasLayout
      main={
        <Section title={X.comingByDay} sub={X.comingByDaySub}>
          {days.length ? (
            days.map((d) => (
              <div key={d.day} className="sp-day">
                <p className={clsx(T.section, 'sp-group-label')}>
                  {d.label}
                  {d.label !== fmtShortDay(d.day) ? ` · ${fmtShortDay(d.day)}` : ''}
                </p>
                <ul>
                  {d.entries.map((e) => {
                    const who = e.memberIds.map((id) => memberName({ members }, id)).join(', ');
                    const color = colors.agents[e.agent];
                    const inner = (
                      <>
                        <span className={clsx(T.small, 'sp-dayrow__slot')}>{e.slot}</span>
                        <Dot color={color} size={7} style={{ boxShadow: `0 0 8px ${color}` }} />
                        <span className="sp-dayrow__text">
                          <span className={T.smallStrong}>{f.text(e.title)}</span>
                          {who || e.undecided ? <span className={T.small}>{[who, e.undecided ? X.undecided : ''].filter(Boolean).join(' · ')}</span> : null}
                        </span>
                      </>
                    );
                    return (
                      <li key={e.id} data-desk-id={e.id} className={clsx(flash.includes(e.id) && 'desk-flash')} style={{ ['--desk-flash-color' as string]: color }}>
                        {e.noticeId ? (
                          <Link to={`/inbox/${e.noticeId}`} className="sp-row-link sp-dayrow">
                            {inner}
                          </Link>
                        ) : (
                          <div className="sp-dayrow">{inner}</div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          ) : (
            <p className={clsx(T.small, 'desk-empty')}>{C.comingEmpty.all}</p>
          )}
        </Section>
      }
      rail={<DecideCard title={X.datesSpotted} items={items} missed={missed} now={now} empty={X.datesEmpty} />}
    />
  );
}
