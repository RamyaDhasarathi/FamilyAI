// Small centred glass dialog for the family screens (mobile ConfirmDialog /
// RemoveDialog / MemberMenu): scrim, focus trapped inside and returned on
// close, Esc and a click outside cancel.
import { useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { springs } from '../../theme/motion';
import { useEscape } from '../../hooks/useEscape';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useReducedMotion } from '../../hooks/useReducedMotion';

export function Dialog({ labelledBy, onCancel, children, className }: { labelledBy: string; onCancel: () => void; children: ReactNode; className?: string }) {
  const card = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  useEscape(true, onCancel);
  useFocusTrap(card, true);
  return createPortal(
    <div className="fam-dialog">
      <motion.div className="fam-dialog__scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.16 }} onClick={onCancel} aria-hidden />
      <motion.div
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={clsx('fam-dialog__card', className)}
        initial={{ opacity: 0, scale: reduced ? 1 : 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={reduced ? { duration: 0.12 } : { type: 'spring', ...springs.snappy }}
      >
        {children}
      </motion.div>
    </div>,
    document.body
  );
}
