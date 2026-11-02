// Small typographic pieces: section labels, the status line (● CALM), card
// meta rows, the count badge and key hints.
import type { CSSProperties, ReactNode } from 'react';
import clsx from 'clsx';
import { T } from '../theme/typography';
import { useViewport } from '../hooks/useBreakpoint';

export function SectionLabel({ children, className, as: Tag = 'h2', id }: { children: ReactNode; className?: string; as?: 'h2' | 'h3' | 'p'; id?: string }) {
  return (
    <Tag id={id} className={clsx(T.section, 'section-label', className)}>
      {children}
    </Tag>
  );
}

export function Dot({ color, size = 6, className, style }: { color: string; size?: number; className?: string; style?: CSSProperties }) {
  return <span aria-hidden className={clsx('dot', className)} style={{ width: size, height: size, background: color, ...style }} />;
}

export function StatusLine({ label, color, className }: { label: string; color: string; className?: string }) {
  return (
    <p className={clsx('status-line', className)}>
      <Dot color={color} size={5} className="status-line__dot" style={{ boxShadow: `0 0 8px ${color}` }} />
      <span className={T.status}>{label}</span>
    </p>
  );
}

export function MetaRow({ left, right }: { left: string; right?: string }) {
  return (
    <div className="meta-row">
      <span className={T.meta}>{left}</span>
      {right ? <span className={T.meta}>{right}</span> : null}
    </div>
  );
}

export function Badge({ count, color, className }: { count: number; color: string; className?: string }) {
  return (
    <span className={clsx('badge', T.badge, className)} style={{ background: color, boxShadow: `0 0 10px ${color}66` }}>
      {count}
    </span>
  );
}

/** Keyboard hint chip, shown only on desktop with a mouse (§8.4). */
export function KeyHint({ keys, className }: { keys: string[]; className?: string }) {
  const { wide, fine } = useViewport();
  if (!wide || !fine) return null;
  return (
    <span className={clsx('key-hint', className)} aria-hidden>
      {keys.map((k) => (
        <kbd key={k} className="kbd">
          {k}
        </kbd>
      ))}
    </span>
  );
}
