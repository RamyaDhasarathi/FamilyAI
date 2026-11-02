// Today — the written summary (AGENT_WEB.md §8.2, video 0:18 and 3:45):
// commute card, weather and first-event tiles, then today's items. Rows
// stagger in (40 ms apart, fade + 12 px rise); a row opens its agent.
import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import type { AgentId } from '../../theme/tokens';
import { colors } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { T } from '../../theme/typography';
import { agentNames, copy } from '../../mocks/data';
import { useFamilyOS } from '../../store/useFamilyOS';
import { GlowOrb } from '../../graphics/GlowDot';
import { SectionLabel } from '../../components/Labels';
import { Pressable } from '../../components/Pressable';
import { Sheet } from '../../components/Sheet';
import { formatLongDate } from '../homeText';

function Tile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="today-tile card">
      <p className={T.meta}>{label}</p>
      <p className={clsx(T.heroSmall, 'today-tile__value')}>{value}</p>
      <p className={clsx(T.small, 'today-tile__detail')}>{detail}</p>
    </div>
  );
}

export function TodayPanel({ open, onClose, onOpenAgent }: { open: boolean; onClose: () => void; onOpenAgent: (a: AgentId) => void }) {
  const today = useFamilyOS((s) => s.today);
  const header = (
    <div className="sheet-title-row">
      <h2 id="today-title" className={T.sheetTitle}>
        {copy.todayTitle}
      </h2>
      <p className={T.date}>{formatLongDate(new Date())}</p>
    </div>
  );
  return (
    <Sheet open={open} onClose={onClose} labelledBy="today-title" header={header} tint>
      {today ? (
        <div className="today-body">
          {today.commute ? (
            <>
              <SectionLabel>{today.commute.section}</SectionLabel>
              <div className="today-commute card">
                <p className={T.meta}>{today.commute.label}</p>
                <p className={clsx(T.heroSmall, 'today-commute__title')}>{today.commute.title}</p>
                <p className={T.small}>{today.commute.detail}</p>
                <span className="chip chip--small today-commute__alt">{today.commute.alt}</span>
              </div>
            </>
          ) : null}
          <div className="today-tiles">
            <Tile {...today.weather} />
            <Tile {...today.firstEvent} />
          </div>
          <SectionLabel className="today-section">{copy.todaySection}</SectionLabel>
          <ul className="today-list">
            {today.items.map((it, i) => (
              <motion.li
                key={it.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.12 + (i * durations.stagger) / 1000, duration: 0.32 }}
              >
                <Pressable
                  className="today-row card hoverable"
                  onClick={() => onOpenAgent(it.agent)}
                  pressScale={0.98}
                  aria-label={`${agentNames[it.agent]}: ${it.text}. Opens ${agentNames[it.agent]}`}
                >
                  <GlowOrb color={colors.agents[it.agent]} size={30} />
                  <span className="today-row__text">
                    <span className={T.meta}>{agentNames[it.agent].toUpperCase()}</span>
                    <span className={T.body}>{it.text}</span>
                  </span>
                  <ChevronRight size={16} color={colors.muted} aria-hidden />
                </Pressable>
              </motion.li>
            ))}
          </ul>
        </div>
      ) : null}
    </Sheet>
  );
}
