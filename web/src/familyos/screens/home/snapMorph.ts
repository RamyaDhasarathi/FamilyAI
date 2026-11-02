// Snap the particle morph back into the gem at once (no 900 ms fly-back).
// Used by useWalkthrough's stopNow on desktop navigation (MASTER_AGENT.md §7
// Phase 1.2), so returning to Home always shows the idle crystal.
import type { OrbitScene } from '../../engine/sceneState';
import { setHighlight } from '../../engine/coreInput';

export function snapMorphHome(scene: OrbitScene) {
  setHighlight(scene, -1);
  scene.morphFrom = 0;
  scene.morphTo = 0;
  scene.tw.set('morphT', 0);
  scene.tw.set('morphAlpha', 0);
  scene.tw.set('explode', 0);
}
