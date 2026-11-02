// Placeholder body for pages a later phase fills in (MASTER_AGENT.md §7
// Phases 3–5). The route, sidebar entry and page frame are real; only the
// content is pending.
import type { ReactNode } from 'react';
import { MiniGem } from '../../components/MiniGem';
import { deskCopy } from '../copy';
import { DeskCard } from './DeskPage';

export function StubBody({ what, children }: { what: string; children?: ReactNode }) {
  return (
    <DeskCard className="desk-stub">
      <div className="desk-empty">
        <MiniGem size={44} still />
        <p className="t-small">{deskCopy.stub(what)}</p>
      </div>
      {children}
    </DeskCard>
  );
}
