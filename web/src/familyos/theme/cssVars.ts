// Every design token as a CSS custom property on :root (AGENT_WEB.md §6.1).
// Generated from tokens.ts and stateThemes.ts so the CSS can never drift
// from the values the mobile app uses.
import { colors, radii, sizes, spacing } from './tokens';
import { SCENARIOS, scenarioThemes, type Scenario } from './stateThemes';

const kebab = (s: string) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

export function tokenVars(): Record<string, string> {
  const v: Record<string, string> = {};
  for (const [k, val] of Object.entries(colors)) {
    if (typeof val === 'string') v[`--${kebab(k)}`] = val;
  }
  for (const [k, val] of Object.entries(colors.agents)) v[`--agent-${k}`] = val;
  for (const [k, val] of Object.entries(colors.severity)) v[`--severity-${k}`] = val;
  for (const [k, val] of Object.entries(spacing)) v[`--space-${k}`] = `${val}px`;
  for (const [k, val] of Object.entries(radii)) v[`--radius-${kebab(k)}`] = `${val}px`;
  for (const [k, val] of Object.entries(sizes)) v[`--size-${kebab(k)}`] = `${val}px`;
  for (const s of SCENARIOS) {
    v[`--scenario-${s}-dot`] = scenarioThemes[s].dot;
    v[`--scenario-${s}-tint-a`] = scenarioThemes[s].sheetTint[0];
    v[`--scenario-${s}-tint-b`] = scenarioThemes[s].sheetTint[1];
  }
  return v;
}

export function applyTokenVars(root: HTMLElement = document.documentElement) {
  for (const [k, val] of Object.entries(tokenVars())) root.style.setProperty(k, val);
}

/** The current mood's colours: focus ring, panel tint and summary dot follow it (§6.2, §6.5). */
export function applyScenarioVars(s: Scenario, root: HTMLElement = document.documentElement) {
  const t = scenarioThemes[s];
  root.style.setProperty('--mood', t.dot);
  root.style.setProperty('--mood-tint-a', t.sheetTint[0]);
  root.style.setProperty('--mood-tint-b', t.sheetTint[1]);
  root.dataset.mood = s;
}
