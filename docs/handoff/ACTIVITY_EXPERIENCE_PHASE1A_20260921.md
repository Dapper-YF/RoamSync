# Activity Experience Phase 1A

Date: 2026-09-21  
Status: VERIFIED — completed and bounded to the Activity Experience Fact Layer.

## Decision and scope

Phase 1A records two user-owned facts for the current activity without changing
formal itinerary duration or starting a replan: `user_extend_stay` and
`user_leave_early`. It deliberately does not model fatigue, interest, mood,
priority, disruption, recovery planning, or automatic plan changes.

`TravelEvent` remains the event store. No separate experience-event table was
introduced. `client_action_id` is nullable for historical rows and is unique at
the database level per `(trip_execution_id, client_action_id)` when supplied.

## Implemented contract

- `POST /api/v1/activity-executions/{id}/extend-stay`
  accepts `client_action_id`, positive `extension_minutes` (maximum 480), an
  optional reason, and an optional `expected_itinerary_version`. It permits
  only the current `arrived` or `in_progress` activity, persists
  `user_extend_stay`, and returns the derived cumulative extension and projected
  end.
- `POST /api/v1/activity-executions/{id}/leave-early`
  permits only the current `in_progress` activity, persists
  `user_leave_early`, applies the existing completion state semantics, and
  advances the current activity. It does not modify `Activity.duration_minutes`
  or treat the activity as abandoned.
- Repeating the exact command returns a replay response; reusing the same
  client action identifier for a different command or payload returns a
  conflict. Row locking and the partial unique index protect concurrent calls.
- `GET /api/v1/trips/{trip_id}/execution-progress` now exposes optional
  `current_activity_experience`: planned duration, actual start/end, elapsed
  experience minutes, total extensions, and a derived projected end. Projected
  end is `actual_started_at + planned duration + valid extension total`; it is
  never stored and is null before start or after completion.

Malformed historical `TravelEvent.details` values are ignored when deriving
extension totals. This makes the read path resilient without retroactively
mutating historical facts.

## Code and migration evidence

- `backend/app/database.py`: nullable `TravelEvent.client_action_id`; allowed
  event types include the two Phase 1A facts.
- `backend/migrations/versions/20260921_0026_activity_experience_events.py`:
  adds the field, partial unique index, and updated check constraint.
- `backend/app/trip_execution_service.py`: command validation, idempotency,
  dynamic extension aggregation, projected timing, and existing completion
  state reuse.
- `backend/app/navigation/execution_read_model.py`: read-model projection only;
  it does not create events or make planning decisions.
- `backend/tests/test_trip_execution.py`: arrived/in-progress behavior,
  idempotency/conflicts, planned-duration immutability, leave-early completion,
  invalid state/version rejection, and concurrent replay coverage.

## Verification

VERIFIED on 2026-09-21 using the isolated Linux/PostgreSQL suite:

`docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test`

Result: `282 passed, 2 warnings in 18.44s`. The warnings are existing FastAPI
deprecation warnings. PostgreSQL duplicate-key messages in the log are expected
assertions from pre-existing concurrency tests; the suite completed successfully.

## Deliberate non-goals / next boundary

No `PlanningRun`, `PlanRevision`, Slack, ETA, navigation observation, or
disruption code consumes these new facts yet. There is no user state model or
automatic replanning trigger. Those are later-phase decisions, not implicit
behavior of Phase 1A.
