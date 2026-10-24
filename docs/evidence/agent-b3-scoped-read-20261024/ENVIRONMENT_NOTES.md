# B3 evidence boundaries and failed attempts

- All database work used the pre-existing synthetic PostgreSQL service on15435,
  exclusively B3 test databases. Production3000/Compose/database were untouched;
  no service restart/deployment, migration, destructive test reset or Obsidian write.
- reader-before.xml: genuine1/1 failure against the baseline reader (third-day
  request returned the first ten activities across days1/2). A red product test,
  not a harness failure. Kept in the pre-implementation test commitadf7cf4.
- reader-first-after.xml1, reader-expanded.xml9, scoped-regression.xml154 and
  authority-regression-valid.xml84 are overlapping historical subsets, not an
  additive unique count or evidence for the final source.
- authority-regression.xml contains0 tests: the command used the nonexistent
  test_input_authority.py instead of test_candidate_input_authority.py. Invalid
  command, followed by the retained valid84 run; not counted as a product pass.
- reader-mvcc.xml19 is an intermediate working-source run. pre-legacy251 and
  4a8-regression252 are superseded source checks, each retained with appropriate
  source manifests where captured. They are not final254 results.
- pool-regression-observer-failure.xml:253 pass/1 fail on product3f. Existing
  query-policy instrumentation listened only to the original Engine, missing the
  independent read Engine's actual activities SELECT. Testb393bfd observes the
  Engine class instead; all original forbidden-query assertions remain. Final
  full14-file run:254/254, no errors/skips, identical app source before/after.
- Four real-model captures are complete, fixed-source, same fixture/config:
  baseline1/6, first41a4=5/6, intermediate4a8=6/6, final3f=5/6. They are author
  reviewed public development inputs, not blind ratings or heldout accuracy.
- First afterturn4 generically clarified despite having the saved day/name;
  unused model query paraphrase failed literal argument validation. The scoped
  normalization fix preserves source_quote and other tools' authority checks.
- Final3fturn2 model emitted forbidden top-level trip:{candidate:null}; strict
  Pydantic validation returned a safe generic retry. Material user goal failed.
  Do not relabel it a successful safety check or overwrite it with4a8's6/6.
  No format relaxation, prompt tuning or selective rerun followed this failure.
- PowerShell Python console sometimes displays Chinese as mojibake; raw JSON
  and markdown are UTF-8 and were inspected via escaped Unicode as well. Python
  3.14 emitted WindowsSelectorEventLoopPolicy deprecation warnings; not failures.
- No new browser/UI, actual venue route/weather/menu/reviews, candidate Accept,
  high-load multi-process capacity or new independent heldout run was performed.
  Historical C2 strict2/20 (valid2/19), its invalid case, and overallNO-GO stand.
- Initial capture stale/busy exceptions use existing AssistantToolError API
  handling. Only answering-stage rationale/notes stale is explicitly recorded as
  read_tools.itinerary_read.status=needs_retry. They must not be conflated.
- Extra read budget: two physical connections per application event loop/process,
  no idle read pool; normal business default15+2, Workers separately budgeted.
  Small-pool saturation, bounded admission and cancellation are real PG checks,
  not a proof of deployment-wide capacity. No new permanent server process.

Raw app-visible model output, every reply, tasks/tools/sources, latency and formal
state fingerprints are retained. No hidden chain of thought or keys are recorded.
Run build_receipt.py only to validate/rebuild presentation of these artifacts;
it neither calls a model nor touches a database. Its PASS labels are explicit
author judgments, and structural checks cannot certify semantic quality.
