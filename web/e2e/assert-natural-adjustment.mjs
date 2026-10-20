import assert from 'node:assert/strict';

// Check user requirements, not one preferred solution. An earliest start is
// not an exact start or an instruction to keep the previous visit order.
export function assertNaturalAdjustment(final) {
  const day = final.days.find(d => d.activities.some(a => a.name.includes('博物院')));
  const museums = day.activities.filter(a => a.name.includes('博物院'));
  assert.equal(museums.length, 1, 'duplicate museum');
  const museum = museums[0];
  const appointment = day.activities.find(a => a.schedule_locked && a.scheduled_time === '14:00:00');
  assert(appointment && appointment.duration_minutes === 60, 'fixed appointment changed');
  const minute = value => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5));
  assert(minute(museum.scheduled_time) >= 750, 'museum before earliest start');
  assert(museum.duration_minutes >= 5 && museum.duration_minutes <= 110, 'unauthorized duration');
  const ordered = [...day.activities].sort((a, b) => a.scheduled_time.localeCompare(b.scheduled_time));
  for (let n = 1; n < ordered.length; n++) {
    const a = ordered[n-1], b = ordered[n];
    const leg = day.route_legs.find(l => l.from_activity_id === a.id && l.to_activity_id === b.id);
    assert(leg && !leg.is_estimated && leg.provider.startsWith('AMap'), 'actual route evidence missing');
    assert(minute(a.scheduled_time) + a.duration_minutes + leg.duration_minutes <= minute(b.scheduled_time), 'route/appointment conflict');
  }
  return museum;
}
