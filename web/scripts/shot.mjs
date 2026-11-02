// Ad-hoc screenshot: node scripts/shot.mjs <url> <out.png> [width] [height] [browser] [waitMs] [dpr]
// Used while building to compare a screen with the mobile reference.
import { chromium, firefox, webkit } from '@playwright/test';

const [url, out, w = '390', h = '844', which = 'chromium', wait = '2500', dpr = '2'] = process.argv.slice(2);
const engines = { chromium, firefox, webkit };
const browser = await engines[which].launch({ args: which === 'chromium' ? ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] : [] });
const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +dpr });
const logs = [];
page.on('console', (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
await page.goto(url, { waitUntil: 'load' });
await page.waitForTimeout(+wait);
await page.screenshot({ path: out });
await browser.close();
if (logs.length) console.log(logs.join('\n'));
