# Latest Handoff

## A2 final measurement candidate — NO-GO (2026-10-23)

Product source is fixed at85d0bd5915a7d7168bf606b7f520fbae0ad6f237 in
E:/Study/RoamSync-reliability-a2-20261022, codex/reliability-a2-20261022.
Later commits import documentation/evidence only. BASE remains
f116ada6d6d46db7aeb48c29c8d5b45da379be00; previous combined6a65ece3 was never deployed.

Implemented A roots: detached planning snapshots; network outside business
transactions; Trip/preferences double CAS; unique Worker claims, fenced writes,
per-attempt checkpoint, conditional heartbeat/cleanup, bounded DB backoff;
atomic clarification answers/receipts and metadata preservation. B strict legacy
checkpoint migration and A typed409 restore original questions/answers and
require a new explicit request when unsafe. No migration or relaxed authority,
Validator, version, execution protection or Accept. Old/new Workers cannot mix.

B code received through523bbd7 (optional compatibility + old checkpoint migration),
with prepared recovery, immutable source authorization, independent day answers,
map identity bridge and compound source aggregation. C route continuity/blank-day
preview received. This is partial operation unification, not a single semantic
decision across all legacy paths. B's address bridge remains a conservative rule.

MEASURED final combined-full-5:1713 main +25 dedicated, zero failures/skips;
source unchanged. Source manifest hashc79ae375d4aa3ac01a8523275cc25712aef48596110fe9d49d898a1bfb33a4bb.
Web243/type/build passed, same inputs. API230 inputs and Web143 inputs/3 artifacts
match final source; build-only stopped containers do not prove runtime readiness.
API LF manifest584d075f687036f77023f9450ee8d600efcfe9cd4262e03539698a8dbe243a68.
Focused red/green and real PG takeover/checkpoint/Accept evidence retained;
counts overlap and cannot be added. A67 and B84 runtime/legacy checks pass.
B Astra independently approved exact85d0 fix, not entire system/release.
Full-2 source drift and full-4 actual optional failure remain preserved.

Final public Edge browser:4 complete input/SSE turns, confirmation, reload and
Trip page on fresh synthetic15435 DB/API18048/Web3048. Two real addresses/sources
are correct, but walking follow-up loses goals. Actual confirmed create produces
Trip1/Day1/Run1 and planner_requested_place_unresolved, zero Revision/Activity.
No actual candidate Accept/modify/503/409 full chain achieved. Root reload returns
free chat; Trip page preserves empty day/failure.1440/390/320 no overflow/pageerror.
API/Worker/Web owned process trees stopped after evidence; test data retained.
Final B public16 is7/16 versus baseline2/16, with2 critical unsupported walking
assurances. Not unseen reliability, no controlled global speed claim.

C sealed20 hash8bb1a83faa83659cf6ceb95745e29934922629012c176061b986dba23bef7da2
remains independent. SHA gate rejected initial DB readiness after A docs-only HEAD
advance; no question call occurred. C now uses exact85d0 own clean worktree/fresh
DB for one measurement. Result pending; do not claim quality gate passed.

Official HEAD6b298caddb79125991bfc5183ddeefc09029f31c and3133 original files,
ignored env and container IDs/images remain unchanged. External runtime outage
left all four official containers exited255. A did not stop/start/redeploy official
services or write/migrate/clean official DB; latest verification does not connect
to DB. A test-container start was policy denied; different already-running
synthetic PG used, no bypass. Original README/Nginx/untracked work preserved.
Public owner/Trip/session isolation P0, provider cancellation, repeated decisions
and unsupported assurance remain OPEN. Four gates still required; NO deployment.
Full report:docs/ENGINEERING_A2_RELIABILITY_20261023.md.

## Reproduction and next decision

Run scripts/run-isolated-tests.py with a new output folder; it creates unique
tmpfs databases and source-bound evidence. Never point tests/migrations at15432.
verify-release.py --allow-stopped is build-only; verify-backup.py restores only
in its own network=none/tmpfs container. Prior32-table backup recovery passed,
but no new production dump or database fingerprint was made during this round.

Receive C aggregate and scoped evidence without exposing sealed questions to B.
Freeze product code throughout measurement; any subsequent code changes require
fresh source-bound regression and independent questions. Product release remains
blocked even if engineering tests pass. A owns final compatibility/integration;
no automatic deployment and no Obsidian record.
