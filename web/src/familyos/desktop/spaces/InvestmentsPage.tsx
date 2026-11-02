// Investments, /agents/finance/investments — the Investments tab of Finance
// (MASTER_AGENT.md §4, §7 Phase 4; FamilyOS.mp4 3:40). Money ↔ Investments
// tabs; the brokerage's statements and notices in order (newest first,
// grouped by month), each linking to its notice. Rail: the last 90 days as
// the statements report them, What arrived, What this is. Read-only: FamilyOS
// never trades, moves money or signs in.
import { useMemo } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { BadgeDollarSign, FileText, Info, Repeat, TrendingUp, type LucideIcon } from 'lucide-react';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import type { Statement } from '../../desk/types';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { Explainer, MoneyTabs, Section, WhatArrived } from './SpaceParts';
import { investActivity, statementsByMonth } from './listModels';
import { useArrived } from './useSpace';
import { SPACE_COLORS } from './spaceIcons';
import { extrasCopy, spaceCopy } from './copy';

const I = extrasCopy.invest;
const KIND_ICON: Record<Statement['kind'], LucideIcon> = { statement: FileText, trade: Repeat, dividend: BadgeDollarSign, notice: Info };

export default function InvestmentsPage() {
  const now = useNow();
  const f = useDeskFormat(now);
  const statements = useDesk((s) => s.statements);
  const tz = useDesk((s) => s.settings.timezone);
  const color = useDesk((s) => s.spaces.find((x) => x.id === 'investments')?.color) ?? SPACE_COLORS.investments;
  const groups = useMemo(() => statementsByMonth(statements), [statements]);
  const activity = useMemo(() => investActivity(statements, now, tz), [statements, now, tz]);
  const arrived = useArrived('investments');
  return (
    <DeskPage
      className="sp-page"
      icon={TrendingUp}
      color={color}
      back="/agents/finance"
      title={I.title}
      description={I.description}
      rail={
        <>
          <DeskCard title={I.activity} className="sp-activity">
            <dl className="sp-kv">
              <div>
                <dt className={T.small}>{I.bought}</dt>
                <dd className={T.smallStrong}>{f.money(activity.bought)}</dd>
              </div>
              <div>
                <dt className={T.small}>{I.dividends}</dt>
                <dd className={T.smallStrong}>{f.money(activity.dividends)}</dd>
              </div>
              <div>
                <dt className={T.small}>{I.statements}</dt>
                <dd className={T.smallStrong}>{activity.statements}</dd>
              </div>
            </dl>
          </DeskCard>
          <Section title={spaceCopy.arrived}>
            <WhatArrived items={arrived} now={now} empty={spaceCopy.arrivedEmpty(I.title)} compact max={5} />
          </Section>
          <Explainer title={extrasCopy.what}>
            <p className={T.small}>{I.whatText}</p>
          </Explainer>
        </>
      }
    >
      <MoneyTabs current="investments" />
      <Section title={I.list} sub={statements.length ? I.listSub(statements.length) : undefined}>
        {groups.length ? (
          groups.map((g) => (
            <div key={g.key} className="sp-month">
              <p className={clsx(T.section, 'sp-group-label')}>{g.label}</p>
              <ul className="sp-statements">
                {g.items.map((s) => {
                  const Icon = KIND_ICON[s.kind];
                  return (
                    <li key={s.id}>
                      <Link to={`/inbox/${s.noticeId}`} className="sp-row-link sp-statement">
                        <span className={clsx(T.small, 'sp-statement__date')}>{fmtShortDay(s.date)}</span>
                        <span className="sp-icon" style={{ color }} aria-hidden>
                          <Icon size={14} strokeWidth={1.9} />
                        </span>
                        <span className="sp-statement__text">
                          <span className={clsx(T.small, 'sp-statement__meta')}>
                            <span>{s.institution}</span>
                            <StatusChip tone="neutral">{I.kind[s.kind]}</StatusChip>
                          </span>
                          <span className={T.smallStrong}>{f.text(s.title)}</span>
                          <span className={T.small}>{f.text(s.summary)}</span>
                        </span>
                        <span className={clsx(T.smallStrong, 'sp-statement__amt')}>{s.amount !== undefined ? f.money(s.amount) : ''}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        ) : (
          <p className={clsx(T.small, 'desk-empty')}>{I.empty}</p>
        )}
      </Section>
    </DeskPage>
  );
}
