/* Development-only browser comparison; Playwright is never a production dependency.
 * node browser_compare.js CASES_JSON CDU_SOURCE OUTPUT_DIR
 * Set XHIBIT_PLAYWRIGHT_MODULE to an existing playwright-core installation.
 * CASES_JSON comes from test_php_reference.py with synthetic, actual PHP/Python outputs.
 */
'use strict';
const assert = require('assert');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require(process.env.XHIBIT_PLAYWRIGHT_MODULE || 'playwright-core');

async function main() {
  const [casesFile, root, output] = process.argv.slice(2);
  if (!casesFile || !root || !output) throw new Error('Expected CASES_JSON CDU_SOURCE OUTPUT_DIR');
  const cases = JSON.parse(fs.readFileSync(casesFile, 'utf8'));
  fs.mkdirSync(output, { mode: 0o700 }); // never overwrite previous evidence
  const publicFiles = new Set(['display_documentNEW.js', 'onscreen-clock.js', 'jquery-3.1.1.min.js',
    'css/new/general.css', 'css/new/notifications.css', 'css/new/table.css',
    'images/MoJLogo.png', 'images/MoJLogoWelsh.png']);
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, 'http://localhost').pathname.slice(1);
    const file = name === 'index.php' ? path.join(root, 'python/templates/index.html') :
      publicFiles.has(name) ? path.join(root, name) : null;
    if (!file) { res.writeHead(404); res.end(); return; }
    const type = name.endsWith('.js') ? 'application/javascript' : name.endsWith('.css') ? 'text/css' :
      name.endsWith('.png') ? 'image/png' : 'text/html; charset=UTF-8';
    res.writeHead(200, { 'Content-Type': type });
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const sample of cases) {
      const states = [], images = [];
      for (const implementation of ['legacy', 'python']) {
        const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, timezoneId: 'UTC' });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.clock.install({ time: new Date('2026-10-23T09:05:00Z') });
        await page.addInitScript(() => {
          window.__timers = [];
          for (const kind of ['setTimeout', 'setInterval']) {
            const original = window[kind];
            window[kind] = function (callback, delay, ...args) {
              window.__timers.push({ kind, delay: Number(delay) });
              return original(callback, delay, ...args);
            };
          }
        });
        let requests = 0;
        const requestPaths = [];
        await page.route('**/xhibit_content.php*', async route => {
          requests++;
          const url = new URL(route.request().url());
          requestPaths.push(url.pathname + url.search);
          await route.fulfill({ status: sample.status || 200, contentType: 'text/html; charset=UTF-8',
            body: Buffer.from(sample[implementation], 'base64') });
        });
        await page.goto(`http://127.0.0.1:${server.address().port}/index.php`, { waitUntil: 'networkidle' });
        await page.clock.pauseAt(new Date('2026-10-23T09:05:02Z'));
        const state = async () => page.evaluate(() => ({
          content: document.getElementById('parentContent').innerHTML,
          time: document.getElementById('time').innerHTML,
          notice: document.getElementById('notificationContents').innerHTML,
          brightness: document.getElementById('brightnessWindow').style.visibility,
          clockVisibility: document.getElementById('timeDisplay').style.visibility,
          page: document.getElementById('pageInfo').innerHTML,
          pages: window.thisDisplayDocument ? window.thisDisplayDocument.pages.length : 0,
          scroll: document.getElementById('displayArea') ? document.getElementById('displayArea').style.top : '',
          timers: window.__timers.filter(timer => timer.delay >= 500)
        }));
        const initial = await state();
        assert.strictEqual(initial.time, '09:05');
        await page.evaluate(() => document.querySelectorAll('marquee').forEach(element => element.stop()));
        const filename = sample.name.replace(/[^a-zA-Z0-9-]/g, '_') + '-' + implementation + '.png';
        images.push(await page.screenshot({ path: path.join(output, filename), animations: 'disabled' }));
        // Fire the real scroller/rotation callbacks under the controlled browser clock.
        await page.clock.runFor(31000);
        await page.waitForLoadState('networkidle');
        const advanced = await state();
        states.push({ initial, advanced, requests, requestPaths, errors });
        await context.close();
      }
      assert.deepStrictEqual(states[1], states[0], sample.name + ': browser state/timing differs');
      assert(images[0].equals(images[1]), sample.name + ': screenshot differs');
      // The verified No Info XSL sets NOINFO="false" without a resultTable.
      // Record this known production-baseline defect; do not conceal other errors.
      const expectedErrors = sample.name.endsWith('No Info') ? ['resultTable is not defined', 'resultTable is not defined'] : [];
      assert.deepStrictEqual(states[0].errors, expectedErrors, sample.name + ': unexpected baseline browser error');
      if (sample.name === 'English scrolling') {
        assert(states[0].initial.pages > 1, 'Scrolling fixture must span multiple pages');
        assert.notStrictEqual(states[0].initial.page, states[0].advanced.page, 'Scroller must advance');
      }
      if (sample.name.endsWith('Court Detail no notices')) {
        // Approved fix: an empty result table is one page and rotation continues.
        assert.strictEqual(states[0].initial.pages, 1, sample.name + ': empty table must be one page');
        assert(states[0].requests >= 2, sample.name + ': rotation must continue past an empty table');
      }
      if (sample.name.endsWith('power saving')) assert.strictEqual(states[0].initial.brightness, 'visible');
      if (sample.name === 'Empty feed holding') assert.strictEqual(states[0].requests, 4);
      if (sample.name === 'AJAX three failures') assert.strictEqual(states[0].requests, 3);
      results.push({ name: sample.name, matched: true, pages: states[0].initial.pages,
        requests: states[0].requests, requestPaths: states[0].requestPaths,
        initialPage: states[0].initial.page, advancedPage: states[0].advanced.page,
        powerSaving: states[0].initial.brightness, notification: states[0].initial.notice,
        timers: states[0].initial.timers, baselineErrors: states[0].errors });
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2), { mode: 0o600 });
    console.log(JSON.stringify({ comparisons: results.length, matched: true, output }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
