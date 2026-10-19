# Formal itinerary write protection — stage 1

Scope: existing dated Trip/Activity writes and candidate acceptance only. Isolated
worktree `E:/Study/RoamSync-write-protection-20261019`, branch
`codex/formal-write-protection-20261019`, base `25a62cb`. No spike schema/code,
frontend, Android, Planner context, production migrations or deployment imported.

## Root cause and red evidence

The actual manual-add API returned201 without changing Trip.version. The old
PlanRevision therefore passed Accept's base-version check, returned200 and
removed the newly-added Activity. `red.xml` records this as a failed regression
expecting409, including `added_survives: false`. The larger pre-fix matrix has
6 failures/1 pass: delete/move/order/route lacked the common version fence, while
the old update path already advanced Trip.version. A no-op update also advanced
the formal version unnecessarily. `red-metadata.xml` separately proves two
concurrent Trip updates both returned200 from the same version and ended at2.

## Minimal implementation

`app/formal_write.py` provides transaction-local protection, not a business
object/workflow. Existing committing manual commands acquire Trip before child
rows, compare an optional client Trip version (or the version observed before
waiting), inspect the before/after semantic state, advance Trip.version once if
the formal result changed, and roll back on failure. Existing Activity version
checks remain; indirectly changed Activity rows also advance their own versions.
No persistent snapshot table, request platform, schema migration or PlanningRun
is added for ordinary edits.

The transient comparison is linear in the Trip's activities/routes and requires
additional SQL reads. It ignores Activity timestamps/versions, regenerated route
row IDs and route calculation timestamps when detecting formal semantic change.
It retains names, notes, ordering, time, decision provenance, route mode/geometry
and other actual fields. A note update still retains the existing Activity-level
version increment even when its normalized value is unchanged; Trip.version does
not advance merely because Activity metadata advanced.

## Audited write paths

| Path | Shared protection / version policy |
|---|---|
| add/delete/update/move/order Activity | Existing service commands wrapped; Trip lock before Day/Activity; one semantic Trip increment |
| route recalculation API | New small committing wrapper protects the existing algorithm; algorithm intentionally unchanged |
| indirect time/order changes | Changed surviving Activity rows increment if the original command did not already increment them |
| Trip metadata/date update/archive | Trip lock then existing expected-version checks; no-op metadata/repeated archive avoid needless increments |
| whole-Trip deletion | Dependent AssistantSession locks before Trip, matching assistant action order, then existing cascade |
| Accept | Trip before Revision/Run/Preferences and child mutation; base version, final Validator and accepted-revision replay preserved |
| create/save/reject candidate | Trip precedes potentially shared child locks/FK writes; candidate work itself does not advance Trip.version |
| Draft promotion | Operation remains authorization owner, then Trip before Revision/Run; capability/content checks unchanged |
| Requirement/Preferences updates | Trip before Preferences; independent Preferences version preserved, no automatic Trip increment; Accept revalidates current requirements |
| assistant requirements/reschedule | Common parent-first order; existing reschedule version and signature check retained |
| execution/experience/navigation observations | Only adjacent lock order adjusted before child writes/recovery; no execution workflow or itinerary-version policy change |
| reads/provider cache/run progress/rejection | Do not advance formal Trip.version merely for being accessed or recorded |

Why the adjacent lock-only changes are necessary: Activity deletion can update
PlanningRun.selected_activity_id through an FK. Holding Run before waiting for
Trip can deadlock with a manual writer holding Trip then deleting that Activity.
Runtime observations/recovery can likewise lock Navigation/Execution/Run while
Accept supersedes them. Taking the common Trip first closes these inversions;
Draft promotion still takes its authorization operation first. No new agent
authority or business path is introduced.

## API compatibility and retry contract

Existing request bodies, endpoint paths, response bodies and Activity version
fields are retained. Manual endpoints add optional positive `X-Trip-Version`.
A mismatch returns409 `detail.code=trip_version_conflict`. Headerless clients
retain sequential operation-on-current-state semantics. A writer that observed
a version before waiting is rejected if another semantic write committed first.

Without a client version/idempotency identity it is impossible to identify every
old UI submission as stale or replay the exact original HTTP response. In
particular a headerless *later* reorder cannot be distinguished from a deliberate
new reorder. Clients requiring stale-page protection should supply the header;
Activity update/move retain their existing mandatory Activity version too.
This limitation is explicit, not a silent reinterpretation of old requests.

Retries do not duplicate effects: repeated addition of the same place remains409
with one Activity; old-version update/move remains409; repeated delete remains404;
absolute order/recalculation does not create duplicate activities; replaying the
same accepted revision remains200 without another formal write. No promise of
exactly-once HTTP-response replay is added. After response loss, read current
state rather than manufacture a new operation or blindly regenerate a plan.

## PostgreSQL evidence

`tests/test_formal_write_protection.py` contains27 dedicated cases. They exercise
the actual HTTP interfaces and PostgreSQL transactions; only external route data
is a deterministic fixture. Races use distinct database sessions and verify
actual PostgreSQL lock waiters, not just Python sleeps.

- Manual add/delete/move/order/update/route invalidate old candidates.
- Both ordering directions of manual edit versus Accept return an explicit loser.
- Two concurrent Activity edits and opposing cross-day moves do not lose a
  successful write or deadlock; concurrent metadata updates produce200/409.
- Delete of an Activity referenced by Run.selected_activity_id races Accept
  without FK lock inversion.
- Six manual-operation fault injections roll back activities/routes/versions;
  Accept failure retains pending revision and original formal result.
- Concurrent/replayed Accept applies once; add replay does not duplicate.
- Indirect Activity changes invalidate old activity forms; no-op/read and repeated
  identical route facts do not needlessly advance Trip.version.
- Preferences changes retain their separate version; concurrent updates conflict,
  and a new daily time window is revalidated when accepting an old candidate.

Evidence in `docs/evidence/write-protection/`: red/green XML and logs, full XML,
plus final source/test manifest in verification.json. Full Windows/Python3.14.3
regression: **1269 passed, 1 skipped**,114.010s, includes27 dedicated tests.
The skipped test is the unrelated place-content concurrent-favorite test whose
guard requires database name `roamsync_test` exactly. Promotion tests run against
a separate `promotion_test` inside the SAME dedicated test container.
Linux/Python3.11.16 test-image regression: **1269 passed, 1 skipped**,80.973s,
with the same skip reason, recorded in linux-full.xml. This reused test image
ran against the dedicated PostgreSQL container, not a production database.
No real model validation was performed and no new product experience is claimed.

## Remaining boundaries

- Existing route recalculation still tightens intentional free time. Only its
  writes are now protected; query/time separation is the next stage.
- Relation storage, mixed precision, Planner visibility and chat product changes
  remain entirely unimplemented here.
- Parent locking can increase contention, especially while old commands await a
  map provider or bound chat holds a transaction. No claim of low-latency behavior
  under production load. The next route-separation stage should shorten this.
- An extra exploratory test found that a bare Preferences.max_walking_minutes
  change is not universally rejected by existing Accept in its minimal scenario.
  That Validator/goal-coverage issue is unchanged; the unsuccessful probe is kept
  in focused-third.xml. The independent-version test uses the already-supported
  daily time window instead. This round does not expand constraint algorithms.
- Test/demo reset and database-direct writes are not ordinary formal edit APIs.
  They remain outside this protection contract.

Conclusion: stage1 write-protection code is ready for review/integration and the
route-query/time-write separation stage. It has NOT been merged into canonical
source or deployed. Production still requires integration of this isolated fix.


## Reproduction

The dedicated container is disposable and has no production data mount. To
recreate it after removal (requires the loopback port to be free):

```powershell
docker run -d --name roamsync-write-protection-pg --label roamsync.task=write-protection-20261019 --tmpfs /var/lib/postgresql/data -p 127.0.0.1:62678:5432 -e POSTGRES_USER=write_test -e POSTGRES_PASSWORD=write_test_only -e POSTGRES_DB=roamsync_test_write_protection postgres:17-alpine
# Wait until pg_isready succeeds, then from the isolated worktree:
powershell -File backend/scripts/run-write-protection.ps1 -Evidence rerun
powershell -File backend/scripts/run-write-protection.ps1 -Full -Evidence rerun-full
```

The helper checks container ownership and loopback binding, and only migrates
the isolated test database. It uses the canonical checkout's already-installed
venv as a runtime; no canonical source files are imported or modified. Recorded
red artifacts were collected before their corresponding app fixes; they are
historical counterexamples, not failures of the delivered revision. The
focused-third max-walking counterexample remains a separate known Validator
coverage limitation. Final focused/full XML describe the delivered behavior.
