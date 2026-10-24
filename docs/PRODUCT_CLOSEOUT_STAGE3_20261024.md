# RoamSync stage3 implementation and acceptance

Status: IN PROGRESS, product remains NO-GO until all gates pass.

## Batch3 — structured preview generation and local candidate edits

MEASURED before: batch3/before.xml reproduces five preview/adoption scope failures;
real-before.json retains the baseline real user failures. Root causes include
save-denial scope cancelling preview/edit, creation metadata duplicated in source
clauses, source paraphrases and canonical names, and workflow controls captured
as new travel requirements invalidating the candidate hash. Implemented scoped
action checks, server literal-span references, literal name/address query evidence,
strict empty-only format recovery and full downstream metadata/route validation.
Named pure lookups render actual provider fields without inventing sibling gaps.

MEASURED real-after6.json: real GLM/AMap ready candidate with 120min People Park,
1h lunch and actual 16min walk, followed by park90min and unchanged peer/window;
formal tables unchanged, source stable. Following Astra source/authorization
review, same-action synonym/pronoun revocation and source/quantity/kind checks
were strengthened; real-after7.json again generates and modifies a ready candidate
(90->90 in this sample, so this capture alone does not prove a non-noop change).
Earlier development captures/failures retained, including root plan output errors,
invalid source bindings, invented walking limit and condition-hash rejection.
batch3/final3.xml passes151 relevant tests; earlier final.xml had two restaurant
branch-name regressions, fixed by preserving exact full branch identities before
interpreting parenthesized address decorations. No unknown constraint was erased.

## Batch2 — effective conditions and receipts

MEASURED before: batch2/before.xml has three intended failures, and real-before
claims solo travel while stored party_size is absent and the sister's requirement
remains. Shared scalar normalization did not recognize self-only quantity, removal
lost subject boundaries and Companion could acknowledge rejected proposals.

Implemented source-bound self-only quantity, exact subject identity for removing
conditions, and versioned merged per-field application receipts. Standalone update
acknowledgements render authoritative effective state, including rejected fields.
Mixed answers receive receipts as context; this prompt boundary still needs final
live/adversarial acceptance. No formal writer change. MEASURED batch2/regression.xml
69 passed on isolated migrated PG; real-after.json confirms 1 person, sister-only
condition removed, personal no-alcohol retained and accurately recalled. Source
unchanged and formal-table fingerprints unchanged. Development failures retained.
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
