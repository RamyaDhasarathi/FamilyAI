// Profile menu (AGENT_WEB.md §8.5, video 0:12 and 1:18). A glass popover that
// scales out of the avatar pill's corner at every width (phones match the
// mobile app, §8.0, which keeps the popover rather than a bottom sheet). Arrow keys move between rows, Esc closes, focus is trapped
// while open and returned to the avatar pill. "Summary button" toggles
// Listen / Read in place with a toast.
import { useEffect, useRef, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useIsPresent } from 'framer-motion';
import { copy } from '../../mocks/data';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useFamily, useNeedsUpdateCount } from '../../store/useFamily';
import { springs } from '../../theme/motion';
import { T } from '../../theme/typography';
import { useViewport } from '../../hooks/useBreakpoint';
import { useEscape } from '../../hooks/useEscape';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { ClosePill } from '../../components/Pills';
import { Pressable } from '../../components/Pressable';
import { slug } from './menuSlug';

export type MenuTarget = string;

interface Props {
  open: boolean;
  onClose: () => void;
  onNavigate: (path: MenuTarget) => void;
  onLogout: () => void;
  anchor: RefObject<HTMLElement | null>;
  /** Desktop: replacement destinations by row label (e.g. → /settings/household#privacy). */
  targets?: Partial<Record<string, MenuTarget>>;
}


function Row({ label, onClick, right, danger }: { label: string; onClick: () => void; right?: ReactNode; danger?: boolean }) {
  return (
    <Pressable className="menu-row" role="menuitem" onClick={onClick} pressScale={0.98} lift={false}>
      <span className={T.menu} style={danger ? { color: 'var(--danger)' } : undefined}>
        {label}
      </span>
      {right}
    </Pressable>
  );
}

export function ProfileMenu(props: Props) {
  return createPortal(<AnimatePresence>{props.open ? <MenuPanel key="menu" {...props} /> : null}</AnimatePresence>, document.body);
}

function MenuPanel({ onClose, onNavigate, onLogout, anchor, targets }: Props) {
  const { W } = useViewport();
  const reduced = useReducedMotion();
  const profile = useFamilyOS((s) => s.profile);
  const mode = useFamilyOS((s) => s.summaryMode);
  const toggle = useFamilyOS((s) => s.toggleSummaryMode);
  const needsUpdate = useNeedsUpdateCount();
  const loadFamily = useFamily((s) => s.load);
  const familyLoaded = useFamily((s) => s.loaded);
  const panel = useRef<HTMLDivElement>(null);
  const present = useIsPresent();
  useEscape(present, onClose);
  useFocusTrap(panel, present, { initial: panel });
  useEffect(() => {
    if (!familyLoaded) void loadFamily();
  }, [familyLoaded, loadFamily]);
  // Anchored under the avatar pill; re-read on every render (resizes re-render via useViewport).
  const r = anchor.current?.getBoundingClientRect();
  const pos = r ? { top: r.bottom + 10, right: Math.max(12, W - r.right) } : { top: 64, right: 16 };

  if (!profile) return null;
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return;
    const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    if (!items.length) return;
    e.preventDefault();
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : e.key === 'ArrowDown' ? (at + 1) % items.length : (at - 1 + items.length) % items.length;
    items[next].focus();
  };
  const rows: [string, MenuTarget][] = [
    [copy.profileMenu.rows[0], `/page/${slug(copy.profileMenu.rows[0])}`],
    [copy.profileMenu.rows[1], '/family'],
    [copy.profileMenu.addMember, '/family?add=1'],
    [copy.profileMenu.rows[2], `/page/${slug(copy.profileMenu.rows[2])}`],
    [copy.profileMenu.rows[3], `/page/${slug(copy.profileMenu.rows[3])}`],
    [copy.profileMenu.rows[4], `/page/${slug(copy.profileMenu.rows[4])}`],
  ];
  const t = reduced ? { duration: 0.12 } : { type: 'spring' as const, ...springs.soft };
  return (
    <div className="menu-root">
      <motion.div className="sheet-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} onClick={onClose} aria-hidden />
      <motion.div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="menu-name"
        className="menu glass"
        style={{ top: pos.top, right: pos.right, transformOrigin: 'top right' }}
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.85, transition: { duration: 0.18 } }}
        transition={t}
        onKeyDown={onKey}
        inert={!present}
        tabIndex={-1}
      >
        <div className="menu__head">
          <span className="menu__avatar t-small-strong">{profile.initial}</span>
          <span className="menu__who">
            <span id="menu-name" className={T.bodyStrong}>
              {profile.name}
            </span>
            <span className={T.small} style={{ fontSize: '0.72rem' }}>
              {profile.plan}
            </span>
          </span>
          <ClosePill onClick={onClose} />
        </div>
        <div role="menu" aria-labelledby="menu-name" className="menu__rows">
          {rows.map(([label, target]) => (
            <Row
              key={label}
              label={label}
              onClick={() => onNavigate(targets?.[label] ?? target)}
              right={
                target === '/family' && needsUpdate > 0 ? (
                  <span className="menu__count" aria-label={`${needsUpdate} ${needsUpdate === 1 ? 'member needs' : 'members need'} details updated`}>
                    {needsUpdate}
                  </span>
                ) : undefined
              }
            />
          ))}
          <Row
            label={copy.profileMenu.summaryButton}
            onClick={toggle}
            right={
              <span className="chip chip--small" aria-label={`mode: ${copy.summaryModeLabel[mode]}`}>
                {copy.summaryModeLabel[mode]}
              </span>
            }
          />
          <Row label={copy.profileMenu.settings} onClick={() => onNavigate('/settings')} />
          <Row label={copy.profileMenu.help} onClick={() => onNavigate(`/page/${slug(copy.profileMenu.help)}`)} />
          <hr className="divider menu__divider" />
          <Row label={copy.profileMenu.switchAccount} onClick={() => onNavigate('/login')} />
          <Row label={copy.profileMenu.logout} onClick={onLogout} danger />
        </div>
      </motion.div>
    </div>
  );
}
