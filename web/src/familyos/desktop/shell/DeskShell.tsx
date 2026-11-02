// The desktop shell (MASTER_AGENT.md §3.1, §7 Phase 2; FamilyOS.mp4 0:25,
// 1:50, 7:20). App.tsx renders it beside the routes only when
// useIsDesktopWeb() is true and the page is not an auth / splash page:
//   • the sidebar (an icon rail over the orb home, so the orb stays the hero);
//   • the floating Ask bar, except on pages with their own Ask bar;
//   • the ⌘K / Ctrl+K palette.
// It marks <html> with `with-desk-shell` / `with-desk-rail` / `with-desk-ask`; shell.css uses
// those classes (desktop-only by construction) to offset every page by the
// sidebar and to keep fixed bars, toasts and the last row clear of it.
import { useEffect, useLayoutEffect } from 'react';
import { useLocation } from 'react-router';
import { Sidebar } from './Sidebar';
import { FloatingAsk } from './FloatingAsk';
import { CommandPalette } from './CommandPalette';
import { pageHasOwnAsk } from './nav';
import { useDeskUI } from './useDeskUI';
import { useNow, useTodayItems } from '../../desk/hooks';
import './shell.css';

export function DeskShell() {
  const { pathname } = useLocation();
  const rail = pathname === '/';
  const ask = !pageHasOwnAsk(pathname);
  const todayCount = useTodayItems(useNow()).length;
  useEffect(() => {
    useDeskUI.getState().setTodayCount(todayCount);
  }, [todayCount]);

  useLayoutEffect(() => {
    const c = document.documentElement.classList;
    c.toggle('with-desk-shell', !rail);
    c.toggle('with-desk-rail', rail);
    c.toggle('with-desk-ask', ask);
    return () => c.remove('with-desk-shell', 'with-desk-rail', 'with-desk-ask');
  }, [rail, ask]);

  // ⌘K / Ctrl+K anywhere, even while typing; the palette's own Esc closes it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== 'k') return;
      e.preventDefault();
      const ui = useDeskUI.getState();
      ui.setPaletteOpen(!ui.paletteOpen);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  // A route change closes the palette.
  useEffect(() => {
    useDeskUI.getState().setPaletteOpen(false);
  }, [pathname]);

  return (
    <>
      <Sidebar rail={rail} />
      {ask ? <FloatingAsk /> : null}
      <CommandPalette />
    </>
  );
}

export default DeskShell;
