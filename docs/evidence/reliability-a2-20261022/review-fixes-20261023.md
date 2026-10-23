# A2 independent review repairs — candidate only

MEASURED, 2026-10-23. No production deployment/database writes.

Read-only review found four important issues: experience trigger replacement
discarded checkpoint provenance; API clarification lacked a lease; approved
clarification changed its authorization text; ordinary prepared semantic decisions
were discarded before Graph execution. A owns the first two and persistence;
B owns downstream decision restoration and constrained clarification.

Second review found a further Important recovery gap: API claim committed before
the literal clarification answer was durable. The replacement checkpoint would
lose it. `clarification-recovery-red` fails both real PostgreSQL windows (after
claim, during planning). The repair stores answers plus original question/request
receipts atomically with the claim; fresh Graph input counts persisted answers.
`clarification-recovery-green`: 46 passed, zero errors/failures/skips. B's resolver
restoration remains required for end-to-end semantic recovery.

External evidence root: E:/Study/RoamSync-a2-evidence-20261022/.
`review-gaps-red`: two real PostgreSQL counterexamples fail on the unpatched code
(lost checkpoint pointer, API has no active claim). `review-envelope-red`: missing
prepared_intent KeyError. `review-gaps-green-2`: 74 passed, errors/failures/skips0,
53.213 seconds, fresh tmpfs database, including concurrent resume rejection and
existing real checkpoint/Accept scenarios. `review-gaps-green-1` was an invalid
test path invocation, pytest exit4; retained, not counted as product failure/pass.

The old and new probes use synthetic inputs and real DB/checkpoints, not real
travel answer quality. API clarification obtains a unique claim, retains the
original interrupted thread, and fences late writes after replacement. Duplicate
resume and incomplete interrupts fail closed. Trigger updates preserve unrelated
server metadata. The persisted semantic envelope contains the grounded draft only
after request binding and Trip/preferences CAS, with no relaxed Validator/Accept.

Prior complete regression `combined-full-1` measured 1592 main +25 dedicated;
Web243/type/build passed on ae52693 before these review repairs. Those results
are not proof of this later source. Full combined regression must run again after
B's final code. Unseen20 and complete real browser flow remain unverified.

`combined-full-2` test image passed 1596 main +25 dedicated, but the source manifest
changed while the new recovery counterexample/repair was added. The runner correctly
returned passed=false/source_unchanged=false. This run is retained as invalid for
final source certification; do not count it as a final full regression pass.

Integrated B523bbd7 supplies strict migration for old server checkpoint append
format; expanded text never authorizes new operations. A runtime supplies a
separate recoverable409 path for unbound history: same live claim restores the
original interruption, preserves literal answers/receipts, and marks restart
required so repeated submissions cannot append input or enter Worker retry loops.
`legacy-runtime-red` reproduces the old generic409/failed handling mismatch;
`legacy-runtime-green`:67 passed, zero errors/failures/skips, including real
HTTP/database repeat409 retention and B's actual old/new PostgreSQL checkpoints.
No relaxed source binding, Validator, permissions or Accept. The restart message
requires a new explicit request; it does not claim to auto-repair unsafe history.
