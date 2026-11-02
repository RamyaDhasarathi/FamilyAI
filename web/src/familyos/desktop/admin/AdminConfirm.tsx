// The one confirmation step for Phase 5 actions (MASTER_AGENT.md §0.3.3
// "Nothing happens without a person confirming", §3.3.1): approve, cancel,
// release, delete, revert, withdraw, revoke, stop, disconnect. A centred
// glass card over a scrim; focus is trapped inside and returned on close;
// Esc or a click outside cancels. The destructive button is `.pill--danger`.
import { useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useEscape } from '../../hooks/useEscape';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useReducedMotion } from '../../hooks/useReducedMotion';

export interface ConfirmProps {
  title: string;
  body?: ReactNode;
  confirm: string;
  cancel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function AdminConfirm({ title, body, confirm, cancel = 'Not now', danger, onConfirm, onCancel }: ConfirmProps) {
  const id = useId();
  const card = useRef<HTMLDivElement>(null);
  const keep = useRef<HTMLButtonElement>(null);
  const reduced = useReducedMotion();
  useEscape(true, onCancel);
  // A destructive step starts on the safe button.
  useFocusTrap(card, true, { initial: danger ? keep : undefined });
  return createPortal(
    <div className="adm-dialog">
      <motion.div className="adm-dialog__scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.16 }} onClick={onCancel} aria-hidden />
      <motion.div
        ref={card}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={`${id}-t`}
        aria-describedby={body ? `${id}-b` : undefined}
        className={clsx('adm-dialog__card', danger && 'adm-dialog__card--danger')}
        initial={{ opacity: 0, scale: reduced ? 1 : 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: reduced ? 0.1 : 0.18, ease: [0.33, 1, 0.68, 1] }}
      >
        <h2 id={`${id}-t`} className={clsx(T.bodyStrong, 'adm-dialog__title')}>
          {title}
        </h2>
        {body ? (
          <div id={`${id}-b`} className="adm-prose">
            {typeof body === 'string' ? <p className={T.small}>{body}</p> : body}
          </div>
        ) : null}
        <div className="adm-dialog__buttons">
          <PillButton ref={keep} label={cancel} onClick={onCancel} />
          <PillButton label={confirm} variant={danger ? 'danger' : 'primary'} onClick={onConfirm} />
        </div>
      </motion.div>
    </div>,
    document.body
  );
}
