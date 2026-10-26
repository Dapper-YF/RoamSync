# Activity Experience Phase 1B — Time Impact

Date: 2026-09-21  
Status: VERIFIED — deterministic read projection only.

## Generic core and navigation boundary

`backend/app/timeline_impact.py` is the source-neutral pure core. It receives
one authoritative current boundary timestamp, remaining formal stops, fixed
window flags, route durations, and the daily end. It returns projected
arrival/start/end, signed time shift, slack, fixed-window feasibility, and
day-end feasibility.

`backend/app/navigation/delay_impact.py` remains the navigation adapter. It
passes navigation ETA as the boundary and converts the generic signed shift to
the existing non-negative `delay_minutes` compatibility field. Navigation
observation ingestion, CAS, risk thresholds, detector behavior, disruption
identity, and recovery logic were not changed.

## Experience impact

`backend/app/activity_experience_impact.py` derives the boundary entirely from
persisted server facts:

- `in_progress`: `actual_started_at + formal duration + valid extensions`;
- `completed`: `actual_ended_at`;
- `arrived` without start: unavailable, with no invented duration estimate.

It compares this boundary with the formal current activity end
(`DayPlan.date + Activity.scheduled_time + Activity.duration_minutes`). The
resulting shift is signed: a late actual start plus extension is therefore a
total shift, while leave-early can be negative. It never edits formal activity,
route, or day data.

The service builds remaining same-day formal stops and uses the formal route
duration from the current activity to the first downstream activity. It returns
`none`, `absorbed`, `at_risk`, `infeasible`, or `unavailable` along with slack,
first impacted activity, fixed-window and day-end feasibility, and a projected
downstream schedule.

`GET /api/v1/trips/{trip_id}/execution-progress` now has optional
`experience_impact`. A live navigation session suppresses this field: navigation
ETA is the single authoritative boundary after actual departure, preventing an
activity shift from being added to the ETA a second time.

## Performance and persistence boundary

Migration `20260921_0027` adds
`ix_travel_events_activity_type(activity_execution_id, event_type)` for the
Phase 1A extension aggregation query. No aggregate is cached and Phase 1B adds
no TravelEvent, TripDisruptionEvent, PlanningRun, PlanRevision, or LLM call.

Migration `20260921_0028` records the formal itinerary version when a
`TripExecution` starts. If that version no longer matches `Trip.version`, the
experience-impact adapter returns `unavailable` rather than silently projecting
an execution context against a changed formal itinerary.

## Verification

- Pure-core regression tests cover signed shift, fixed appointment, day end,
  and negative/early boundary behavior in `backend/tests/test_timeline_impact.py`.
- Existing navigation delay/event tests continue through the adapter.
- Docker Linux/PostgreSQL full suite:
  `286 passed, 2 warnings in 19.13s` using
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test`.

## Phase 1C entry point

Phase 1C may decide whether an `experience_impact` projection should become a
general replanning trigger. That phase must consume this projection rather than
reinterpret raw extension events, and must define policy/confirmation before it
creates planning work. Phase 1B intentionally stops before that decision.
