# Repository Reproducibility Proposal — 2026-10-07

Current HEAD5572849 is not a complete system baseline. Dirty/untracked runtime, migration, test, Web and documentation files must not be committed as an unattributed bulk git add. No Git history changes are authorized or executed by this document.

## Concrete safe release procedure (requires explicit user approval before execution)

1. Retain main and all local files. Record current HEAD, porcelain inventory, backend source manifest and Web build-file manifest. Preserve existing file hashes and accepted production image digests. No reset/clean/stash/rebase.
2. Build a reviewed allowlist from runtime directories: backend/app, backend/migrations, backend/evals excluding results, backend/tests/fixtures/tests, Dockerfile/pyproject/uv.lock/alembic; Web src/public/package and lock/build configs; compose files; narrowly selected operator scripts and contract/handoff documents. Include tracked deletions intentionally. Exclude .env/secrets, test-results, browser profiles, unrelated assets, raw DB dumps, screenshots and private records. List every proposed path and origin before staging.
3. Separate provenance groups: accepted prior backend/runtime foundation; accepted prior Web and tests; source lifecycle offline additions; this current Demo acceptance work. Distinguish unknown/unaccepted dirty changes explicitly. Do not retroactively claim historical ownership or exact author attribution from a dirty tree alone.
4. After approval, create a codex/release-acceptance branch from current HEAD without discarding working tree. Stage only exact reviewed paths, inspect staged diff and secret checks, then make attributed grouped commits with manifests and acceptance evidence references. Do not stage all files with git add . and do not merge into main automatically.
5. Create a clean checkout from approved release ref, supply credentials externally, install exact locks, migrate isolated PG17, run required focused/full/Web/provider/rehearsal gates and compare manifests. Only then claim Git reproducibility and candidate release readiness. A build from the present dirty checkout cannot prove this gate.
6. Deploy only ready runtime changes after final gates and bind API/worker/Web to release manifests. Preserve data, keep existing production images/config references for rollback. Schema migration/data deletion requires separate decision.

## Current concrete evidence

Source Repair baseline d982, final ec632. Exactly3 offline added source files and no prior manifest hash changes, with reversible overlay zip and verification.json. Production API167 files still match fc3. Existing historical dirty work is inventoried but cannot yet be safely attributed/committed. Demo starts with isolated acceptance runtime, not a production reset.

## Decision required later

Explicit permission is required to execute the exact release-branch/staging/commit procedure after the final path allowlist and gates are ready for review. No permission is needed to continue read-only audits, manifests, isolated acceptance evaluation or bounded fixes. Until approval and clean-ref verification, Repository Reproducible remains RISK and Product Milestone completion is unproven.


## Concrete release approval proposal — 2026-10-08

Pre-release gates: latest Linux/Python3.11/PG17 full854, Web125/typecheck/build, isolated real lifecycle/Recovery and final scoped Knowledge/facts/rejection followups. Latest source1acc754b9122b2aded24612947f74f3c23ea7017ee388c8a4412bd4c6cddb2e5. Raw source/test/evidence hashes are in backend/evals/results/demo_acceptance_20261007/verification.json; exact file list in release_allowlist.txt/JSON.

Proposed authorization: create codex/roamsync-demo-release-20261007 from current5572849; stage only the363 existing allowlisted paths and two already-existing deletions (web/.env.test and web/src/components/TripBriefingDrawer.tsx), then make grouped commits for backend baseline/facts/corrections, Web baseline/lifecycle tests, and operator/docs contracts. 330 paths are currently dirty/untracked within that reviewed scope; unchanged allowlisted files need no commit delta. Existing baseline ownership is historical, not attributed wholesale to this slice. No Android changes, .env/real keys, raw eval results/private data, unrelated attachments or unverified branding artifacts. No reset/rebase/merge/force push or blanket add. Git index is empty; history operations remain unexecuted.

After authorization: verify source hashes immediately before staging, inspect staged exact allowlist, commit groups, create a clean Git checkout of final release ref, install/build using locked dependencies, run isolated PG regression and complete live browser rehearsal on the clean source, then deploy API/worker/Web from that ref only when all release gates pass. Bind image/runtime/clean-ref manifests, verify readiness/provider smoke and production formal-state safety; preserve previous images/config for rollback and never reset real trips. Production currently remains the accepted v1 snapshot; deployment reproducibility and clean-ref rehearsal are still unproven.

User goal section22 explicitly states: “任何 Git history 操作：需要用户明确允许。” This is the approval boundary; do not infer approval from continuation or a preselected option. No approval has yet been received. Goal remains ACTIVE pending that decision; no three-turn blocker threshold has occurred.
