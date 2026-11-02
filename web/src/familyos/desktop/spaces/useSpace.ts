// Memoised hooks over the space model (spaceModel.ts) for the Phase 4 pages
// and dashboard extras (MASTER_AGENT.md §7 Phase 4). Each hook selects the
// raw store slices it needs and derives in useMemo, so views follow the one
// desk store without copying it.
import { useMemo } from 'react';
import { useDesk } from '../../desk/store';
import type { SpaceId } from '../../desk/types';
import { decideList, missedCount, spaceCounts, spaceTimeline, whatArrived, type Scope } from './spaceModel';

export function useTimeline(scope: Scope, now: Date, from = -7, to = 60) {
  const proposals = useDesk((s) => s.proposals);
  const agenda = useDesk((s) => s.agenda);
  const todos = useDesk((s) => s.todos);
  const conflicts = useDesk((s) => s.conflicts);
  const members = useDesk((s) => s.members);
  const tz = useDesk((s) => s.settings.timezone);
  return useMemo(() => spaceTimeline({ proposals, agenda, todos, conflicts, members }, scope, now, tz, { from, to }), [proposals, agenda, todos, conflicts, members, scope, now, tz, from, to]);
}

export function useArrived(scope: Scope) {
  const notices = useDesk((s) => s.notices);
  const proposals = useDesk((s) => s.proposals);
  return useMemo(() => whatArrived({ notices, proposals }, scope), [notices, proposals, scope]);
}

export function useSpaceCounts(space: SpaceId) {
  const notices = useDesk((s) => s.notices);
  const proposals = useDesk((s) => s.proposals);
  const agenda = useDesk((s) => s.agenda);
  const todos = useDesk((s) => s.todos);
  return useMemo(() => spaceCounts({ notices, proposals, agenda, todos }, space), [notices, proposals, agenda, todos, space]);
}

/** Undecided proposals to decide here, and how many dated ones went by undecided. */
export function useDecide(now: Date, opts: { scope?: Scope; datedOnly?: boolean }) {
  const proposals = useDesk((s) => s.proposals);
  const tz = useDesk((s) => s.settings.timezone);
  const { scope = 'all', datedOnly = false } = opts;
  return useMemo(
    () => ({ items: decideList({ proposals }, { scope, datedOnly }, now, tz), missed: missedCount({ proposals }, now, tz, scope) }),
    [proposals, scope, datedOnly, now, tz]
  );
}

/** The space's display record (name, colour, route) from the store. */
export function useSpaceMeta(space: SpaceId) {
  return useDesk((s) => s.spaces.find((x) => x.id === space));
}
