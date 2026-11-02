// Icons for spaces and notice sources (MASTER_AGENT.md §3.1 "each space has
// its own small coloured icon", §4): the same lucide icons as the sidebar, in
// the same colours (the space record's colour = the agent token).
import {
  CalendarDays, ClipboardPaste, Globe, GraduationCap, HeartPulse, House, Images, Mail, MessageCircle, Plane, Send, ShoppingBasket, Smartphone, TrendingUp, Wallet,
  type LucideIcon,
} from 'lucide-react';
import type { NoticeSource, SpaceId } from '../../desk/types';
import { colors } from '../../theme/tokens';

export const SPACE_ICONS: Record<SpaceId, LucideIcon> = {
  education: GraduationCap, health: HeartPulse, travel: Plane, finance: Wallet, investments: TrendingUp,
  household: House, grocery: ShoppingBasket, calendar: CalendarDays, memories: Images,
};

/** Fallback colours when a space record is missing (same values as seedSpaces). */
export const SPACE_COLORS: Record<SpaceId, string> = {
  education: colors.agents.education, health: colors.health, travel: colors.agents.calendar, finance: colors.agents.finance, investments: colors.agents.finance,
  household: colors.agents.household, grocery: colors.agents.grocery, calendar: colors.agents.calendar, memories: colors.dust,
};

export const SOURCE_ICONS: Record<NoticeSource, LucideIcon> = { email: Mail, phone: Smartphone, whatsapp: MessageCircle, telegram: Send, paste: ClipboardPaste, site: Globe };
