// Dev-only graphics preview (/dev/graphics, AGENT_WEB.md §7): mini gems in
// every scenario and agent palette, and the hero charts, to tune each piece
// on its own. The full stage (gem, satellites, morph) is Home itself; open
// it and press Shift+S to cycle scenarios.
import { AGENT_IDS, colors } from '../../theme/tokens';
import { SCENARIOS } from '../../theme/stateThemes';
import { agentDetails, agentNames } from '../../mocks/data';
import { T } from '../../theme/typography';
import { MiniGem } from '../../components/MiniGem';
import { AgentHero } from '../../components/AgentHero';
import { SectionLabel } from '../../components/Labels';
import { ScreenShell } from '../../components/ScreenShell';

export default function DevGraphics() {
  return (
    <ScreenShell title="Graphics (dev)" wide>
      <SectionLabel>SCENARIOS</SectionLabel>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {SCENARIOS.map((s) => (
          <figure key={s} style={{ margin: 0, textAlign: 'center' }}>
            <MiniGem size={160} scenario={s} />
            <figcaption className={T.small}>{s}</figcaption>
          </figure>
        ))}
      </div>
      <SectionLabel className="gap-top">AGENTS</SectionLabel>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {AGENT_IDS.map((a) => (
          <figure key={a} style={{ margin: 0, textAlign: 'center' }}>
            <MiniGem size={110} agentColor={colors.agents[a]} />
            <figcaption className={T.small}>{agentNames[a]}</figcaption>
          </figure>
        ))}
      </div>
      <SectionLabel className="gap-top">HERO CHARTS</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
        {AGENT_IDS.map((a) => (
          <AgentHero key={a} hero={agentDetails[a].hero} color={colors.agents[a]} />
        ))}
      </div>
    </ScreenShell>
  );
}
