// Press-and-hold a satellite: a circle in the agent's colour expands from
// the satellite to cover the screen, then the agent page fades in over it
// (AGENT_WEB.md §7.3, §9 "the agent page expands from its position").
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import { colors, withAlpha } from '../../theme/tokens';
import type { Reveal } from '../../store/useWebUI';

export function AgentReveal({ reveal, onCovered, onDone }: { reveal: Reveal; onCovered: () => void; onDone: () => void }) {
  const { x, y, agent } = reveal;
  const W = window.innerWidth;
  const H = window.innerHeight;
  const R = Math.hypot(Math.max(x, W - x), Math.max(y, H - y));
  useEffect(() => {
    const a = window.setTimeout(onCovered, 380);
    const b = window.setTimeout(onDone, 1100);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return createPortal(
    <motion.div
      className="agent-reveal"
      aria-hidden
      style={{ left: x - R, top: y - R, width: R * 2, height: R * 2, background: withAlpha(colors.agents[agent], 0.16) }}
      initial={{ scale: 0.04, opacity: 0 }}
      animate={{ scale: 1, opacity: [0, 1, 1, 0] }}
      transition={{ scale: { duration: 0.38, ease: [0.33, 1, 0.68, 1] }, opacity: { duration: 1.1, times: [0, 0.1, 0.6, 1] } }}
    >
      <span className="agent-reveal__dark" />
    </motion.div>,
    document.body
  );
}
