# Official integration acceptance evidence

Start with integration-summary.json and ../../OFFICIAL_INTEGRATION_20261020.md.

- Canonical source fast-forward: 25a62cb → 8344b54 → 8c23a93. A following report-only commit is included in final Git HEAD.
- windows-full.xml / linux-full.xml: final full-source reruns, each 1349 passed and 1 skipped. The favorite case was separately verified in favorites-postgresql.xml.
- postgresql-core.xml / postgresql-core-matrix.json: 93 real PostgreSQL core cases.
- web-final.json: 206 passed. web-production-flags-build.txt: typecheck/build with official product/context flags and public browser-map configuration.
- migration-compatibility.json: six legacy tables' full-row hashes unchanged around 0037. Only an empty new-table downgrade was tested; no production migration or full production-backup rehearsal.
- preservation-after-code-merge.json: two local edits plus1856 untracked files byte-identical; source/config changes were not discarded. Full before manifest is archived.
- lint-comparison.json: 41 pre-existing errors, 27 warnings, zero new error identities.
- production-runtime-readonly.json: 3000 still serves the old image. Source merge did not deploy services.
- style-baseline.json / style-revised.json: actual three-question content comparison. Style is PARTIAL, not a claimed naturalness benchmark pass.
- Selected images and mobile/accepted-plan screenshots are directly accessible.

raw-acceptance.zip retains the original filenames and unmodified contents of raw browser JSON, other screenshots, full lint output, logs, preservation manifest and the first uninitialized-database failure. Latest real browser chain: web-live-2026-10-20T03-11-06-622Z.json at3021, PASS. Latest actual web-search/images check: experience-2026-10-20T03-16-08-402Z.json, PASS.

The initial Windows failure was test preparation (missing database migration), not a green run: 215 failed/80 errors. The diagnostic DB was retained; a clean initialized DB was then used for both final suites. No Mock substituted for the real model/map/browser chain. All trip/appointment data in acceptance is synthetic and isolated.

Reproduction prerequisites: start the separate localhost51420 test PostgreSQL; create the explicitly named test databases; upgrade roamsync_test_write_protection to Alembic head before the suite. Use backend/scripts/run_write_protection_tests.py on Windows for the existing selector-loop boundary. Live services use official_integration_runtime.py, guarded to the independent acceptance checkout, and vite.integration.config.ts on3021→18021. Provider settings are loaded in memory from canonical configuration; no secrets are included in these artifacts.
