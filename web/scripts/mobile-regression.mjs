// Mobile-width regression snapshots (MASTER_AGENT.md §11 "Mobile regression").
// Deterministic: reduced motion (the stage is still), a frozen clock and fresh
// storage, so two runs of unchanged code give identical pixels.
//
//   node scripts/mobile-regression.mjs capture <dir> [baseUrl]
//   node scripts/mobile-regression.mjs compare <beforeDir> <afterDir>
import { chromium } from '@playwright/test';
import { mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const [mode, a, b = 'http://localhost:5175'] = process.argv.slice(2);
const SIZES = [
  [390, 844],
  [412, 915],
  [768, 1024],
];
const home = [{ go: '/' }, { wait: 2200 }];
const SCREENS = [
  ['home', [...home]],
  ['stone_tap', [...home, { click: '.sat__hit >> nth=3' }, { wait: 1600 }]],
  ['stone_hold', [...home, { hold: ['.sat__hit >> nth=0', 700] }, { wait: 1800 }]],
  ['agents_sheet', [...home, { key: 'd' }, { wait: 1400 }]],
  ['today_sheet', [...home, { click: '.home-head__summary' }, { wait: 1200 }]],
  ['ask_panel', [...home, { click: '.home__ask .ask-bar__input' }, { wait: 1200 }]],
  ['avatar_menu', [...home, { click: '.avatar-pill' }, { wait: 1000 }]],
  ['finance', [{ go: '/agent/finance' }, { wait: 2000 }]],
  ['household', [{ go: '/agent/household' }, { wait: 2000 }]],
  ['grocery', [{ go: '/agent/grocery' }, { wait: 2000 }]],
  ['education', [{ go: '/agent/education' }, { wait: 2000 }]],
  ['calendar', [{ go: '/agent/calendar' }, { wait: 2000 }]],
  ['family', [{ go: '/family' }, { wait: 2200 }]],
  ['profile', [{ go: '/family/m_ethan' }, { wait: 2000 }]],
  ['wizard', [{ go: '/family/m_sarah/details/basic' }, { wait: 1800 }]],
  ['settings', [{ go: '/settings' }, { wait: 1000 }]],
  ['login', [{ go: '/login' }, { wait: 1200 }]],
  ['splash', [{ go: '/loading' }, { wait: 1200 }]],
];

if (mode === 'capture') {
  const browser = await chromium.launch({ args: ['--use-angle=metal'] });
  for (const [w, h] of SIZES) {
    mkdirSync(join(a, `${w}`), { recursive: true });
    for (const [name, steps] of SCREENS) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
      await ctx.addInitScript(() => sessionStorage.setItem('familyos.session', '1'));
      const page = await ctx.newPage();
      await page.clock.install({ time: new Date('2026-10-28T14:40:00') });
      for (const s of steps) {
        if (s.go) await page.goto(b + s.go, { waitUntil: 'load' });
        if (s.wait) await page.clock.runFor(s.wait).then(() => page.waitForTimeout(250));
        if (s.click) await page.click(s.click);
        if (s.key) await page.keyboard.press(s.key);
        if (s.hold) {
          const box = await page.locator(s.hold[0]).first().boundingBox();
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.down();
          await page.clock.runFor(s.hold[1]);
          await page.mouse.up();
        }
      }
      // Let every entrance animation finish on the frozen clock before the shot.
      await page.clock.runFor(4000);
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(a, `${w}`, `${name}.png`), animations: 'disabled', caret: 'hide' });
      await ctx.close();
    }
    console.log(`captured ${SCREENS.length} screens at ${w}×${h}`);
  }
  await browser.close();
} else if (mode === 'compare') {
  let same = 0;
  const diffs = [];
  for (const [w] of SIZES) {
    for (const f of readdirSync(join(a, `${w}`))) {
      const x = readFileSync(join(a, `${w}`, f));
      let y;
      try {
        y = readFileSync(join(b, `${w}`, f));
      } catch {
        diffs.push(`${w}/${f} (missing)`);
        continue;
      }
      if (Buffer.compare(x, y) === 0) same++;
      else diffs.push(`${w}/${f}`);
    }
  }
  console.log(`identical: ${same}; different: ${diffs.length}${diffs.length ? `\n  ${diffs.join('\n  ')}` : ''}`);
  process.exitCode = diffs.length ? 1 : 0;
} else {
  console.log('usage: capture <dir> [baseUrl] | compare <before> <after>');
}
