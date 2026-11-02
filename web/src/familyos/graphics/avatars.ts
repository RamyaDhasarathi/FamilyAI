// Avatar life stages from the design pack (design.md §6, AGENT_WEB.md §11.3).
// Same table as the mobile app's graphics/avatars.ts; on the web each stage is
// an animated WebP (converted from the pack's GIF) plus a still WebP, served
// from public/familyos/avatars.

export interface AvatarStage {
  stage: number;
  name: string;
  ages: string;
  /** Animated image URL. */
  gif: string;
  /** Still image URL. */
  png: string;
}

const base = `${import.meta.env.BASE_URL}familyos/avatars/`;
const stage = (n: number, name: string, ages: string, file: string): AvatarStage => ({
  stage: n,
  name,
  ages,
  gif: `${base}${file}.webp`,
  png: `${base}${file}_still.webp`,
});

export const AVATAR_STAGES: AvatarStage[] = [
  stage(1, 'The Playful Spark', '3–5', 'stage1_playful_spark'),
  stage(2, 'The Adventure Pod', '6–8', 'stage2_adventure_pod'),
  stage(3, 'The Bio-Kinetic Catalyst', '9–12', 'stage3_biokinetic_catalyst'),
  stage(4, 'The Glitch Synth', '13–15', 'stage4_glitch_synth'),
  stage(5, 'The Kinetic Prism', '16–18', 'stage5_kinetic_prism'),
  stage(6, 'The Digital Oasis', '19–25', 'stage6_digital_oasis'),
  stage(7, 'The Quantum Glass Hub', '26–59', 'stage7_quantum_glass_hub'),
  stage(8, 'The Warm Solaria', '60+', 'stage8_warm_solaria'),
];

/**
 * Accent colour per stage (design.md §6): stage 1 pastel pink, 2 bubble cyan,
 * 3 warm orange, 4 acid magenta, 5 prism cyan, 6 oasis mint, 7 teal-violet,
 * 8 warm gold. Used for halos, orbit dots and tints.
 */
export const stageAccent: Record<number, string> = {
  1: '#FF9EC7',
  2: '#7FD8FF',
  3: '#FF9A3C',
  4: '#FF3FD2',
  5: '#33D9FF',
  6: '#5EE6C8',
  7: '#7FA8FF',
  8: '#FFC14D',
};

/** Stage by age: 1: up to 5 (under-3s too), 2: 6–8, 3: 9–12, 4: 13–15, 5: 16–18, 6: 19–25, 7: 26–59, 8: 60+. */
export function avatarForAge(age: number): AvatarStage {
  const bounds = [5, 8, 12, 15, 18, 25, 59];
  const i = bounds.findIndex((b) => age <= b);
  return AVATAR_STAGES[i === -1 ? 7 : i];
}
