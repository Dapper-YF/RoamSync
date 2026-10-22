import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve('../docs/evidence/product-c-20261022');
const fixture=JSON.parse(await readFile(resolve(out,'fixture.json'),'utf8'));
const base='http://127.0.0.1:3042';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:390,height:844}});
const report={generation:'synthetic candidate, actual protected edit/409; isolated DB only'};
try{
 await page.goto(`${base}/trips/${fixture.trip_id}`);
 await page.getByRole('region',{name:'调整预览'}).waitFor();
 const api=base+'/api/v1';
 const trip=await (await page.request.get(`${api}/trips/${fixture.trip_id}`)).json();
 const days=await (await page.request.get(`${api}/trips/${fixture.trip_id}/days`)).json();
 const runs=await (await page.request.get(`${api}/trips/${fixture.trip_id}/planning-runs`)).json();
 const run=runs.find(r=>r.status==='awaiting_confirmation');assert(run);
 const revision=await (await page.request.get(`${api}/planning-runs/${run.id}/revision`)).json();
 const activity=days.flatMap(d=>d.activities).find(a=>!a.schedule_locked);
 const edit=await page.request.put(`${api}/activities/${activity.id}`,{headers:{'X-Trip-Version':String(trip.version)},data:{version:activity.version,scheduled_time:'13:45',duration_minutes:60}});
 assert(edit.ok(),await edit.text());
 const after=await (await page.request.get(`${api}/trips/${fixture.trip_id}/days`)).json();
 await page.reload();await page.getByRole('region',{name:'调整预览'}).waitFor();
 assert.equal(await page.getByRole('button',{name:/^采用.*的调整$/}).isDisabled(),true);
 await page.getByRole('alert').filter({hasText:'建议已过期'}).waitFor();
 const denied=await page.request.post(`${api}/plan-revisions/${revision.id}/accept`);
 assert.equal(denied.status(),409);
 assert.deepEqual(await (await page.request.get(`${api}/trips/${fixture.trip_id}/days`)).json(),after);
 await page.screenshot({path:resolve(out,'stale-mobile.png'),fullPage:true});
 report.passed=true;report.httpStatus=denied.status();report.versionBefore=trip.version;
 await page.getByRole('button',{name:'返回原安排',exact:true}).click();
}catch(e){report.passed=false;report.failure=String(e);throw e}
finally{await writeFile(resolve(out,'stale.json'),JSON.stringify(report,null,2));await browser.close();console.log(report)}
