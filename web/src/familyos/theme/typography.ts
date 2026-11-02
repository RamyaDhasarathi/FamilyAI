// Inter type roles (AGENT_WEB.md §6.3), the same roles as the mobile app's
// theme/typography.ts. Sizes, weights and tracking live in globals.css as
// rem values (mobile px = rem at 16 px); components use these class names.
export const T = {
  greeting: 't-greeting',
  date: 't-date',
  summary: 't-summary',
  summaryStrong: 't-summary-strong',
  satLabel: 't-sat-label',
  status: 't-status',
  headline: 't-headline',
  agentTitle: 't-agent-title',
  sheetTitle: 't-sheet-title',
  section: 't-section',
  meta: 't-meta',
  body: 't-body',
  bodyStrong: 't-body-strong',
  hero: 't-hero',
  heroSmall: 't-hero-small',
  small: 't-small',
  smallStrong: 't-small-strong',
  pill: 't-pill',
  chip: 't-chip',
  stat: 't-stat',
  statLabel: 't-stat-label',
  menu: 't-menu',
  input: 't-input',
  badge: 't-badge',
} as const;
