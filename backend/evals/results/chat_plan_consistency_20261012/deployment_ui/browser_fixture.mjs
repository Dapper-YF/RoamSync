import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(join(process.cwd(), 'package.json'));
const { chromium } = require('@playwright/test');
const evidence = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 680, height: 1000 } });
let status = 'researching';
const requests = [];
const trip = { id: 'fixture', title: '隔离界面测试', destination: '南京市', start_date: '2026-10-11', end_date: '2026-10-13',
  total_budget_fen: null, daily_budget_fen: null, currency: 'CNY', version: 1, status: 'draft', accommodation: '',
  center_longitude: null, center_latitude: null, accommodation_longitude: null, accommodation_latitude: null };
const place = { id: 'place', name: '合成文化场馆', category: 'attraction', neighborhood: '', description: '',
  longitude: 118.8, latitude: 32.0, suggested_duration_minutes: 60, estimated_cost_fen: 0, rating: 4, tags: [],
  source: { id: 'source', title: '测试夹具', url: '', provider: 'fixture', queried_at: new Date().toISOString(), confidence: 1 } };
const session = { id: 'session', trip_id: 'fixture', latest_run_id: null, pending_action: null,
  messages: [{ id: 'created', user: '确认执行', assistant: '旅行已创建，正在准备候选行程。', run_id: null }] };
const run = () => ({ id: 'run', trip_id: 'fixture', status, run_type: 'initial_plan', user_request: '合成规划',
  token_usage: 0, created_at: new Date().toISOString(), heartbeat_at: new Date().toISOString(),
  progress: { stage: 'search', message: '正在搜索网页资料…', updated_at: new Date().toISOString() } });
const revision = { id: 'revision', planning_run_id: 'run', status: 'pending', reason: '合成候选',
  proposed_snapshot: { activities: [{ candidate_id: 'activity', day_date: '2026-10-11', place_candidate_id: 'place',
    planned_start_time: '10:00', duration_minutes: 60, estimated_cost_fen: 0, transport_mode_to_here: 'walk', reason: '回应文化兴趣', locked: false }] },
  difference_summary: {}, validation_result: { valid: true }, source_ids: [] };
const response = '这份待确认候选方案生成时保存的安排说明是：回应文化兴趣。涉及天气、开放时间等事实仍需核实。';
const errors = [];
page.on('pageerror', error => errors.push(String(error)));
await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  if (url.origin !== 'http://127.0.0.1:3000') throw new Error('External request forbidden: ' + url.origin);
  if (!url.pathname.startsWith('/api/')) return route.continue();
  const path = url.pathname;
  requests.push({ path, method: route.request().method(), synthetic: true });
  let json;
  if (path === '/api/v1/trips') json = [trip];
  else if (path.endsWith('/days')) json = [];
  else if (path.endsWith('/candidates')) json = [place];
  else if (path.endsWith('/planning-context')) return route.fulfill({ status: 503, json: { detail: 'Synthetic optional context unavailable' } });
  else if (path === '/api/v1/assistant/sessions') json = session;
  else if (path.endsWith('/messages')) {
    session.latest_run_id = 'run';
    session.messages.push({ id: 'explain', user: '为什么会这样安排？', assistant: response, run_id: null,
      companion_result: { response_text: response, goal_type: 'explanation', status: 'completed', suggestions: [],
        resolved_suggestion_refs: [], runtime_trace: [], explanation: { explanation_type: 'saved_plan_notes',
          reasons: ['回应文化兴趣'], based_on_prior_decision: false, source_decision_ref: 'revision:revision',
          fact_freshness_warning: '保存的模型说明尚未验证事实依据' } } });
    json = session;
  } else if (path.endsWith('/revision')) json = revision;
  else if (path === '/api/v1/planning-runs/run') json = run();
  else if (path.endsWith('/planning-runs')) json = [run()];
  else throw new Error('Unexpected API request: ' + path);
  await route.fulfill({ json });
});
try {
  await page.goto('http://127.0.0.1:3000/dev/agent-conversation/fixture');
  await page.getByRole('status').filter({ hasText: '正在搜索网页资料' }).waitFor();
  await page.screenshot({ path: join(evidence, 'browser_progress.png'), fullPage: true });
  status = 'awaiting_confirmation';
  await page.getByRole('button', { name: '确认并应用' }).waitFor();
  if (!(await page.getByRole('button', { name: '确认并应用' }).isEnabled())) throw new Error('Confirmation disabled');
  await page.reload();
  await page.getByRole('button', { name: '确认并应用' }).waitFor();
  await page.screenshot({ path: join(evidence, 'browser_candidate.png'), fullPage: true });
  await page.getByLabel('告诉旅程总管').fill('为什么会这样安排？');
  await page.getByRole('button', { name: '发送需求', exact: true }).click();
  await page.getByText(response, { exact: true }).waitFor();
  await page.getByText('Thinking · 回答说明', { exact: true }).click();
  await page.getByText('对应方案：revision', { exact: true }).waitFor();
  await page.screenshot({ path: join(evidence, 'browser_explanation.png'), fullPage: true });
  if (!(await page.getByRole('button', { name: '确认并应用' }).isEnabled())) throw new Error('Explanation lost confirmation');
  await page.getByRole('button', { name: '确认并应用' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(evidence, 'browser_confirmation_after_question.png'), fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  writeFileSync(join(evidence, 'browser_result.json'), JSON.stringify({ status: 'passed', synthetic_api: true,
    real_model: false, formal_writes: 0, checks: ['progress', 'polling_transition', 'legacy_reload', 'confirmation_visible',
      'saved_notes_provenance', 'confirmation_retained_after_explanation'], requests, errors }, null, 2));
} finally { await browser.close(); }
