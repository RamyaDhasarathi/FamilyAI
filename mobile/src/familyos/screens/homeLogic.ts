// Pure helpers for the Home screen.
import type { NeedsItem } from '../services/interfaces';
import type { AgentId } from '../theme/tokens';
import { colors } from '../theme/tokens';

const rank = { urgent: 0, headsup: 1, insight: 2 } as const;

/** Per-agent badge: open count, coloured by that agent's most severe item. */
export function agentBadges(needs: NeedsItem[]): Partial<Record<AgentId, { n: number; color: string }>> {
  const out: Partial<Record<AgentId, { n: number; color: string; r: number }>> = {};
  for (const it of needs) {
    const cur = out[it.agent];
    const r = rank[it.severity];
    if (!cur) out[it.agent] = { n: 1, color: colors.severity[it.severity], r };
    else {
      cur.n += 1;
      if (r < cur.r) {
        cur.r = r;
        cur.color = colors.severity[it.severity];
      }
    }
  }
  return out;
}
