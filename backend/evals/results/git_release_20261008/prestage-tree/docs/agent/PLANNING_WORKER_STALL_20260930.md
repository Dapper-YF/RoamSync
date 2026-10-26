# Planning worker stall incident (2026-09-30)

## Evidence

- VERIFIED: one planning run remained in `researching` at `research_model` after
  destination web search and weather lookup had completed. Its progress message
  said it was waiting for the model's streamed response.
- VERIFIED: a second run for the same trip stayed `queued` while the single
  worker awaited that first graph execution. The first and second runs later
  failed with `planner_research_incomplete_output`; neither produced a revision.
- VERIFIED: the configured provider call timeout was 180 seconds with 2 SDK
  retries. The worker awaited each run serially, so a slow or incomplete stream
  occupied its only execution slot for several minutes. API status polling
  continued to return 200; this was not a frontend polling or database outage.
- INFERRED: the long wait was in the BigModel/GLM destination-research
  completion path. The persisted trace does not distinguish provider latency,
  stream completion delay, or the individual SDK retry attempts.

## Changes

- Bound model calls to 90 seconds with no automatic SDK retry by default; an
  operator may configure at most one retry.
- Bound the complete planning execution to 360 seconds. Expiry records
  `planning_run_timeout`, completes the run as failed, and exits the worker task
  so its lease is released.
- Run two independently claimed jobs concurrently, so one slow provider call
  does not block the entire queue.
- Use low reasoning effort for destination research; planning retains its own
  configured reasoning effort.
- Record `started_at` when the worker first claims a run.

## Verification

- VERIFIED: focused runtime-deadline, worker-concurrency, and destination
  research tests passed (3 passed).
- VERIFIED: Compose API and agent-worker were rebuilt and started; API health
  returned 200, API/Web/PostgreSQL were healthy, and the worker was running.
- VERIFIED: the running worker loaded concurrency 2, run deadline 360 seconds,
  model timeout 90 seconds, 0 retries, and low research reasoning effort.
- LIMITATION: no fresh paid/remote model request was made to measure provider
  latency after deployment. The reliability controls are locally exercised and
  deployed; they cannot guarantee that an external provider returns a useful
  plan.
