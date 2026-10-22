# B evidence scope and reproduction

All participants, venue-price probes and database owners are synthetic. Live
dialogues use the configured model, AMap and web providers. No production writes.
Raw evidence remains immutable; the runner refuses to overwrite an existing file.
Do not rerun the published holdout and call it independent again.

From the B repository root, with its backend Python dependencies installed:

```powershell
python backend/evals/report_agent_b_quality.py
```

This exports saved answers and recalculates review/metrics and LF-normalized
hashes without model calls. Evaluation entry point is
backend/evals/run_agent_b_quality.py; --help lists arguments. Use only the dedicated
15435 disposable container and the explicitly named test databases. Settings are
read in memory from the user-provided settings file; never copy that file here.

Windows regression summary merges five XML suites by test node, not run totals.
b-delivery-final.xml is a fresh final 12/12 focused rerun; the preceding
b-delivery-without-optin.xml intentionally skipped the two PostgreSQL checks
because their opt-in flag was missing. a-scope-review.xml is separate integration
source testing (13 pass), not B holdout evidence; its additional bootstrap
counterexample remains preserved even though those tests passed.

See ../../AGENT_QUALITY_B_DELIVERY_20261022.md for failed-environment exclusions,
shared-database exclusions, all limitations and the overall NO-GO conclusion.
