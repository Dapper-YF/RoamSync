// Exercise deployed static assets against an isolated synthetic SSE server.
// Only GETs for static files reach the deployed Web; business APIs never do.
import { chromium, expect } from '@playwright/test';
import { createServer } from 'node:http';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const origin = process.env.ROAMSYNC_SMOKE_WEB_ORIGIN || 'http://127.0.0.1:3000';
const evidence = resolve('../docs/evidence/streaming-release-20261015');
await mkdir(evidence, { recursive: true });
const deferred = () => {
  let release;
  return { promise: new Promise((r) => { release = r; }), release: () => release() };
};
const firstGate = deferred(), secondGate = deferred(), doneGate = deferred(), disconnectGate = deferred();
const session = { id: 'release-synthetic', trip_id: null, latest_run_id: null, pending_action: null, messages: [] };
const analysis = '结合文化兴趣与游览节奏整理建议。';
const first = '可以先了解城市的历史文化。';
const second = '再按自己的兴趣选择体验。';
const retryAnswer = '重试后的完整回答。';
const requests = [], checks = [], errors = [], staticFiles = new Set();
let streamCalls = 0;
const save = (input, text) => {
  if (!session.messages.some((m) => m.id === input.message_id)) {
    session.messages.push({ id: input.message_id, user: input.message, assistant: text,
      companion_result: { response_text: text, analysis_summary: analysis, goal_type: 'recommendation',
        status: 'completed', suggestions: [], resolved_suggestion_refs: [], runtime_trace: [] } });
  }
};
const server = createServer(async (req, res) => {
  try {
    if (req.url.endsWith('/messages/stream')) {
      let body = '';
      for await (const chunk of req) body += chunk;
      const input = JSON.parse(body);
      requests.push({ message_id: input.message_id, message: input.message });
      streamCalls += 1;
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
      const send = (event) => res.write('data: ' + JSON.stringify(event) + '\n\n');
      if (streamCalls === 1) {
        send({ type: 'analysis_delta', delta: analysis });
        await firstGate.promise;
        send({ type: 'answer_delta', delta: first });
        await secondGate.promise;
        send({ type: 'answer_delta', delta: second });
        await doneGate.promise;
        save(input, first + second);
      } else if (streamCalls === 2) {
        send({ type: 'answer_delta', delta: '这段回答尚未完成。' });
        await disconnectGate.promise;
        res.destroy();
        return;
      } else {
        save(input, retryAnswer);
      }
      send({ type: 'done', session });
      res.end();
      return;
    }
    if (req.url.startsWith('/api/')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(req.url.includes('/assistant/sessions') ? session : []));
      return;
    }
    if (req.method !== 'GET') throw new Error('Unexpected non-static request');
    const target = new URL(req.url, origin);
    if (target.origin !== new URL(origin).origin) throw new Error('Unexpected static origin');
    const response = await fetch(target);
    staticFiles.add(target.pathname);
    res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'application/octet-stream' });
    res.end(Buffer.from(await response.arrayBuffer()));
  } catch {
    if (!res.headersSent) res.writeHead(500);
    res.end('Synthetic fixture failed');
  }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const fixtureOrigin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
page.on('pageerror', (error) => errors.push(error.message));
await page.route('**/*', (route) => new URL(route.request().url()).origin === fixtureOrigin
  ? route.continue() : route.abort());
try {
  await page.goto(fixtureOrigin);
  await page.getByRole('button', { name: '旅程总管', exact: true }).click();
  const input = page.getByRole('textbox', { name: '告诉旅程总管' });
  await expect(input).toBeEnabled();
  await input.fill('推荐一些文化体验。');
  await input.press('Enter');
  await expect(page.getByText(analysis, { exact: true })).toBeVisible();
  checks.push('public summary visible before completion');
  firstGate.release();
  await expect(page.getByText(first, { exact: true })).toBeVisible();
  await expect(input).toBeDisabled();
  checks.push('answer visible while SSE remains open');
  secondGate.release();
  await expect(page.getByText(first + second, { exact: true })).toBeVisible();
  checks.push('answer grows before done');
  await page.screenshot({ path: resolve(evidence, 'streaming.png') });
  doneGate.release();
  await expect(input).toBeEnabled();
  await expect(page.getByText('回答依据', { exact: true })).toBeVisible();
  checks.push('completed answer replaces preview');
  await page.reload();
  await page.getByRole('button', { name: '旅程总管', exact: true }).click();
  await expect(page.getByText(first + second, { exact: true })).toBeVisible();
  checks.push('completed synthetic session restores on refresh');
  await input.fill('再推荐一种体验。');
  await input.press('Enter');
  await expect(page.getByText('这段回答尚未完成。', { exact: true })).toBeVisible();
  disconnectGate.release();
  await expect(input).toBeEnabled();
  await expect(page.getByText('本次请求尚未确认成功，内容已保留，可重试发送。', { exact: true })).toBeVisible();
  await expect(page.getByText('这段回答尚未完成。', { exact: true })).toHaveCount(0);
  if (session.messages.length !== 1) throw new Error('Incomplete response persisted');
  checks.push('disconnect removes partial preview and preserves request');
  await input.press('Enter');
  await expect(page.getByText(retryAnswer, { exact: true })).toBeVisible();
  if (requests[1].message_id !== requests[2].message_id) throw new Error('Retry changed message identity');
  if (session.messages.length !== 2) throw new Error('Retry duplicated synthetic turn');
  checks.push('retry reuses message ID and renders one completed turn');
  if (errors.length) throw new Error('Browser runtime errors');
  await page.screenshot({ path: resolve(evidence, 'retry-complete.png') });
  await writeFile(resolve(evidence, 'browser.json'), JSON.stringify({ status: 'passed', checks,
    static_origin: origin, static_files: [...staticFiles], synthetic_business_api: true,
    production_business_api_access: false, browser_errors: errors, stream_requests: requests.length }, null, 2));
  console.log(JSON.stringify({ status: 'passed', checks: checks.length }));
} catch (error) {
  await page.screenshot({ path: resolve(evidence, 'failure.png') });
  await writeFile(resolve(evidence, 'browser-failure.json'), JSON.stringify({ message: error.message, checks, errors }, null, 2));
  throw error;
} finally {
  for (const gate of [firstGate, secondGate, doneGate, disconnectGate]) gate.release();
  await browser.close();
  server.closeAllConnections();
  await new Promise((r) => server.close(r));
}
