// Which needs-you items are open in each demo scenario (AGENT.md §6.2, §10),
// and how the Home mood is derived from whatever is still open.
import type { NeedsItem } from '../services/interfaces';
import type { Scenario } from '../theme/stateThemes';
import { needsItems } from './data';

const ids = (...xs: string[]) => xs;

/** calm: none · insight: 1 insight · heads-up: 4 heads-ups + 3 insights · urgent: all 13. */
export const scenarioItems: Record<Scenario, string[]> = {
  calm: [],
  insight: ids('n11'),
  headsup: ids('n4', 'n5', 'n6', 'n7', 'n10', 'n11', 'n12'),
  urgent: needsItems.map((n) => n.id),
};

const rank = { urgent: 0, headsup: 1, insight: 2 } as const;

/** Most severe first, then the list's own order. */
export function sortNeeds(items: NeedsItem[]): NeedsItem[] {
  const order = new Map(needsItems.map((n, i) => [n.id, i]));
  return [...items].sort((a, b) => rank[a.severity] - rank[b.severity] || order.get(a.id)! - order.get(b.id)!);
}

/** The Home mood follows the most severe open item. */
export function moodOf(items: NeedsItem[]): Scenario {
  if (items.some((n) => n.severity === 'urgent')) return 'urgent';
  if (items.some((n) => n.severity === 'headsup')) return 'headsup';
  if (items.length > 0) return 'insight';
  return 'calm';
}

/** Item shown as the Home headline: most severe, then lowest priority number. */
export function headlineItem(items: NeedsItem[]): NeedsItem | undefined {
  return [...items].sort((a, b) => rank[a.severity] - rank[b.severity] || a.priority - b.priority)[0];
}

/** "3 urgent" in urgent mood, otherwise "7 need you" / "1 needs you". */
export function summaryCount(items: NeedsItem[]): { n: number; word: string } {
  const mood = moodOf(items);
  if (mood === 'urgent') return { n: items.filter((i) => i.severity === 'urgent').length, word: 'urgent' };
  return { n: items.length, word: items.length === 1 ? 'needs you' : 'need you' };
}
