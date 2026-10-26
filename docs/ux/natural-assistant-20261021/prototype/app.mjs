import { initialState, reduce, places, samples, VERSION } from './model.mjs';
const KEY = 'roamsync.ux-audit.20261021.prototype.v1';
let storageError = false;
let state = initialState();
try { const saved = JSON.parse(localStorage.getItem(KEY) || 'null'); if (saved?.schema === VERSION && Array.isArray(saved.intents) && Array.isArray(saved.messages) && saved.trip?.dates?.length === 4) state = saved; } catch { storageError = true; }
const $ = id => document.getElementById(id);
const esc = str => String(str ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const btn = (label, action, attrs = '') => `<button data-action="${action}" ${attrs}>${label}</button>`;
function dispatch(action) {
  state = reduce(state, action);
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { storageError = true; }
  render();
}
function endTime(time, duration) { const [h, m] = time.split(':').map(Number); const n = h * 60 + m + duration; return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`; }
function scopeText() {
  if (state.focus?.kind === 'place') return `正在讨论：${places[state.focus.placeId].name} · 成都`;
  if (state.focus?.kind === 'day') return `成都这趟旅行 · ${state.focus.date} · 只讨论这一天`;
  return '自由聊 · 没有关联旅行或待修改对象';
}
function candidate() {
  const c = state.candidate; if (!c) return '';
  const stale = c.stale || c.baseVersion !== state.trip.version;
  const preserved = [...state.trip.activities.filter(a => a.date === c.date && a.protected).map(a => `${a.time} ${a.name}`), ...(state.trip.free.date === c.date ? ['15:00—16:00 自由活动'] : [])];
  return `<section class="candidate ${stale ? 'stale' : ''}" aria-label="待采用的一天建议"><span class="label">${stale ? '建议已过期' : 'AI 建议 · 尚未采用'}</span><h3>${esc(c.date)} · 留一点余地</h3><p>新增：13:00—14:30 人民公园 · 喝茶散步</p><p>${preserved.length ? '保留：' + esc(preserved.join('；')) + '。' : ''}其他日期不动。</p><p class="muted">安排时间为合成建议。实际地点、交通和天气尚未查询。</p>${stale ? '<p>当前安排已经改变，旧建议不能覆盖。可以重新生成。</p>' : ''}<div class="actions">${btn('采用这一天的建议', 'accept', `class="primary" ${stale ? 'disabled' : ''}`)}${btn('继续商量', 'continue')}${btn('放弃这份建议', 'reject')}${stale ? btn('重新生成建议', 'propose') : ''}</div></section>`;
}
function render() {
  document.querySelectorAll('nav [data-page]').forEach(el => el.setAttribute('aria-current', el.dataset.page === state.page ? 'page' : 'false'));
  document.querySelector('.workspace').dataset.page = state.page;
  const explore = state.page === 'explore';
  $('arrangements').hidden = explore; $('explore').hidden = !explore;
  $('tab-arrangements').setAttribute('aria-selected', String(!explore)); $('tab-explore').setAttribute('aria-selected', String(explore));
  $('context').innerHTML = `<span>${esc(scopeText())}</span>${state.focus ? btn('移除背景', 'clear') : ''}`;
  $('feedback').textContent = state.notice; $('errors').textContent = state.error;
  $('storage-warning').hidden = !storageError; $('storage-warning').textContent = '浏览器存储不可用，当前内容仅在本页保留；刷新可能丢失。';
  $('messages').innerHTML = state.messages.map(m => `<article class="message ${m.role}"><div class="speaker">${m.role === 'user' ? '你' : 'RoamSync'}</div><p>${esc(m.text)}</p>${m.kind === 'ambiguous' ? `<div class="message-actions">${btn('讨论人民公园', 'discuss', 'data-place="park"')}${btn('讨论宽窄巷子', 'discuss', 'data-place="alley"')}</div>` : ''}${m.kind === 'compare' ? `<div class="message-actions">${btn('看看两个地点的位置', 'explore')}${btn('先了解人民公园', 'discuss', 'data-place="park"')}</div>` : ''}</article>`).join('');
  const showInChat = state.page === 'assistant' && state.focus?.kind === 'day' && state.focus.date === state.candidate?.date;
  $('decisions').innerHTML = `${state.retry ? `<div class="candidate" role="status"><p>待保存：${esc(state.retry.text)}</p>${btn('重试保存', 'retry', 'class="primary"')}</div>` : ''}${showInChat ? candidate() : ''}`;
  const active = state.intents.filter(i => i.status === 'active'); const cancelled = state.intents.filter(i => i.status === 'cancelled');
  const events = state.trip.activities.filter(a => a.date === state.day);
  $('arrangements').innerHTML = `<div class="section-heading"><h2>记下的打算</h2><span class="small-count">${active.length}项 · 不必先建旅行</span></div>${active.length ? active.map(i => `<article class="intent"><span class="badge">你已决定 · 钟点未定</span><strong>${esc(i.label)}</strong><span class="when">${esc(i.date || '日期未定')} · ${esc(i.period)}</span><div class="actions">${btn('讨论这项打算', 'discuss', `data-place="${i.placeId}"`)}${btn('撤销', 'undo', `data-id="${esc(i.id)}"`)}</div><details><summary>查看原话与日期来源</summary><p class="muted">${esc(i.source)}<br>按${esc(i.capturedAt)}表达时锚定；地点身份尚需实际核对。</p></details></article>`).join('') : '<p class="empty">想好一个地方，就告诉助手。具体几点去可以以后再定。</p>'}${cancelled.length ? `<details><summary>已撤销的打算（${cancelled.length}）</summary>${cancelled.map(i => `<p class="muted">${esc(i.label)} · ${esc(i.date || '日期未定')}</p>`).join('')}</details>` : ''}<section class="trip" aria-label="成都旅行示例"><p class="eyebrow">YOUR JOURNEY</p><h2>${state.trip.title}</h2><p class="muted">11月2日—5日 · 合成旅行，供体验局部安排</p><div class="date-tabs" aria-label="选择旅行日期">${state.trip.dates.map((d, i) => btn(`第${i + 1}天<small>${d.slice(5)}</small>`, 'day', `data-date="${d}" class="${d === state.day ? 'selected' : ''}" aria-pressed="${d === state.day}"`)).join('')}</div><div class="section-heading"><h3>${state.day}</h3>${btn('调整这一天', 'focus-day')}</div>${events.length ? events.map(a => `<article class="event"><span class="time">${a.time}—${endTime(a.time, a.duration)}</span><strong>${esc(a.name)}</strong><p>${esc(a.source)}</p>${!a.protected ? `<details><summary>直接修改时间或时长</summary><form class="editor" data-edit="${a.id}"><label>开始时间<input type="time" name="time" value="${a.time}" required></label><label>停留分钟<input type="number" name="duration" value="${a.duration}" min="5" max="1440" required></label><button type="submit">保存直接修改</button></form></details>` : ''}</article>`).join('') : '<p class="empty">这天尚未排具体活动，可以先保留空闲。</p>'}${state.day === state.trip.free.date ? `<div class="free"><strong>15:00—16:00 · 自由活动</strong><p>你有意保留的时间，不需要补全。</p></div>` : ''}<div class="actions">${btn('请 AI 建议怎么安排', 'plan-day', 'class="primary"')}</div>${state.page !== 'assistant' ? candidate() : ''}<details><summary>这次安排依据了什么</summary><p class="muted">合成场景：想轻松一些，人民公园想去；上午预约保持原样，下午明确留白。不表示真实预约或路线已核验。</p></details></section>`;
  const p = places[state.browsing];
  $('explore').innerHTML = `<h2>看看位置，再继续聊</h2><p class="muted">空间关系示意 · 不是实际地图或可导航路线</p><div class="place-picker">${Object.values(places).map(p => btn(p.name, 'browse', `data-place="${p.id}" aria-pressed="${p.id === state.browsing}"`)).join('')}</div><div class="map"><svg viewBox="0 0 470 265" role="img" aria-label="合成空间示意：人民公园、宽窄巷子与附近餐饮，没有真实距离"><path class="roads" d="M-20 180L490 50M90 -20L250 290M-10 65L490 220"/><path class="water" d="M350 -20Q280 80 370 170T400 290"/><path class="connection" d="M130 175L210 68L270 184"/><circle cx="130" cy="175" r="10"/><circle cx="210" cy="68" r="10"/><circle cx="270" cy="184" r="10"/><text x="60" y="211">人民公园</text><text x="165" y="45">宽窄巷子</text><text x="250" y="223">餐饮候选</text></svg></div><article class="place-detail"><span class="badge">当前浏览</span><h3>${esc(p.name)}</h3><p>${esc(p.description)}</p><p class="muted">${esc(p.verification)}</p><div class="actions">${btn('讨论这里', 'discuss', `data-place="${p.id}" class="primary"`)}${p.id !== 'food' ? btn('记下这里，日期未定', 'remember', `data-place="${p.id}"`) : ''}</div></article><section class="route-box"><h3>怎么过去</h3><p class="muted">起点需要明确。浏览位置不等于你的位置。</p><label for="origin">选择出发点</label><select id="origin"><option value="">尚未选择</option><option>从酒店出发（示例）</option><option>从另一个地点出发（示例）</option></select><div class="actions">${btn('查询路线', 'route')}</div><p class="muted">这里只演示交互，不提供真实距离、ETA或持续导航。</p></section>`;
  $('fail-save').checked = state.failNextSave; $('fail-weather').checked = state.weatherUnavailable; $('fail-route').checked = state.routeUnavailable;
  $('debug').textContent = `当前安排版本 ${state.trip.version} · 待采用建议 ${state.candidate ? '1' : '0'} · 保存的打算 ${active.length} · 原型固定日期 2026-10-21（Asia/Shanghai）`;
}
document.addEventListener('click', event => {
  const pageButton = event.target.closest('button[data-page]');
  if (pageButton) { dispatch({ type: 'PAGE', page: pageButton.dataset.page }); return; }
  const b = event.target.closest('[data-action]'); if (!b) return;
  const a = b.dataset.action;
  if (a === 'day') dispatch({ type: 'DAY', date: b.dataset.date });
  else if (a === 'browse') dispatch({ type: 'BROWSE', placeId: b.dataset.place });
  else if (a === 'discuss') dispatch({ type: 'DISCUSS', placeId: b.dataset.place });
  else if (a === 'remember') dispatch({ type: 'SEND', text: `记下${places[b.dataset.place].name}，日期没定。`, id: crypto.randomUUID() });
  else if (a === 'undo') dispatch({ type: 'UNDO', id: b.dataset.id });
  else if (a === 'clear') dispatch({ type: 'CLEAR_FOCUS' });
  else if (a === 'focus-day') { dispatch({ type: 'FOCUS_DAY' }); $('message').focus(); }
  else if (a === 'plan-day') { dispatch({ type: 'FOCUS_DAY' }); dispatch({ type: 'SEND', text: `帮我安排${state.day}，人民公园想去，${state.day === state.trip.free.date ? '15:00—16:00留白，' : ''}别太满。`, id: crypto.randomUUID() }); }
  else if (a === 'propose') { dispatch({ type: 'PROPOSE' }); }
  else if (a === 'continue') { dispatch({ type: 'CONTINUE' }); $('message').focus(); }
  else if (a === 'explore') dispatch({ type: 'PAGE', page: 'explore' });
  else if (a === 'route') { if (!$('origin').value) { $('errors').textContent = '请先明确出发点，不会把浏览地点当成你的位置。'; return; } dispatch({ type: 'ROUTE' }); }
  else dispatch({ type: ({ accept: 'ACCEPT', reject: 'REJECT', retry: 'RETRY' })[a] });
});
$('composer').addEventListener('submit', event => { event.preventDefault(); const text = $('message').value; if (!text.trim()) return; dispatch({ type: 'SEND', text, id: crypto.randomUUID() }); $('message').value = ''; });
document.addEventListener('submit', event => { if (!event.target.matches('[data-edit]')) return; event.preventDefault(); const data = new FormData(event.target); dispatch({ type: 'EDIT', id: event.target.dataset.edit, time: data.get('time'), duration: data.get('duration') }); });
$('message').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); $('composer').requestSubmit(); } });
$('new-chat').addEventListener('click', () => dispatch({ type: 'NEW_CHAT' }));
$('reset').addEventListener('click', () => dispatch({ type: 'RESET' }));
$('external-change').addEventListener('click', () => dispatch({ type: 'EXTERNAL_CHANGE' }));
for (const [id, key] of [['fail-save', 'failNextSave'], ['fail-weather', 'weatherUnavailable'], ['fail-route', 'routeUnavailable']]) $(id).addEventListener('change', event => dispatch({ type: 'SETTING', key, value: event.target.checked }));
$('samples').innerHTML = samples.map((s, i) => `<button data-sample="${i}">${esc(s)}</button>`).join('');
$('samples').addEventListener('click', event => { const b = event.target.closest('[data-sample]'); if (!b) return; $('message').value = samples[Number(b.dataset.sample)]; $('message').focus(); });
render();
