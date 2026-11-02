// Small shared pieces for the Phase 5 pages (MASTER_AGENT.md §8): the actor
// chip (a person or FamilyOS — always text, never colour alone), a member
// initial, and a labelled form field with its error line.
import { useId, type ReactNode } from 'react';
import clsx from 'clsx';
import { Sparkle } from 'lucide-react';
import { useDesk } from '../../desk/store';
import { actorName } from '../../desk/selectors';
import { StatusChip } from '../shell/DeskPage';

export function ActorChip({ actor, className }: { actor: string; className?: string }) {
  const members = useDesk((s) => s.members);
  const fos = actor === 'FamilyOS';
  return (
    <StatusChip tone="neutral" className={className}>
      {fos ? <Sparkle size={10} aria-hidden /> : null}
      {actorName({ members }, actor) || 'Someone'}
    </StatusChip>
  );
}

export function Initial({ letter, label }: { letter: string; label?: string }) {
  return (
    <span className="adm-avatar" aria-hidden={label ? undefined : true} aria-label={label} role={label ? 'img' : undefined}>
      {letter}
    </span>
  );
}

/** Label + control + error. `children` receives the ids to wire aria. */
export function Field({ label, error, hint, className, children }: {
  label: string;
  error?: string | null;
  hint?: ReactNode;
  className?: string;
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const msg = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div className={clsx('adm-field', className)}>
      <label htmlFor={id} className="adm-label">
        {label}
      </label>
      {children({ id, describedBy: msg, invalid: !!error })}
      {error ? (
        <p id={`${id}-err`} className="adm-error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="t-small adm-row__sub">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
