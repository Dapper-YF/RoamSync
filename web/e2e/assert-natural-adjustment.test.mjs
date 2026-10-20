import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { assertNaturalAdjustment } from './assert-natural-adjustment.mjs';

const saved = JSON.parse(readFileSync(new URL('../../docs/evidence/natural-closure-20261020/late-start-accepted-counterexample.json', import.meta.url), 'utf8')).state;
test('accepts actual 39-minute route and a full museum visit after the fixed appointment', () => assertNaturalAdjustment(saved));
test('rejects 110 minutes before the fixed appointment when the real route cannot fit', () => {
  const state = structuredClone(saved);
  state.days.flatMap(d => d.activities).find(a => a.name.includes('博物院')).scheduled_time = '12:30:00';
  assert.throws(() => assertNaturalAdjustment(state));
});
test('rejects estimated routes even when the times look plausible', () => {
  const state = structuredClone(saved);
  state.days.flatMap(d => d.route_legs).forEach(l => { l.is_estimated = true; });
  assert.throws(() => assertNaturalAdjustment(state));
});
