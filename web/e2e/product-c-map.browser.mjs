import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve('../docs/evidence/product-c-20261022');
const fixture=JSON.parse(await readFile(resolve(out,'fixture.json'),'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const report={provider:'actual AMap JS API',cases:[]};
try{
 await page.goto(`http://127.0.0.1:3042/trips/${fixture.trip_id}`);
 await page.getByRole('tab',{name:'第2天 11-03'}).click();
 if(await page.getByRole('region',{name:'调整预览'}).isVisible())await page.getByRole('button',{name:'返回原安排',exact:true}).click();
 for(const width of [1440,390,320]){
  await page.setViewportSize({width,height:1000});
  await page.getByRole('tab',{name:'第1天 11-02'}).click();
  await page.getByRole('tab',{name:'第2天 11-03'}).click();
  await page.getByRole('button',{name:'查看当天地图 ↗'}).click();
  await page.locator('.map-container.amap-container').waitFor({timeout:30000});
  await page.locator('.amap-marker button').first().waitFor();
  const markers=page.locator('.amap-marker button');
  assert.equal(await markers.count(),2);
  await page.waitForFunction(()=>[...document.querySelectorAll('.amap-marker button')].every(e=>{const r=e.getBoundingClientRect();const m=e.closest('.handbook-map').getBoundingClientRect();return r.width>=44&&r.height>=44&&r.left>=m.left&&r.right<=m.right&&r.top>=m.top&&r.bottom<=m.bottom}),null,{timeout:30000});
  const boxes=await markers.evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();const m=e.closest('.handbook-map').getBoundingClientRect();return {width:r.width,height:r.height,inside:r.left>=m.left&&r.right<=m.right&&r.top>=m.top&&r.bottom<=m.bottom}}));
  assert(boxes.every(b=>b.width>=44&&b.height>=44&&b.inside));
  await page.getByRole('button',{name:'宽窄巷子景区',exact:true}).click();
  await page.getByText(/宽窄巷子景区 · 13:45/).waitFor();
  await page.screenshot({path:resolve(out,`map-${width}.png`),fullPage:true});
  report.cases.push({width,markers:boxes,selection:'actual marker updates the schedule context'});
  await page.getByRole('button',{name:'返回时间轴'}).click();
 }
 report.passed=true;
}catch(e){report.passed=false;report.failure=String(e);throw e}
finally{await writeFile(resolve(out,'map.json'),JSON.stringify(report,null,2));await browser.close();console.log(report)}
