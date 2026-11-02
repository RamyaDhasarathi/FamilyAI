// Errands, /errands (MASTER_AGENT.md §3.2 Errands 5:50–6:10, §7 Phase 5;
// FamilyOS.mp4 ≈5:45, frame f_069). One honest sentence about what an
// errand is; "Ask for one" opens Ask prefilled; one card per errand with its
// site, when, the most it may cost and a status chip (proposed / approved /
// done / cancelled), worst first — what waits for a guardian on top. Filter
// pills narrow by status. Nothing here changes anything: each card opens the
// errand, where approving or cancelling asks for a confirm.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { ChevronRight, ShoppingCart } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { agentNames } from '../../mocks/data';
import { Dot } from '../../components/Labels';
import { MiniGem } from '../../components/MiniGem';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';
import type { Errand, ErrandStatus } from '../../desk/types';
import { DeskPage, StatusChip } from '../shell/DeskPage';
import { askPath } from '../shell/routes';
import { siteOf, sortErrands, STATUS_ORDER } from './errandModel';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

const C = ADMIN_COPY.errands;

export default function ErrandsPage() {
  const errands = useDesk((s) => s.errands);
  const members = useDesk((s) => s.members);
  const f = useDeskFormat();
  const [filter, setFilter] = useState<ErrandStatus | 'all'>('all');
  const sorted = useMemo(() => sortErrands(errands), [errands]);
  const shown = filter === 'all' ? sorted : sorted.filter((e) => e.status === filter);
  const count = (s: ErrandStatus) => errands.filter((e) => e.status === s).length;
  const name = (id?: string) => memberName({ members }, id);

  const line = (e: Errand) => {
    if (e.status === 'proposed') return C.lineProposed;
    if (e.status === 'approved') return `approved by ${name(e.approvedBy)} · runs only as written down`;
    if (e.status === 'done') return `done · ${e.steps.length} ${e.steps.length === 1 ? 'step' : 'steps'}, a screenshot kept at each`;
    return e.cancelledReason ? `cancelled · ${e.cancelledReason}` : 'cancelled before it ran';
  };

  return (
    <DeskPage
      className="adm-page"
      icon={ShoppingCart}
      color={colors.agents.household}
      title="Errands"
      description={C.description}
      actions={
        <Link to={askPath(C.askPrefill)} className="pill pill--primary">
          {C.ask}
        </Link>
      }
    >
      <div className="adm-filters" role="group" aria-label="Show errands that are">
        <button type="button" className={clsx('adm-filter', filter === 'all' && 'is-on')} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
          All <span className="adm-filter__n">{errands.length}</span>
        </button>
        {STATUS_ORDER.map((s) => (
          <button key={s} type="button" className={clsx('adm-filter', filter === s && 'is-on')} aria-pressed={filter === s} onClick={() => setFilter(s)}>
            {C.status[s]} <span className="adm-filter__n">{count(s)}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="desk-empty card adm-note">
          <MiniGem size={36} still />
          <p className={T.small}>{filter === 'all' ? C.empty : `No ${C.status[filter]} errands.`}</p>
        </div>
      ) : (
        <ul className="adm-stack" aria-label="Errands">
          {shown.map((e) => (
            <li key={e.id}>
              <Link to={`/errands/${e.id}`} className="adm-linkrow card" aria-label={`${e.title}, ${e.status}. ${siteOf(e.where)}, at most ${f.money(e.atMost)}. Opens the errand`}>
                <span className="adm-row__main">
                  <span className={clsx(T.bodyStrong, 'adm-row__title')}>{f.text(e.title)}</span>
                  <span className={clsx(T.small, 'adm-row__sub')}>
                    <Dot color={colors.agents[e.agent]} size={6} /> {agentNames[e.agent]} · {siteOf(e.where)} · {f.text(e.when)} · at most {f.money(e.atMost)} · asked by {name(e.requestedBy)}
                  </span>
                  <span className={clsx(T.small, 'adm-row__sub')}>{f.text(line(e))}</span>
                </span>
                <StatusChip tone={e.status}>{C.status[e.status]}</StatusChip>
                <ChevronRight size={16} aria-hidden className="adm-chev" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </DeskPage>
  );
}
