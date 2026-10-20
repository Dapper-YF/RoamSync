import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const out = resolve(process.env.ROAMSYNC_EVIDENCE_DIR || '../docs/evidence/unified-assistant');
const base = process.env.ROAMSYNC_WEB_BASE_URL || 'http://127.0.0.1:3020';
if (!['http://127.0.0.1:3020', 'http://127.0.0.1:3021'].includes(base)) throw Error('Isolated acceptance ports only');
await mkdir(out, { recursive: true });
const id = new Date().toISOString().replace(/[:.]/g, '-');
const report = { kind: 'actual browser, configured model and Tavily; no mocks', base_url: base, cases: [], errors: [] };
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.addInitScript(() => {
  window.__streams = {}; window.__changes = [];
  const original = window.fetch;
  window.fetch = async (...args) => {
    const r = await original(...args);
    if (String(args[0]).endsWith('/messages/stream')) {
      const message = JSON.parse(args[1].body).message;
      r.clone().text().then(text => { window.__streams[message] = text; });
    }
    return r;
  };
  new MutationObserver(() => {
    const text = [...document.querySelectorAll('.travel-assistant-turn')].at(-1)?.querySelector('.travel-assistant-text')?.textContent ?? '';
    if (text && window.__changes.at(-1)?.text !== text) window.__changes.push({ at: performance.now(), text });
  }).observe(document, { childList: true, subtree: true, characterData: true });
});
page.on('pageerror', e => report.errors.push(e.message));
try {
  await page.goto(`${base}/`);
  for (const [name, message] of [
    ['general', '如果喜欢慢慢逛，成都和苏州分别有什么体验特点？先只讨论，不创建旅行。'],
    ['web-images', '请联网搜索成都有什么特色美食，配一张火锅或小吃相关的真实图片，介绍体验特点。'],
  ]) {
    await page.getByRole('textbox', { name: '告诉助手你的旅行想法' }).fill(message);
    await page.waitForFunction(() => !document.querySelector('button[aria-label="发送消息"]')?.disabled);
    await page.evaluate(() => { window.__changes = []; });
    const start = Date.now();
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await page.waitForFunction(m => window.__streams[m], message, { timeout: 180000 });
    const raw = await page.evaluate(m => window.__streams[m], message);
    const events = raw.split('\n\n').flatMap(f => f.startsWith('data: ') ? [JSON.parse(f.slice(6))] : []);
    const session = events.find(e => e.type === 'done')?.session;
    if (!session) throw Error(events.find(e => e.type === 'error')?.message || 'No completed session');
    const turn = session.messages.at(-1);
    const imageElements = page.locator('.travel-assistant-turn').last().locator('.assistant-answer-images img');
    await imageElements.first().waitFor({ timeout: 10000 }).catch(() => {});
    await page.waitForFunction(() => [...document.querySelectorAll('.assistant-answer-images img')].every(i => i.complete), undefined, { timeout: 20000 }).catch(() => {});
    const images = await imageElements.evaluateAll(els => els.map(i => ({ src: i.src, alt: i.alt, loaded: i.complete && i.naturalWidth > 0, width: i.naturalWidth })));
    const changes = await page.evaluate(() => window.__changes);
    report.cases.push({ name, message, elapsed_ms: Date.now() - start, turn, events: events.filter(e => e.type !== 'done'), changes, images,
      internal_copy_visible: await page.getByText(/这次回答基于 AI 通用知识|未进行来源或实时核验/).count(), screenshot: `experience-${id}-${name}.png` });
    await page.screenshot({ path: resolve(out, `experience-${id}-${name}.png`), fullPage: true });
  }
  report.result = report.cases.every(c => c.internal_copy_visible === 0) && report.cases[1].images.some(i => i.loaded) ? 'PASS' : 'PARTIAL';
} catch (e) { report.result = 'FAIL'; report.failure = e.message; }
finally { await writeFile(resolve(out, `experience-${id}.json`), JSON.stringify(report, null, 2)); await browser.close(); }
console.log(report.result, report.failure ?? '');
