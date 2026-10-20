import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { assertNaturalAdjustment } from './assert-natural-adjustment.mjs';

const out = resolve(process.env.ROAMSYNC_EVIDENCE_DIR || '../docs/evidence/unified-assistant');
const base = process.env.ROAMSYNC_WEB_BASE_URL || 'http://127.0.0.1:3020';
if (!['http://127.0.0.1:3020', 'http://127.0.0.1:3021'].includes(base)) throw Error('Isolated acceptance ports only');
await mkdir(out, { recursive: true });
const id = new Date().toISOString().replace(/[:.]/g, '-');
const report = { kind: 'real Chromium / real isolated API / real model / real map; synthetic user', base_url: base, started_at: new Date().toISOString(), steps: [], requests: [], consoleErrors: [] };
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
await page.addInitScript(() => {
  window.__assistantStreams = {};
  const original = window.fetch;
  window.fetch = async (...args) => {
    const response = await original(...args);
    if (String(args[0]).endsWith('/messages/stream')) {
      const message = JSON.parse(args[1].body).message;
      response.clone().text().then(text => { window.__assistantStreams[message] = text; });
    }
    return response;
  };
});
page.setDefaultTimeout(20000);
page.on('pageerror', error => report.consoleErrors.push(error.message));
page.on('requestfinished', request => {
  if (request.url().includes('/api/v1/')) report.requests.push({ path: new URL(request.url()).pathname, method: request.method(), timing: request.timing() });
});
const record = async (step, detail = {}) => {
  report.steps.push({ step, at: new Date().toISOString(), ...detail });
  await writeFile(resolve(out, `web-live-${id}.json`), JSON.stringify(report, null, 2));
  console.log(step);
};
const send = async (message) => {
  const start = Date.now();
  if (!await page.getByRole('textbox', { name: '告诉助手你的旅行想法' }).count()) await page.getByRole('button', { name: '旅行助手', exact: true }).click();
  await page.getByRole('button', { name: '发送消息', exact: true }).waitFor();
  await page.getByRole('textbox', { name: '告诉助手你的旅行想法' }).fill(message);
  const finished = page.waitForResponse(r => /\/assistant\/sessions\/[^/]+\/messages\/stream$/.test(r.url()) && r.request().method() === 'POST', { timeout: 180000 });
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const response = await finished;
  await page.waitForFunction(message => window.__assistantStreams[message], message, { timeout: 180000 });
  const raw = await page.evaluate(message => window.__assistantStreams[message], message);
  const frames = raw.split('\n\n').flatMap(frame => frame.startsWith('data: ') ? [JSON.parse(frame.slice(6))] : []);
  const body = frames.find(e => e.type === 'done')?.session;
  if (!body) throw Error(JSON.stringify(frames.find(e => e.type === 'error') || frames));
  await record('chat', { message, elapsed_ms: Date.now() - start, status: response.status(), body });
  if (!response.ok()) throw Error(`chat failed ${response.status()}`);
  await page.getByRole('button', { name: '发送消息', exact: true }).waitFor({ state: 'visible' });
  return body;
};
try {
  await page.goto(`${base}/`);
  await page.getByRole('heading', { name: '下一站，想去哪里？' }).waitFor();
  const before = await (await page.request.get(`${base}/api/v1/trips`)).json();
  const first = await send('第一次去南京，南京博物院和玄武湖的体验有什么区别？先只聊聊，不创建旅行。');
  if (first.trip_id || first.pending_action) throw Error('consultation incorrectly became saved work');
  const afterQuestion = await (await page.request.get(`${base}/api/v1/trips`)).json();
  if (JSON.stringify(before) !== JSON.stringify(afterQuestion)) throw Error('Trip created during consultation');
  await send('南京博物院确定想去但时间未定；玄武湖有时间再去。现在先讨论。');
  const proposal = await send('我决定2026-11-07到2026-11-08去南京两天。周日总统府14:00-15:00已经预约；周六15:00-16:00明确留白。保留南京博物院但暂不排时间，玄武湖还是备选。请形成允许留白的旅行安排建议，别把两天填满。');
  if (!proposal.pending_action?.flexible) throw Error('no usable flexible preview');
  await page.getByRole('region', { name: '待采用的安排建议' }).waitFor();
  await page.screenshot({ path: resolve(out, `web-${id}-preview.png`), fullPage: true });
  const adoption = page.waitForResponse(r => /\/assistant\/sessions\/[^/]+\/decision$/.test(r.url()), { timeout: 60000 });
  await page.getByRole('button', { name: '采用并保存这份安排' }).click();
  const adoptedResponse = await adoption;
  const adopted = await adoptedResponse.json();
  if (!adopted.trip_id || !adoptedResponse.ok()) throw Error('adoption failed');
  const tid = adopted.trip_id;
  await page.getByRole('link', { name: /查看.*的已保存安排/ }).click();
  await page.waitForURL(`**/trips/${tid}`);
  await page.getByRole('heading', { name: adopted.pending_action?.title || /南京/ }).first().waitFor();
  const panel = page.getByRole('complementary', { name: '我的安排' });
  await panel.getByText('有意保留，不自动填满').waitFor();
  await page.locator('.journeys-schedule').waitFor();
  await page.screenshot({ path: resolve(out, `web-${id}-saved.png`), fullPage: true });
  const museum = panel.locator('.natural-choice').filter({ hasText: '南京博物院' });
  const pageEdit = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/arrangement-items/'));
  await museum.getByRole('button', { name: '改为备选' }).click();
  if (!(await pageEdit).ok()) throw Error('page edit failed');
  await page.getByText('已保存这项决定，其他时间没有重新安排。').waitFor();
  const chat = await send('保留玄武湖，其他暂时不定');
  if (chat.latest_run_id) throw Error('simple change unnecessarily started Graph');
  const state = await (await page.request.get(`${base}/api/v1/trips/${tid}/arrangement-items`)).json();
  if (!state.items.some(i => i.label.includes('博物院') && i.kind === 'optional') || !state.items.some(i => i.label.includes('玄武湖') && i.kind === 'selected')) throw Error('chat lost page change');
  await record('page-plus-chat-readback', { trip_id: tid, body: state });
  await page.reload();
  await page.getByRole('complementary', { name: '我的安排' }).getByText('有意保留，不自动填满').waitFor();
  await page.locator('.natural-choice').filter({ hasText: '玄武湖' }).getByText('已选 · 时间未定').waitFor();
  await page.locator('.natural-choice').filter({ hasText: '南京博物院' }).getByText('备选 · 可以不去').waitFor();
  await page.screenshot({ path: resolve(out, `web-${id}-restored.png`), fullPage: true });
  // Continue the SAME browser/user task: resolve the selected name and choose
  // concrete time, then encounter a late start that needs real coordination.
  const museumChoice = page.locator('.natural-choice').filter({ hasText: '南京博物院' });
  await museumChoice.getByRole('button', { name: '安排具体时间' }).click();
  const scheduling = page.getByRole('form', { name: '为南京博物院安排具体时间' });
  await scheduling.getByRole('button', { name: '查询实际地点' }).click();
  await scheduling.getByRole('button', { name: '南京博物院 · 选择此地点', exact: true }).click();
  await scheduling.getByLabel('排程日期').selectOption({ label: '2026-11-08' });
  await scheduling.getByLabel('排程开始时间').fill('10:00');
  await scheduling.getByLabel('排程停留分钟').fill('60');
  const schedulingResponse = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/schedule'));
  await scheduling.getByRole('button', { name: '保存这项具体安排' }).click();
  const scheduled = await schedulingResponse;
  await record('schedule-chosen-place-and-time', { status: scheduled.status(), body: await scheduled.json() });
  if (!scheduled.ok()) throw Error('explicit UI scheduling failed');
  await page.getByText('已按你选择的地点和时间保存，没有补填其他时间；相邻路线仍需核实。').waitFor();
  const beforeAdjustment = await (await page.request.get(`${base}/api/v1/trips/${tid}/arrangement-items`)).json();
  const queried = page.waitForResponse(r => /\/day-plans\/[^/]+\/route$/.test(r.url()) && r.request().method() === 'GET', { timeout: 60000 });
  await page.getByRole('button', { name: '查看活动间路线，不改时间' }).last().click();
  const routeResponse = await queried;
  await record('read-only-route', { status: routeResponse.status(), body: await routeResponse.json() });
  if (!routeResponse.ok()) throw Error('actual route query failed');
  const afterRoute = await (await page.request.get(`${base}/api/v1/trips/${tid}/arrangement-items`)).json();
  if (JSON.stringify(afterRoute) !== JSON.stringify(beforeAdjustment)) throw Error('read-only route modified arrangement');
  await send('请调整第二天的安排：南京博物院需要12:30以后才能开始。总统府不要动。希望还可以游览110分钟，但如果赶不上预约请缩短博物院，说明取舍。其他日期和留白保持不变，玄武湖保持已选但时间未定，这次不要把它排进具体时间。');
  const adjustment = page.getByRole('region', { name: '局部调整建议' });
  await adjustment.waitFor({ timeout: 240000 });
  const beforeAccept = await (await page.request.get(`${base}/api/v1/trips/${tid}/arrangement-items`)).json();
  if (JSON.stringify(beforeAccept) !== JSON.stringify(beforeAdjustment)) throw Error('candidate changed formal result before acceptance');
  const runs = report.steps.filter(s => s.step === 'chat' && s.body.latest_run_id);
  const lastRun = runs.at(-1)?.body.latest_run_id;
  if (lastRun) await record('real-run-observations', { body: await (await page.request.get(`${base}/api/v1/planning-runs/${lastRun}`)).json() });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: resolve(out, `web-${id}-adjustment.png`), fullPage: true });
  const accepting = page.waitForResponse(r => /\/plan-revisions\/[^/]+\/accept$/.test(r.url()), { timeout: 60000 });
  await adjustment.getByRole('button', { name: '采用这次调整' }).click();
  const accepted = await accepting;
  await record('accept-real-local-adjustment', { status: accepted.status(), body: await accepted.json() });
  if (!accepted.ok()) throw Error('final adjustment acceptance failed');
  await adjustment.waitFor({ state: 'hidden' });
  await page.reload();
  await page.locator('.journeys-schedule').filter({ hasText: '南京博物院' }).waitFor();
  const final = await (await page.request.get(`${base}/api/v1/trips/${tid}/arrangement-items`)).json();
  assertNaturalAdjustment(final);
  if (!final.days.flatMap(d => d.activities).some(a => a.schedule_locked && a.scheduled_time === '14:00:00')) throw Error('appointment moved');
  if (JSON.stringify(final.days[0]) !== JSON.stringify(beforeAdjustment.days[0])) throw Error('unrelated free day changed');
  const lake = final.items.find(i => i.label.includes('玄武湖'));
  if (lake.kind !== 'selected' || lake.activity_id) throw Error('unscheduled choice was silently scheduled');
  for (const item of beforeAdjustment.items) {
    if (final.items.find(i => i.id === item.id)?.source_ref !== item.source_ref) throw Error('original item provenance changed');
  }
  await record('final-same-trip-readback', { body: final });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '刷新已保存内容' }).click();
  await page.getByRole('complementary', { name: '我的安排' }).getByText('有意保留，不自动填满').waitFor();
  await page.screenshot({ path: resolve(out, `web-${id}-mobile.png`), fullPage: true });
  const overflow = await page.locator('body').evaluate(el => el.scrollWidth > innerWidth);
  if (overflow) throw Error('mobile horizontal overflow');
  report.result = 'PASS one real browser/user/Trip chain: consultation→preview→adoption→page edit→chat edit→explicit time→late-start conflict→real Graph/route→Accept→reload';
} catch (error) {
  report.result = 'FAIL'; report.failure = error.message;
  await page.screenshot({ path: resolve(out, `web-${id}-failure.png`), fullPage: true }).catch(() => {});
} finally {
  report.finished_at = new Date().toISOString();
  await writeFile(resolve(out, `web-live-${id}.json`), JSON.stringify(report, null, 2));
  console.log(report.result);
  await browser.close();
}
if (report.result === 'FAIL') process.exitCode = 1;
