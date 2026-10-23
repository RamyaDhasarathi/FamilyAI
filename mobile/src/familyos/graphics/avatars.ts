// Avatar life stages from the design pack (design.md §6, AGENT.md §11.3).
// Stills and animations live in separate folders: Android packages bundled
// images as resources named without their extension, so `x.png` and `x.gif`
// in one folder collide in release builds.

export interface AvatarStage {
  stage: number;
  name: string;
  ages: string;
  gif: number;
  png: number;
}

export const AVATAR_STAGES: AvatarStage[] = [
  { stage: 1, name: 'The Playful Spark', ages: '3–5', gif: require('../../../assets/familyos/avatars/anim/stage1_playful_spark.gif'), png: require('../../../assets/familyos/avatars/still/stage1_playful_spark.png') },
  { stage: 2, name: 'The Adventure Pod', ages: '6–8', gif: require('../../../assets/familyos/avatars/anim/stage2_adventure_pod.gif'), png: require('../../../assets/familyos/avatars/still/stage2_adventure_pod.png') },
  { stage: 3, name: 'The Bio-Kinetic Catalyst', ages: '9–12', gif: require('../../../assets/familyos/avatars/anim/stage3_biokinetic_catalyst.gif'), png: require('../../../assets/familyos/avatars/still/stage3_biokinetic_catalyst.png') },
  { stage: 4, name: 'The Glitch Synth', ages: '13–15', gif: require('../../../assets/familyos/avatars/anim/stage4_glitch_synth.gif'), png: require('../../../assets/familyos/avatars/still/stage4_glitch_synth.png') },
  { stage: 5, name: 'The Kinetic Prism', ages: '16–18', gif: require('../../../assets/familyos/avatars/anim/stage5_kinetic_prism.gif'), png: require('../../../assets/familyos/avatars/still/stage5_kinetic_prism.png') },
  { stage: 6, name: 'The Digital Oasis', ages: '19–25', gif: require('../../../assets/familyos/avatars/anim/stage6_digital_oasis.gif'), png: require('../../../assets/familyos/avatars/still/stage6_digital_oasis.png') },
  { stage: 7, name: 'The Quantum Glass Hub', ages: '26–59', gif: require('../../../assets/familyos/avatars/anim/stage7_quantum_glass_hub.gif'), png: require('../../../assets/familyos/avatars/still/stage7_quantum_glass_hub.png') },
  { stage: 8, name: 'The Warm Solaria', ages: '60+', gif: require('../../../assets/familyos/avatars/anim/stage8_warm_solaria.gif'), png: require('../../../assets/familyos/avatars/still/stage8_warm_solaria.png') },
];

/** Stage by age: 1: 3–5, 2: 6–8, 3: 9–12, 4: 13–15, 5: 16–18, 6: 19–25, 7: 26–59, 8: 60+. */
export function avatarForAge(age: number): AvatarStage {
  const bounds = [5, 8, 12, 15, 18, 25, 59];
  const i = bounds.findIndex((b) => age <= b);
  return AVATAR_STAGES[i === -1 ? 7 : i];
}
