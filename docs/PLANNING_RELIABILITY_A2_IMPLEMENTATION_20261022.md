# A2 short transaction implementation plan

User approved the design on 2026-10-22. Execute inline using superpowers:executing-plans.
Spec: docs/PLANNING_RELIABILITY_A2_DESIGN_20261022.md.

Goal: close read sessions before semantic/map requests, then lock Trip and Preferences/Run and reject stale facts before deterministic persistence. Preserve authorization, Validator, versions, Accept and recovery uniqueness. No production writes or deployment. Do not read C's sealed questions.

## 1. Creation boundary

Files: app/planning_preparation.py (new), app/planning_run_repository.py, tests/test_planning_transactions.py, all under backend. Consume B's planning_intent_service snapshot helpers.

- [ ] Retain valid red tests: a paused provider probes select(Trip).with_for_update(nowait=True) through another connection; Event-controlled editors change itinerary or preferences before provider completion.
- [ ] Define frozen PreparedPlanningIntent(trip_id, user_request, entry_point, selected_day_id, selected_activity_id, base_trip_version, preferences_version, draft). prepare_planning_intent(session, trip_id, payload, *, semantic_provider=None) reads snapshot and preference version in one independent short session, closes it, then resolves without session.
- [ ] create_planning_run(..., prepared_intent=None) binds prepared input to payload; locks Trip then Preferences and compares both versions. Ground only with approved draft. Network preparation requires an inactive caller transaction; commit=False callers provide prepared intent or deterministic resolution. No implicit preferences repair commit.
- [ ] Verify no caller transaction during provider, stale Trip/preferences, wrong binding, provider cancellation/failure, and new-Trip commit=False rollback. Run existing planning/recovery/assistant suites. Commit explicit paths.

## 2. Route boundary

Files: backend/app/candidate_route_service.py, maps_service.py, planning_run_repository.py and tests/test_planning_transactions.py. Coordinate Graph boundary with B.

- [ ] Record paused map provider red tests; another connection probes Trip/Run locks and changes versions or cancels run.
- [ ] Freeze route inputs without ORM. Cache read/write each use short sessions. Network transport has no session. Preserve TTL, provenance, estimate restrictions, protected activities and structured errors.
- [ ] Prepare default revision routes before locks, then compare versions and run state. Preserve atomic enrich_routes=False/commit=False. Never commit/rollback caller writes to permit network.
- [ ] Verify concurrent saves, cancellations and stale refusal; run route, Validator, Accept, execution and recovery tests. Commit separately.

## 3. Worker recovery (after planning passes)

Files: backend/app/agent_worker.py, planning_progress.py, planning_runtime.py and A persistence boundary. Coordinate Graph writes with B.

- [ ] Enumerate every leased mutation; record two-worker test where old owner returns after reclaim. Verify it cannot refresh/clear new lease, save revision or mark failure. Include transient claim failure and shutdown.
- [ ] Unique claim identity and ownership checks for every mutation; bounded database backoff and observed task completion. Cleanup-only protection is not complete fencing.
- [ ] Run targeted and full regression; explicitly retain uncovered fencing boundaries as open rather than claim success.

## 4. Evidence and integration

- [ ] Run scripts/run-isolated-tests.py against committed source, relevant Web verification, hashes/JUnit/timings. Update handoff and architecture state with actual changes and open failures.
- [ ] Send frozen SHA/interfaces to B/C; review frozen commits and conflicts before integration. C executes sealed holdout only after freeze; A runs full real continuous browser acceptance. Review four gates before any deployment.
