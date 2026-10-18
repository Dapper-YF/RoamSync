// UI creates the dedicated journey. Read-only API snapshots bind the handoff to one Trip.
// A missing Android receipt always leaves the full cross-client acceptance incomplete.
import { chromium, expect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';

const mode = process.argv[2] || 'prepare';
if (!['prepare', 'resume-prepare', 'verify'].includes(mode)) throw Error('Use prepare, resume-prepare or verify');
if (process.env.ROAMSYNC_ALLOW_ISOLATED_WRITES !== '1') throw Error('Explicit isolated acceptance scope required');
const base = 'http://127.0.0.1:3016';
const isolation = execFileSync('docker', ['exec', 'roamsync-product-20261016-api-1', 'python', '-c',
  'import os; print(os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION")=="1" and os.environ.get("DATABASE_URL", "").endswith("/roamsync_v2_integration"))'], { encoding: 'utf8' }).trim();
if (isolation !== 'True') throw Error('Isolated database identity check failed');
const out = resolve(process.env.ROAMSYNC_CROSS_CLIENT_EVIDENCE || '../docs/evidence/cross-client-20261018');
await mkdir(out, { recursive: true });
const manifestFile = resolve(out, 'handoff.json');
let report;
if (mode === 'prepare') {
  try { await readFile(manifestFile); throw Error('Dedicated handoff already exists; use verify or a new evidence directory'); }
  catch (e) { if (e.code !== 'ENOENT') throw e; }
  report = { created_at: new Date().toISOString(), base, isolated_database: 'roamsync_v2_integration',
    source_commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    title: `跨端同一旅行验收 ${Date.now()}`, checks: [], failures: [],
    physical_android: 'not_run', cross_client_acceptance: 'incomplete',
    fixture_semantics: 'software only; not visited; opening and booking unknown' };
} else report = JSON.parse(await readFile(manifestFile, 'utf8'));
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1365, height: 1000 } });
const page = await context.newPage();
report.last_attempt = { mode, started_at: new Date().toISOString(), status: 'running' };
page.on('pageerror', e => report.failures.push({ kind: 'browser', code: e.name }));
const save = () => writeFile(manifestFile, JSON.stringify(report, null, 2));
const get = async path => {
  const response = await context.request.get(base + '/api/v1' + path);
  expect(response.status(), path).toBe(200);
  return response.json();
};
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
async function snapshot() {
  const [trip, days, execution, requirements] = await Promise.all([
    get(`/trips/${report.trip_id}`), get(`/trips/${report.trip_id}/days`),
    get(`/trips/${report.trip_id}/execution-progress`), get(`/trips/${report.trip_id}/requirements`),
  ]);
  expect(trip.id).toBe(report.trip_id);
  expect(trip.title).toBe(report.title);
  return { trip_id: trip.id, version: trip.version, title: trip.title, start_date: trip.start_date,
    day_ids: days.map(d => d.id), activities: days.flatMap(d => d.activities.map(a => ({
      id: a.id, day_id: d.id, name: a.display_name || a.name, start: a.scheduled_time, duration: a.duration_minutes,
    }))), execution, requirements, days_sha256: digest(days) };
}
async function deviceProtocolRead() {
  // This is a protocol client, explicitly not an Android/device test.
  const issued = await context.request.post(base + '/api/v1/device-pairing');
  expect(issued.ok()).toBeTruthy();
  const pairing = await issued.json();
  const paired = await context.request.post('http://127.0.0.1:18004/api/v1/device-sessions', {
    data: { pairing_code: pairing.pairing_code },
  });
  expect(paired.ok()).toBeTruthy();
  const session = await paired.json();
  const headers = { Authorization: `Bearer ${session.access_token}` };
  try {
    const responses = await Promise.all([
      context.request.get(`http://127.0.0.1:18004/api/v1/trips/${report.trip_id}`, { headers }),
      context.request.get(`http://127.0.0.1:18004/api/v1/trips/${report.trip_id}/days`, { headers }),
    ]);
    for (const response of responses) expect(response.status()).toBe(200);
    const [trip, days] = await Promise.all(responses.map(response => response.json()));
    expect(trip.id).toBe(report.trip_id);
    expect(trip.title).toBe(report.title);
    expect(digest(days)).toBe(report.after_read.days_sha256);
    report.device_protocol_read = { passed: true, physical_device: false, trip_id: trip.id,
      version: trip.version, days_sha256: digest(days), authentication: 'fresh short-lived paired bearer, revoked after read' };
  } finally {
    const revoked = await context.request.delete('http://127.0.0.1:18004/api/v1/device-sessions/current', { headers });
    expect(revoked.status()).toBe(204);
  }
}
try {
  if (mode !== 'verify') {
    if (mode === 'prepare') {
    await page.goto(base + '/drafts/new');
    await page.getByLabel('想去哪里', { exact: true }).fill('杭州');
    await page.getByLabel('为这次旅行起个名字', { exact: true }).fill(report.title);
    await page.getByLabel('玩几天', { exact: true }).fill('1');
    await page.getByLabel('你想怎样度过这几天', { exact: true }).fill('喜欢了解杭州历史，轻松游览，每天步行不超过60分钟。');
    await page.getByRole('button', { name: '开始筹划', exact: true }).click();
    await page.waitForURL(/\/drafts\/[0-9a-f-]+$/);
    report.draft_id = page.url().split('/').at(-1);
    await save();
    await page.getByLabel('这次希望怎样安排', { exact: true }).fill('只安排杭州博物馆和河坊街两个地点，先了解城市历史再游览街区，每处活动保持轻松，不安排其他地点。');
    await page.getByRole('button', { name: '生成活动建议', exact: true }).click();
    await expect(page.getByRole('button', { name: '按范围调整草稿', exact: true })).toBeVisible({ timeout: 180000 });
    } else {
      if (!report.draft_id || report.trip_id) throw Error('Only an unpromoted dedicated draft can resume preparation');
      await page.goto(base + `/drafts/${report.draft_id}`);
    }
    const day = page.locator('.journeys-days > article').first();
    const names = ['杭州博物馆', '河坊街'];
    const expectedIds = ['0a6a0146-2fe0-587a-8527-ed7c31ada254', '9c4e5176-122f-56b7-b783-f37788dd7a45'];
    await expect(day.locator('ol.journeys-activities > li')).toHaveCount(2);
    for (let i = 0; i < names.length; i++) {
      const row = day.locator('ol.journeys-activities > li').nth(i);
      await row.getByRole('button', { name: '从真实搜索选择地点', exact: true }).click();
      await row.getByLabel('在杭州搜索地点', { exact: true }).fill(names[i]);
      await row.getByRole('button', { name: '搜索真实地点', exact: true }).click();
      const exactPlace = row.locator(`.journeys-picker-body > article[data-place-id="${expectedIds[i]}"]`);
      await expect(exactPlace).toHaveCount(1, { timeout: 45000 });
      await exactPlace.getByRole('button', { name: '使用这个地点', exact: true }).click();
    }
    await page.getByRole('button', { name: '核对并保存修改', exact: true }).click();
    await page.getByRole('button', { name: '确认保存修改', exact: true }).click();
    await expect(page.getByText('修改已保存，离开后可以继续。', { exact: true })).toBeVisible();
    report.checks.push('Web UI create, actual model draft, exact Provider place selection and explicit save');
    const savedDraft = await get(`/drafts/${report.draft_id}`);
    const generatedRun = savedDraft.runs.at(-1);
    expect(generatedRun.status).toBe('completed');
    expect(generatedRun.source).toBe('model');
    report.model_run = { id: generatedRun.id, status: generatedRun.status, source: generatedRun.source };
    const tomorrow = new Date(Date.now() + 86400000).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
    report.start_date = tomorrow;
    await page.getByLabel('出发日期', { exact: true }).fill(tomorrow);
    await page.getByLabel('总预算（元，可留空）', { exact: true }).fill('500');
    await page.getByLabel('每日预算（元，可留空）', { exact: true }).fill('500');
    await page.getByLabel('每处活动停留（分钟）', { exact: true }).fill('45');
    await page.getByRole('button', { name: '查看日期和完整方案', exact: true }).click();
    await expect(page.getByRole('article', { name: '待确认的正式安排' })).toBeVisible({ timeout: 90000 });
    await page.screenshot({ path: resolve(out, 'web-before-explicit-confirm.png'), fullPage: true });
    report.checks.push('Web UI real route and complete dated plan preview');
    const confirmation = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/draft-promotions'));
    await page.getByRole('button', { name: '确认创建并采用这份日程', exact: true }).click();
    const created = await (await confirmation).json();
    report.operation_id = created.id;
    await save();
    await expect(page.getByText('旅行和日程已确认', { exact: true })).toBeVisible({ timeout: 120000 });
    const operation = await get(`/draft-promotions/${created.id}`);
    expect(operation.status).toBe('applied');
    report.trip_id = operation.target_trip_id;
    await page.getByRole('link', { name: '查看这次旅行 →', exact: true }).click();
    await expect(page.getByRole('heading', { name: report.title, exact: true })).toBeVisible();
    report.before_android = await snapshot();
    report.checks.push('Web UI explicit adoption and same formal Trip page read');
    report.web_preparation = 'passed';
    report.next_required = 'Same Trip on final physical APK; manual execution, Recovery Accept, next stop, interruption, then verify';
    await page.screenshot({ path: resolve(out, 'web-formal-handoff.png'), fullPage: true });
  } else {
    if (!report.trip_id || !report.before_android) throw Error('Missing original Web handoff');
    report.after_read = await snapshot();
    const draft = await get(`/drafts/${report.draft_id}`);
    const generatedRun = draft.runs.at(-1);
    expect(generatedRun.status).toBe('completed');
    expect(generatedRun.source).toBe('model');
    report.model_run = { id: generatedRun.id, status: generatedRun.status, source: generatedRun.source };
    await page.goto(base + `/trips/${report.trip_id}`);
    await expect(page.getByRole('heading', { name: report.title, exact: true })).toBeVisible();
    await page.screenshot({ path: resolve(out, 'web-same-trip-reread.png'), fullPage: true });
    report.checks.push('Read-only Web reread resolves original Trip ID and title');
    await deviceProtocolRead();
    report.checks.push('Fresh paired device protocol sees identical Trip/day data; not physical Android evidence');
    // Phone evidence is deliberately mandatory. A script/API replay cannot substitute.
    const receipt = JSON.parse(await readFile(resolve(out, 'android-receipt.json'), 'utf8').catch(() => 'null'));
    if (receipt?.physical_device === true && receipt?.passed === true && receipt.trip_id === report.trip_id
        && receipt.apk_sha256 === report.expected_apk_sha256 && report.expected_apk_sha256
        && receipt.recovery_accepted === true && receipt.next_stop_started === true
        && receipt.interruption_restored === true && report.after_read.version > report.before_android.version) {
      report.cross_client_acceptance = 'passed';
    } else {
      report.cross_client_acceptance = 'incomplete';
      report.next_required = 'Missing matching final physical APK execution/Recovery/interruption receipt';
    }
  }
  report.last_attempt.status = 'passed';
} catch (error) {
  report.last_attempt.status = 'failed';
  report.failures.push({ kind: mode, message: error.message });
  await page.screenshot({ path: resolve(out, `${mode}-failure.png`), fullPage: true }).catch(() => {});
  throw error;
} finally {
  report.last_attempt.finished_at = new Date().toISOString();
  report.checks = [...new Set(report.checks)];
  await save();
  await browser.close();
  console.log(JSON.stringify({ mode, trip_id: report.trip_id, web: report.web_preparation, full_cross_client: report.cross_client_acceptance, failures: report.failures.length }));
}
