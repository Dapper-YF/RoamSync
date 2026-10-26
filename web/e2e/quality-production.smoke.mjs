import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base=process.env.ROAMSYNC_WEB_BASE_URL||'http://127.0.0.1:3024';
if(!['http://127.0.0.1:3024','http://127.0.0.1:3000'].includes(base))throw Error('Local acceptance only');
const kind=base.endsWith(':3000')?'production':'isolated';
const out=resolve('../docs/evidence/quality-integration-20261021/production-smoke');await mkdir(out,{recursive:true});
const report={kind,cases:[],errors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1050}});
await page.addInitScript(()=>{
  window.__p1streams={};const original=window.fetch;
  window.fetch=async(...args)=>{const response=await original(...args);
    if(String(args[0]).endsWith('/messages/stream')){const body=JSON.parse(args[1].body);response.clone().text().then(raw=>window.__p1streams[body.message]=raw);}
    return response;};
});
page.on('pageerror',error=>report.errors.push(error.message));
async function send(message){
  const input=page.getByRole('textbox',{name:'告诉助手你的旅行想法'});
  await input.fill(message);await page.getByRole('button',{name:'发送消息',exact:true}).click();
  await page.waitForFunction(m=>window.__p1streams[m],message,{timeout:105000});
  const raw=await page.evaluate(m=>window.__p1streams[m],message);
  const events=raw.split('\n\n').flatMap(frame=>frame.startsWith('data: ')?[JSON.parse(frame.slice(6))]:[]);
  const done=events.find(e=>e.type==='done');if(!done)throw Error('Missing saved turn: '+message);
  const turn=done.session.messages.at(-1);
  if(turn.execution_summary?.answer_status==='failed')throw Error('Failed answer');
  if(done.session.trip_id||turn.run_id||done.session.pending_action)throw Error('Consultation wrote or previewed an itinerary');
  report.cases.push({user:message,answer:turn.assistant,summary:turn.execution_summary,memory:turn.context?.conversation_memory,visuals:turn.read_tools?.visuals});
  return turn;
}
async function fresh(){
  await page.getByRole('button',{name:'新对话',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.travel-assistant-turn'));
  await page.waitForFunction(()=>!document.querySelector('button[aria-label="发送消息"]')?.disabled||document.querySelector('textarea')?.value==='');
}
function hasDiet(turn){return turn.context?.conversation_memory?.preferences?.some(p=>p.value==='不吃辣'&&p.source_quote?.includes('不吃辣')&&p.message_id);}
try{
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.getByRole('textbox',{name:'告诉助手你的旅行想法'}).waitFor();
  await fresh();
  await send('第一次去成都，想了解城市气质和慢慢体验的事情。');
  const visual=await send('介绍成都牛油火锅与串串香的区别。');
  if(!visual.read_tools?.visuals?.images?.length)throw Error('No proactive illustrations');
  await page.waitForFunction(()=>[...document.querySelectorAll('.assistant-inline-photo img')].some(i=>i.complete&&i.naturalWidth>0),null,{timeout:20000});
  if(await page.locator(".assistant-photo-kind").count())throw Error("Unwanted photo badge");
  report.loaded_images=await page.locator('.assistant-inline-photo img').evaluateAll(images=>images.filter(i=>i.complete&&i.naturalWidth>0).length);
  report.photo_layout=await page.locator('.assistant-inline-photo').evaluateAll(figures=>figures.filter(f=>f.getBoundingClientRect().width>0).map(f=>({
    float:getComputedStyle(f).float,width:f.getBoundingClientRect().width,parent_width:f.parentElement.getBoundingClientRect().width,
    height:f.getBoundingClientRect().height,paragraph_top_delta:Math.abs(f.getBoundingClientRect().top-f.parentElement.querySelector('p').getBoundingClientRect().top)})));
  if(report.photo_layout.some(f=>f.float!=='right'||f.width>f.parent_width*.4||f.height>176))throw Error('Photo is not embedded beside its paragraph');
  await page.screenshot({path:resolve(out,`${kind}-illustrations.png`),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:resolve(out,`${kind}-illustrations-mobile.png`),fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Illustration mobile overflow');
  await page.setViewportSize({width:1440,height:1050});
  const stated=await send('我去成都，2026-11-02出发，玩四天，不吃辣。');
  if(!hasDiet(stated))throw Error('Explicit diet not persisted');
  const corrected=await send('改成11月5日出发，只玩三天。');
  const slots=corrected.context?.conversation_memory?.slots;
  if(slots?.start_date?.value!=='2026-11-05'||slots?.duration_days?.value!==3)throw Error('Condition correction was lost');
  if(!hasDiet(corrected))throw Error('Date correction dropped diet');
  const recalled=await send('我的出发日期、天数和忌口是什么？');
  if(!/11月5|11-05/.test(recalled.assistant)||!/三天|3天|天数.{0,3}3/.test(recalled.assistant)||!recalled.assistant.includes('不吃辣'))throw Error('Recall does not use current conditions');
  if(!hasDiet(recalled)||/没有存|没存|没有记录|未记录|似乎没有|再告诉|告诉我一声/.test(recalled.assistant))throw Error('Recall disclaims an already saved diet');
  if(recalled.read_tools?.visuals?.images?.length)throw Error('Forced an image onto a recall question');
  await page.reload({waitUntil:'domcontentloaded'});
  await page.getByText('不吃辣',{exact:false}).first().waitFor();
  const restored=await send('刷新后，我的出发日期、天数和忌口是什么？');
  if(!hasDiet(restored)||!restored.assistant.includes('不吃辣'))throw Error('Reload lost persisted diet');
  report.refresh_restored=true;
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:resolve(out,`${kind}-mobile.png`),fullPage:true});
  report.mobile_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  if(report.mobile_overflow)throw Error('Mobile overflow');
  await fresh();
  const reset=await send('我这次的出发日期和忌口确定了吗？');
  if(Object.keys(reset.context?.conversation_memory?.slots||{}).length||reset.context?.conversation_memory?.preferences?.length)throw Error('Old conditions leaked into new chat');
  report.new_chat_isolated=true;
  if(report.errors.length)throw Error('Browser script errors');
  report.passed=true;
}catch(error){report.failure=error.message;process.exitCode=1;}
finally{await writeFile(resolve(out,`${kind}-browser.json`),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({kind,passed:!!report.passed,cases:report.cases.length,failure:report.failure}));}
