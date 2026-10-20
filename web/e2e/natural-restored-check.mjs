// Continuation on the SAME accepted Trip, not a replacement whole-chain claim.
import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { assertNaturalAdjustment } from './assert-natural-adjustment.mjs';

const out = '../docs/evidence/natural-closure-20261020';
const seed = JSON.parse(await readFile(`${out}/late-start-accepted-counterexample.json`, 'utf8'));
const trip = seed.run.trip_id;
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
let runRequests = 0;
page.on('request', request => { if (request.url().includes('/planning-runs/')) runRequests++; });
const report = { kind: 'same-Trip persisted-state continuation; no new model run', trip_id: trip };
try {
  await page.goto(`http://127.0.0.1:3019/arrangements/${trip}`);
  await page.getByRole('heading', { name: /聊聊南京/ }).waitFor();
  const state = await (await page.request.get(`http://127.0.0.1:3019/api/v1/trips/${trip}/arrangement-items`)).json();
  assertNaturalAdjustment(state);
  if (JSON.stringify(state) !== JSON.stringify(seed.state)) throw Error('accepted result changed unexpectedly');
  await page.getByText('有意保留，不自动填满').waitFor();
  await page.screenshot({ path: `${out}/same-trip-restored-desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '刷新已保存内容' }).click();
  await page.getByText('已选 · 时间未定').waitFor();
  if (await page.locator('body').evaluate(el => el.scrollWidth > innerWidth)) throw Error('horizontal overflow');
  await page.screenshot({ path: `${out}/same-trip-restored-mobile.png`, fullPage: true });
  await new Promise(resolve => setTimeout(resolve, 6000));
  if (runRequests !== 1) throw Error(`terminal run was queried ${runRequests} times`);
  report.terminal_run_requests_over_six_seconds = runRequests;
  report.result = 'PASS same accepted Trip restored on desktop/mobile; original full-chain failure record retained';
  report.state = state;
} catch (error) { report.result = 'FAIL'; report.failure = error.message; process.exitCode = 1; }
finally { await writeFile(`${out}/same-trip-restored.json`, JSON.stringify(report, null, 2)); await browser.close(); }
console.log(report.result);
