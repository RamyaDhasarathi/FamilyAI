// Waiting on you, /waiting (MASTER_AGENT.md §7 Phase 3, §3.3 principles 1–4,
// §10 copy; FamilyOS.mp4 4:20–4:40, frames f_053–f_055). Top: what was
// missed (nobody decided before its date). Then the undecided proposals,
// worst first: Overdue / This week / Later / No date, each row with its kind,
// due, person, "the notice", Accept and ✕, and honest state lines (missed,
// changed, clashes). Right rail: To-dos, Worth doing, You will be told.
// Accept moves the item to its agent (the store does it and writes the audit
// row); the toast offers Undo. Nothing here pays.
import { useMemo } from 'react';
import { Link } from 'react-router';
import { Hourglass } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow, useWaiting } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';

import { DeskPage } from '../shell/DeskPage';
import { MissedCard, WaitingRow } from './WaitingRow';
import { TodoCard, ToldCard, WorthCard } from './WaitingRail';
import { byText, dueText, findClashes, stateLines, todoRail, toldItems, worthDoing } from './waitingModel';
import './waiting.css';

const WAITING_DESCRIPTION = 'Proposed from notices you can see. Nothing here has been agreed to yet, and nothing here pays.';

export default function WaitingPage() {
  const now = useNow();
  const f = useDeskFormat(now);
  const view = useWaiting(now);
  const members = useDesk((s) => s.members);
  const proposals = useDesk((s) => s.proposals);
  const agenda = useDesk((s) => s.agenda);
  const todos = useDesk((s) => s.todos);
  const notices = useDesk((s) => s.notices);
  const recurring = useDesk((s) => s.recurring);
  const plans = useDesk((s) => s.plans);
  const clashes = useMemo(() => findClashes({ proposals, agenda, todos }, now, f.tz), [proposals, agenda, todos, now, f.tz]);
  const rail = useMemo(() => todoRail({ todos }, now, f.tz), [todos, now, f.tz]);
  const worth = useMemo(() => worthDoing({ recurring, plans }, now, f.tz), [recurring, plans, now, f.tz]);
  const told = useMemo(() => toldItems({ notices, proposals }, now), [notices, proposals, now]);
  const name = (id?: string) => memberName({ members }, id);
  const grouped = view.count - view.missed.length;

  return (
    <DeskPage
      icon={Hourglass}
      color={colors.severity.headsup}
      title="Waiting on you"
      description={WAITING_DESCRIPTION}
      className="wt-page"
      actions={
        <Link to="/inbox?show=all" className="pill pill--secondary">
          All notices
        </Link>
      }
      rail={
        <>
          <TodoCard open={rail.open} doneToday={rail.doneToday} by={(t) => byText(t, now, f.tz)} name={name} text={f.text} />
          <WorthCard items={worth} text={f.text} />
          <ToldCard notices={told} ago={f.ago} text={f.text} />
        </>
      }
    >
      {view.missed.length ? (
        <MissedCard rows={view.missed.map((p) => ({ p, title: f.text(p.title), when: p.due ? f.day(p.due).replace(/^(Today|Tomorrow|Yesterday)$/, (w) => w.toLowerCase()) : 'no date' }))} more={grouped} />
      ) : null}
      {view.count === 0 ? (
        <p className={`${T.small} desk-empty`}>Nothing is waiting on anyone. New notices will be read into proposals here.</p>
      ) : null}
      <div id="waiting-groups" className="wt-groups">
        {view.groups
          .filter((g) => g.items.length)
          .map((g) => (
            <section key={g.id} aria-labelledby={`wt-g-${g.id}`} className="wt-group">
              <h2 id={`wt-g-${g.id}`} className={`${T.section} wt-group__label wt-group__label--${g.id}`}>
                {g.label} <span className="wt-group__count">· {g.items.length}</span>
              </h2>
              <ul className="wt-rows">
                {g.items.map((p) => (
                  <WaitingRow
                    key={p.id}
                    p={p}
                    title={f.text(p.title)}
                    meta={`${p.kind} · ${dueText(p, f.tz, f.today)}`}
                    person={p.forMemberId ? name(p.forMemberId) : undefined}
                    lines={stateLines(p, now, f.tz, clashes.get(p.id))}
                  />
                ))}
              </ul>
            </section>
          ))}
      </div>
    </DeskPage>
  );
}
