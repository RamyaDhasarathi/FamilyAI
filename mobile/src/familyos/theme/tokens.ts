// Design tokens (AGENT.md §6.1, §6.4). The app is dark-only on OLED black.

export type AgentId = 'finance' | 'education' | 'household' | 'grocery' | 'calendar';
export type Severity = 'urgent' | 'headsup' | 'insight' | 'positive';

export const AGENT_IDS: AgentId[] = ['finance', 'education', 'household', 'grocery', 'calendar'];

export const colors = {
  bg: '#000000',
  ink: '#E8EAF0',
  inkStrong: '#FFFFFF',
  muted: '#8E93A3',
  dim: '#5D6272',
  satLabel: '#C8CDD7',
  glassFill: 'rgba(255,255,255,0.06)',
  glassFillStrong: 'rgba(255,255,255,0.10)',
  glassBorder: 'rgba(255,255,255,0.12)',
  glassHighlight: 'rgba(255,255,255,0.08)',
  glassFallback: 'rgba(20,22,28,0.82)',
  sheetFill: 'rgba(26,29,38,0.9)',
  cardFill: 'rgba(255,255,255,0.055)',
  divider: 'rgba(255,255,255,0.07)',
  scrim: 'rgba(0,0,0,0.55)',
  pillPrimaryBg: '#FFFFFF',
  pillPrimaryInk: '#0B0C10',
  pillSecondaryBg: 'rgba(255,255,255,0.08)',
  danger: '#FF5A5F',
  done: '#3FCB7E',
  later: '#E9A23B',
  violet: '#8073FF',
  agents: {
    finance: '#1FC7B8',
    education: '#BD9EFF',
    household: '#FF9E33',
    grocery: '#6BF294',
    calendar: '#61B8FF',
  } as Record<AgentId, string>,
  health: '#FF6B9A',
  dust: '#BFD1FF',
  severity: {
    urgent: '#FF4D5E',
    headsup: '#FFB23F',
    insight: '#A98BFF',
    positive: '#4DFF8C',
  } as Record<Severity, string>,
};

export const spacing = { xs: 4, s: 8, m: 12, l: 16, xl: 20, xxl: 24, xxxl: 32 };

export const radii = { card: 20, sheet: 28, tile: 16, bubble: 16, pill: 999 };

export const sizes = {
  screenPad: 20,
  sheetMargin: 16,
  pillSmall: 32,
  askBar: 52,
  micButton: 40,
  avatarPill: 28,
  badge: 16,
  orb: 28,
  minTouch: 44,
};

/** '#RRGGBB' → [r, g, b] in 0..1 (worklet-safe). */
export function hexToRgb(hex: string): [number, number, number] {
  'worklet';
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255, parseInt(h.slice(4, 6), 16) / 255];
}

/** '#RRGGBB' + alpha → 'rgba(...)'. */
export function withAlpha(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)},${alpha})`;
}
