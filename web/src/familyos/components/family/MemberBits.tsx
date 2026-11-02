// Small family pieces (mobile components/family/MemberBits.tsx): the member
// avatar (stage image or photo in a glass ring with a halo in the stage
// colour), a completion ring, "needs update" tags and section status pills.
import { motion } from 'framer-motion';
import clsx from 'clsx';
import type { FamilyMember, SectionStatus } from '../../services/interfaces';
import { stageOf } from '../../family/model';
import { colors, withAlpha } from '../../theme/tokens';
import { useReducedMotion } from '../../hooks/useReducedMotion';

export const AMBER = '#FFB23F';
export const GREEN = '#4DD98C';

/** Stage image (animated when `animated`), or the member's photo, in a glass ring with a stage-coloured halo. */
export function MemberAvatar({ member, size, animated, className }: { member: FamilyMember; size: number; animated?: boolean; className?: string }) {
  const st = stageOf(member);
  const src = member.photoUri || (animated ? st.gif : st.png);
  return (
    <span className={clsx('member-avatar', className)} style={{ width: size, height: size }} aria-hidden>
      <span className="member-avatar__halo" style={{ background: `radial-gradient(circle, ${withAlpha(st.accent, 0.35)} 36%, ${withAlpha(st.accent, 0)} 68%)` }} />
      <span className="member-avatar__ring" style={{ borderColor: withAlpha(st.accent, 0.55) }}>
        <img src={src} alt="" width={size - 4} height={size - 4} loading="lazy" decoding="async" />
      </span>
    </span>
  );
}

/** Completion ring; the sweep animates in on mount. */
export function CompletionRing({ value, size, stroke = 3, color, delay = 0 }: { value: number; size: number; stroke?: number; color: string; delay?: number }) {
  const reduced = useReducedMotion();
  const r = (size - stroke) / 2;
  return (
    <svg width={size} height={size} className="completion-ring" role="img" aria-label={`${Math.round(value * 100)}% complete`}>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.1)" strokeWidth={stroke} fill="none" />
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        stroke={color}
        strokeWidth={stroke}
        fill="none"
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        initial={{ pathLength: reduced ? value : 0 }}
        animate={{ pathLength: value }}
        transition={{ delay: reduced ? 0 : delay / 1000, duration: reduced ? 0 : 0.7, ease: [0.33, 1, 0.68, 1] }}
      />
    </svg>
  );
}

export function Tag({ text, color }: { text: string; color: string }) {
  return (
    <span className="family-tag t-chip" style={{ color, background: withAlpha(color, 0.14), borderColor: withAlpha(color, 0.45) }}>
      {text}
    </span>
  );
}

const STATUS: Record<SectionStatus, { text: string; color: string }> = {
  complete: { text: 'Complete', color: GREEN },
  needsUpdate: { text: 'Needs update', color: AMBER },
  notStarted: { text: 'Not started', color: '#8E93A3' },
};

export function StatusPill({ status }: { status: SectionStatus }) {
  const s = STATUS[status];
  return <Tag text={s.text} color={status === 'notStarted' ? colors.muted : s.color} />;
}
