// Motion tokens (AGENT.md §6.5, §9).
import { Easing } from 'react-native-reanimated';

export const springs = {
  /** Presses, pills, badges. */
  snappy: { damping: 18, stiffness: 220, mass: 1 },
  /** Sheets and layout. */
  soft: { damping: 22, stiffness: 120, mass: 1 },
  /** Gem squash on tap. */
  squash: { damping: 9, stiffness: 260, mass: 0.8 },
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
};

export const easings = {
  inOutCubic: Easing.inOut(Easing.cubic),
  outCubic: Easing.out(Easing.cubic),
  inOutSine: Easing.inOut(Easing.sin),
};

export const press = { scale: 0.96, opacity: 0.85 };

/** One full turn of the core, in seconds. All ambient loops are whole multiples of this phase. */
export const LOOP_SECONDS = 18;
