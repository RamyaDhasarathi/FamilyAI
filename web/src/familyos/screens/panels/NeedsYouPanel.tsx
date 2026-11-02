// Needs you (AGENT_WEB.md §8.4, video 2:05): live count, tinted by the most
// severe item, swipeable / clickable cards. J / K (or the arrow keys) move
// between cards, Enter runs the main action, L snoozes. Emptying the list
// closes the panel and Home goes calm with a burst (useCelebration).
import { useRef, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { copy } from '../../mocks/data';
import { webCopy } from '../../mocks/webData';
import { useFamilyOS } from '../../store/useFamilyOS';
import { T } from '../../theme/typography';
import { KeyHint } from '../../components/Labels';
import { Sheet } from '../../components/Sheet';
import { SwipeCard } from '../../components/SwipeCard';

export function NeedsYouPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const needs = useFamilyOS((s) => s.needs);
  const resolve = useFamilyOS((s) => s.resolve);
  const snooze = useFamilyOS((s) => s.snooze);
  const list = useRef<HTMLDivElement>(null);

  const onKey = (e: KeyboardEvent) => {
    const keys = ['j', 'k', 'J', 'K', 'ArrowDown', 'ArrowUp'];
    if (!keys.includes(e.key)) return;
    const cards = Array.from(list.current?.querySelectorAll<HTMLElement>('[data-swipe-card]') ?? []);
    if (!cards.length) return;
    e.preventDefault();
    const at = cards.findIndex((c) => c.contains(document.activeElement));
    const down = e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown';
    const next = at < 0 ? 0 : Math.min(cards.length - 1, Math.max(0, at + (down ? 1 : -1)));
    cards[next].focus();
    cards[next].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };

  const header = (
    <div className="needs-head">
      <h2 id="needs-title" className={T.smallStrong} style={{ color: '#fff' }}>
        {copy.needsTitle(needs.length)}
      </h2>
      <KeyHint keys={['J', 'K']} />
    </div>
  );
  return (
    <Sheet open={open} onClose={onClose} labelledBy="needs-title" header={header} tint maxFrac={0.8}>
      <div ref={list} className="needs-body" onKeyDown={onKey}>
        {needs.length === 0 ? <p className={`${T.small} t-center needs-empty`}>{webCopy.emptyNeeds}</p> : null}
        <AnimatePresence initial={false}>
          {needs.map((n) => (
            <motion.div key={n.id} layout exit={{ opacity: 0, height: 0, transition: { duration: 0.2 } }} transition={{ layout: { duration: 0.28 } }}>
              <SwipeCard item={n} onDone={resolve} onLater={snooze} hints />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Sheet>
  );
}
