// Circular summary button (AGENT_WEB.md §8.1.5): Listen mode plays the spoken
// walkthrough, Read mode opens the written summary. While playing, the icon
// is a stop square and the ring fills with progress.
import { useId } from 'react';
import { motion } from 'framer-motion';
import { FileText, ListPlus, Square } from 'lucide-react';
import type { SummaryMode } from '../services/interfaces';
import { colors, sizes } from '../theme/tokens';
import { easings } from '../theme/motion';
import { Pressable } from './Pressable';

const S = sizes.askBar;
const R = S / 2 - 1.5;
const CIRC = 2 * Math.PI * R;

interface Props {
  mode: SummaryMode;
  playing: boolean;
  /** 0..1 progress through the walkthrough. */
  progress: number;
  onPress: () => void;
}

export function SummaryButton({ mode, playing, progress, onPress }: Props) {
  const id = useId().replace(/:/g, '');
  const Icon = playing ? Square : mode === 'listen' ? ListPlus : FileText;
  const label = playing
    ? 'Stop the summary'
    : mode === 'listen'
      ? "Summary, plays today's summary aloud"
      : "Summary, opens today's written summary";
  return (
    <Pressable onClick={onPress} aria-label={label} className="summary-btn" style={{ width: S, height: S }}>
      <svg width={S} height={S} className="summary-btn__ring" aria-hidden>
        <defs>
          <linearGradient id={`sr${id}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#5FF2E0" />
            <stop offset="0.5" stopColor="#8C7CFF" />
            <stop offset="1" stopColor="#F07BD0" />
          </linearGradient>
        </defs>
        <circle cx={S / 2} cy={S / 2} r={R} stroke={`url(#sr${id})`} strokeWidth={1.4} fill="rgba(28,31,40,0.8)" opacity={0.9} />
        <motion.circle
          cx={S / 2}
          cy={S / 2}
          r={R}
          stroke="#FFFFFF"
          strokeWidth={2.2}
          fill="none"
          strokeDasharray={`${CIRC} ${CIRC}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${S / 2} ${S / 2})`}
          initial={false}
          animate={{ strokeDashoffset: CIRC * (1 - (playing ? progress : 0)) }}
          transition={{ duration: playing ? 0.6 : 0.25, ease: easings.outCubic }}
        />
      </svg>
      <span className="summary-btn__icon" aria-hidden>
        <Icon size={playing ? 14 : 20} color={colors.inkStrong} fill={playing ? colors.inkStrong : 'none'} strokeWidth={1.8} />
      </span>
    </Pressable>
  );
}
