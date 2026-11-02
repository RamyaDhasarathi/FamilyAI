// One errand, /errands/:id (MASTER_AGENT.md §3.2 Errands 5:50–6:10, §7
// Phase 5, §11; FamilyOS.mp4 ≈5:50–6:05, frames f_070–f_074). Status chip
// and who asked / approved under the title; Approve (guardians only) and
// Cancel, each behind a confirm; What was written down with the fingerprint
// (editing a term shows the approval voided live); The run; and a rail with
// How it runs and the errand's own audit rows. Approval is bound to the
// fingerprint: the store voids it the moment a written-down term changes.
import { Link, useParams } from 'react-router';
import { ShoppingCart } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { askPath } from '../shell/routes';
import { canApprove, canCancel, siteOf } from './errandModel';
import { ErrandTerms } from './ErrandTerms';
import { ErrandRun, HowItRuns } from './ErrandRun';
import { useConfirm } from './useConfirm';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

const C = ADMIN_COPY.errands;
const lower = (t: string) => t.charAt(0).toLowerCase() + t.slice(1);

export default function ErrandPage() {
  const { id } = useParams();
  const errand = useDesk((s) => s.errands.find((e) => e.id === id));
  const members = useDesk((s) => s.members);
  const actor = useDesk((s) => s.actor);
  const approve = useDesk((s) => s.approveErrand);
  const cancel = useDesk((s) => s.cancelErrand);
  const now = useNow();
  const f = useDeskFormat(now);
  const [dialog, ask] = useConfirm();
  const voided = useVoided(id ?? '');
  const name = (m?: string) => memberName({ members }, m);
  const stamp = (i: string) => f.when(i);

  if (!errand) {
    return (
      <DeskPage className="adm-page" icon={ShoppingCart} color={colors.agents.household} back="/errands" title="Errand not found" description="There is no errand with this address. It may have been erased with the household.">
        <DeskCard>
          <Link to="/errands" className="desk-link">
            All errands ›
          </Link>
        </DeskCard>
      </DeskPage>
    );
  }

  const e = errand;
  const role = members.find((m) => m.id === actor)?.role;
  const site = siteOf(e.where);
  const toast = (t: string) => useFamilyOS.getState().toast(t, { duration: 4200 });

  const onApprove = () =>
    ask({
      title: `Approve “${f.text(e.title)}”?`,
      body: (
        <>
          <p className="t-small">
            You approve exactly what is written down — fingerprint <span className="adm-code adm-code--ink">{e.fingerprint}</span>. FamilyOS may spend at most{' '}
            <strong>{f.money(e.atMost)}</strong> on <strong>{site}</strong>, and stops if {lower(f.text(e.stopsIf))}.
          </p>
          <p className="t-small">If anything written down changes, this approval no longer applies.</p>
        </>
      ),
      confirm: 'Approve exactly this',
      run: () => {
        if (approve(e.id)) toast('Approved. It runs only as written down.');
      },
    });

  const onCancel = () =>
    ask({
      title: `Cancel “${f.text(e.title)}”?`,
      body: 'It will not run. What was written down stays on record, and the Audit notes who cancelled it.',
      confirm: 'Cancel the errand',
      cancel: 'Keep it',
      danger: true,
      run: () => {
        if (cancel(e.id, `Cancelled by ${name(actor)} before it ran.`)) toast('Cancelled. Nothing ran.');
      },
    });

  const meta = [`on ${site}`, `asked by ${name(e.requestedBy)}`, e.approvedBy && e.status !== 'proposed' ? `approved by ${name(e.approvedBy)}` : null].filter(Boolean).join(' · ');

  return (
    <DeskPage
      className="adm-page"
      icon={ShoppingCart}
      color={colors.agents[e.agent]}
      back="/errands"
      title={f.text(e.title)}
      metaTitle={`${e.title} · Errands · FamilyOS`}
      description={
        <>
          <StatusChip tone={e.status}>{C.status[e.status]}</StatusChip> <span>{meta}</span>
        </>
      }
      actions={
        <>
          <Link to={askPath(`Tell me about the errand “${e.title}”`)} className="pill pill--secondary">
            Ask about this
          </Link>
          {canCancel(e) ? <PillButton label="Cancel" className="adm-pill--soft-danger" aria-label={`Cancel the errand ${e.title}`} onClick={onCancel} /> : null}
          {e.status === 'proposed' ? (
            <PillButton
              label="Approve"
              variant="primary"
              disabled={!canApprove(e, role)}
              title={canApprove(e, role) ? undefined : 'Only a guardian approves an errand.'}
              aria-label={`Approve the errand ${e.title}`}
              onClick={onApprove}
            />
          ) : null}
        </>
      }
      rail={<HowItRuns errand={e} money={f.money} text={f.text} stamp={stamp} />}
    >
      {e.status === 'proposed' ? (
        <p className="adm-note t-small" role="status">
          {voided ? 'An earlier approval no longer applies: what was written down changed. ' : ''}
          Waiting for a guardian. Nothing runs, and nothing is paid, until a guardian approves exactly what is written down.
          {canApprove(e, role) ? '' : ' Only a guardian can approve it.'}
        </p>
      ) : null}
      <ErrandTerms errand={e} money={f.money} text={f.text} when={stamp} />
      <ErrandRun errand={e} text={f.text} ago={(i) => `${f.ago(i)} · ${f.time(i)}`} />
      <p className={T.small}>
        {C.detail}
      </p>
      {dialog}
    </DeskPage>
  );
}

/** Since this errand was last approved, the Audit says the approval stopped applying. */
function useVoided(errandId: string) {
  return useDesk((s) => {
    for (let i = s.audit.length - 1; i >= 0; i--) {
      const a = s.audit[i];
      if (a.raw?.errandId !== errandId) continue;
      if (a.code === 'errand.approval_voided') return true;
      if (a.code === 'errand.approved') return false;
    }
    return false;
  });
}
