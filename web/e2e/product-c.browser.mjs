import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

// This suite deliberately refuses the production URL.
const base='http://127.0.0.1:3042';
const out=resolve('../docs/evidence/product-c-20261022');
const fixture=JSON.parse(await readFile(resolve(out,'fixture.json'),'utf8'));
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const report={environment:'isolated real API/AMap/Worker, synthetic schedule; review mode uses a synthetic candidate with actual route enrichment, Validator and Accept',checks:[],viewports:[],errors:[]};
page.on('pageerror',e=>report.errors.push(e.message));
const tripPath=`/trips/${fixture.trip_id}`;
const get=async path=>{const r=await page.request.get(base+'/api/v1'+path);assert(r.ok(),`${path}: ${r.status()}`);return r.json()};
const snapshot=async()=>({trip:await get(`/trips/${fixture.trip_id}`),days:await get(`/trips/${fixture.trip_id}/days`),items:await get(`/trips/${fixture.trip_id}/arrangement-items`)});
async function shot(name){await page.screenshot({path:resolve(out,name+'.png'),fullPage:true})}
try{
 if(process.env.PRODUCT_C_REVIEW!=='1'){
 await page.goto(base+tripPath);await page.getByRole('tab',{name:'第2天 11-03'}).click();
 await page.getByRole('region',{name:'当天未排程事项'}).waitFor();
 if(await page.getByRole('region',{name:'调整预览'}).isVisible())await page.getByRole('button',{name:'返回原安排',exact:true}).click();
 assert.equal(await page.locator('.handbook-timeline').getByText('武侯祠',{exact:true}).count(),0);
 assert.match(await page.locator('.handbook-timeline').innerText(),/自由活动/);
 assert.match(await page.locator('.handbook-connection').innerText(),/前往.*宽窄巷子/);
 report.checks.push('saved timeline, deliberate free time, day-unscheduled and trip-undated are separate');
 await page.locator('.handbook-activity-photo img').first().waitFor();
 await page.waitForFunction(()=>[...document.querySelectorAll('.handbook-activity-photo img')].some(i=>i.complete&&i.naturalWidth>0));
 for(const width of [1440,390,320]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  await page.evaluate(()=>scrollTo(0,0));
  await shot('journey-'+width);
  const metrics=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,adjustTop:document.querySelector('.handbook-day-summary button')?.getBoundingClientRect().top,smallTargets:[...document.querySelectorAll('.handbook button,.handbook summary')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&r.height<43;}).length}));
  assert(metrics.scrollWidth<=width+1);assert.equal(metrics.smallTargets,0);report.viewports.push(metrics);
  await page.getByRole('button',{name:'和 AI 调整这一天',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  assert.equal(await page.getByRole('dialog').getByRole('textbox',{name:'告诉助手你的旅行想法'}).count(),1);
  assert.match(await page.getByRole('dialog').innerText(),/2026-11-03/);
  await shot('assistant-'+width);
  await page.getByRole('button',{name:'关闭助手',exact:true}).click();
 }
 report.checks.push('1440/390/320: no overflow, 44px targets, one scoped input');
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole('button',{name:'整趟概览',exact:true}).click();
 assert.equal(await page.locator('.handbook-overview .handbook-activity-photo:visible').count(),0);
 await page.getByRole('button',{name:'当天日程',exact:true}).click();
 await page.getByRole('button',{name:'查看当天地图 ↗'}).click();
 await page.locator('.handbook-map').waitFor();await shot('map-desktop');
 await page.getByRole('button',{name:'返回时间轴'}).click();
 // Search, detail, favorite, independent route and return to search use actual APIs.
 await page.getByRole('link',{name:'探索',exact:true}).click();
 await page.getByRole('textbox',{name:'城市或地点',exact:true}).fill('人民公园');
 await page.getByRole('textbox',{name:'所在城市',exact:true}).fill('成都');
 await page.getByRole('button',{name:'搜索',exact:true}).click();
 await page.waitForURL('**/explore?**',{timeout:45000});
 await page.getByRole('heading',{name:/人民公园.*个地点/}).waitFor();
 const searchURL=page.url();await shot('explore-desktop');
 await page.reload();await page.getByRole('heading',{name:/人民公园.*个地点/}).waitFor();
 await page.getByRole('link',{name:/景点 人民公园 成都市 · 小南街8号/}).click();
 await page.waitForURL('**/places/*');
 await page.getByRole('heading',{name:'人民公园',exact:true,level:1}).waitFor();
 await page.waitForFunction(()=>{const button=document.querySelector('.discovery-detail-actions button');return button&&!button.disabled});
 if(await page.getByRole('button',{name:'收藏地点',exact:true}).isVisible())await page.getByRole('button',{name:'收藏地点',exact:true}).click();
 await page.getByRole('button',{name:/已收藏/}).waitFor();
 await page.getByRole('link',{name:'怎么去',exact:true}).click();
 await page.getByRole('textbox',{name:'路线起点'}).waitFor();
 assert(!page.url().includes('/trips/'));
 await page.getByRole('link',{name:'收藏',exact:true}).click();
 await page.getByRole('link',{name:'返回探索',exact:true}).click();
 assert.match(page.url(),/\/explore/);
 report.checks.push('real search stays in Explore, reload restores query, real favorite and trip-free route, correct return links');
 // Legacy search bookmarks redirect without stealing an ordinary AI homepage visit.
 await page.goto(searchURL.replace('/explore?','/?'));await page.waitForURL('**/explore?**');
 report.checks.push('legacy search bookmarks remain compatible');
 }
 if(process.env.PRODUCT_C_REVIEW==='1'){
  await page.goto(base+tripPath);
  await page.getByRole('region',{name:'调整预览'}).waitFor({timeout:300000});
  const before=await snapshot();
  report.review=await page.getByRole('region',{name:'调整预览'}).innerText();
  await shot('review-desktop');
  await page.setViewportSize({width:390,height:844});await shot('review-mobile');
  await page.getByRole('button',{name:'继续商量',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  assert.match(await page.getByRole('dialog').innerText(),/2026-11-03/);
  await page.getByRole('button',{name:'关闭助手',exact:true}).click();
  assert.deepEqual((await snapshot()).days,before.days);
  await page.getByRole('button',{name:'返回原安排',exact:true}).click();
  assert.equal(await page.getByRole('region',{name:'调整预览'}).count(),0);
  await page.getByRole('button',{name:/查看待采用的调整/}).click();
  let failures=0;
  await page.route('**/plan-revisions/*/accept',async route=>{failures++;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{message:'验收模拟：连接暂不可用，请重试。'}})});});
  await page.getByRole('button',{name:/^采用.*的调整$/}).click();
  await page.getByRole('alert').filter({hasText:'验收模拟'}).waitFor();
  assert.equal(failures,1);assert.deepEqual((await snapshot()).days,before.days);
  assert.equal(await page.getByRole('region',{name:'调整预览'}).count(),1);await shot('accept-failed');
  await page.unroute('**/plan-revisions/*/accept');
  await page.reload();await page.getByRole('region',{name:'调整预览'}).waitFor();
  await page.getByRole('button',{name:/^采用.*的调整$/}).click();
  await page.getByText('已采用调整并重新读取安排。',{exact:true}).waitFor({timeout:45000});
  const after=await snapshot();
  assert(after.trip.version>before.trip.version);
  assert.deepEqual(after.days[0],before.days[0]);
  assert.deepEqual(after.items.items,before.items.items);
  await page.reload();await page.getByRole('tab',{name:'第2天 11-03'}).click();
  assert.match(await page.locator('.handbook-timeline').innerText(),/13:30/);
  assert.equal(await page.getByRole('region',{name:'调整预览'}).count(),0);
  await shot('accepted-mobile');
  report.accepted={versionBefore:before.trip.version,versionAfter:after.trip.version,days:after.days,items:after.items.items};
  report.checks.push('synthetic candidate → continue/return without reject → simulated 503 preserves candidate and formal state → reload → actual Validator/Accept → persisted result');
 }
 assert.deepEqual(report.errors,[]);
 report.passed=true;
}catch(e){report.passed=false;report.failure=String(e);await shot('browser-failure');throw e}
finally{await writeFile(resolve(out,process.env.PRODUCT_C_REVIEW==='1'?'browser-review.json':'browser.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({passed:report.passed,checks:report.checks,viewports:report.viewports,failure:report.failure}));}
