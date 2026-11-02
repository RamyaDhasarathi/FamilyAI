// Visual check (AGENT_WEB.md §13.3): every screen at 390, 768, 1280 and 1920 px
// wide, and the 390 px shot placed beside the matching mobile reference
// (design-reference/compare/*.png: video frame | mobile app).
//
//   npm run dev            # scenario switching is dev-only, so use the dev server
//   npm run shots          # or: node scripts/shots.mjs http://localhost:5175
//
// Output: ../design-reference/compare-web/<width>/<screen>.png and
//         ../design-reference/compare-web/pairs/<screen>.png (git-ignored).
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] ?? 'http://localhost:5175';
const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'design-reference');
const out = join(root, 'compare-web');
const SIZES = [
  [390, 844, 2],
  [768, 1024, 2],
  [1280, 800, 2],
  [1920, 1080, 1],
];

const home = [{ go: '/' }, { wait: 2600 }];
const scenario = (n) => Array.from({ length: n }, () => [{ key: 'Shift+S' }, { wait: 900 }]).flat();
/** [name, mobile reference or null, steps] */
const SCREENS = [
  ['01_home_calm', '01_home_calm', [...home]],
  ['02_profile_menu', '02_profile_menu', [...home, { click: '.avatar-pill' }, { wait: 900 }]],
  ['03_today', '03_today_sheet', [...home, { click: '.home-head__summary' }, { wait: 1100 }]],
  ['04_walk_education', '04_walk_education', [...home, { click: '.sat__hit >> nth=1' }, { wait: 2400 }]],
  ['05_chat', '05_chat', [...home, { key: '/' }, { wait: 700 }, { type: ['.chat-input__field', 'What needs me today?'] }, { key: 'Enter' }, { wait: 1800 }]],
  ['06_home_urgent', '06_home_urgent', [...home, ...scenario(3), { wait: 600 }]],
  ['07_needs_you', '07_needs_you', [...home, ...scenario(3), { key: 'n' }, { wait: 1100 }]],
  ['08_home_insight', '08_home_insight', [...home, ...scenario(1), { wait: 600 }]],
  ['09_dashboard', '09_dashboard', [...home, { key: 'd' }, { wait: 1400 }]],
  ['10_finance', '10_finance', [{ go: '/agent/finance' }, { wait: 2400 }]],
  ['11_finance_expanded', '11_finance_expanded', [{ go: '/agent/finance' }, { wait: 2000 }, { click: '.timeline-item__head >> nth=0' }, { wait: 900 }]],
  ['12_calendar', '12_calendar', [{ go: '/agent/calendar' }, { wait: 2400 }]],
  ['13_grocery', '13_grocery', [{ go: '/agent/grocery' }, { wait: 2400 }]],
  ['14_family_hub', null, [{ go: '/family' }, { wait: 2400 }]],
  ['15_member_profile', null, [{ go: '/family/m_ethan' }, { wait: 2200 }]],
  ['16_member_wizard', null, [{ go: '/family/m_sarah/details/banking' }, { wait: 2000 }]],
  ['17_settings', null, [{ go: '/settings' }, { wait: 1200 }]],
  ['18_login', null, [{ go: '/login' }, { wait: 1400 }]],
  ['19_loading', null, [{ go: '/loading' }, { wait: 1400 }]],
];

const browser = await chromium.launch({ args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] });
for (const [w, h, dpr] of SIZES) {
  mkdirSync(join(out, String(w)), { recursive: true });
  for (const [name, , steps] of SCREENS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
    await ctx.addInitScript(() => sessionStorage.setItem('familyos.session', '1'));
    const page = await ctx.newPage();
    for (const s of steps) {
      if (s.go) await page.goto(base + s.go, { waitUntil: 'load' });
      if (s.wait) await page.waitForTimeout(s.wait);
      if (s.click) await page.click(s.click);
      if (s.key) await page.keyboard.press(s.key);
      if (s.type) await page.fill(s.type[0], s.type[1]);
    }
    await page.screenshot({ path: join(out, String(w), `${name}.png`) });
    await ctx.close();
  }
  console.log(`captured ${SCREENS.length} screens at ${w} px`);
}

// Pairs: mobile reference (video | app) beside the web shot at 390 px.
mkdirSync(join(out, 'pairs'), { recursive: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const data = (p) => `data:image/png;base64,${readFileSync(p).toString('base64')}`;
for (const [name, ref] of SCREENS) {
  const refPath = ref ? join(root, 'compare', `${ref}.png`) : null;
  const web = join(out, '390', `${name}.png`);
  await page.setContent(`<html><body style="margin:0;background:#16171b;font:600 18px system-ui;color:#ddd;display:flex;gap:24px;padding:20px;align-items:flex-start">
    ${refPath && existsSync(refPath) ? `<figure style="margin:0"><figcaption>Mobile reference (video | app)</figcaption><img src="${data(refPath)}" style="height:900px"></figure>` : ''}
    <figure style="margin:0"><figcaption>Web · 390 px</figcaption><img src="${data(web)}" style="height:900px;border-radius:24px"></figure></body></html>`);
  await page.waitForTimeout(100);
  await page.screenshot({ path: join(out, 'pairs', `${name}.png`), fullPage: true });
}
await browser.close();
console.log(`pairs written to ${join(out, 'pairs')}`);
