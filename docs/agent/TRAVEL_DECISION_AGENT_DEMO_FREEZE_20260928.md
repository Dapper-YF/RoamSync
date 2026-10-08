# RoamSync Demo Freeze / Rehearsal Report

Date: 2026-09-29  
Status: **Travel Decision Agent Demo NOT READY**

## Demo Status

The freeze gate is incomplete. Infrastructure preflight and reset passed, and backend regression passed on the final narrow parser fix. The required five consecutive live UI rehearsals did not complete: the final-code tally is **0/5** because the user asked to stop while the first request was still planning. No readiness claim is made.

Earlier cycles on prior parser builds are historical only and do not count toward the final tally. Three such cycles reached the second pending revision, with exact rejection feedback, one retrieved Memory item, and unchanged formal itinerary. A later assistant paraphrase still produced a false activity clarification, which prompted the final parser correction. The user then stopped further rehearsals.

## Frozen Architecture

Goal-Aware Planning, Decision Context Engine, Decision Memory, Activity Decision Semantics, and Agent Reliability MVP remain the frozen scope. Planner output stays a reviewable `PlanRevision`; explicit user approval and transactional revalidation remain required before formal changes.

Decision Ledger MVP remains OPEN, Stage 2.2 remains OPEN, and Ledger stays in shadow mode. Stage 2.3 Trade-off Intelligence, Critic, Reflection, Long-term Memory, Preference Learning, Multi-Agent, new Recovery, and new navigation work were not started.

Provider remains GLM `glm-5.3-flash`, high reasoning, streaming, 180-second timeout. No provider or model change was made.

## Demo Trip

- Trip: `00000000-0000-4000-8000-000000000003`
- Target day: `2026-10-20`
- Final reset: VERIFIED — Trip.version 1, 5 activities, 4 route legs, no pending/rejected revisions, no Memory, no assistant sessions, no executions.
- China Academy of Art remains `must_do`, `can_skip=false`, minimum duration 60 minutes in the reset baseline.

## First Request

```text
请帮我调整 2026-10-20 当天的行程。

我希望轻松一点，
尽量少走路，
18:00 前结束，
现有活动尽量不要大改。
```

## First Revision

No first Revision from the final parser build was completed and captured after the user stopped the rehearsal. On earlier builds, real UI candidates passed the hard Goal checks and remained pending before rejection; these results are excluded from the final-code tally.

## Reject Feedback

Required UI flow: reason `too_rushed`, exact text `五项活动仍显得紧凑，希望多留休息与停留时间。`. The feedback field is located by its accessible label `补充拒绝原因`. Prior-build API evidence confirmed exact text persistence. Final-code rehearsal evidence is not yet available.

## Decision Memory

Prior-build cycles displayed one real Memory item in UI and API (`count=1`, visible to Planner) sourced from the same Trip/day rejection. This evidence is historical and excluded from the final tally. Do not resend the feedback in the second prompt.

## Second Revision

No second Revision from the final parser build was captured. Earlier candidate output varied by run (including 4 or 5 activities); the acceptance boundary stayed pending and formal Trip state remained unchanged. Candidate variability alone is not a reason to expand scope.

## Activity Semantics

Reset validation confirms the must-do activity and its 60-minute minimum. The 0/5 final tally means its preservation in a final-code second candidate has not been re-established during this freeze phase.

## Goal Check

Earlier real candidates showed UI checks for end-before-18:00 and max walking 80 minutes. A prior-build second candidate ended 16:07 with 61 walking minutes and 4 activities; another ended 17:59 with 61 minutes and 5/5 preserved. These are examples of run variability, not final-code results.

## Entity Resolution

The final backend-only correction filters observed plan-meta fragments from protected-activity parsing while retaining clarification for genuinely unknown place names. The added regression cases cover the observed paraphrases. No schema, graph, tool, provider, Planner, or Ledger change was made.

## Five Rehearsals

Final code: **0/5 complete**. Rehearsal halted at the user's request during the first live request, then the fixed demo Trip was reset. Do not label the phase complete or READY.

## Timing

Timing samples from earlier builds were not accepted as final-code measurements. Planning may take roughly 1–3 minutes per request in observed runs. One assistant request showed HTTP 504 while its PlanningRun later reached a pending Revision; inspect run state before any UI resend. No mock candidate fallback was used.

## Reset

Run from the repository root:

```powershell
.\scripts\reset-travel-decision-demo.ps1
```

Latest output: `RESET VALIDATION PASS` with version 1, 5 activities, 4 route legs, zero pending/rejected revisions, zero Memory, zero sessions, and zero executions.

## Preflight

Run:

```powershell
.\scripts\demo-preflight.ps1
```

Latest preflight passed backend, frontend, Postgres, Tavily, AMap POI, AMap Route, GLM, and agent worker, ending in `DEMO READY`. This is infrastructure readiness only; the overall Demo remains NOT READY until its rehearsal and final frontend gates pass.

## Regression

- Final Linux/PostgreSQL backend: **395 passed, 2 existing Starlette deprecation warnings**, 46.92 seconds.
- Focused parser regression: passed.
- Web: prior verified result was 100 tests; typecheck and production build passed before the latest backend-only parser changes. They were not rerun after that change, at the user's request to stop testing.

## Known Limitations

- Five consecutive final-code UI rehearsals remain outstanding.
- Web tests, typecheck, and production build require a final run after the latest backend change.
- Assistant timeout can precede completion of a PlanningRun; verify run state before resending.
- Do not infer Ledger validity or model rationale while Ledger is unavailable/invalid in shadow mode.

## Exact Demo Steps

1. Run preflight and reset; confirm the five baseline activities and must-do semantics.
2. Open the fixed Trip and submit the first request exactly as written above.
3. Wait for a pending candidate and show Goals, Context, route/walking evidence, and Activity Semantics.
4. Reject through the UI with `行程太赶` / `too_rushed` and the exact feedback above; verify it persisted and formal Trip stayed unchanged.
5. Submit only this second request:

```text
请再调整一次 2026-10-20 当天的行程，
节奏轻松一点，
尽量少走路，
18:00 前结束，
现有活动尽量不要大改。
```

6. Show the retrieved Memory text and the second pending Revision in UI/API. Never Accept during rehearsal.
7. After all five consecutive cycles, reset once more and rerun the required frontend gates before changing status to READY.

## Stage Achievement

“RoamSync 已经从‘现实变化后重新规划行程’，推进到‘围绕用户 Goal、当前 Context、历史反馈和 Activity Semantics 持续做旅行规划’。”
