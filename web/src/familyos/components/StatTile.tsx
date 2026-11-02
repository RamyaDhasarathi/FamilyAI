// Stat tile: 2 px top border in the agent colour fading out to the sides,
// label, and a number that counts up on mount (AGENT_WEB.md §6.4, §7.6).
import type { StatTile as Stat } from '../services/interfaces';
import { useCountUp } from '../graphics/Charts';
import { withAlpha } from '../theme/tokens';
import { T } from '../theme/typography';

function formatStat(s: Stat, v: number) {
  if (s.text) return s.text;
  const n = s.decimals ? v.toFixed(s.decimals) : Math.round(v).toLocaleString('en-US');
  return `${s.prefix ?? ''}${n}${s.suffix ?? ''}`;
}

export function StatTile({ stat, color }: { stat: Stat; color: string }) {
  const v = useCountUp(stat.value);
  return (
    <div className="stat-tile">
      <span className="stat-tile__top" style={{ background: `linear-gradient(90deg, ${withAlpha(color, 0)}, ${color}, ${withAlpha(color, 0)})` }} aria-hidden />
      <p className={T.statLabel}>{stat.label}</p>
      <p className={`${T.stat} stat-tile__value`} aria-hidden>
        {formatStat(stat, v)}
      </p>
      <span className="sr-only">{formatStat(stat, stat.value)}</span>
    </div>
  );
}
