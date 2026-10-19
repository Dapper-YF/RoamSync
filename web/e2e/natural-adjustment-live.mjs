import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const out = resolve('../docs/evidence/natural-assistant');
const source = JSON.parse(await readFile(resolve(out, 'live-graph-final-accept.json'), 'utf8'));
if (!source.result.startsWith('PASS')) throw Error('verified synthetic baseline required');
const tid = source.after.trip_id;
const id = new Date().toISOString().replace(/[:.]/g, '-');
const report = { kind: 'real browser, model, map, Graph and Accept; synthetic existing Trip', trip_id: tid, steps: [] };
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
page.setDefaultTimeout(20000);
try {
  await page.goto(`http://127.0.0.1:3019/arrangements/${tid}`);
  await page.getByRole('heading', { name: /聊聊南京/ }).waitFor();
  const before = await (await page.request.get(`http://127.0.0.1:3019/api/v1/trips/${tid}/arrangement-items`)).json();
  await page.getByLabel('告诉助手你的问题或变化').fill('请调整第二天的安排：南京博物院需要12:30以后才能开始。总统府不要动。希望还可以游览110分钟，但如果赶不上预约请缩短博物院，说明取舍。其他日期和留白保持不变，玄武湖仍为备选。');
  await page.getByRole('button', { name: '发送', exact: true }).waitFor();
  const pending = page.waitForResponse(r => /\/assistant\/sessions\/[^/]+\/messages$/.test(r.url()), { timeout: 180000 });
  await page.getByRole('button', { name: '发送', exact: true }).click();
  const response = await pending;
  const message = await response.json();
  report.steps.push({ step: 'request-adjustment', status: response.status(), body: message });
  if (!message.latest_run_id) throw Error('No Graph started for the explicit existing-activity adjustment');
  const proposal = page.getByRole('region', { name: '局部调整建议' });
  await proposal.waitFor({ timeout: 240000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: resolve(out, `web-adjust-${id}-proposal.png`), fullPage: true });
  const adoption = page.waitForResponse(r => /\/plan-revisions\/[^/]+\/accept$/.test(r.url()), { timeout: 60000 });
  await proposal.getByRole('button', { name: '采用这次调整' }).click();
  const accepted = await adoption;
  report.steps.push({ step: 'accept', status: accepted.status(), body: await accepted.json() });
  if (!accepted.ok()) throw Error('Candidate final acceptance failed');
  await page.getByRole('status').filter({ hasText: '已采用调整' }).waitFor();
  await page.reload();
  await page.getByRole('complementary', { name: '我的安排' }).getByText('有意保留，不自动填满').waitFor();
  const after = await (await page.request.get(`http://127.0.0.1:3019/api/v1/trips/${tid}/arrangement-items`)).json();
  const museum = after.days.flatMap(d => d.activities).find(a => a.name.includes('博物院'));
  if (museum.scheduled_time < '12:30:00' || museum.duration_minutes >= 110) throw Error('Late-start/appointment tradeoff not reflected in adopted result');
  if (JSON.stringify(before.days[0]) !== JSON.stringify(after.days[0])) throw Error('Unrelated day changed');
  if (!after.days.flatMap(d => d.activities).some(a => a.schedule_locked && a.scheduled_time === '14:00:00')) throw Error('Fixed appointment moved');
  if (!after.items.some(i => i.label.includes('玄武湖') && i.kind === 'optional')) throw Error('Optional was promoted');
  report.steps.push({ step: 'restored', body: after });
  await page.screenshot({ path: resolve(out, `web-adjust-${id}-restored.png`), fullPage: true });
  report.result = 'PASS real browser explicit local adjustment→review→Accept→reload; unrelated decisions preserved';
} catch (error) {
  report.result = 'FAIL'; report.failure = error.message;
  await page.screenshot({ path: resolve(out, `web-adjust-${id}-failure.png`), fullPage: true }).catch(() => {});
} finally {
  await writeFile(resolve(out, `web-adjust-${id}.json`), JSON.stringify(report, null, 2));
  console.log(report.result, report.failure ?? ''); await browser.close();
}
if (report.result === 'FAIL') process.exitCode = 1;
