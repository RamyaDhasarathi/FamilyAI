// ⌘K / Ctrl+K palette (MASTER_AGENT.md §3.2, §7 Phase 2.3; FamilyOS.mp4
// 7:20): "Find a notice, a person, a page — or ask anything…" with a mic.
// Empty: six suggestions for the Carters (each asks). Typing: pages, people
// and notices that match; ↑/↓ move, Enter opens the highlighted (first)
// match or, with none, asks on /ask?q=… Esc closes. It only finds and
// navigates; it never changes anything.
import { useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router';
import { AnimatePresence, motion } from 'framer-motion';
import clsx from 'clsx';
import {
  CalendarDays, Clock, CornerDownLeft, FileText, GraduationCap, LayoutDashboard, Mic, Receipt, Search, Sparkles, Sun, User, UtensilsCrossed, type LucideIcon,
} from 'lucide-react';
import { useEscape } from '../../hooks/useEscape';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useDesk } from '../../desk/store';
import { visibleNotices } from '../../desk/selectors';
import { fmtText } from '../../desk/format';
import { useListening } from '../../screens/home/useHomeEffects';
import { AGENT_IDS, colors } from '../../theme/tokens';
import { agentNames } from '../../mocks/data';
import { deskCopy } from '../copy';
import { askPath, navItems } from './nav';
import { useDeskUI } from './useDeskUI';

interface Hit {
  id: string;
  group: 'pages' | 'people' | 'notices' | 'ask';
  label: string;
  sub?: string;
  to: string;
  icon: LucideIcon;
  color?: string;
}

const C = deskCopy.palette;
const SUGGESTION_ICONS: Record<string, LucideIcon> = { Sun, CalendarDays, Receipt, GraduationCap, UtensilsCrossed, Clock };
const norm = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ’']/g, '');

export function CommandPalette() {
  const open = useDeskUI((s) => s.paletteOpen);
  const setOpen = useDeskUI((s) => s.setPaletteOpen);
  return createPortal(<AnimatePresence>{open ? <Panel key="palette" onClose={() => setOpen(false)} /> : null}</AnimatePresence>, document.body);
}

function Panel({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const members = useDesk((s) => s.members);
  const notices = useDesk((s) => s.notices);
  const currency = useDesk((s) => s.settings.currency);
  const { listening, listen } = useListening(null, (t) => {
    setQ(t);
    setActive(0);
    input.current?.focus();
  });
  useEscape(true, onClose);
  useFocusTrap(panel, true, { initial: input });

  const hits = useMemo<Hit[]>(() => {
    const t = norm(q.trim());
    if (!t) return [];
    const has = (...xs: (string | undefined)[]) => xs.some((x) => x && norm(x).includes(t));
    const pages: Hit[] = [
      ...navItems().filter((i) => i.to && has(i.label)).map((i) => ({ id: `p_${i.id}`, group: 'pages' as const, label: i.label, to: i.to!, icon: i.icon, color: i.color })),
      ...AGENT_IDS.filter((a) => has(agentNames[a], `${agentNames[a]} dashboard`)).map((a) => ({ id: `p_${a}`, group: 'pages' as const, label: `${agentNames[a]} dashboard`, to: `/agents/${a}`, icon: LayoutDashboard, color: colors.agents[a] })),
    ];
    const people: Hit[] = members.filter((m) => has(m.name, m.fullName, m.school)).map((m) => ({ id: `m_${m.id}`, group: 'people', label: m.fullName, sub: m.school ? `${m.school} · ${m.grade}` : m.role, to: `/family/${m.id}`, icon: User }));
    const found: Hit[] = visibleNotices({ notices })
      .filter((n) => has(n.title, n.sender, fmtText(n.summary, currency)))
      .sort((a, b) => b.receivedAt.localeCompare(a.receivedAt))
      .slice(0, 6)
      .map((n) => ({ id: `n_${n.id}`, group: 'notices', label: fmtText(n.title, currency), sub: `${n.sender} · ${fmtText(n.summary, currency)}`, to: `/inbox/${n.id}`, icon: FileText }));
    return [...pages.slice(0, 4), ...people.slice(0, 4), ...found, { id: 'ask', group: 'ask', label: C.askRow(q.trim()), to: askPath(q.trim()), icon: Sparkles }];
  }, [q, members, notices, currency]);

  const go = (to: string) => {
    onClose();
    navigate(to);
  };
  const onKey = (e: KeyboardEvent) => {
    if (!hits.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => (i + (e.key === 'ArrowDown' ? 1 : hits.length - 1)) % hits.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      go(hits[active]?.to ?? askPath(q.trim()));
    }
  };

  let lastGroup = '';
  return (
    <div className="desk-palette-root">
      <motion.div className="sheet-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.16 }} onClick={onClose} aria-hidden />
      <motion.div
        ref={panel}
        className="desk-palette glass glass--sheet"
        role="dialog"
        aria-modal="true"
        aria-label={C.label}
        initial={{ opacity: 0, y: -8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -6, transition: { duration: 0.12 } }}
        transition={{ duration: 0.18, ease: [0.33, 1, 0.68, 1] }}
      >
        <div className="desk-palette__bar">
          <Search size={18} className="desk-palette__glass" aria-hidden />
          <input
            ref={input}
            className="desk-palette__input t-input"
            value={listening ? '' : q}
            placeholder={listening ? C.listening : C.placeholder}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKey}
            role="combobox"
            aria-expanded={hits.length > 0}
            aria-controls="desk-palette-list"
            aria-activedescendant={hits[active] ? `pal-${hits[active].id}` : undefined}
            aria-label={C.placeholder}
            autoComplete="off"
          />
          <button type="button" className={clsx('desk-palette__mic', listening && 'is-on')} onClick={listen} aria-label={deskCopy.ask.mic} aria-pressed={listening}>
            <Mic size={17} aria-hidden />
          </button>
        </div>
        {q.trim() ? (
          <ul id="desk-palette-list" className="desk-palette__list scroll-y" role="listbox" aria-label={C.label}>
            {hits.map((h, i) => {
              const head = h.group !== 'ask' && h.group !== lastGroup ? C.groups[h.group] : null;
              lastGroup = h.group;
              const Icon = h.icon;
              return (
                <li key={h.id} role="presentation">
                  {head ? <p className="desk-palette__group t-section">{head}</p> : null}
                  <button
                    id={`pal-${h.id}`}
                    type="button"
                    role="option"
                    aria-selected={i === active}
                    className={clsx('desk-palette__row', i === active && 'is-active')}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => go(h.to)}
                    tabIndex={-1}
                  >
                    <Icon size={16} aria-hidden style={h.color ? { color: h.color } : undefined} className="desk-palette__icon" />
                    <span className="desk-palette__text">
                      <span className="t-small-strong">{h.label}</span>
                      {h.sub ? <span className="t-small desk-palette__sub">{h.sub}</span> : null}
                    </span>
                    {i === active ? <CornerDownLeft size={14} className="desk-palette__enter" aria-hidden /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <ul className="desk-palette__list" aria-label="Suggestions">
            {C.suggestions.map((s) => {
              const Icon = SUGGESTION_ICONS[s.icon] ?? Sparkles;
              return (
                <li key={s.text}>
                  <button type="button" className="desk-palette__row" onClick={() => go(askPath(s.text))}>
                    <Icon size={16} aria-hidden className="desk-palette__icon" />
                    <span className="t-small-strong">{s.text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <p className="desk-palette__foot t-small">{C.footer}</p>
      </motion.div>
    </div>
  );
}
