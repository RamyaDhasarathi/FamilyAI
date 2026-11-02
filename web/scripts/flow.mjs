// Scripted flow screenshots: node scripts/flow.mjs <base> <outDir> <w> <h> <browser> '<json steps>'
// Steps: {go:"/path"} {wait:ms} {click:"selector"} {key:"T"} {shot:"name"} {eval:"js"} {wheel:dy} {drag:[x0,y0,x1,y1]}
// {shotEl:["selector","name"]} {hold:["selector", ms]} {type:["selector","text"]} {scenario:"urgent"}. Prints console errors.
import { chromium, firefox, webkit } from '@playwright/test';

const [base, out, w = '390', h = '844', which = 'chromium', json = '[]', dpr = '2'] = process.argv.slice(2);
const steps = JSON.parse(json);
const engines = { chromium, firefox, webkit };
const browser = await engines[which].launch({ args: which === 'chromium' ? ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] : [] });
const ctx = await browser.newContext({ viewport: { width: +w, height: +h }, deviceScaleFactor: +dpr, hasTouch: false });
await ctx.addInitScript(() => {
  try {
    window.sessionStorage.setItem('familyos.session', '1');
  } catch {
    /* ignore */
  }
});
const page = await ctx.newPage();
const errors = [];
page.on('console', (m) => {
  if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text().slice(0, 300)}`);
});
page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
for (const s of steps) {
  if (s.go) await page.goto(base + s.go, { waitUntil: 'load' });
  if (s.wait) await page.waitForTimeout(s.wait);
  if (s.click) await page.click(s.click);
  if (s.key) await page.keyboard.press(s.key);
  if (s.eval) await page.evaluate(s.eval);
  if (s.wheel) {
    await page.mouse.move(+w / 2, +h / 2);
    await page.mouse.wheel(0, s.wheel);
  }
  if (s.drag) {
    const [x0, y0, x1, y1] = s.drag;
    await page.mouse.move(x0, y0);
    await page.mouse.down();
    for (let i = 1; i <= 12; i++) await page.mouse.move(x0 + ((x1 - x0) * i) / 12, y0 + ((y1 - y0) * i) / 12);
    await page.mouse.up();
  }
  if (s.hold) {
    const box = await page.locator(s.hold[0]).first().boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.waitForTimeout(s.hold[1]);
    await page.mouse.up();
  }
  if (s.type) await page.fill(s.type[0], s.type[1]);
  if (s.shot) await page.screenshot({ path: `${out}/${s.shot}.png` });
  if (s.shotEl) await page.locator(s.shotEl[0]).first().screenshot({ path: `${out}/${s.shotEl[1]}.png` });
}
await browser.close();
if (errors.length) console.log(errors.join('\n'));
