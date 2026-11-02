// Pill buttons: white primary ("Move call to 3:30"), glass secondary ("Later",
// "Ask about this") and the floating Close pill.
import clsx from 'clsx';
import { copy } from '../mocks/data';
import { Pressable, type PressableProps } from './Pressable';

interface PillProps extends Omit<PressableProps, 'children'> {
  label: string;
  variant?: 'primary' | 'secondary' | 'violet' | 'danger';
  block?: boolean;
}

export function PillButton({ label, variant = 'secondary', block, className, ...rest }: PillProps) {
  return (
    <Pressable className={clsx('pill', `pill--${variant}`, block && 'pill--block', className)} aria-label={rest['aria-label'] ?? label} {...rest}>
      {label}
    </Pressable>
  );
}

export function ClosePill({ onClick, label = copy.close, className }: { onClick: () => void; label?: string; className?: string }) {
  return (
    <Pressable className={clsx('pill', 'pill--close', className)} onClick={onClick} aria-label={label}>
      {label}
    </Pressable>
  );
}
