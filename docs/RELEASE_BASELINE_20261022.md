# Shared release source baseline — 2026-10-22

This baseline preserves the verified, currently deployed product at canonical
`E:/Study/RoamSync`, parent `6b298caddb79125991bfc5183ddeefc09029f31c`.
It includes the Oct 21 seven-task release via ancestor `1fab037`, plus the Oct 22
handbook, saved intentions and venue handoff fixes. It is a release **source**
baseline, not architecture acceptance or authorization to deploy.

Evidence: `docs/evidence/engineering-a-20261022/`. API and Worker each matched all
224 runtime files byte-for-byte; official verification passed both health checks.
364 runtime/build files match Git after LF normalization. Their deterministic
aggregate LF SHA256 is
`772a651705b23a8cb1e49d6382fdc269787a76432877dffd7231fe54434b7259`.
The historical Oct 21 stored runtime manifest contains 219 entries (the final
report says 222); all 219 are present in `1fab037`, including mixed-EOL files
verified through the preserved pre-handbook raw source. This historical manifest
is incomplete evidence for the final 222-file release; current 224-file runtime
verification and ancestry establish this baseline's actual content.

Before isolation, 3,133 tracked/untracked files (450,467,533 bytes) were copied
and SHA256 inventoried under `E:/Study/RoamSync-audit-evidence-20261022/`.
That private directory is outside Git. `.env` was only hashed, never copied to
Git; ignored databases/backups/caches remain in place. No original file was
overwritten, staged, deleted or reset.

Four unrelated tracked local edits remain at canonical source: README.md,
.env.example, backend/scripts/quality_runtime.py and web/nginx.conf.
They are preserved in the private snapshot and intentionally excluded from this
product baseline: none changes the verified API/Worker or official Web build
(Web uses nginx.local-product.conf.template). Untracked reports, experiments,
temporary inputs, screenshots, evaluation outputs and private sessions are
preserved there too; only the three reviewed Oct 21 delivery reports are copied
into this commit. No raw evidence containing session data is staged.

B and C must start from this commit's full SHA, work in separate worktrees and
return commits plus verification scope. Do not independently deploy, migrate or
write the official database. A owns engineering/test/reliability, B owns Agent
intelligence and C owns Web product experience. Final integration requires a
fresh combined isolated acceptance. Existing regression results are historical;
the final deployed tree has not yet received a fresh full suite in this round.

Known prior acceptance limitation: empty-trip initial planning still reports
`planner_research_unavailable` with the external provider. Existing-trip revision
acceptance does not certify that scenario. Public multi-user release is not
accepted.
