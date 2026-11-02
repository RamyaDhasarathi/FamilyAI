// Revisions, /revisions (MASTER_AGENT.md §7 Phase 5 "history of edits to
// records (who, what changed, when, Revert where allowed)"; linked from the
// reference's Audit, FamilyOS.mp4 ≈7:15, frame f_084). Newest first, grouped
// by day: the record (with a link to where it lives), the field, before →
// after in household terms, who, when. Revert asks for a confirm and is
// written as a new revision; rows that can't be reverted say why.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { ArrowRight, History } from 'lucide-react';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { MiniGem } from '../../components/MiniGem';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { dayKey, fmtLongDay, fmtRelDay } from '../../desk/format';
import type { RecordType, Revision } from '../../desk/types';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { ActorChip } from './AdminBits';
import { canRevert, fieldLabel, fmtValue, RECORD_LABEL, recordHref, sortRevisions, whyNoRevert } from './revisionModel';
import { useConfirm } from './useConfirm';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

const C = ADMIN_COPY.revisions;
const TYPES = Object.keys(RECORD_LABEL) as RecordType[];

export default function RevisionsPage() {
  const revisions = useDesk((s) => s.revisions);
  const agenda = useDesk((s) => s.agenda);
  const todos = useDesk((s) => s.todos);
  const revert = useDesk((s) => s.revertRevision);
  const now = useNow();
  const f = useDeskFormat(now);
  const [type, setType] = useState<RecordType | 'all'>('all');
  const [dialog, ask] = useConfirm();
  const sorted = useMemo(() => sortRevisions(revisions), [revisions]);
  const shown = type === 'all' ? sorted : sorted.filter((r) => r.recordType === type);
  const days = useMemo(() => {
    const out: { day: string; rows: Revision[] }[] = [];
    for (const r of shown) {
      const d = dayKey(r.at, f.tz);
      if (out.at(-1)?.day === d) out.at(-1)!.rows.push(r);
      else out.push({ day: d, rows: [r] });
    }
    return out;
  }, [shown, f.tz]);
  const val = (r: Revision, v: Revision['before']) => fmtValue(r.field, v, { currency: f.currency, tz: f.tz, money: f.money });

  const onRevert = (r: Revision) =>
    ask({
      title: `Put ${fieldLabel(r.field)} on “${f.text(r.recordLabel)}” back to ${val(r, r.before)}?`,
      body: `It is ${val(r, r.after)} now. The revert is written as a new change, by you; nothing is deleted, and the Audit records it.`,
      confirm: 'Revert',
      run: () => {
        if (revert(r.id)) useFamilyOS.getState().toast('Reverted. Written to the Audit.', { duration: 4200 });
      },
    });

  return (
    <DeskPage
      className="adm-page"
      icon={History}
      title="Revisions"
      description={C.description}
      rail={
        <DeskCard title="What can be reverted">
          <div className="adm-prose">
            <p className={T.small}>A change a person made to a to-do, a plan, a person or the calendar can be put back here.</p>
            <p className={T.small}>Errand terms can’t: they change on the errand itself, where any change voids the guardian’s approval.</p>
            <p className={T.small}>A change FamilyOS read from a notice follows that notice. Revert the notice’s proposal instead.</p>
            <Link to="/audit" className="desk-link">
              Everything that happened is in the Audit ›
            </Link>
          </div>
        </DeskCard>
      }
    >
      <div className="adm-filters" role="group" aria-label="Show changes to">
        {(['all', ...TYPES] as const).map((t) => (
          <button key={t} type="button" className={clsx('adm-filter', type === t && 'is-on')} aria-pressed={type === t} onClick={() => setType(t)}>
            {t === 'all' ? 'Every record' : RECORD_LABEL[t]}
            <span className="adm-filter__n">{t === 'all' ? revisions.length : revisions.filter((r) => r.recordType === t).length}</span>
          </button>
        ))}
      </div>
      {days.length === 0 ? (
        <div className="desk-empty card adm-note">
          <MiniGem size={36} still />
          <p className={T.small}>{type === 'all' ? C.empty : `No changes to a ${RECORD_LABEL[type]} yet.`}</p>
        </div>
      ) : (
        days.map((d) => (
          <DeskCard key={d.day} title={fmtRelDay(d.day, f.today)} sub={fmtLongDay(d.day)}>
            <ul className="adm-list">
              {d.rows.map((r) => {
                const href = recordHref(r, { agenda, todos });
                const why = whyNoRevert(r);
                return (
                  <li key={r.id} className="adm-row adm-row--top">
                    <span className="adm-row__main">
                      <span className={clsx(T.small, 'adm-row__title')}>
                        <StatusChip tone="neutral">{RECORD_LABEL[r.recordType]}</StatusChip>
                        {href ? (
                          <Link to={href} className={clsx(T.smallStrong, 'desk-link')}>
                            {f.text(r.recordLabel)}
                          </Link>
                        ) : (
                          <span className={T.smallStrong}>{f.text(r.recordLabel)}</span>
                        )}
                        <span>· {fieldLabel(r.field)}</span>
                      </span>
                      <span className={clsx(T.body, 'adm-change')}>
                        <span className="adm-change__before">{val(r, r.before)}</span>
                        <ArrowRight size={13} aria-label="changed to" />
                        <span className="adm-change__after">{val(r, r.after)}</span>
                      </span>
                      <span className={clsx(T.small, 'adm-row__sub')}>
                        {f.time(r.at)}
                        {r.revertOf ? ' · a revert of an earlier change' : ''}
                        {r.revertedAt ? ` · reverted ${f.ago(r.revertedAt)}` : ''}
                        {why ? ` · ${why}` : ''}
                      </span>
                    </span>
                    <span className="adm-row__actions">
                      <ActorChip actor={r.actor} />
                      {r.revertedAt ? <StatusChip tone="done">reverted</StatusChip> : null}
                      {canRevert(r) ? <PillButton label="Revert" aria-label={`Revert ${fieldLabel(r.field)} on ${r.recordLabel}`} onClick={() => onRevert(r)} /> : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          </DeskCard>
        ))
      )}
      {dialog}
    </DeskPage>
  );
}
