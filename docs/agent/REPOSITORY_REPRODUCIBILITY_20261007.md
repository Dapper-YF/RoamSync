# Repository Reproducibility Acceptance — 2026-10-08

Status: VERIFIED clean Git checkout / locked build / regression; NOT READY for release because real-provider lifecycle acceptance failed. Production deployment, main merge and production database changes are not authorized.

## Authorized scope and history

Base main: 5572849209c943c5f5ad1579db4cef0ba2fb5b25. Branch: codex/roamsync-demo-release-20261007. The human authorized exact grouped release commits and isolated acceptance, then explicitly approved the dependency amendment: remove the launcher's automatic reset invocation; add three frozen evaluation inputs; update two evaluation input paths. Reviewed scope is 366 existing files plus the two existing deletions web/.env.test and web/src/components/TripBriefingDrawer.tsx. Original 330 dirty/untracked paths and the three added inputs were accounted for. Android, raw results, private data, credentials and unrelated files remain outside the release.

|Group|Commit|Changed paths|
|---|---|---|
|Backend / Travel Facts / Planning / Execution|fbd65f28f3fe5ee1ed99ba8182976a717c0018bc|219|
|Web / UI / Tests|93118dc6f1370c7be78e167ffb7adb640375573a|66 including two deletions|
|Operator Scripts / Contracts / historical Documentation|8ee7dbf0ddc27fdb8fd55bc20fad9777ec4bf209|48|

These commits capture previously developed, reviewed functionality. They do not attribute all historical code to this release-preparation round. A final documentation-only checkpoint updates the four explicitly requested reports within the same allowlist; its exact SHA is recorded in release_final_binding.json and the final handoff response. Application source remains identical to 8ee7dbf.

Each group used an exact NUL-delimited pathspec, staged diff review and manifest/commit record. No blanket add, reset, clean, stash, rebase, history rewrite, push or main merge. The 366 candidate Git blobs match audited SHA256 values; both deletions and empty index were verified. Literal secret scans and full-file classification found no identified real credentials/private artifacts in the candidate. This is a bounded release audit, not a claim of exhaustive security certification. Browser map configuration is externally supplied public client configuration; server keys remain external.

## Clean source and build evidence

Application checkout: E:/Study/RoamSync-release-20261008, detached 8ee7dbf; initially clean, all 366 hashes exact. Backend source manifest: e7e22849869443bb73f96bce736fb86a1c4b3745f2a48f6f32da3273176622a6. Runtime API and Worker are built images with no source mounts; 175 shipped source/config files match the checkout exactly and both runtime manifests are identical. Web is the built Nginx image on 127.0.0.1:3001, not a development server. Build artifact hashes and actual image IDs are recorded separately.

Backend/Worker build uses uv 0.11.15 and uv.lock with uv sync --frozen --no-dev; the test target uses the same lock including test dependencies. Web installs pnpm 11.19.0 with --frozen-lockfile. Python3.11, Node24, Nginx1.27 and PG17 resolved image digests are captured in build/runtime records. Dependencies are locked; upstream base tags remain mutable, so reuse recorded digests for future release reconstruction. Bit-for-bit rebuild identity across arbitrary dates/platforms is not claimed.

MEASURED: an independent empty PostgreSQL17 test instance migrated 0→0034, then full Backend 854 passed, zero failures/errors/skips, two existing warnings. Web 125 tests, typecheck and production build passed. Controlled frozen evaluation from clean checkout: Knowledge60 runtime/authority60, need34, assertions35/44, mixed7/10; Phase2.5 holdout50 routing/authorization50, need38, expected assertions35, unsupported claims0. Frozen labels and original input bytes are unchanged. The controlled evaluation used the existing Windows Python tool; locked Linux full regression is separate evidence. A production-image evaluation attempt lacked source-only Dockerfile needed by the manifest helper; this instrumentation failure is retained and is not reported as a successful image evaluation.

## Real-provider release gate

Real Chrome UI / GLM / AMap / Tavily / Open-Meteo, isolated PG17, API8001/Worker/Nginx3001. First weather query failed safely because Open-Meteo geocoding was unavailable; second conversation verified current forecast and official published-date opening facts. Explicit create preview/confirmation created an isolated Trip. Its initial research failed planner_research_invalid_output (json_invalid). Two normal UI retries kept the same request/Trip and terminated planner_unavailable; the last Worker log records RemoteProtocolError. A direct no-proxy model diagnostic returned APIConnectionError/ConnectError.

All failures are preserved. Trip stays version1 with zero formal activities. No validated Candidate exists for this fresh release attempt. Accept/Reject, Execution, Disruption, Recovery and Explanation downstream gates remain UNVERIFIED on the clean release; older successful dirty-tree fixtures are historical evidence only. No mock, weakened assertion, fabricated candidate or silent fallback was introduced. Release status is NOT READY.

## Production differences, deployment plan and rollback

Production remains the accepted fc3a06ba3cf95aaa6317f95f3b3cc300d2dd582299ac24ac7b91dce995f3bdfb capability snapshot on API8000/Web3000 and the existing PG volume. Seven formal-table snapshots plus Trip versions remain exactly equal to the pre-release baseline. Candidate contains the previously reviewed Demo authority/UI/Knowledge fixes and reproducible input packaging; they are not deployed. Existing migration0034 is the isolated test target; this round applied no production migration.

Next gate: restore reliable model transport, rerun the unchanged clean-ref full real lifecycle and bind all evidence to the release/source manifests. Only after every isolated gate passes, report production differences and request final online authorization. A subsequent approved deployment must preserve previous API/Worker/Web image IDs/configuration, take and verify an authorized database backup, check readiness and read-only source/formal-state bindings, and prohibit reset/user-data deletion. Any required production database change needs separate approval; do not invoke the image's automatic migration entrypoint against production without resolving this boundary.

Rollback plan (not executed): stop only newly deployed API/Worker/Web after approval, restore recorded prior image IDs and external configuration, retain the existing PG volume and verify readiness/formal-state hashes. No down migration, volume removal or data restoration over newer user records without a separate recovery decision. Current isolated runtime can be stopped independently; preserve its failure artifacts first.

Evidence: backend/evals/results/git_release_20261008 contains allowlist_366, group staged patches/commit records, clean checkout binding, full test XML/logs, frozen evaluation reports, actual image/runtime/artifact manifests, failed browser attempts, clean_rehearsal_verdict.json, production safety and rollback inventory. Raw evidence is intentionally excluded from Git. Main and unrelated local work remain intact.
