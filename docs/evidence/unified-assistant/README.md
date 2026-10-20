# Unified assistant evidence

Read machine-summary.json and ../../UNIFIED_ASSISTANT_DELIVERY_20261020.md first.

- Code: 27db70f; bounded image followup: 9540436; baseline: 1df46af.
- windows-final.xml / linux-final.xml: each 1349 passed, 1 skipped.
- favorites-postgresql.xml: independently covers the otherwise skipped isolated favorites concurrency case.
- web-final.json: 206 passed. Typecheck/Vite production build also exited zero.
- same-trip-preview-red.json then green.json: stale date after accepting a same-Trip preview, then corrected refresh and new-version use.
- image-reference-green.xml / image-reference-linux-final.xml: 14 tests each after reference-image deduplication.
- raw-records.zip: unmodified raw browser records, earlier failed attempts, earlier test runs, image-reference-red.xml and eslint-final.json. ZIP entries retain their original filenames.
- Latest complete real target-interface chain: archived web-live-2026-10-20T02-24-52-232Z.json, with desktop and 390px mobile snapshots.
- Latest real image/display check: archived experience-2026-10-20T02-32-29-443Z.json; selected screenshots remain outside the ZIP.
- integration-preflight.json: canonical local changes and untracked-file collision check, read-only.
- changed-source-files.txt: exact source/test/runtime diff from 1df46af through 9540436, before evidence-only changes.

Real service tests use synthetic user/trip data in an isolated PostgreSQL database, not production data.
Full suites ran on 27db70f. The image-only followup has focused Windows/Linux and real-browser checks.
Global ESLint is not green: 41 errors in untouched files, with no errors in this round's changed files.
No merge, production migration or deployment was performed.
