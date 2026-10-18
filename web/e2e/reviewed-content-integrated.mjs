import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const base = process.env.ROAMSYNC_CONTENT_BASE || 'http://127.0.0.1:3016';
if (!['http://127.0.0.1:3016', 'http://127.0.0.1:3000'].includes(base)) throw Error('Existing local product entry required');
const out = process.env.ROAMSYNC_CONTENT_EVIDENCE || '../docs/evidence/place-content-photos-20261018';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1365, height: 1000 } });
const page = await context.newPage();
const report = { base, business_writes: 0, cases: [], failures: [] };
await context.route('**/api/**', route => {
  if (route.request().method() !== 'GET') { report.business_writes++; return route.abort('blockedbyclient'); }
  return route.continue();
});
try {
  for (const [id, name] of [
    ['7489846f-f1da-596d-97f9-1a4c0a30164d', '杭州西湖风景名胜区'],
    ['99ac1e1a-20b8-5a8d-a295-115696890899', '中国丝绸博物馆'],
    ['0a6a0146-2fe0-587a-8527-ed7c31ada254', '杭州博物馆'],
  ]) {
    // A fresh database has no canonical snapshot until a real Provider search.
    // Never seed a production cache by copying the isolated place record.
    const search = await context.request.get(base + '/api/v1/places/search?' +
      new URLSearchParams({ city: '杭州', query: name }));
    expect(search.status()).toBe(200);
    const searched = await search.json();
    expect(searched.items.some(place => place.ref.place_id === id && place.name === name)).toBe(true);
    const response = await context.request.get(base + '/api/v1/places/' + id);
    expect(response.status()).toBe(200);
    const place = await response.json();
    expect(place.ref.place_id).toBe(id);
    expect(place.name).toBe(name);
    expect(place.images.length).toBe(1);
    const photo = place.images[0];
    const imageResponse = await context.request.get(base + photo.url);
    expect(imageResponse.status()).toBe(200);
    expect(imageResponse.headers()['content-type']).toContain('image/jpeg');
    const body = await imageResponse.body();
    await page.goto(base + '/places/' + id);
    const gallery = page.getByRole('region', { name: `${name}的地点照片` });
    await expect(gallery).toBeVisible();
    await expect.poll(() => gallery.locator('img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
    await expect(gallery.getByRole('link', { name: 'CC BY-SA 4.0', exact: true })).toBeVisible();
    await page.screenshot({ path: `${out}/integrated-${id}.png`, fullPage: true });
    report.cases.push({ id, name, photo_count: place.images.length, media_url: photo.url,
      media_sha256: createHash('sha256').update(body).digest('hex'), api_and_render: 'passed' });
  }
  expect(report.business_writes).toBe(0);
} catch (error) { report.failures.push(error.message); throw error; }
finally {
  await writeFile(`${out}/integrated-browser.json`, JSON.stringify(report, null, 2));
  await browser.close();
  console.log(JSON.stringify({ cases: report.cases.length, failures: report.failures.length }));
}
