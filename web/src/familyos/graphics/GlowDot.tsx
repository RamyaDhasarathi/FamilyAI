// Glowing orb in an agent colour (Today rows) and the small timeline dot.
import { useId } from 'react';

export function GlowOrb({ color, size = 28 }: { color: string; size?: number }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden className="glow-orb">
      <defs>
        <radialGradient id={`o${id}`} cx="38%" cy="34%" r="70%">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity={0.85} />
          <stop offset="0.28" stopColor={color} stopOpacity={0.95} />
          <stop offset="0.85" stopColor={color} stopOpacity={0.45} />
          <stop offset="1" stopColor={color} stopOpacity={0.1} />
        </radialGradient>
        <radialGradient id={`h${id}`} cx="50%" cy="50%" r="50%">
          <stop offset="0.55" stopColor={color} stopOpacity={0.35} />
          <stop offset="1" stopColor={color} stopOpacity={0} />
        </radialGradient>
      </defs>
      <circle cx={20} cy={20} r={20} fill={`url(#h${id})`} />
      <circle cx={20} cy={20} r={13} fill={`url(#o${id})`} />
    </svg>
  );
}

export function GlowDot({ color, size = 8 }: { color: string; size?: number }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg width={size * 2.2} height={size * 2.2} viewBox="0 0 22 22" aria-hidden>
      <defs>
        <radialGradient id={`d${id}`} cx="50%" cy="50%" r="50%">
          <stop offset="0.35" stopColor={color} stopOpacity={0.5} />
          <stop offset="1" stopColor={color} stopOpacity={0} />
        </radialGradient>
      </defs>
      <circle cx={11} cy={11} r={11} fill={`url(#d${id})`} />
      <circle cx={11} cy={11} r={4} fill={color} />
    </svg>
  );
}
