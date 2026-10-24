# RoamSync stage3 implementation and acceptance

Status: IN PROGRESS, product remains NO-GO until all gates pass.
Isolated branch codex/product-closeout-stage3-20261024 starts at c2be562;
official E:/Study/RoamSync remains ea3ba83 with its original local edits preserved.
Raw evidence: E:/Study/RoamSync-stage3-evidence-20261024. No production DB writes,
deployment or Obsidian operations. The new holdout is sealed; implementation
must not read it before the final product freeze.

## Batch1 — shared read identity and task execution

MEASURED before: batch1/before.xml has two intended failures; real-before.json
returns absent-suggestion clarification for a named comparison, then loses both
ordinal and compound reads. Root causes: competing Suggestion/place resolvers,
direct root dropping valid read_tasks, missing same-turn ellipsis and parent-city
provenance, and split direct answers losing parent subjects. Reverse route result
order also renumbered comparison members.

Implemented one frozen parent read projection, exact literal same-turn search
subjects (ID-less until provider resolution), preserved comparison order, shared
Companion projection and parent-question context. Read tasks retain independent
execution/status/results. No new writer or permission.

MEASURED after: batch1/after-r7.xml passes 49 related tests on an isolated migrated
PostgreSQL DB. real-after5.json uses real GLM and AMap: named comparisons and two
ordinal addresses work; compound route is 2.1km/29min, and missing current hours
are disclosed without losing the route. Source unchanged during capture; formal
state unchanged. General comparison prose is model knowledge, not reviewed venue
evidence. Prior after/after2/after3/after4 failures retained; after2 source drift
must not be treated as frozen evidence. Earlier local harness configuration
failures are retained separately from product failures. Astra reviewed identity
freeze, incomplete resolution and reverse-route ordering risks; regressions added.
