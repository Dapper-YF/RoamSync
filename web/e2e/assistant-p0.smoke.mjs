import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = process.env.ROAMSYNC_WEB_BASE_URL || 'http://127.0.0.1:3024';
if (!['http://127.0.0.1:3024', 'http://127.0.0.1:3000'].includes(base)) throw Error('Local acceptance ports only');
const out = resolve('../docs/evidence/assistant-p0-20261021');
await mkdir(out, { recursive: true });
const kind = base.endsWith(':3000') ? 'production' : 'isolated';
const report = { kind, base, cases: [], errors: [] };
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.addInitScript(() => {
  window.__p0streams = {};
  const original = window.fetch;
  window.fetch = async (...args) => {
    const response = await original(...args);
    if (String(args[0]).endsWith('/messages/stream')) {
      const body = JSON.parse(args[1].body);
      response.clone().text().then(text => { window.__p0streams[body.message] = text; });
    }
    return response;
  };
});
page.on('pageerror', e => report.errors.push(e.message));
try {
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  const messages = kind === 'production' ? [
    '那就玩四天的吧，帮我罗列一下成都的所有热门景点',
    '查成都明天的天气，并查询成都武侯祠博物馆到成都杜甫草堂博物馆的驾车路线',
  ] : [
    '展开说说：尝试成都牛油老火锅与串串香',
    '如果我明天去成都的话，计划玩几天比较合适',
    '那就玩四天的吧，帮我罗列一下成都的所有热门景点',
    '从成都武侯祠博物馆步行到成都杜甫草堂博物馆要多久？',
  ];
  for (const message of messages) {
    await page.getByRole('textbox', { name: '告诉助手你的旅行想法' }).fill(message);
    await page.waitForFunction(() => !document.querySelector('button[aria-label="发送消息"]')?.disabled);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await page.waitForFunction(m => window.__p0streams[m], message, { timeout: 105000 });
    const raw = await page.evaluate(m => window.__p0streams[m], message);
    const events = raw.split('\n\n').flatMap(f => f.startsWith('data: ') ? [JSON.parse(f.slice(6))] : []);
    const done = events.find(e => e.type === 'done');
    if (!done) throw Error(events.find(e => e.type === 'error')?.message || 'No done event');
    const turn = done.session.messages.at(-1);
    const summary = turn.execution_summary;
    if (!summary || summary.answer_status === 'failed') throw Error('Persisted failed answer');
    if (done.session.trip_id || turn.run_id) throw Error('Consultation created a formal itinerary/run');
    const visible = await page.locator('.travel-assistant-turn').last().innerText();
    if (!visible.replace(/\s+/g, '').includes(turn.assistant.replaceAll('**', '').replace(/\s+/g, '').slice(0, 20))) throw Error('Visible answer differs from saved reply');
    report.cases.push({ message, message_id: turn.id, summary, answer: turn.assistant,
      event_types: [...new Set(events.map(e => e.type))], trip_id: done.session.trip_id });
  }
  await page.screenshot({ path: resolve(out, `${kind}-desktop.png`), fullPage: true });
  const expected = report.cases.at(-1).answer.replaceAll('**', '').replace(/\s+/g, '').slice(0, 20);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(text => document.body.innerText.replace(/\s+/g, '').includes(text), expected, { timeout: 15000 });
  report.refresh_restored = true;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.travel-assistant-turn').last().scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(out, `${kind}-mobile.png`), fullPage: true });
  report.mobile_overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  report.passed = !report.mobile_overflow && report.errors.length === 0;
} catch (e) {
  report.passed = false; report.failure = e.message;
  await page.screenshot({ path: resolve(out, `${kind}-failure.png`), fullPage: true }).catch(() => {});
} finally {
  await writeFile(resolve(out, `${kind}-browser.json`), JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(JSON.stringify({ kind, passed: report.passed, failure: report.failure, cases: report.cases.length }));
if (!report.passed) process.exitCode = 1;
