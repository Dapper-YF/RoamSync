// Isolated browser smoke: built Web + a real local SSE socket, synthetic data.
// No requests reach production and no formal trips are read or modified.
import { chromium, expect } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';

const dist = resolve('dist');
const evidence = resolve('../backend/evals/results/companion_stream_20261012/browser');
await mkdir(evidence, { recursive: true });
let answerGate, secondGate, doneGate;
const answerReady = new Promise(r => { answerGate = r; });
const secondReady = new Promise(r => { secondGate = r; });
const doneReady = new Promise(r => { doneGate = r; });
const session = { id: 'socket-fixture', trip_id: null, latest_run_id: null, messages: [], pending_action: null };
const analysis = '结合区域分布、文化兴趣与每日节奏解释；交通衔接仍需核实。';
const first = '第一天把钟山片区的历史体验集中安排。';
const second = '下午接室内博物馆，让游览节奏有所变化。';
const server = createServer(async (req, res) => {
  try {
    if (req.url.endsWith('/messages/stream')) {
      let body = '';
      for await (const chunk of req) body += chunk;
      const input = JSON.parse(body);
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' });
      const send = event => res.write('data: ' + JSON.stringify(event) + '\n\n');
      send({ type: 'analysis_delta', delta: analysis });
      await answerReady;
      send({ type: 'answer_delta', delta: first });
      await secondReady;
      send({ type: 'answer_delta', delta: second });
      await doneReady;
      session.messages = [{ id: input.message_id, user: input.message, assistant: first + second,
        companion_result: { response_text: first + second, analysis_summary: analysis, goal_type: 'explanation',
          status: 'completed', suggestions: [], resolved_suggestion_refs: [], runtime_trace: [] } }];
      send({ type: 'done', session });
      res.end();
      return;
    }
    if (req.url.startsWith('/api/')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(req.url.includes('/assistant/sessions') ? session : []));
      return;
    }
    let file = resolve(dist, '.' + req.url.split('?')[0]);
    if (!file.startsWith(dist)) throw new Error('path');
    if (!extname(file)) file = resolve(dist, 'index.html');
    const mime = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' };
    const content = await readFile(file);
    res.writeHead(200, { 'Content-Type': mime[extname(file)] || 'application/octet-stream' });
    res.end(content);
  } catch {
    if (!res.headersSent) res.writeHead(404);
    res.end('fixture failure');
  }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
const checks = [];
const requests = [];
const errors = [];
page.on('request', req => { if (req.url().includes('/api/')) requests.push(req.method() + ' ' + new URL(req.url()).pathname); });
page.on('pageerror', err => errors.push(err.message));
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.getByRole('button', { name: '旅程总管', exact: true }).click();
  const input = page.getByRole('textbox', { name: '告诉旅程总管' });
  await input.fill('为什么会这样安排？');
  await expect(page.getByRole('button', { name: '发送需求', exact: true })).toBeEnabled();
  await input.press('Enter');
  await page.getByText(analysis, { exact: true }).waitFor({ state: 'visible' });
  checks.push('analysis visible before answer');
  await page.screenshot({ path: resolve(evidence, '01-analysis.png') });
  answerGate();
  await page.getByText(first, { exact: true }).waitFor({ state: 'visible' });
  if (!await input.isDisabled()) throw new Error('request incorrectly completed');
  checks.push('first answer visible while request remains pending');
  await page.screenshot({ path: resolve(evidence, '02-streaming-answer.png') });
  secondGate();
  await page.getByText(first + second, { exact: true }).waitFor({ state: 'visible' });
  checks.push('answer grows over a real SSE socket');
  doneGate();
  await page.getByText('回答依据', { exact: true }).waitFor({ state: 'visible' });
  await page.getByText('Thinking · 分析摘要', { exact: true }).click();
  await page.getByText(analysis, { exact: true }).waitFor({ state: 'visible' });
  checks.push('completed turn preserves analysis summary');
  await page.screenshot({ path: resolve(evidence, '03-completed.png') });
  await page.reload();
  await page.getByRole('button', { name: '旅程总管', exact: true }).click();
  await page.getByText(first + second, { exact: true }).waitFor({ state: 'visible' });
  checks.push('completed answer restored after reload');
  await writeFile(resolve(evidence, 'result.json'), JSON.stringify({ status: 'passed', checks, synthetic: true, production_access: false }, null, 2));
  console.log(JSON.stringify({ status: 'passed', checks: checks.length }));
} catch (err) {
  await page.screenshot({ path: resolve(evidence, 'failure.png') });
  await writeFile(resolve(evidence, 'failure.json'), JSON.stringify({ requests, errors, message: err.message, pageText: await page.locator('body').innerText() }, null, 2));
  throw err;
} finally {
  answerGate(); secondGate(); doneGate();
  await browser.close();
  server.closeAllConnections();
  await new Promise(r => server.close(r));
}
