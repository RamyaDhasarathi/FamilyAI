// Inter type scale (AGENT.md §6.3). Each weight is its own font family; never
// combine a custom family with fontWeight (Android picks the wrong face).
import type { TextStyle } from 'react-native';
import { colors } from './tokens';

export const fonts = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
};

/** Text grows with the system font size, capped so layouts hold (§11.4). */
export const MAX_FONT_SCALE = 1.3;

const t = (s: TextStyle): TextStyle => s;

export const type = {
  greeting: t({ fontFamily: fonts.medium, fontSize: 26, letterSpacing: -0.4, color: colors.inkStrong }),
  date: t({ fontFamily: fonts.medium, fontSize: 12, color: colors.muted }),
  summary: t({ fontFamily: fonts.medium, fontSize: 12, color: colors.muted }),
  summaryStrong: t({ fontFamily: fonts.semibold, fontSize: 12, color: colors.inkStrong }),
  satLabel: t({ fontFamily: fonts.medium, fontSize: 11, color: colors.satLabel }),
  status: t({ fontFamily: fonts.semibold, fontSize: 10, letterSpacing: 1.6, color: colors.muted }),
  headline: t({ fontFamily: fonts.regular, fontSize: 19, lineHeight: 25, color: colors.ink, textAlign: 'center' }),
  agentTitle: t({ fontFamily: fonts.medium, fontSize: 30, letterSpacing: -0.4, color: colors.inkStrong }),
  sheetTitle: t({ fontFamily: fonts.medium, fontSize: 22, letterSpacing: -0.2, color: colors.inkStrong }),
  section: t({ fontFamily: fonts.semibold, fontSize: 10, letterSpacing: 1.2, color: colors.dim }),
  meta: t({ fontFamily: fonts.semibold, fontSize: 9, letterSpacing: 1.0, color: colors.muted }),
  body: t({ fontFamily: fonts.medium, fontSize: 15, lineHeight: 20, color: colors.ink }),
  bodyStrong: t({ fontFamily: fonts.semibold, fontSize: 15, lineHeight: 20, color: colors.inkStrong }),
  hero: t({ fontFamily: fonts.medium, fontSize: 40, letterSpacing: -0.8, color: colors.inkStrong }),
  heroSmall: t({ fontFamily: fonts.medium, fontSize: 30, letterSpacing: -0.6, color: colors.inkStrong }),
  small: t({ fontFamily: fonts.regular, fontSize: 13, lineHeight: 18, color: colors.muted }),
  smallStrong: t({ fontFamily: fonts.semibold, fontSize: 13, lineHeight: 18, color: colors.ink }),
  pill: t({ fontFamily: fonts.semibold, fontSize: 13, color: colors.pillPrimaryInk }),
  chip: t({ fontFamily: fonts.semibold, fontSize: 11, color: colors.ink }),
  stat: t({ fontFamily: fonts.semibold, fontSize: 18, color: colors.inkStrong }),
  statLabel: t({ fontFamily: fonts.medium, fontSize: 11, color: colors.muted }),
  menu: t({ fontFamily: fonts.medium, fontSize: 15, color: colors.ink }),
  input: t({ fontFamily: fonts.medium, fontSize: 15, color: colors.ink }),
  badge: t({ fontFamily: fonts.bold, fontSize: 10, color: '#0B0C10' }),
};
