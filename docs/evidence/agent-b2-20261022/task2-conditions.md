# B2 Task 2: effective conditions and polarity

Scope: `assistant_memory.py`, `assistant_context.py`, `requirements.py`,
`requirement_language.py`, and `test_agent_b2_conditions.py`. No schema, provider,
planner, production, deployment, Obsidian, or C holdout access. Product edits
started only after root's explicit baseline-capture-finished signal.

## Measured test-first evidence

Before product edits, the development test file first yielded 16 failures and
3 passes. Tightening the continuous-walking counterexample to literal
`不超过20分钟` and adding cropped-literal cases yielded 19 failures and 2 passes.
Failures covered:

- Chinese/Arabic duration and headcount equivalence lost by substring checking.
- Unverified scalar proposals rejected without an observable reason.
- Paraphrased constraints lost instead of retaining literal user evidence.
- Normalized ISO dates rejected despite an explicit equivalent quoted date.
- Hypothetical and reported statements contaminating typed requirements.
- Negative photography and pace becoming positive interests/preferences.
- Continuous/internal walking converted to a route/daily walking hard cap.
- Literal fragments dropping negation, accompanying subject, or walking scope.
- A personal preference promoting a later trip clause to global lifetime.

Three later self-review tests failed before fixes (3 failed / 21 passed):
day-local `不再喜欢拍照` reactivated photography; withdrawing continuous walking
revoked the unrelated transit cap; a whole `我朋友喜欢拍照` quote was accepted.
A final normal-chat capture counterexample failed (1 failed / 24 passed) because
`妈妈连续走路不能超过20分钟` missed the unforced requirement gate. All these tests
remain in the committed 25-case development file; old assertions were unchanged.

## Implemented behavior

Scalar normalization requires one explicit quoted quantity/date, a bounded value,
and equality with the model proposal. Mixed adult/child sums, implied nights-to-
days, conflicting dates, and missing date precision remain unverified. Raw quote,
message reference, scope, and v2 scope evidence remain separate from normalized
values. Unverifiable text paraphrases/fragments preserve the complete current-user
quote. Only a plain first-person prefix may be dropped from a literal condition.

The existing memory dictionary carries bounded latest-turn diagnostics; no public
model fields changed. `memory_prompt` adds `diagnostics` alongside existing keys.
All projections use the same literal current-user provenance guard. Typed atoms
retain their original source clause. Negated photography/pace remain exact prose;
continuous/internal walking remains prose because route evidence does not prove
internal/continuous tolerance. Its local withdrawal uses scoped tombstones without
revoking the separate `max_walking_minutes` dimension. Explicit global lifetime is
determined per clause. Legacy personal/bootstrap scope protections remain intact.

## Verified regression

Official interpreter: `E:/Study/RoamSync/backend/.venv/Scripts/python.exe`.
Environment: `APP_ENV=test`; disposable `roamsync_test` on loopback port 15435,
the provided test identity; LANGGRAPH uses the same database with `postgresql`
driver. Windows selector event-loop policy was set in the test launcher, not app
code. Fresh consolidated run: **136 passed in 11.50 seconds**, exit 0; no skips.

```text
pytest -q -o addopts= --tb=short
  tests/test_agent_b2_conditions.py
  tests/test_agent_b_conditions.py
  tests/test_memory_scope_compatibility.py
  tests/test_complex_requirement_intents.py
  tests/test_requirement_context_boundary.py
  tests/test_effective_requirements.py
  tests/test_assistant_product_context.py
  tests/test_decision_context.py
  tests/test_assistant_p1.py
  tests/test_assistant_p1_postgres.py
```

An earlier broader launch without the selector policy produced five Psycopg
Proactor errors; rerunning with the policy passed, without weakening tests or
adding an application workaround. `test_agent_b_postgres.py` remains gated to its
historical exclusive database names and was not claimed as passed here; the
unmodified P1 PostgreSQL tests covered persisted reload/receipt-date provenance.
`git diff --check` for owned product files passed.

Limits: deterministic extraction is conservative, not a general Chinese semantic
parser. Unsupported paraphrases remain literal; no internal walking, menu, weather,
or other missing external evidence becomes a verified guarantee. This test result
does not replace the independent frozen holdout, real action-chain validation, or
root's integrated review and release gates.
