// Sidebar items (MASTER_AGENT.md §3.1, FamilyOS.mp4 0:25): five groups,
// space icons in our agent colours (§4), a feature flag per item so an item
// whose page is not built yet can be hidden rather than shown as a dead link.
// Every page now exists (at least as a stub), so every flag is on.
import {
  CalendarDays, DatabaseZap, Download, KeyRound, GraduationCap, HeartPulse, History, House, Hourglass, Images, Inbox, Plane, ScrollText, Search, Settings, ShieldAlert,
  ShoppingBasket, ShoppingCart, Sparkles, Sun, TrendingUp, Users, Wallet, type LucideIcon,
} from 'lucide-react';
import { colors } from '../../theme/tokens';
import { deskCopy } from '../copy';

export type NavId = keyof typeof deskCopy.nav;

export interface NavItem {
  id: NavId;
  label: string;
  icon: LucideIcon;
  /** Route; absent for actions (Search opens the ⌘K palette). */
  to?: string;
  /** Space colour for the icon (§4); plain items use the text colour. */
  color?: string;
  /** Extra path prefixes that make this item active. */
  also?: string[];
  /** Keyboard hint shown on the right. */
  kbd?: string;
  /** false: reachable from ⌘K only, not listed in the sidebar. */
  sidebar?: false;
}

/** Feature flags: set one to false to hide an unfinished page from the sidebar and ⌘K. */
export const DESK_FLAGS: Record<NavId, boolean> = {
  today: true, family: true, memories: true,
  school: true, health: true, travel: true, money: true, investments: true, home: true, groceries: true, calendar: true,
  inbox: true, waiting: true, ask: true, errands: true,
  quarantine: true, revisions: true, collect: true, sources: true, services: true, audit: true,
  search: true, settings: true,
};

const N = deskCopy.nav;
const A = colors.agents;

export const NAV_GROUPS: NavItem[][] = [
  [
    { id: 'today', label: N.today, icon: Sun, to: '/today' },
    { id: 'family', label: N.family, icon: Users, to: '/family' },
    { id: 'memories', label: N.memories, icon: Images, to: '/memories', color: colors.dust },
  ],
  [
    { id: 'school', label: N.school, icon: GraduationCap, to: '/agents/education', color: A.education, also: ['/agent/education'] },
    { id: 'health', label: N.health, icon: HeartPulse, to: '/health', color: colors.health },
    { id: 'travel', label: N.travel, icon: Plane, to: '/travel', color: A.calendar, also: ['/plans/'] },
    { id: 'money', label: N.money, icon: Wallet, to: '/agents/finance', color: A.finance, also: ['/agent/finance'] },
    { id: 'investments', label: N.investments, icon: TrendingUp, to: '/agents/finance/investments', color: A.finance },
    // Our other three agents (§4: their colour on every sidebar icon), after the reference's five spaces.
    { id: 'home', label: N.home, icon: House, to: '/agents/household', color: A.household, also: ['/agent/household'] },
    { id: 'groceries', label: N.groceries, icon: ShoppingBasket, to: '/agents/grocery', color: A.grocery, also: ['/agent/grocery'] },
    { id: 'calendar', label: N.calendar, icon: CalendarDays, to: '/agents/calendar', color: A.calendar, also: ['/agent/calendar'] },
  ],
  [
    { id: 'inbox', label: N.inbox, icon: Inbox, to: '/inbox' },
    { id: 'waiting', label: N.waiting, icon: Hourglass, to: '/waiting' },
    { id: 'ask', label: N.ask, icon: Sparkles, to: '/ask', sidebar: false },
    { id: 'errands', label: N.errands, icon: ShoppingCart, to: '/errands' },
  ],
  [
    { id: 'quarantine', label: N.quarantine, icon: ShieldAlert, to: '/quarantine' },
    { id: 'revisions', label: N.revisions, icon: History, to: '/revisions' },
    { id: 'collect', label: N.collect, icon: Download, to: '/collect' },
    // Our collecting layer (famos-notes/COLLECTION_PLAN.md): what FamilyOS reads, with permission.
    { id: 'sources', label: N.sources, icon: DatabaseZap, to: '/sources' },
    { id: 'services', label: N.services, icon: KeyRound, to: '/services' },
    { id: 'audit', label: N.audit, icon: ScrollText, to: '/audit' },
  ],
  [
    { id: 'search', label: N.search, icon: Search, kbd: '⌘K' },
    { id: 'settings', label: N.settings, icon: Settings, to: '/settings/household', also: ['/settings'] },
  ],
];

export const navItems = (): NavItem[] => NAV_GROUPS.flat().filter((i) => DESK_FLAGS[i.id]);

/** Is this item the current page? Exact for '/agents/finance' (Investments is its own item). */
export function isActive(item: NavItem, path: string): boolean {
  if (!item.to) return false;
  const hit = (p: string) => path === p || (p !== '/agents/finance' && path.startsWith(p.endsWith('/') ? p : `${p}/`));
  if (item.id === 'money') return path === '/agents/finance' || path === '/agent/finance';
  return hit(item.to) || (item.also ?? []).some((p) => (p.endsWith('/') ? path.startsWith(p) : hit(p)));
}

export { askPath, isChromeless, pageHasOwnAsk } from './routes';
