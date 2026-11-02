// A plan, /plans/:id (MASTER_AGENT.md §7 Phase 4 "Travel + Plans", §3.2;
// FamilyOS.mp4 3:00–3:20). Header: status badge (draft / done / dropped),
// dates, budget, author; Mark done / Drop (or Reopen), each through an inline
// confirmation — nothing changes until Confirm, and Undo puts it back. Main:
// the narrative summary with the notice it was written from, Itinerary by
// day, Bookings. Rail: To-dos and "When something is booked".
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import type { Plan } from '../../desk/types';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { Explainer } from './SpaceParts';
import { Bookings, Itinerary, PlanTodos } from './PlanParts';
import { SPACE_COLORS, SPACE_ICONS } from './spaceIcons';
import { planCopy, spaceCopy } from './copy';

const P = planCopy;
type Status = Plan['status'];
const TONE = { draft: 'draft', done: 'done', dropped: 'cancelled' } as const;

export default function PlanPage() {
  const { id } = useParams();
  const plan = useDesk((s) => s.plans.find((p) => p.id === id));
  const members = useDesk((s) => s.members);
  const notices = useDesk((s) => s.notices);
  const travelColor = useDesk((s) => s.spaces.find((x) => x.id === 'travel')?.color) ?? SPACE_COLORS.travel;
  const now = useNow();
  const f = useDeskFormat(now);
  const [asking, setAsking] = useState<Status | null>(null);

  if (!plan) {
    return (
      <DeskPage icon={SPACE_ICONS.travel} color={travelColor} back="/travel" title={P.notFound} description={P.notFoundText}>
        <DeskCard>
          <Link to="/travel" className="desk-link">
            ‹ {P.backToTravel}
          </Link>
        </DeskCard>
      </DeskPage>
    );
  }

  const source = notices.find((n) => n.id === plan.noticeIds[0]);
  const dates = `${fmtShortDay(plan.start)} – ${fmtShortDay(plan.end)}`;
  const actions =
    plan.status === 'draft' ? (
      <>
        <PillButton label={P.markDone} aria-expanded={asking === 'done'} onClick={() => setAsking('done')} />
        <PillButton label={P.drop} aria-expanded={asking === 'dropped'} onClick={() => setAsking('dropped')} />
      </>
    ) : (
      <PillButton label={P.reopen} aria-expanded={asking === 'draft'} onClick={() => setAsking('draft')} />
    );

  return (
    <DeskPage
      className="sp-page sp-plan"
      icon={SPACE_ICONS.travel}
      color={travelColor}
      back="/travel"
      title={plan.title}
      metaTitle={`${plan.title} · FamilyOS`}
      description={
        <span className="sp-plan-meta">
          <StatusChip tone={TONE[plan.status]}>{plan.status}</StatusChip>
          <span>{P.meta(dates, f.money(plan.budget), memberName({ members }, plan.authorId))}</span>
        </span>
      }
      actions={actions}
      rail={
        <>
          <PlanTodos plan={plan} now={now} />
          <Explainer title={P.whenBooked}>
            <p className={T.small}>{P.whenBookedText}</p>
          </Explainer>
        </>
      }
    >
      {asking ? <ConfirmStatus key={asking} plan={plan} to={asking} onClose={() => setAsking(null)} /> : null}
      <DeskCard className="sp-plan-summary">
        <p className={T.body}>{f.text(plan.summary)}</p>
        {source ? (
          <p className={clsx(T.small, 'sp-plan-source')}>
            {P.writtenFrom(source.title, source.sender, f.ago(source.receivedAt))}{' '}
            <Link to={`/inbox/${source.id}`} className="desk-link">
              {spaceCopy.theNotice} ›
            </Link>
          </p>
        ) : null}
      </DeskCard>
      <Itinerary plan={plan} />
      <Bookings plan={plan} now={now} />
    </DeskPage>
  );
}

/** Mark done / Drop / Reopen, written out before it happens (MASTER §0.3 rule 3). */
function ConfirmStatus({ plan, to, onClose }: { plan: Plan; to: Status; onClose: () => void }) {
  const setStatus = useDesk((s) => s.setPlanStatus);
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const confirm = () => {
    const prev = plan.status;
    setStatus(plan.id, to);
    onClose();
    useFamilyOS.getState().toast(P.toast[to], { action: { label: spaceCopy.undo, onPress: () => setStatus(plan.id, prev) }, duration: 5000 });
  };
  return (
    <section className="sp-confirm card" role="group" aria-labelledby="sp-confirm-q">
      <p className={T.meta}>{P.confirmLabel}</p>
      <p id="sp-confirm-q" className={T.bodyStrong}>
        {P.ask[to]}
      </p>
      <p className={T.small}>{P.askNote[to]}</p>
      <div className="sp-confirm__actions">
        <button ref={ref} type="button" className="pill pill--primary" onClick={confirm}>
          {P.confirm[to]}
        </button>
        <PillButton label={P.keep} onClick={onClose} />
      </div>
    </section>
  );
}
