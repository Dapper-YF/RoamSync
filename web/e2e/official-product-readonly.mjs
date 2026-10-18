import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const base = 'http://127.0.0.1:3000';
const out = '../docs/evidence/official-v2-20261018';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const report = { checks: [], failures: [], historicalTripsRead: 0, officialBusinessWrites: 0 };
page.on('pageerror', e => report.failures.push(e.message));
await context.route('**/api/**', async route => {
  const req = route.request();
  const readPost = ['/api/v1/routes/query', '/api/v1/places/discover'].includes(new URL(req.url()).pathname);
  if (req.method() !== 'GET' && !readPost) {
    report.officialBusinessWrites++;
    return route.abort('blockedbyclient');
  }
  await route.continue();
});
try {
  const html = await (await context.request.get(base)).text();
  expect(html).toContain('探索你的下一站');
  await page.goto(base);
  await expect(page.locator('.discovery-hero')).toBeVisible();
  await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible();
  await page.screenshot({ path: `${out}/official-home.png`, fullPage: true });
  report.checks.push('3000 built DiscoveryApp with approved product shell');
  await page.getByLabel('城市或地点', { exact: true }).fill('成都人民公园');
  await page.getByLabel('所在城市', { exact: true }).fill('成都');
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await expect(page.locator('a[href^="/places/"]').first()).toBeVisible({ timeout: 45000 });
  await page.locator('a[href^="/places/"]').first().click();
  await page.waitForURL(/\/places\/[0-9a-f-]+$/);
  await expect(page.getByRole('heading', { name: '人民公园', exact: true })).toBeVisible({ timeout: 30000 });
  report.checks.push('real place search to exact-ID detail through 3000');
  const api = async path => {
    const response = await context.request.get(base + '/api/v1' + path);
    expect(response.status()).toBe(200);
    return response.json();
  };
  await api('/me/favorites'); await api('/me/travel-preferences'); await api('/drafts');
  report.checks.push('favorites preferences and drafts API reachable through official gateway');
  const trips = await api('/trips');
  for (const trip of trips) {
    await api(`/trips/${trip.id}/days`);
    await api(`/trips/${trip.id}/preferences`);
    await api(`/trips/${trip.id}/execution-progress`);
    report.historicalTripsRead++;
  }
  await page.goto(base + '/trips');
  for (const name of ['正在筹划', '即将出发', '正在旅行', '历史旅行'])
    await expect(page.getByRole('tab', { name: new RegExp(name) })).toBeVisible();
  if (trips.length) {
    await page.goto(`${base}/trips/${trips[0].id}/planner`);
    await expect(page.locator('.journeys-page')).toBeVisible();
    await expect(page.getByRole('heading', { name: /^(已确认的日程|保留的旅行日程)$/ })).toBeVisible();
    expect(await page.locator('.planner-workbench').count()).toBe(0);
  }
  report.checks.push('journey lifecycle and historical planner URL use new formal page');
  await page.goto(base + '/nearby');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.goto(base + '/drafts/new');
  await expect(page.getByLabel('想去哪里')).toHaveValue('');
  report.checks.push('nearby page and undated draft entry mount without trip or GPS');
  expect((await context.request.get('http://127.0.0.1:8000/api/v1/trips')).status()).toBe(401);
  expect((await context.request.get(base + '/api/v1/trips', { headers: { Origin: 'https://untrusted.invalid' } })).status()).toBe(403);
  report.checks.push('direct unauthenticated API denied and foreign origin denied');
  expect(report.failures).toEqual([]);
  expect(report.officialBusinessWrites).toBe(0);
} catch (e) {
  report.failures.push(e.message); process.exitCode = 1;
} finally {
  await writeFile(`${out}/official-readonly.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
}
