// When WebGL is unavailable or too slow (AGENT_WEB.md §7.1, §11.2): the
// stage-7 render from the design pack in place of the gem, tinted by a CSS
// overlay in the scenario colour, under the same satellites, labels and
// controls. Positioned by the same layout maths every frame.
import { useRef } from 'react';
import { AVATAR_STAGES } from '../../graphics/avatars';
import { gemAt } from '../../engine/orbitLayout';
import { webCopy } from '../../mocks/webData';
import { useEngine, useFrame } from './engineContext';

export function StageFallback() {
  const engine = useEngine();
  const el = useRef<HTMLDivElement>(null);
  useFrame(engine, (e) => {
    const d = el.current;
    if (!d) return;
    const g = gemAt(e.stage, e.scene.v.dashT);
    const s = g.r * 2.6;
    d.style.transform = `translate3d(${(g.x - s / 2).toFixed(1)}px, ${(g.y - s / 2).toFixed(1)}px, 0)`;
    d.style.width = d.style.height = `${s.toFixed(1)}px`;
  });
  return (
    <div className="stage-fallback">
      <div className="stage-fallback__glow" />
      <div ref={el} className="stage-fallback__gem">
        <img src={AVATAR_STAGES[6].gif} alt="" width={320} height={320} />
        <span className="stage-fallback__tint" />
      </div>
      <p className="sr-only">{webCopy.webglFallback}</p>
    </div>
  );
}
