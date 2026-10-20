import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = 'http://127.0.0.1:3021';
const tag = process.env.ROAMSYNC_STYLE_TAG || 'baseline';
if (!/^[a-z-]+$/.test(tag)) throw Error('Invalid evidence tag');
const out = resolve('../docs/evidence/official-integration-20261020');
await mkdir(out, { recursive: true });
const report = { kind: 'actual isolated browser and configured model; subjective style evidence, not a statistical benchmark', tag, cases: [] };
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.addInitScript(() => {
  localStorage.setItem('roamsync.discovery.topic', `style-${crypto.randomUUID()}`);
  window.__styleStreams = {};
  const original = window.fetch;
  window.fetch = async (...args) => {
    const response = await original(...args);
    if (String(args[0]).endsWith('/messages/stream')) {
      const message = JSON.parse(args[1].body).message;
      response.clone().text().then(text => { window.__styleStreams[message] = text; });
    }
    return response;
  };
});
try {
  await page.goto(base);
  const before = await (await page.request.get(`${base}/api/v1/trips`)).json();
  for (const question of ['成都有什么打卡拍照的地方', '成都有什么特色美食', '成都适合慢慢逛吗']) {
    await page.getByRole('textbox', { name: '告诉助手你的旅行想法' }).fill(question);
    await page.getByRole('button', { name: '发送消息' }).click();
    await page.waitForFunction(q => !!window.__styleStreams[q], question, { timeout: 120000 });
    const raw = await page.evaluate(q => window.__styleStreams[q], question);
    const events = raw.split('\n').filter(l => l.startsWith('data: ')).map(l => JSON.parse(l.slice(6)));
    const done = events.findLast(e => e.type === 'done');
    if (!done) throw Error(JSON.stringify(events.find(e => e.type === 'error') || 'No completed turn'));
    const turn = done.session.messages.filter(m => m.user === question).at(-1);
    report.cases.push({ question, answer: turn.assistant, tool: turn.tool, trip_id: done.session.trip_id,
      bold_heading_count: (turn.assistant.match(/\*\*[^*\n]{1,30}\*\*/g) || []).length });
    await page.getByRole('button', { name: '发送消息' }).isEnabled();
  }
  const after = await (await page.request.get(`${base}/api/v1/trips`)).json();
  if (JSON.stringify(before) !== JSON.stringify(after)) throw Error('Consultation changed Trip list');
  await page.screenshot({ path: resolve(out, `style-${tag}.png`), fullPage: true });
  report.result = 'COMPLETED; review actual answer content, no fabricated style score';
} catch (e) {
  report.result = 'FAIL'; report.failure = e.message; process.exitCode = 1;
} finally {
  await writeFile(resolve(out, `style-${tag}.json`), JSON.stringify(report, null, 2));
  await browser.close(); console.log(report.result);
}
