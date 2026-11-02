// Hero card of an agent's Deep Layer page (AGENT_WEB.md §8.7): Finance and
// Grocery show a sparkline, Calendar week bars, Education progress bars,
// Household a task ring. A faint glow in the agent colour from the top right.
import type { AgentHero as Hero } from '../services/interfaces';
import { ProgressBars, Sparkline, TaskRing, WeekBars } from '../graphics/Charts';
import { withAlpha } from '../theme/tokens';
import { T } from '../theme/typography';

export function AgentHero({ hero, color }: { hero: Hero; color: string }) {
  return (
    <section className="agent-hero" aria-label={`${hero.label}: ${hero.value}`} style={{ backgroundImage: `linear-gradient(225deg, ${withAlpha(color, 0.2)}, ${withAlpha(color, 0)} 55%)` }}>
      <div className="agent-hero__row">
        <div className="agent-hero__text">
          <p className={T.small} style={{ fontSize: '0.75rem' }}>
            {hero.label}
          </p>
          <p className={`${T.hero} agent-hero__value`}>{hero.value}</p>
          <p className={T.smallStrong} style={{ color, fontSize: '0.78rem' }}>
            {hero.kind === 'sparkline' ? hero.delta : hero.note}
          </p>
        </div>
        {hero.kind === 'ring' ? <TaskRing pct={hero.pct} color={color} /> : null}
      </div>
      {hero.kind === 'sparkline' ? (
        <div className="agent-hero__chart">
          <Sparkline series={hero.series} color={color} />
        </div>
      ) : null}
      {hero.kind === 'bars' ? (
        <div className="agent-hero__chart">
          <WeekBars bars={hero.bars} todayIndex={hero.todayIndex} color={color} />
        </div>
      ) : null}
      {hero.kind === 'progress' ? (
        <div className="agent-hero__chart">
          <ProgressBars
            items={hero.items}
            color={color}
            renderLabel={(name, pct) => (
              <div className="progress-label">
                <span className={T.small} style={{ color: 'var(--ink)', fontSize: '0.78rem' }}>
                  {name}
                </span>
                <span className={T.small} style={{ fontSize: '0.78rem' }}>
                  {Math.round(pct * 100)}%
                </span>
              </div>
            )}
          />
        </div>
      ) : null}
    </section>
  );
}
