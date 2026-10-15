# Travel Decision Agent Demo Checklist

**Current status: NOT READY.** Final-code five-rehearsal tally is 0/5; the user stopped further rehearsals. The trip was reset cleanly.

1. Docker Compose running.
2. `.\scripts\demo-preflight.ps1` → `DEMO READY`.
3. `.\scripts\reset-travel-decision-demo.ps1` → `RESET VALIDATION PASS`.
4. Open `http://127.0.0.1:3000/trips/00000000-0000-4000-8000-000000000003`.
5. Show five activities and China Academy of Art: 必去、至少 60 分钟.
6. Submit the fixed first request; show Goal, candidate, Goal Check and semantics.
7. 暂不采用 → `too_rushed` → paste the fixed feedback and confirm rejection.
8. Submit the fixed second request without repeating the feedback.
9. Show retrieved Memory text and the second pending revision.
10. Stop before Accept; point out the user confirmation boundary.

If the assistant shows HTTP 504, inspect PlanningRuns before resending. A run may still complete and leave a pending revision.
