// Desktop sidebar (MASTER_AGENT.md §3.1, §7 Phase 2.1; FamilyOS.mp4 0:25,
// 1:50): logo, five groups split by thin dividers, space icons in our agent
// colours, the active page as a filled pill, Search ⌘K, Settings, and the
// signed-in member with Sign out. `rail` is the slim icon-only version shown
// over the orb home (§1 A2), so the orb stays the hero. Hovering the rail (or
// tabbing into it) opens the full sidebar over the stage; leaving folds it back.
import { useLayoutEffect, useState, type FocusEvent } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router';
import clsx from 'clsx';
import { LogOut } from 'lucide-react';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { isMissed, isUndecided } from '../../desk/selectors';
import { MiniGem } from '../../components/MiniGem';
import { deskCopy } from '../copy';
import { DESK_FLAGS, NAV_GROUPS, isActive, type NavItem } from './nav';
import { useDeskUI } from './useDeskUI';

function useCounts(): Partial<Record<NavItem['id'], number>> {
  const proposals = useDesk((s) => s.proposals);
  const quarantine = useDesk((s) => s.quarantine.length);
  const tz = useDesk((s) => s.settings.timezone);
  const now = new Date();
  const waiting = proposals.filter((p) => isUndecided(p) || isMissed(p, now, tz)).length;
  return { waiting, quarantine };
}

export function Sidebar({ rail: railProp = false }: { rail?: boolean }) {
  const { pathname } = useLocation();
  // Hover / focus "peek": the rail shows as the full sidebar while the pointer or focus is on it.
  const [peek, setPeek] = useState(false);
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    setLastPath(pathname);
    setPeek(false);
  }
  const rail = railProp && !peek;
  // Lets the Home header (shell.css) slide right with the opened rail.
  useLayoutEffect(() => {
    const c = document.documentElement.classList;
    c.toggle('desk-rail-peek', railProp && peek);
    return () => c.remove('desk-rail-peek');
  }, [railProp, peek]);
  const onBlur = (e: FocusEvent<HTMLElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setPeek(false);
  };
  const navigate = useNavigate();
  const profile = useFamilyOS((s) => s.profile);
  const logOut = useFamilyOS((s) => s.logOut);
  const openPalette = useDeskUI((s) => s.setPaletteOpen);
  const actor = useDesk((s) => s.actor);
  const counts = useCounts();
  // Today and the logo bring the Home's stones back if it had turned into the Ask chat.
  const endHomeChat = () => useDeskUI.getState().setHomeChat(false);

  const item = (it: NavItem) => {
    const Icon = it.icon;
    const active = isActive(it, pathname);
    const n = counts[it.id];
    const inner = (
      <>
        <span className="desk-nav__icon" style={it.color ? { color: it.color } : undefined}>
          <Icon size={rail ? 18 : 16} strokeWidth={1.9} aria-hidden />
        </span>
        <span className={clsx('desk-nav__label', rail && 'sr-only')}>{it.label}</span>
        {!rail && n ? <span className="desk-nav__count" aria-label={`${n} open`}>{n}</span> : null}
        {!rail && it.kbd ? <kbd className="kbd desk-nav__kbd">{it.kbd}</kbd> : null}
      </>
    );
    const cls = clsx('desk-nav__item', active && 'is-active');
    const title = rail ? it.label : undefined;
    return (
      <li key={it.id}>
        {it.to ? (
          <NavLink to={it.to} className={cls} aria-current={active ? 'page' : undefined} title={title} onClick={it.id === 'today' ? endHomeChat : undefined}>
            {inner}
          </NavLink>
        ) : (
          <button type="button" className={cls} onClick={() => openPalette(true)} title={title} aria-haspopup="dialog" aria-keyshortcuts="Meta+K Control+K">
            {inner}
          </button>
        )}
      </li>
    );
  };

  return (
    <nav
      className={clsx('desk-side', rail && 'desk-side--rail', railProp && peek && 'desk-side--peek')}
      aria-label={deskCopy.navLabel}
      onMouseEnter={railProp ? () => setPeek(true) : undefined}
      onMouseLeave={railProp ? () => setPeek(false) : undefined}
      onFocus={railProp ? () => setPeek(true) : undefined}
      onBlur={railProp ? onBlur : undefined}
    >
      <NavLink to="/" onClick={endHomeChat} className="desk-side__brand" aria-label={`${deskCopy.brand}, ${deskCopy.homeLink}`} title={rail ? deskCopy.homeLink : undefined}>
        <MiniGem size={rail ? 34 : 30} still />
        {rail ? null : <span className="desk-side__word">{deskCopy.brand}</span>}
      </NavLink>
      <div className="desk-side__groups scroll-y no-scrollbar">
        {NAV_GROUPS.map((g, i) => {
          const items = g.filter((it) => DESK_FLAGS[it.id] && it.sidebar !== false);
          return items.length ? (
            <ul key={i} className="desk-nav">
              {items.map(item)}
            </ul>
          ) : null;
        })}
      </div>
      {profile ? (
        <div className="desk-side__foot">
          <NavLink to={`/family/${actor}`} className="desk-side__me" title={rail ? profile.name : undefined} aria-label={`${profile.name}, your profile`}>
            <span className="desk-side__avatar t-chip" aria-hidden>
              {profile.initial}
            </span>
            {rail ? null : <span className="desk-side__name t-small-strong">{profile.name}</span>}
          </NavLink>
          {rail ? null : (
            <button
              type="button"
              className="desk-side__out round-btn"
              aria-label={deskCopy.signOut}
              title={deskCopy.signOut}
              onClick={async () => {
                await logOut();
                navigate('/login', { replace: true });
              }}
            >
              <LogOut size={15} aria-hidden />
            </button>
          )}
        </div>
      ) : null}
    </nav>
  );
}
