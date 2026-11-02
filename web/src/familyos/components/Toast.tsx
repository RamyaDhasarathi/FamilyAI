// Glass toast pill above the bottom bar; auto-hides after 2.2 s (AGENT_WEB.md
// §8.1.8) or its own duration, announced politely to screen readers. An
// optional action ("Undo") sits inside the pill.
import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useFamilyOS, type Toast } from '../store/useFamilyOS';
import { durations } from '../theme/motion';
import { T } from '../theme/typography';
import { Pressable } from './Pressable';

function ToastPill({ toast }: { toast: Toast }) {
  const dismiss = useFamilyOS((s) => s.dismissToast);
  useEffect(() => {
    const id = setTimeout(() => dismiss(toast.id), toast.duration ?? durations.toast);
    return () => clearTimeout(id);
  }, [toast.id, toast.duration, dismiss]);
  const action = toast.action;
  return (
    <motion.div
      className={action ? 'toast toast--action' : 'toast'}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      transition={{ duration: 0.22 }}
    >
      <span className={T.smallStrong}>{toast.text}</span>
      {action ? (
        <Pressable
          className="toast__action"
          onClick={() => {
            dismiss(toast.id);
            action.onPress();
          }}
        >
          {action.label}
        </Pressable>
      ) : null}
    </motion.div>
  );
}

export function ToastHost({ bottom = 96 }: { bottom?: number | string }) {
  const toasts = useFamilyOS((s) => s.toasts);
  const last = toasts[toasts.length - 1];
  return (
    <div className="toast-host" style={{ bottom }} aria-live="polite" role="status">
      <AnimatePresence>{last ? <ToastPill key={last.id} toast={last} /> : null}</AnimatePresence>
    </div>
  );
}
