// Motion tokens (AGENT_WEB.md §6.5, §9), ported from the mobile app's
// theme/motion.ts. Springs use the same stiffness and damping in Framer
// Motion's `type: 'spring'`; the render loop uses the same numbers in
// engine/tween.ts.

export const springs = {
  /** Presses, pills, badges. */
  snappy: { damping: 18, stiffness: 220, mass: 1 },
  /** Sheets and layout. */
  soft: { damping: 22, stiffness: 120, mass: 1 },
  /** Gem squash on tap. */
  squash: { damping: 9, stiffness: 260, mass: 0.8 },
};

/** Framer Motion transitions built from the springs above. */
export const fm = {
  snappy: { type: 'spring' as const, ...springs.snappy },
  soft: { type: 'spring' as const, ...springs.soft },
};

export const durations = {
  scenario: 700,
  fadeIn: 400,
  stagger: 40,
  satelliteStagger: 80,
  morph: 900,
  dissolve: 650,
  walkStep: 3500,
  toast: 2200,
  countUp: 600,
  sparkline: 900,
  headline: 320,
  listen: 2500,
  hover: 120,
  /** Press-and-hold on the crystal or a satellite (mobile long-press). */
  hold: 480,
};

/** Cubic-bezier equivalents of the mobile easings, for CSS and Framer Motion. */
export const easings = {
  inOutCubic: [0.65, 0, 0.35, 1] as [number, number, number, number],
  outCubic: [0.33, 1, 0.68, 1] as [number, number, number, number],
  inCubic: [0.32, 0, 0.67, 0] as [number, number, number, number],
  inOutSine: [0.37, 0, 0.63, 1] as [number, number, number, number],
};

export const press = { scale: 0.96, opacity: 0.85 };

/** One full turn of the core, in seconds. All ambient loops are whole multiples of this phase. */
export const LOOP_SECONDS = 18;
