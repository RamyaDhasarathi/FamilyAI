// Every clickable (AGENT_WEB.md §6.5): press = scale 0.96 + opacity 0.85 on the
// snappy spring; hover (mouse only) lifts 1 px. Always a real <button>.
import { forwardRef } from 'react';
import { motion, type HTMLMotionProps } from 'framer-motion';
import { fm, press } from '../theme/motion';
import { useReducedMotion } from '../hooks/useReducedMotion';

export type PressableProps = HTMLMotionProps<'button'> & {
  /** Scale on press; defaults to the motion token. */
  pressScale?: number;
  /** Lift on hover (off for full-width rows). */
  lift?: boolean;
};

export const Pressable = forwardRef<HTMLButtonElement, PressableProps>(function Pressable(
  { pressScale = press.scale, lift = true, type = 'button', ...rest },
  ref
) {
  const reduced = useReducedMotion();
  return (
    <motion.button
      ref={ref}
      type={type}
      whileTap={reduced ? { opacity: press.opacity } : { scale: pressScale, opacity: press.opacity }}
      whileHover={lift && !reduced ? { y: -1 } : undefined}
      transition={fm.snappy}
      {...rest}
    />
  );
});
