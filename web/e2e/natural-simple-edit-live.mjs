import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const out = resolve('../docs/evidence/natural-assistant');
const baseline = JSON.parse(await readFile(resolve(out, 'live-graph-final-accept.json'), 'utf8'));
const tid = baseline.after.trip_id;
const report = { kind: 'real browser deterministic no-conflict edit; no new model/Graph', trip_id: tid };
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage();
try {
  await page.goto(`http://127.0.0.1:3019/arrangements/${tid}`);
  const before = await (await page.request.get(`http://127.0.0.1:3019/api/v1/trips/${tid}/arrangement-items`)).json();
  await page.getByRole('complementary', { name: '我的安排' }).getByText('固定活动 · 调整需核对影响').waitFor();
  await page.getByLabel('告诉助手你的问题或变化').fill('请把第二天南京博物院的停留时长改为30分钟，总统府不要动。其他日期和留白保持不变。');
  const waiting = page.waitForResponse(r => /\/assistant\/sessions\/[^/]+\/messages$/.test(r.url()), { timeout: 30000 });
  await page.getByRole('button', { name: '发送', exact: true }).click();
  const response = await waiting;
  const body = await response.json();
  if (!response.ok() || body.messages.at(-1)?.tool !== 'arrangement_edit') throw Error('safe scalar edit did not use deterministic command');
  const after = await (await page.request.get(`http://127.0.0.1:3019/api/v1/trips/${tid}/arrangement-items`)).json();
  const old = before.days.flatMap(d => d.activities);
  for (const a of after.days.flatMap(d => d.activities)) {
    const previous = old.find(p => p.id === a.id);
    if (a.name.includes('博物院')) { if (a.duration_minutes !== 30 || a.scheduled_time !== previous.scheduled_time) throw Error('wrong scalar edit'); }
    else if (JSON.stringify(a) !== JSON.stringify(previous)) throw Error('unrelated activity changed');
  }
  await page.reload();
  await page.locator('.natural-activity').filter({ hasText: '南京博物院' }).getByText(/30分钟/).waitFor();
  report.result = 'PASS safe scalar edit persisted without Graph or other activity changes';
  report.before = before; report.after = after; report.response = body;
} catch (e) { report.result = 'FAIL'; report.failure = e.message; }
finally { await writeFile(resolve(out, 'web-simple-duration.json'), JSON.stringify(report, null, 2)); await browser.close(); console.log(report.result, report.failure ?? ''); }
if (report.result === 'FAIL') process.exitCode = 1;
