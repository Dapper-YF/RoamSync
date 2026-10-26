# RoamSync parallel closeout and official-workspace acceptance

## Authorization and status

2026-10-26: user explicitly requested separate conversations for parallel work,
and integration into E:/Study/RoamSync before formal acceptance. This supersedes
the earlier exclusion of official-source integration. Production database writes,
production deployment and existing user-work deletion remain outside scope.

Overall NO-GO. Batch1/2 reached limited exits, batch3 is incomplete. The shared
starting checkpoint is development WIP, not a passing baseline or freeze.
Latest exploratory backend run: 2164 tests, 13 failures, 40 skipped. Eleven
failures involve fake snapshot rows without required fields; two involve
duration/count classification and compound opening-time task classification.
No new sealed score or complete fresh browser chain exists.

## Parallel ownership

All workers branch from one exact WIP commit in separate worktrees. No worker
edits another worktree or the official directory. Product and evidence commits
must be separate; reports retain failures and distinguish static/unit/live.

| Lane | Owned scope | Deliverable |
|---|---|---|
| A candidates | conversation_candidate/*, companion_state.py; source/identity/window candidate tests | Genuine new-city candidates, no guessed identity, exact retained constraints |
| B answers | read_calculations.py, read_references.py, assistant_capabilities.py, assistant_selection_contract.py, companion_answer_reliability.py; related tests | Budget fee coverage, compound read completion, bounded explanatory task context |
| C engineering | saved_operation_bindings.py, snapshot fake fixtures, Web tests/config; engineering harness | Count versus duration correction, fixture contract, deterministic Web timeout diagnosis |
| D Astra review | Read-only contracts and worker diffs, own review report only | Independent review of critical changes, no sealed questions or product edits |
| Coordinator | Shared docs, source integration, conflict resolution, frozen full acceptance | Official workspace integration followed by same-source final checks |

Workers do not run full suites concurrently or reuse one mutable database.
Use a distinct fixture DB per lane on test Postgres127.0.0.1:15435. Never use
production15432. Live runs use their own exclusively created blank DBs.
Full model inputs/outputs/tools/DB diffs and source hashes must be preserved.
Do not read E:/Study/RoamSync-stage6-evidence-20261025/private-sealed cases or
rubric before coordinator freeze. Old independent sets are regression only.

## Integration and final acceptance order

1. Commit the incomplete common checkpoint with known failures explicit.
2. Workers reproduce, fix minimally, test, commit and hand off exact hashes.
3. Coordinator integrates worker commits in the isolated integration branch;
   Astra reviews shared contracts and any conflict resolution.
4. Inspect official HEAD/dirty files again; preserve tracked and untracked work
   with a recoverable manifest/snapshot outside production runtime. Resolve
   overlapping files explicitly. No reset/clean or destructive overwrite.
5. Integrate reviewed code into E:/Study/RoamSync. Freeze the actual official
   source/test/config hashes; use services launched from that directory with
   isolated DB/ports. Historical development-tree runs are not final acceptance.
6. Run backend/dedicated DB/Web/type/build, fresh real model+AMap browser chains
   (Chengdu plus two other cities), new-object safety, photographs and refresh.
7. Execute the independent sealed5x4 exactly once after freeze, with independent
   grading. Do not combine different runs into a successful continuous chain.
8. GO requires all stated gates including >=16/20, zero unauthorized formal
   writes and zero critical unsupported guarantees. Otherwise report NO-GO and
   exact remaining blockers. No production deployment follows automatically.

## Official workspace observation

Read-only inspection on2026-10-26: HEAD ea3ba833e6a77122c08c1c9327c18a346e3c48ef,
branch codex/journey-handbook; six tracked local modifications plus many
untracked files. This observation is not a backup or integration. Recheck before
mutation. Prior plan's no-official-source statement is historical after the
user's new integration instruction.
