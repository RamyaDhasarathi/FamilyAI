// Spaces on one template: Health, Travel, Memories — /health, /travel,
// /memories (MASTER_AGENT.md §7 Phase 4, §3.2; FamilyOS.mp4 2:40–2:55 and
// 9:30–10:40 for the School space this template follows, 3:00 Travel).
// Header: icon, title, "{n} notices · {m} dated" and one honest sentence;
// Travel adds its Trips list ("draft · N to book · N to do"); then Coming up
// (honest state lines) and What arrived. Right rail: Spent here and the
// space's own card — Health "To decide" (✓ / ✕), Travel "Pages you are
// watching", Memories "How memories are kept". The Ask bar is the shell's.
import { Link } from 'react-router';
import clsx from 'clsx';
import { Plane } from 'lucide-react';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { askPath } from '../shell/routes';
import { Section, Timeline, WhatArrived } from './SpaceParts';
import { DecideCard, SpentHereCard } from './RailParts';
import { useArrived, useDecide, useSpaceCounts, useSpaceMeta, useTimeline } from './useSpace';
import { tripView } from './listModels';
import { SPACE_COLORS, SPACE_ICONS } from './spaceIcons';
import { spaceCopy } from './copy';

const C = spaceCopy;
type SpaceKey = 'health' | 'travel' | 'memories';

export default function SpacePage({ space }: { space: SpaceKey }) {
  const now = useNow();
  const meta = useSpaceMeta(space);
  const counts = useSpaceCounts(space);
  const entries = useTimeline(space, now);
  const arrived = useArrived(space);
  const name = meta?.name ?? space;
  const color = meta?.color ?? SPACE_COLORS[space];
  return (
    <DeskPage
      className="sp-page"
      icon={SPACE_ICONS[space]}
      color={color}
      title={name}
      metaTitle={`${name} · FamilyOS`}
      description={
        <>
          <span className="sp-counts">{C.counts(counts.notices, counts.dated)}</span>
          {meta?.description}
        </>
      }
      rail={
        <>
          <SpentHereCard scope={space} now={now} />
          {space === 'health' ? <HealthDecide now={now} /> : space === 'travel' ? <WatchingCard now={now} /> : <KeptCard />}
        </>
      }
    >
      {space === 'travel' ? <Trips now={now} color={color} /> : null}
      <Section title={C.coming}>
        <Timeline entries={entries} now={now} empty={C.comingEmpty[space]} label={`${C.coming} in ${name}`} />
      </Section>
      <Section title={C.arrived} sub={arrived.length ? C.plural(arrived.length, 'notice') : undefined}>
        <WhatArrived items={arrived} now={now} empty={C.arrivedEmpty(name)} />
      </Section>
    </DeskPage>
  );
}

/** Travel: the family's trips, each opening its plan. */
function Trips({ now, color }: { now: Date; color: string }) {
  const plans = useDesk((s) => s.plans);
  const todos = useDesk((s) => s.todos);
  const members = useDesk((s) => s.members);
  const f = useDeskFormat(now);
  const action = (
    <Link className="pill pill--secondary sp-pill-sm" to={askPath(C.planTripAsk)}>
      {C.planTrip}
    </Link>
  );
  return (
    <Section title={C.trips} sub={plans.length ? C.plural(plans.length, 'trip') : undefined} action={action}>
      {plans.length ? (
        <ul className="sp-trips">
          {plans.map((p) => {
            const v = tripView(p, todos);
            return (
              <li key={p.id}>
                <Link to={`/plans/${p.id}`} className="sp-row-link sp-trip">
                  <span className="sp-icon sp-icon--lg" style={{ color }} aria-hidden>
                    <Plane size={18} strokeWidth={1.9} />
                  </span>
                  <span className="sp-trip__text">
                    <span className="sp-trip__title">
                      <span className={T.bodyStrong}>{p.title}</span>
                      <StatusChip tone={p.status === 'draft' ? 'draft' : p.status === 'done' ? 'done' : 'cancelled'}>{p.status}</StatusChip>
                    </span>
                    <span className={T.small}>
                      {fmtShortDay(p.start)} – {fmtShortDay(p.end)} · {f.money(p.budget)} · by {memberName({ members }, p.authorId)}
                    </span>
                    <span className="sp-chips">
                      {C.tripChips(v.toBook, v.toDo).map((c) => (
                        <span key={c} className="chip chip--small">
                          {c}
                        </span>
                      ))}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className={clsx(T.small, 'desk-empty')}>{C.tripsEmpty}</p>
      )}
    </Section>
  );
}

function HealthDecide({ now }: { now: Date }) {
  const { items, missed } = useDecide(now, { scope: 'health' });
  return <DecideCard title={C.decideTitle} items={items} missed={missed} now={now} empty={C.decideEmpty} />;
}

/** Travel: read-only page watchers (prices and rates); stopping one lives in Settings. */
function WatchingCard({ now }: { now: Date }) {
  const watchers = useDesk((s) => s.watchers);
  const f = useDeskFormat(now);
  const mine = watchers.filter((w) => w.spaceId === 'travel' && w.status === 'watching');
  return (
    <DeskCard title={C.watching}>
      {mine.length ? (
        <ul className="sp-watch">
          {mine.map((w) => (
            <li key={w.id}>
              <a className="sp-row-link sp-watch__row" href={w.url} target="_blank" rel="noopener noreferrer">
                <span className={T.smallStrong}>{w.label}&nbsp;↗</span>
                <span className={T.small}>{C.watchLine(w.lastChecked ? f.ago(w.lastChecked) : 'not yet')}</span>
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className={T.small}>{C.watchingEmpty}</p>
      )}
    </DeskCard>
  );
}

/** Memories: where photos stay, and whether the model reads them (a household toggle). */
function KeptCard() {
  const on = useDesk((s) => s.toggles.find((t) => t.id === 'picturesByModel')?.on ?? false);
  return (
    <DeskCard title={C.kept} className="sp-explain">
      <div className="sp-explain__body">
        <p className={T.small}>{on ? C.keptOn : C.keptOff}</p>
        <Link to="/settings/household" className="desk-link">
          {C.keptLink} ›
        </Link>
      </div>
    </DeskCard>
  );
}
