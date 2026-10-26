// Synthetic prototype only. No provider, database or product API is called.
export const VERSION = 1;
export const TODAY = '2026-10-21';
export const TOMORROW = '2026-10-22';
export const places = {
  park: { id: 'park', name: '人民公园', city: '成都', description: '喝茶、散步。可以围绕一个地方慢慢体验。', verification: '合成地点示例；尚未查询实际开放、天气和路线' },
  alley: { id: 'alley', name: '宽窄巷子', city: '成都', description: '看街巷、建筑与商业街区。和喝茶散步是两种体验方向。', verification: '合成地点示例；尚未查询实际开放、天气和路线' },
  food: { id: 'food', name: '附近餐饮候选', city: '成都', description: '实际产品应查询餐厅身份、距离及营业情况后供选择。', verification: '占位示例，不是真实餐厅推荐' },
};
export const samples = [
  '成都人为什么喜欢喝茶？',
  '人民公园和宽窄巷子哪个更适合慢慢逛？',
  '我明天下午去人民公园，几点再说。',
  '帮我安排第二天，人民公园想去，15:00—16:00留白，别太满。',
  '附近有什么好吃的？',
  '这里怎么样？',
];
export function initialState() {
  return {
    schema: VERSION, page: 'assistant', focus: null, browsing: 'park', day: '2026-11-03',
    intents: [], seen: [], candidate: null, retry: null, undo: null, notice: '', error: '',
    failNextSave: false, weatherUnavailable: false, routeUnavailable: false,
    trip: { id: 'chengdu-demo', title: '成都 · 4日慢旅行', version: 1, dates: ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05'],
      activities: [{ id: 'booking', date: '2026-11-03', time: '10:00', duration: 60, name: '已订茶艺体验', protected: true, source: '你提供的预约（合成示例，未核验订单）' }],
      free: { date: '2026-11-03', start: '15:00', end: '16:00' } },
    messages: [{ role: 'assistant', text: '可以先聊想了解的，也可以告诉我已经决定的事。明确打算可以先记下，日期和钟点不必一次想好。', kind: 'welcome' }],
  };
}
const clone = s => structuredClone(s);
function say(s, text, kind = 'text') { s.messages.push({ role: 'assistant', text, kind }); }
function unique(s, prefix) { return `${prefix}-${s.seen.length}-${s.messages.length}-${s.trip.version}`; }
function decidePlace(s, text) {
  if (/人民公园/.test(text) && !/宽窄巷子/.test(text)) return 'park';
  if (/宽窄巷子/.test(text) && !/人民公园/.test(text)) return 'alley';
  return s.focus?.kind === 'place' ? s.focus.placeId : null;
}
function ambiguous(s, text) {
  return /这里|这个地方|附近/.test(text) && s.focus?.kind === 'place' && s.browsing && s.browsing !== s.focus.placeId && !/人民公园|宽窄巷子/.test(text);
}
function plan(s) {
  if (s.focus?.kind !== 'day') {
    say(s, '这句话涉及某一天的安排。请从右侧选择“调整这一天”，明确是哪一趟旅行的第二天；我不会把独立打算自动并入四日游。', 'scope');
    return;
  }
  const date = s.focus.date;
  s.candidate = { id: unique(s, 'candidate'), baseVersion: s.trip.version, date,
    activity: { id: 'park-activity', date, name: '人民公园 · 喝茶散步', time: '13:00', duration: 90, protected: false, source: 'AI 建议（原型模拟）' }, stale: false };
  const protectedText = s.trip.activities.some(a => a.date === date && a.protected) ? '先保留上午的预约，' : '';
  const freeText = s.trip.free.date === date ? '15:00—16:00继续留白，' : '';
  say(s, `${date}${protectedText}建议13:00—14:30去人民公园。${freeText}其余时间先不加项目。地点开放、实际路线和天气仍需核实。当前安排没有改动。`, 'candidate');
  s.page = 'arrangements';
}
function saveIntent(s, text, id) {
  if (s.failNextSave) {
    s.failNextSave = false; s.retry = { text, id }; s.error = '这次未能保存，原话已保留。重试成功后才会显示“已记下”。';
    say(s, '打算还没有保存成功。你可以重试，或者继续聊其他事情。', 'save-error'); return;
  }
  const placeId = decidePlace(s, text);
  if (!placeId) { say(s, '你说的是人民公园还是宽窄巷子？请明确要记下的地方。', 'clarify'); return; }
  const date = /明天/.test(text) ? TOMORROW : /后天/.test(text) ? '2026-10-23' : null;
  const period = /下午/.test(text) ? '下午' : /上午/.test(text) ? '上午' : /晚上/.test(text) ? '晚上' : '时间未定';
  const old = s.intents.find(i => i.status === 'active' && i.placeId === placeId && i.date === date && i.period === period);
  if (old) { say(s, `已经记有这项打算，没有重复添加：${old.label}。`, 'saved'); s.retry = null; return; }
  const item = { id, placeId, label: places[placeId].name, date, period, status: 'active', version: 1, source: text, capturedAt: TODAY };
  s.intents.push(item); s.undo = { id, version: 1 }; s.retry = null;
  s.focus = { kind: 'place', placeId }; s.browsing = placeId;
  s.notice = `已记下：${date || '日期未定'} ${period} · ${item.label}。`;
  say(s, `${s.notice}具体钟点仍未定，也没有创建旅行或调整其他活动。`, 'saved');
}
export function reduce(state, action) {
  if (action.type === 'RESET') return initialState();
  const s = clone(state); s.notice = ''; s.error = '';
  switch (action.type) {
    case 'PAGE': s.page = action.page; return s;
    case 'BROWSE': s.browsing = action.placeId; s.page = 'explore'; return s;
    case 'DISCUSS': s.focus = { kind: 'place', placeId: action.placeId }; s.page = 'assistant'; s.notice = `正在讨论：${places[action.placeId].name}`; return s;
    case 'DAY': s.day = action.date; return s;
    case 'FOCUS_DAY': s.focus = { kind: 'day', tripId: s.trip.id, date: s.day }; s.page = 'arrangements'; s.notice = `本次只讨论 ${s.day}。`; return s;
    case 'CLEAR_FOCUS': s.focus = null; s.notice = '已回到自由聊，保存过的内容仍在。'; return s;
    case 'NEW_CHAT': s.focus = null; s.messages = [{ role: 'assistant', text: '新的对话开始了。先前记下的打算和旅行仍可在“我的安排”找到。' }]; s.page = 'assistant'; s.notice = '已清空当前讨论背景。'; return s;
    case 'SETTING': s[action.key] = action.value; return s;
    case 'SEND': {
      const text = action.text.trim(); if (!text) return state;
      const id = action.id || unique(s, 'message');
      if (s.seen.includes(id)) { s.notice = '该消息已经处理，没有重复写入。'; return s; }
      s.messages.push({ role: 'user', text });
      if (ambiguous(s, text)) {
        say(s, `你正在浏览${places[s.browsing].name}，对话原先在说${places[s.focus.placeId].name}。你指哪一个？`, 'ambiguous'); s.seen.push(id); return s;
      }
      if (/先别保存|不要保存|先不安排|先随便看看/.test(text)) {
        say(s, '可以，先看看或比较，不新增打算或安排。');
      } else if (/不去|取消.*人民公园|取消.*宽窄巷子/.test(text)) {
        const pid = decidePlace(s, text); const matches = s.intents.filter(i => i.status === 'active' && i.placeId === pid);
        if (matches.length === 1) { matches[0].status = 'cancelled'; matches[0].version++; s.undo = null; say(s, '已撤销这项独立打算。正式旅行中的活动和预约未受影响。'); }
        else say(s, '请在“我的安排”中选择要撤销的具体打算；同名或正式预约不会一并取消。', 'clarify');
      } else if (/帮我安排|安排第|调整第|帮我排|规划第/.test(text)) {
        plan(s);
      } else if (/我(?:们)?明天|记下|确定想去/.test(text) && /人民公园|宽窄巷子/.test(text) && !/[？?]|如果|假如|听说|朋友说/.test(text)) {
        saveIntent(s, text, id); if (s.retry) return s;
      } else if (/天气|下雨/.test(text)) {
        say(s, s.weatherUnavailable ? '暂时没有取得天气信息。我不会判断明天下雨，也不会撤掉你决定要去的地点。可以先保留安排，出发前再查。' : '这里没有接入实时天气。可以演示“天气不可用”的处理；不会根据合成场景自动修改安排。', 'weather');
      } else if (/附近|吃什么|好吃/.test(text)) {
        const pid = decidePlace(s, text);
        if (!pid) say(s, '你想看哪个地方附近的餐饮？可以在地点卡上选择“讨论这里”。没有把浏览位置当成你的实时位置。', 'clarify');
        else { say(s, `以${places[pid].name}为中心找餐饮。原型只展示查询入口，实际产品应返回可核实的餐厅，不会自动加入安排。`, 'food'); s.browsing = pid; }
      } else if (/过去|路线|导航/.test(text)) {
        s.page = 'explore'; say(s, '可以先明确起点并查询路线。这里未接入真实地图，不会显示模拟的导航用时或当前位置。', 'route');
      } else if (/人民公园/.test(text) && /宽窄巷子/.test(text)) {
        say(s, '想坐下来喝茶、散步，可以先了解人民公园；更想看街巷和建筑，可以先了解宽窄巷子。若你更在意少走路，还需要结合出发点查询实际路线，不能仅凭地点介绍保证。', 'compare');
      } else if (/为什么.*喝茶|喝茶文化/.test(text)) {
        say(s, '喝茶可以是日常休息，也可以是见朋友、摆龙门阵的一种方式。你可以先了解这种生活体验，不必马上决定去哪。此处为交互示例回答。', 'knowledge');
      } else {
        say(s, '这是按场景模拟的交互原型，没有调用真实 AI。可以使用下方示例，体验保存打算、明确讨论对象和采用一天的建议。未知输入不会触发写入。', 'unsupported');
      }
      s.seen.push(id); return s;
    }
    case 'RETRY': {
      if (!s.retry) return s; const { text, id } = s.retry; saveIntent(s, text, id); if (!s.retry && !s.seen.includes(id)) s.seen.push(id); return s;
    }
    case 'UNDO': {
      const i = s.intents.find(i => i.id === (action.id || s.undo?.id));
      if (i && i.status === 'active' && (!s.undo || i.id !== s.undo.id || i.version === s.undo.version)) { i.status = 'cancelled'; i.version++; s.undo = null; s.notice = '已撤销这项打算。'; }
      else s.error = '这项内容已经变化，请重新查看。'; return s;
    }
    case 'PROPOSE': plan(s); return s;
    case 'CONTINUE':
      if (s.candidate) { s.focus = { kind: 'day', tripId: s.trip.id, date: s.candidate.date }; s.page = 'assistant'; s.notice = '这份建议仍保留。可以继续说希望怎样调整。'; } return s;
    case 'REJECT': s.candidate = null; s.notice = '已放弃这份建议，原安排保留。'; return s;
    case 'ACCEPT':
      if (!s.candidate) return s;
      if (s.candidate.baseVersion !== s.trip.version) { s.candidate.stale = true; s.error = '安排已有新修改，这份建议已过期。请读取当前安排后重新生成。'; return s; }
      s.trip.activities = [...s.trip.activities.filter(i => !(i.id === s.candidate.activity.id && i.date === s.candidate.date)), s.candidate.activity]; s.trip.version++;
      s.notice = `已采用${s.candidate.date}的建议。预约与留白保留。`; s.candidate = null; return s;
    case 'EXTERNAL_CHANGE': s.trip.version++; s.notice = '已模拟另一处更新：当前安排版本增加，旧候选不能覆盖。'; return s;
    case 'EDIT': {
      const i = s.trip.activities.find(i => i.id === action.id && i.date === s.day);
      if (!i || i.protected) { s.error = '预约事项需要核对影响，不能用普通编辑覆盖。'; return s; }
      const time = action.time; const duration = Number(action.duration);
      if (!/^\d{2}:\d{2}$/.test(time) || !Number.isFinite(duration) || duration < 5 || duration > 1440) { s.error = '请填写有效时间与停留分钟。'; return s; }
      const [h, m] = time.split(':').map(Number); const start = h * 60 + m; const end = start + duration;
      if (h > 23 || m > 59 || end > 1440 || i.date === s.trip.free.date && start < 960 && end > 900) { s.error = '这次修改会越过当天或侵入15:00—16:00留白，请重新选择。'; return s; }
      if (s.trip.activities.some(a => a.id !== i.id && a.date === i.date && start < Number(a.time.slice(0, 2)) * 60 + Number(a.time.slice(3)) + a.duration && end > Number(a.time.slice(0, 2)) * 60 + Number(a.time.slice(3)))) { s.error = '时间与已有活动冲突，尚未保存。'; return s; }
      i.time = time; i.duration = duration; s.trip.version++; s.notice = '已保存直接修改；实际路线仍需核实。'; return s;
    }
    case 'ROUTE': s.notice = s.routeUnavailable ? '路线暂不可用。没有生成距离、用时或导航状态。' : '原型未接入真实路线；正式产品将从明确起点查询，不假设 GPS。'; return s;
    default: return s;
  }
}
