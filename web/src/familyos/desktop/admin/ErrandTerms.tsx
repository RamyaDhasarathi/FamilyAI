// "What was written down" (MASTER_AGENT.md §3.2 Errands 6:00, §11 "Errand
// approval voids if any written-down field changes"; frames f_070–f_074):
// What, When, Where, At most, Paid, Card (last four only), Stops if, and the
// fingerprint with "if anything changes, the approval no longer applies".
// "Change what was written down" turns the rows into fields; while you type,
// changed rows are marked, the new fingerprint is shown beside the old one,
// and — if a guardian's approval holds — a warning says that saving voids it.
// Nothing is written until Save; Save calls the store's editErrand, which
// voids the approval and writes the revision and audit rows.
import { useState } from 'react';
import clsx from 'clsx';
import { Check } from 'lucide-react';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { approvalHolds } from '../../desk/fingerprint';
import { memberName } from '../../desk/selectors';
import type { Errand } from '../../desk/types';
import { DeskCard } from '../shell/DeskPage';
import { canEdit, draftEffect, parseDraft, patchOf, safeCard, TERM_ROWS, toDraft, type Draft, type TermKey } from './errandModel';
import { ADMIN_COPY } from './adminCopy';

const C = ADMIN_COPY.errands;

interface Props {
  errand: Errand;
  money: (n: number) => string;
  text: (s: string) => string;
  when: (i: string) => string;
}

export function ErrandTerms({ errand: e, money, text, when }: Props) {
  const members = useDesk((s) => s.members);
  const edit = useDesk((s) => s.editErrand);
  const [draft, setDraft] = useState<Draft | null>(null);
  const parsed = draft ? parseDraft(draft) : null;
  const effect = parsed?.terms ? draftEffect(e, parsed.terms) : null;
  const changed = new Set<TermKey>(effect?.changed ?? []);
  const holds = e.status === 'approved' && approvalHolds(e);
  const approver = memberName({ members }, e.approvedBy);

  const save = () => {
    if (!parsed?.terms || !effect?.changed.length) return;
    const voids = effect.voids;
    if (!edit(e.id, patchOf(e, parsed.terms))) return;
    setDraft(null);
    useFamilyOS.getState().toast(voids ? 'Saved. The approval no longer applies; it waits for a guardian again.' : 'Saved. Written to the Audit.', { duration: 4200 });
  };

  const show = (k: TermKey) => {
    if (k === 'atMost') return <span className={T.bodyStrong}>{money(e.atMost)}<span className={T.small}> · the most it may cost</span></span>;
    if (k === 'card') return <span className={T.body}>{safeCard(e.card) ?? 'last four digits only'}</span>;
    if (k === 'stopsIf') return <span className="adm-stops">{text(e.stopsIf)}</span>;
    return <span className={k === 'what' ? T.bodyStrong : T.body}>{text(e[k])}</span>;
  };

  return (
    <DeskCard
      title="What was written down"
      className="adm-terms-card"
      action={
        canEdit(e) && !draft ? <PillButton label="Change what was written down" onClick={() => setDraft(toDraft(e))} /> : null
      }
    >
      <dl className="adm-terms">
        {TERM_ROWS.map((r) => (
          <div key={r.key} style={{ display: 'contents' }}>
            <dt className="adm-terms__k">{draft ? <label htmlFor={`term-${r.key}`}>{r.label}</label> : r.label}</dt>
            <dd className={clsx('adm-terms__v', changed.has(r.key) && 'is-changed')}>
              {draft ? (
                <>
                  <input
                    id={`term-${r.key}`}
                    className="adm-input"
                    value={draft[r.key]}
                    placeholder={r.placeholder}
                    inputMode={r.key === 'atMost' ? 'decimal' : undefined}
                    aria-invalid={!!parsed?.errors[r.key]}
                    aria-describedby={parsed?.errors[r.key] ? `term-${r.key}-err` : undefined}
                    onChange={(ev) => setDraft({ ...draft, [r.key]: ev.target.value })}
                  />
                  {parsed?.errors[r.key] ? (
                    <p id={`term-${r.key}-err`} className="adm-error">
                      {parsed.errors[r.key]}
                    </p>
                  ) : changed.has(r.key) ? (
                    <p className={clsx(T.small, 'adm-row__sub')}>changed · was {r.key === 'atMost' ? money(e.atMost) : text(String(e[r.key]))}</p>
                  ) : null}
                </>
              ) : (
                show(r.key)
              )}
            </dd>
          </div>
        ))}
      </dl>

      <div className="adm-fp" aria-live="polite">
        <p className="adm-code">
          Fingerprint{' '}
          {effect?.changed.length ? (
            <>
              <s>{e.fingerprint}</s> → <span className="adm-code--ink">{effect.fingerprint}</span>
            </>
          ) : (
            <span className="adm-code--ink">{e.fingerprint}</span>
          )}
          . {C.fpNote}
        </p>
        {holds && !effect?.voids ? (
          <p className={T.small}>
            <Check size={12} aria-hidden style={{ color: 'var(--done)', verticalAlign: -1 }} /> The approval by {approver} holds: it was given for this fingerprint{e.approvedAt ? `, ${when(e.approvedAt)}` : ''}.
          </p>
        ) : null}
      </div>

      {draft ? (
        <>
          {effect?.voids ? (
            <p className="adm-note adm-note--warn t-small" role="status" style={{ marginTop: 12 }}>
              Saving this voids {approver}’s approval. The errand goes back to waiting for a guardian, and nothing runs until one approves the new terms.
            </p>
          ) : effect?.changed.length && e.status === 'proposed' ? (
            <p className="adm-note t-small" role="status" style={{ marginTop: 12 }}>
              Saving changes the fingerprint. A guardian approves the new terms, not the old ones.
            </p>
          ) : null}
          <div className="adm-actions" style={{ marginTop: 14 }}>
            <PillButton label="Save changes" variant="primary" disabled={!effect?.changed.length} onClick={save} />
            <PillButton label="Discard" onClick={() => setDraft(null)} />
            <span className={T.small}>{effect?.changed.length ? `${effect.changed.length} changed` : parsed && !parsed.terms ? 'Fix the marked fields to save.' : 'Nothing changed yet.'}</span>
          </div>
        </>
      ) : null}
    </DeskCard>
  );
}
