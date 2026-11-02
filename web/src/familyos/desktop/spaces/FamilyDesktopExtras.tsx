// Desktop-only additions under the existing Family hub, /family
// (MASTER_AGENT.md §7 Phase 4 "Our family"; FamilyOS.mp4 2:20, frames
// f_029–f_030): space tiles (School "N upcoming", Health "N to see", Travel,
// Money "N bills", Investments → their pages), This week (every space, with
// honest state lines, "everything waiting" → Waiting on you), Spent here and
// Charges again. FamilyHub renders it only on desktop; it also checks the
// gate itself, so below 1024 px it renders nothing. The mobile hub above is
// untouched.
import { useMemo } from 'react';
import { Link } from 'react-router';
import { T } from '../../theme/typography';
import { useIsDesktopWeb } from '../../hooks/useIsDesktopWeb';
import { useDesk } from '../../desk/store';
import { useNow } from '../../desk/hooks';
import type { SpaceId } from '../../desk/types';
import { Section, Timeline } from './SpaceParts';
import { ChargesAgainCard, SpentHereCard } from './RailParts';
import { upcoming, upcomingBills } from './spaceModel';
import { useDecide, useTimeline } from './useSpace';
import { SPACE_COLORS, SPACE_ICONS } from './spaceIcons';
import { familyCopy, spaceCopy } from './copy';
import './spaces.css';

const F = familyCopy;
const WEEK_MAX = 10;

export default function FamilyDesktopExtras() {
  const desk = useIsDesktopWeb();
  return desk ? <OurFamily /> : null;
}

function OurFamily() {
  const now = useNow();
  const week = useTimeline('all', now, 0, 6);
  return (
    <section className="sp-family" aria-label={F.label}>
      <SpaceTiles now={now} />
      <Section
        title={F.week}
        action={
          <Link to="/waiting" className="desk-link">
            {F.weekAll} ›
          </Link>
        }
      >
        <Timeline entries={week} now={now} empty={spaceCopy.comingEmpty.all} label={F.week} max={WEEK_MAX} />
        {week.length > WEEK_MAX ? (
          <Link to="/agents/calendar" className="desk-link sp-more">
            {F.weekMore(week.length - WEEK_MAX)} ›
          </Link>
        ) : null}
      </Section>
      <div className="sp-family__pair">
        <SpentHereCard scope="all" now={now} />
        <ChargesAgainCard scope="all" now={now} />
      </div>
    </section>
  );
}

function SpaceTiles({ now }: { now: Date }) {
  const spaces = useDesk((s) => s.spaces);
  const plans = useDesk((s) => s.plans);
  const recurring = useDesk((s) => s.recurring);
  const statements = useDesk((s) => s.statements);
  const tz = useDesk((s) => s.settings.timezone);
  const school = useTimeline('education', now);
  const health = useDecide(now, { scope: 'health' });
  const invest = useDecide(now, { scope: 'investments' });
  const bills = useMemo(() => upcomingBills(recurring, now, tz).length, [recurring, now, tz]);
  const trip = plans.find((p) => p.status === 'draft') ?? plans[0];
  const tiles: { id: SpaceId; line: string }[] = [
    { id: 'education', line: F.tiles.education(upcoming(school).length) },
    { id: 'health', line: F.tiles.health(health.items.length) },
    { id: 'travel', line: F.tiles.travel(trip?.title) },
    { id: 'finance', line: F.tiles.finance(bills) },
    { id: 'investments', line: F.tiles.investments(invest.items.length, statements.length) },
  ];
  return (
    <ul className="sp-tiles">
      {tiles.map((t) => {
        const meta = spaces.find((x) => x.id === t.id);
        const Icon = SPACE_ICONS[t.id];
        const name = meta?.name ?? t.id;
        const to = meta?.route ?? '/';
        return (
          <li key={t.id}>
            <Link to={to} className="sp-tile card" aria-label={F.tileLabel(name, t.line)}>
              <span className="sp-icon sp-icon--lg" style={{ color: meta?.color ?? SPACE_COLORS[t.id] }} aria-hidden>
                <Icon size={17} strokeWidth={1.9} />
              </span>
              <span className="sp-tile__text" aria-hidden>
                <span className={T.smallStrong}>{name}</span>
                <span className={T.small}>{t.line}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
