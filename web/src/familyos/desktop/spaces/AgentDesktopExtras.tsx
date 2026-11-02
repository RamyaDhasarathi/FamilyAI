// Desktop-only sections under an agent dashboard (MASTER_AGENT.md §4 agent ↔
// space mapping, §7 Phase 4; FamilyOS.mp4 2:40–2:55 / 9:30–10:40 School,
// 3:30 Money, 3:40 Investments, 3:50 Dates spotted, 5:50 Errands, 1:50 Order
// again). AgentPage renders this under its existing panel on desktop only;
// it adds sections and never restyles the panel above. Below 1024 px it
// renders nothing (its own check, besides AgentPage's).
import type { ReactNode } from 'react';
import type { AgentId } from '../../theme/tokens';
import { colors } from '../../theme/tokens';
import { agentNames } from '../../mocks/data';
import { useIsDesktopWeb } from '../../hooks/useIsDesktopWeb';
import { useNow } from '../../desk/hooks';
import { FinanceExtras } from './FinanceExtras';
import { CalendarExtras, SchoolExtras } from './SchoolCalendarExtras';
import { GroceryExtras, HouseholdExtras } from './HomeExtras';
import './spaces.css';

const BODIES: Record<AgentId, (p: { now: Date }) => ReactNode> = {
  finance: FinanceExtras,
  education: SchoolExtras,
  household: HouseholdExtras,
  grocery: GroceryExtras,
  calendar: CalendarExtras,
};

export default function AgentDesktopExtras({ agent }: { agent: AgentId }) {
  const desk = useIsDesktopWeb();
  return desk ? <Extras agent={agent} /> : null;
}

function Extras({ agent }: { agent: AgentId }) {
  const now = useNow();
  const Body = BODIES[agent];
  return (
    <section className="sp-x" aria-label={`${agentNames[agent]}: more`} style={{ ['--desk-accent' as string]: colors.agents[agent] }}>
      <Body now={now} />
    </section>
  );
}
