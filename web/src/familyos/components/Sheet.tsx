// The panel every Home overlay uses (AGENT_WEB.md §8.0, §8.2, §8.4, §8.6),
// adapting by width:
//   phone   < 640  floating bottom card with 16 px margins and radius 28,
//                  Close pill above, drag the header down to dismiss
//                  (the mobile ModalCard);
//   tablet  < 1024 centred modal, max width 560;
//   desktop ≥ 1024 right-hand drawer, full height, radius 28 on the inner side.
// Always a real dialog: role="dialog", aria-modal, a labelled title, focus
// trapped inside and returned on close, Esc and a click on the scrim close it.
// Home stays visible behind, dimmed and blurred.
import { useRef, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useIsPresent, useMotionValue, animate } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import clsx from 'clsx';
import { fm, springs } from '../theme/motion';
import { useViewport } from '../hooks/useBreakpoint';
import { useEscape } from '../hooks/useEscape';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { ClosePill } from './Pills';

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  /** id of the element that names the dialog. */
  labelledBy: string;
  /** Rendered above the scrolling body; on phones it is the drag handle. */
  header?: ReactNode;
  children: ReactNode;
  /** Pinned under the body (Chat input). */
  footer?: ReactNode;
  /** Faint scenario tint on the panel (§6.4). */
  tint?: boolean;
  /** 'above' = a Close pill above the card (phone) / at the top right (wider); 'none' = the header has its own. */
  close?: 'above' | 'none';
  /** Drawer width on desktop. */
  drawerWidth?: number;
  /** Phone: fixed height as a fraction of the viewport (Chat); otherwise hugs content up to maxFrac. */
  fixedFrac?: number;
  maxFrac?: number;
  initialFocus?: RefObject<HTMLElement | null>;
  className?: string;
  bodyClassName?: string;
  /** Solid fill when nothing animated sits behind (family pages). */
  opaque?: boolean;
  /** Desktop presentation (default 'drawer'). */
  desktop?: 'drawer' | 'center';
}

export function Sheet(props: SheetProps) {
  return createPortal(<AnimatePresence>{props.open ? <SheetPanel key="sheet" {...props} /> : null}</AnimatePresence>, document.body);
}

function SheetPanel({
  onClose,
  labelledBy,
  header,
  children,
  footer,
  tint,
  close = 'above',
  drawerWidth = 440,
  fixedFrac,
  maxFrac = 0.85,
  initialFocus,
  className,
  bodyClassName,
  opaque,
  desktop = 'drawer',
}: SheetProps) {
  const { bp, H } = useViewport();
  const reduced = useReducedMotion();
  const panel = useRef<HTMLDivElement>(null);
  const mode = bp === 'phone' ? 'sheet' : bp === 'tablet' || desktop === 'center' ? 'modal' : 'drawer';
  // While the exit animation runs the panel is inert and focus is already back where it was.
  const present = useIsPresent();
  useEscape(present, onClose);
  // Focus the dialog itself unless a field should take it (Chat's input), so
  // opening never paints a focus ring on the first button.
  useFocusTrap(panel, present, { initial: initialFocus ?? panel });

  // Phone: drag the header down to dismiss (mobile ModalCard: > 110 px or a fast flick).
  const dragY = useMotionValue(0);
  const bind = useDrag(
    ({ movement: [, my], velocity: [, vy], direction: [, dy], last, event }) => {
      if (mode !== 'sheet') return;
      if ((event as PointerEvent).pointerType === 'mouse') return;
      if (!last) {
        dragY.set(Math.max(0, my));
        return;
      }
      if (my > 110 || (vy > 0.9 && dy > 0)) onClose();
      else animate(dragY, 0, fm.snappy);
    },
    { axis: 'y', filterTaps: true, pointer: { touch: true } }
  );

  const variants = {
    sheet: { initial: { opacity: 0, y: 36, scale: 0.94 }, animate: { opacity: 1, y: 0, scale: 1 }, exit: { opacity: 0, y: 36, scale: 0.97 } },
    modal: { initial: { opacity: 0, y: 18, scale: 0.96 }, animate: { opacity: 1, y: 0, scale: 1 }, exit: { opacity: 0, y: 12, scale: 0.98 } },
    drawer: { initial: { opacity: 0.4, x: '104%' }, animate: { opacity: 1, x: 0 }, exit: { opacity: 0.4, x: '104%' } },
  }[mode];
  // Mobile closes with a 220 ms ease-in rather than the spring.
  const exitT = { duration: reduced ? 0.12 : 0.22, ease: [0.32, 0, 0.67, 0] as [number, number, number, number] };
  const transition = reduced ? { duration: 0.15 } : { type: 'spring' as const, ...springs.soft };

  const style: CSSProperties =
    mode === 'drawer'
      ? { width: `min(${drawerWidth}px, calc(100vw - 32px))` }
      : mode === 'sheet'
        ? fixedFrac
          ? { height: `calc(${fixedFrac * 100}dvh - env(safe-area-inset-bottom))` }
          : { maxHeight: `calc(${maxFrac * 100}dvh - env(safe-area-inset-bottom))` }
        : { maxHeight: `min(${Math.round(H * 0.86)}px, 86dvh)`, ...(fixedFrac ? { height: `min(${Math.round(H * 0.86)}px, 86dvh)` } : null) };

  return (
    <div className={clsx('sheet-root', `sheet-root--${mode}`)}>
      <motion.div
        className="sheet-scrim"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.22 }}
        onClick={onClose}
        aria-hidden
      />
      <motion.div
        className={clsx('sheet-anchor', `sheet-anchor--${mode}`)}
        initial={variants.initial}
        animate={variants.animate}
        exit={{ ...variants.exit, transition: exitT }}
        transition={transition}
        style={mode === 'sheet' ? { y: dragY } : undefined}
        inert={!present}
      >
        {close === 'above' && mode === 'sheet' ? <ClosePill onClick={onClose} className="sheet-close-above" /> : null}
        <div
          ref={panel}
          role="dialog"
          aria-modal="true"
          aria-labelledby={labelledBy}
          tabIndex={-1}
          className={clsx('glass glass--sheet sheet-panel', `sheet-panel--${mode}`, tint && 'tint-mood', opaque && 'sheet-panel--opaque', className)}
          style={style}
        >
          {header ? (
            <div className="sheet-header" {...(mode === 'sheet' ? bind() : {})}>
              {mode === 'sheet' ? <span className="sheet-grip" aria-hidden /> : null}
              {header}
              {close === 'above' && mode !== 'sheet' ? <ClosePill onClick={onClose} className="sheet-close-inline" /> : null}
            </div>
          ) : null}
          <div className={clsx('sheet-body scroll-y', bodyClassName)}>{children}</div>
          {footer}
        </div>
      </motion.div>
    </div>
  );
}
