import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=process.env.ROAMSYNC_WEB_BASE_URL||'http://127.0.0.1:3024';
if(base!=='http://127.0.0.1:3024')throw Error('Full write acceptance uses the isolated service only');
const mode=process.env.ROAMSYNC_CHAIN_MODE||'normal';
const output=resolve('../docs/evidence/quality-integration-20261021',mode+'-'+new Date().toISOString().replace(/[:.]/g,'-'));
await mkdir(output,{recursive:true});
const report={mode,kind:'actual browser/model/AMap/Graph/Validator/Accept; one synthetic continuous conversation',steps:[],errors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1050}});
await page.addInitScript(()=>{window.__journeyStreams={};const original=window.fetch;window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/messages/stream')){const body=JSON.parse(args[1].body);response.clone().text().then(text=>window.__journeyStreams[body.message]=text).catch(()=>window.__journeyStreams[body.message]='data: '+JSON.stringify({type:'error',code:'browser_stream_disconnected'})+'\n\n');}return response;};});
page.on('pageerror',e=>report.errors.push(e.message));
async function record(step,details={}){report.steps.push({step,at:new Date().toISOString(),...details});await writeFile(resolve(output,'journey.json'),JSON.stringify(report,null,2));console.log(step);}
async function send(message){
  if(!await page.getByRole('textbox',{name:'告诉助手你的旅行想法'}).count())await page.getByRole('button',{name:'旅行助手',exact:true}).click();
  const input=page.getByRole('textbox',{name:'告诉助手你的旅行想法'});await input.fill(message);
  await page.waitForFunction(()=>!document.querySelector('button[aria-label="发送消息"]')?.disabled);
  const start=Date.now();await page.getByRole('button',{name:'发送消息',exact:true}).click();
  await page.waitForFunction(m=>window.__journeyStreams[m],message,{timeout:180000});
  const raw=await page.evaluate(m=>window.__journeyStreams[m],message);
  const frames=raw.split('\n\n').flatMap(f=>f.startsWith('data: ')?[JSON.parse(f.slice(6))]:[]);
  const next=frames.find(f=>f.type==='done')?.session;
  await record('chat',{message,elapsed_ms:Date.now()-start,body:next,errors:frames.filter(f=>f.type==='error')});
  if(!next)throw Error('No final saved response');
  if(next.messages.at(-1).execution_summary?.answer_status==='failed')throw Error('Failed response');
  return next;
}
async function arrangement(tid){return (await page.request.get(base+'/api/v1/trips/'+tid+'/arrangement-items')).json();}
try{
  await page.goto(base,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'新对话',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.travel-assistant-turn'));
  const before=await (await page.request.get(base+'/api/v1/trips')).json();
  for(const message of ['第一次去成都，想了解这里的城市气质和适合慢慢体验的事情。','牛油火锅和串串香有什么区别？我不吃辣，也想知道怎么选。','那就玩四天吧，2026年11月2日出发，别太赶。先不形成安排。','帮我列出成都值得看的几个景点，介绍一下建筑和景色，图片有帮助就展示。','人民公园确定想去，武侯祠有时间再去。我喜欢喝茶和建筑，先聊选择。']){
    const session=await send(message);if(session.trip_id||session.pending_action||session.latest_run_id)throw Error('Consultation mutated or previewed an itinerary');
  }
  const after=await (await page.request.get(base+'/api/v1/trips')).json();if(JSON.stringify(after)!==JSON.stringify(before))throw Error('Consultation changed saved trips');
  const photos=await page.locator('.assistant-inline-photo img').evaluateAll(images=>images.map(i=>({alt:i.alt,loaded:i.complete&&i.naturalWidth>0,visible:getComputedStyle(i.closest('figure')).display!=='none'})));
  await record('photo_rendering',{photos});
  if(await page.locator('.assistant-answer').filter({hasText:'参考图'}).count())throw Error('Visible reference-image label');
  await page.screenshot({path:resolve(output,'consultation.png'),fullPage:true});
  const proposal=await send('就按前面说的四天和出发日期，帮我形成允许留白的旅行安排建议。保留人民公园但暂不排时间，武侯祠还是备选；第二天15:00-16:00明确留白。别把四天填满。');
  if(!proposal.pending_action?.flexible)throw Error('Missing creation preview');
  const adoption=page.waitForResponse(r=>r.url().endsWith('/decision')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'采用并保存这份安排'}).click();const response=await adoption;const adopted=await response.json();
  await record('adopt_creation',{status:response.status(),body:adopted});if(!response.ok()||!adopted.trip_id)throw Error('Creation adoption failed');
  const tid=adopted.trip_id;report.trip_id=tid;
  await page.getByRole('link',{name:/查看.*的已保存安排/}).click();await page.waitForURL('**/trips/'+tid);
  const panel=page.getByRole('complementary',{name:'我的安排'});await panel.waitFor();
  const saved=await arrangement(tid);await record('saved_arrangement',{body:saved});
  if(saved.days.length!==4||!saved.items.some(i=>i.kind==='free_window')||!saved.items.some(i=>i.kind==='optional'&&i.label.includes('武侯祠')))throw Error('Lost duration, optional choice or free time');
  const park=panel.locator('.natural-choice').filter({hasText:'人民公园'});await park.getByRole('button',{name:'安排具体时间'}).click();
  const form=page.getByRole('form',{name:'为人民公园安排具体时间'});
  const finding=page.waitForResponse(r=>r.url().includes('/places/search?q=')&&r.request().method()==='GET');
  await form.getByRole('button',{name:'查询实际地点'}).click();const found=await finding;
  await record('actual_place_choices',{status:found.status(),body:await found.json()});
  const choose=form.getByRole('button',{name:/^(?:成都(?:市)?)?人民公园 · 青羊区 · 小南街8号.*选择此地点$/});
  await choose.first().waitFor({timeout:20000});
  if(await choose.count()!==1)throw Error('Ambiguous park identity, do not auto-select');await choose.click();
  await form.getByLabel('排程日期').selectOption({label:'2026-11-02'});await form.getByLabel('排程开始时间').fill('10:00');await form.getByLabel('排程停留分钟').fill('60');
  const scheduling=page.waitForResponse(r=>r.url().endsWith('/schedule')&&r.request().method()==='POST');await form.getByRole('button',{name:'保存这项具体安排'}).click();
  const scheduled=await scheduling;await record('schedule',{status:scheduled.status(),body:await scheduled.json()});if(!scheduled.ok())throw Error('Schedule failed');
  await send('保留武侯祠，其他暂时不定。');
  const beforeChange=await arrangement(tid);
  if(!beforeChange.items.some(i=>i.label.includes('武侯祠')&&i.kind==='selected'))throw Error('Natural change lost');
  await record('before_graph_change',{body:beforeChange});
  const changed=await send('请协调第一天的安排：人民公园需要12:30以后才能开始，仍想游览60分钟；不要新加地点，其他日期、已选但时间未定的武侯祠和第二天留白保持不变。请先给我候选方案，等我确认再保存。');
  if(!changed.latest_run_id)throw Error('Expected real planning run for coordination');
  const region=page.getByRole('region',{name:'局部调整建议'});await region.waitFor({timeout:300000});
  const run=await (await page.request.get(base+'/api/v1/planning-runs/'+changed.latest_run_id)).json();await record('real_graph_result',{body:run});
  const pending=await arrangement(tid);if(JSON.stringify(pending)!==JSON.stringify(beforeChange))throw Error('Candidate changed formal state before adoption');
  await page.screenshot({path:resolve(output,'candidate.png'),fullPage:true});
  if(mode==='recovery'){
    await page.route('**/plan-revisions/*/accept',r=>r.abort('failed'));await region.getByRole('button',{name:'采用这次调整'}).click();await page.getByRole('alert').first().waitFor();
    if(JSON.stringify(await arrangement(tid))!==JSON.stringify(beforeChange))throw Error('Failed Accept mutated formal state');
    await record('accept_network_failure_preserved_state');await page.unroute('**/plan-revisions/*/accept');await page.reload();
    if(!await region.isVisible())await page.getByRole('button',{name:'旅行助手',exact:true}).click();await region.waitFor();
  }
  const accepting=page.waitForResponse(r=>/\/plan-revisions\/[^/]+\/accept$/.test(r.url()));await region.getByRole('button',{name:'采用这次调整'}).click();
  const accepted=await accepting;await record('accept_adjustment',{status:accepted.status(),body:await accepted.json()});if(!accepted.ok())throw Error('Accept failed');
  await page.reload();const final=await arrangement(tid);await record('final_arrangement',{body:final});
  const activity=final.days.flatMap(d=>d.activities).find(a=>a.display_name.includes('人民公园'));
  if(!activity||activity.scheduled_time<'12:30:00'||activity.duration_minutes!==60)throw Error('Final arrangement does not match adjustment');
  if(!final.items.some(i=>i.kind==='free_window')||!final.items.some(i=>i.label.includes('武侯祠')&&i.kind==='selected'))throw Error('Adjustment lost unscoped choices');
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:resolve(output,'mobile.png'),fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Mobile overflow');
  if(report.errors.length)throw Error('Browser errors');report.passed=true;
}catch(error){report.failure=error.message;await page.screenshot({path:resolve(output,'failure.png'),fullPage:true});process.exitCode=1;}
finally{await writeFile(resolve(output,'journey.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({output,passed:!!report.passed,failure:report.failure}));}
