// Today dashboard, /today — the centre crystal (MASTER_AGENT.md §7 Phase 1
// "Today dashboard" + Phase 2.4; FamilyOS.mp4 0:25, 1:50, 10:50 for the
// reference Today). Back ‹ and a small crystal on top, "Today" with the
// five-agent underline; member cards; FamilyOS noticed; the hero and agent
// chips beside HAPPENING TODAY; Needs someone · worst first; right rail
// Coming up and Order again. Everything reads the one desk store; nothing
// changes without a Confirm click.
import { useMemo } from 'react';
import { AGENT_IDS, colors } from '../../theme/tokens';
import { useDesk } from '../../desk/store';
import { useComingUp, useDeskFormat, useNeedsSomeone, useNow, useTodayItems } from '../../desk/hooks';
import { fmtLongDay, fmtShortDay } from '../../desk/format';
import { memberName, openConflicts } from '../../desk/selectors';
import { DeskPage } from '../shell/DeskPage';
import { deskCopy } from '../copy';
import { TodayHero } from './TodayHero';
import { HappeningToday } from './HappeningToday';
import { MemberCards, NeedsSomeone, NoticedCard } from './TodayFamily';
import { TodayRail } from './TodayRail';
import './today.css';

const C = deskCopy.today;
const UNDERLINE = `linear-gradient(90deg, ${AGENT_IDS.map((id) => colors.agents[id]).join(', ')})`;

export default function TodayPage() {
  const now = useNow();
  const f = useDeskFormat(now);
  const rows = useTodayItems(now);
  const needs = useNeedsSomeone(now);
  const coming = useComingUp(now);
  const members = useDesk((s) => s.members);
  const conflicts = useDesk((s) => s.conflicts);
  const orderAgain = useDesk((s) => s.orderAgain);
  const conflict = useMemo(() => openConflicts({ conflicts })[0] ?? [...conflicts].filter((c) => c.resolvedAt).sort((a, b) => b.resolvedAt!.localeCompare(a.resolvedAt!))[0], [conflicts]);
  const name = (id?: string) => memberName({ members }, id);
  const tomorrow = coming.find((d) => d.label === 'Tomorrow');

  return (
    <DeskPage
      className="dt-page"
      title={C.title}
      description={C.subtitle(fmtLongDay(f.today), rows.length)}
      underline={UNDERLINE}
      back="/"
      gem
      metaTitle="Today · FamilyOS"
      rail={<TodayRail days={coming} orderAgain={orderAgain} memberName={name} money={f.money} text={f.text} shortDay={fmtShortDay} />}
    >
      <MemberCards members={members} />
      {conflict ? <NoticedCard key={conflict.id} conflict={conflict} /> : null}
      <div className="dt-grid">
        <TodayHero rows={rows} now={now} tomorrow={tomorrow} text={f.text} time={(i) => f.time(i)} />
        <HappeningToday rows={rows} now={now} text={f.text} />
      </div>
      <NeedsSomeone cards={needs} memberName={name} day={f.day} slot={f.slot} text={f.text} />
    </DeskPage>
  );
}
