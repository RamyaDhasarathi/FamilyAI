// Frosted-glass surface (AGENT_WEB.md §6.4): backdrop blur + translucent fill +
// 1 px border + soft inner top highlight, with an opaque fallback where
// backdrop-filter is unsupported (globals.css).
import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';

interface Props extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
  strong?: boolean;
  sheet?: boolean;
  /** Faint wash of the current scenario colour (panels). */
  tint?: boolean;
}

export function Glass({ children, strong, sheet, tint, className, ...rest }: Props) {
  return (
    <div className={clsx('glass', strong && 'glass--strong', sheet && 'glass--sheet', tint && 'tint-mood', className)} {...rest}>
      {children}
    </div>
  );
}
