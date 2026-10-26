import test from 'node:test';
import assert from 'node:assert/strict';
import { initialState, reduce, TOMORROW } from './model.mjs';
const send = (s, text, id = text) => reduce(s, { type: 'SEND', text, id });
const intention = '我明天下午去人民公园，几点再说。';
const focusDay = s => reduce(s, { type: 'FOCUS_DAY' });
const proposal = s => send(focusDay(s), '帮我安排第二天，人民公园想去，别太满。');
test('T01 knowledge and tentative exploration create no intention or candidate', () => {
  for (const text of ['成都人为什么喜欢喝茶？', '先随便看看，不用安排', '如果我明天下午去人民公园会怎样？', '人民公园和宽窄巷子哪个更适合慢慢逛？']) {
    const s = send(initialState(), text); assert.equal(s.intents.length, 0); assert.equal(s.candidate, null); assert.equal(s.trip.version, 1);
  }
});
test('T02 explicit intention anchors date without clock, duration or Trip creation', () => {
  const s = send(initialState(), intention); assert.equal(s.intents.length, 1); assert.equal(s.intents[0].date, TOMORROW); assert.equal(s.intents[0].period, '下午'); assert.equal(s.intents[0].time, undefined); assert.equal(s.trip.version, 1); assert.equal(s.messages.at(-1).kind, 'saved');
});
test('T03 duplicate message and repeated expression do not duplicate records', () => {
  let s = send(initialState(), intention, 'message-1'); s = send(s, intention, 'message-1'); s = send(s, intention, 'message-2'); assert.equal(s.intents.length, 1);
});
test('T04 failed save is not acknowledged as saved, retry retains identity', () => {
  let s = reduce(initialState(), { type: 'SETTING', key: 'failNextSave', value: true }); s = send(s, intention, 'pending-1'); assert.equal(s.intents.length, 0); assert.equal(s.retry.id, 'pending-1'); assert.equal(s.messages.at(-1).kind, 'save-error'); s = reduce(s, { type: 'RETRY' }); assert.equal(s.intents[0].id, 'pending-1'); assert.equal(s.retry, null); s = reduce(s, { type: 'RETRY' }); assert.equal(s.intents.length, 1);
});
test('T05 reload serialization and new conversation retain saved records and clear focus', () => {
  let s = JSON.parse(JSON.stringify(send(initialState(), intention))); s = reduce(s, { type: 'NEW_CHAT' }); assert.equal(s.intents[0].date, TOMORROW); assert.equal(s.focus, null); assert.equal(s.messages.length, 1);
});
test('T06 proposing affects only candidate, accept preserves booking and free time', () => {
  let s = initialState(); const trip = structuredClone(s.trip); s = proposal(s); assert.deepEqual(s.trip, trip); assert.equal(s.candidate.date, '2026-11-03'); s = reduce(s, { type: 'ACCEPT' }); assert.equal(s.trip.activities.length, 2); assert.deepEqual(s.trip.activities[0], trip.activities[0]); assert.deepEqual(s.trip.free, trip.free); assert.equal(s.trip.version, 2);
});
test('T07 continuing discussion retains exact candidate, rejection only removes suggestion', () => {
  let s = proposal(initialState()); const c = structuredClone(s.candidate); s = reduce(s, { type: 'CONTINUE' }); assert.deepEqual(s.candidate, c); assert.equal(s.focus.date, c.date); s = reduce(s, { type: 'REJECT' }); assert.equal(s.candidate, null); assert.equal(s.trip.version, 1);
});
test('T08 stale accept cannot overwrite a later version', () => {
  let s = proposal(initialState()); s = reduce(s, { type: 'EXTERNAL_CHANGE' }); const trip = structuredClone(s.trip); s = reduce(s, { type: 'ACCEPT' }); assert.deepEqual(s.trip, trip); assert.equal(s.candidate.stale, true); assert.match(s.error, /过期/);
});
test('T09 browsing does not silently change discussing place, ambiguous reference clarifies', () => {
  let s = reduce(initialState(), { type: 'DISCUSS', placeId: 'park' }); s = reduce(s, { type: 'BROWSE', placeId: 'alley' }); s = send(s, '这里怎么样？'); assert.equal(s.focus.placeId, 'park'); assert.equal(s.messages.at(-1).kind, 'ambiguous'); assert.equal(s.intents.length, 0);
});
test('T10 weather and route failures make no factual claims or itinerary writes', () => {
  let s = reduce(initialState(), { type: 'SETTING', key: 'weatherUnavailable', value: true }); s = send(s, '明天会下雨吗？'); assert.match(s.messages.at(-1).text, /没有取得天气/); s = reduce(s, { type: 'SETTING', key: 'routeUnavailable', value: true }); s = reduce(s, { type: 'ROUTE' }); assert.match(s.notice, /没有生成距离/); assert.equal(s.trip.version, 1);
});
test('T12 undated explicit intention remains undated and can be revoked', () => {
  let s = send(initialState(), '记下人民公园，日期没定。'); assert.equal(s.intents[0].date, null); s = reduce(s, { type: 'UNDO', id: s.intents[0].id }); assert.equal(s.intents[0].status, 'cancelled'); assert.equal(s.trip.version, 1);
});
test('T13 direct edit protects bookings and deliberate free time', () => {
  let s = reduce(proposal(initialState()), { type: 'ACCEPT' }); s = reduce(s, { type: 'EDIT', id: 'park-activity', time: '14:30', duration: 90 }); assert.match(s.error, /留白/); assert.equal(s.trip.version, 2); s = reduce(s, { type: 'EDIT', id: 'booking', time: '09:00', duration: 30 }); assert.match(s.error, /预约/); s = reduce(s, { type: 'EDIT', id: 'park-activity', time: '12:30', duration: 90 }); assert.equal(s.trip.version, 3); assert.equal(s.trip.activities.at(-1).time, '12:30');
});
test('unscoped planning asks for a target and never silently selects a Trip', () => {
  const s = send(initialState(), '帮我安排第二天'); assert.equal(s.candidate, null); assert.equal(s.trip.version, 1); assert.equal(s.messages.at(-1).kind, 'scope');
});
test('proposal respects the selected date instead of hardcoding the second day', () => {
  let s = reduce(initialState(), { type: 'DAY', date: '2026-11-04' }); s = send(focusDay(s), '帮我安排2026-11-04，人民公园想去，别太满。'); assert.equal(s.candidate.date, '2026-11-04'); assert.doesNotMatch(s.messages.at(-1).text, /上午的预约|15:00/);
});
