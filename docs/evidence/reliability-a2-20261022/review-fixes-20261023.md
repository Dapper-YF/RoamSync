# A2 independent review repairs — candidate only

MEASURED, 2026-10-23. No production deployment/database writes.

Read-only review found four important issues: experience trigger replacement
discarded checkpoint provenance; API clarification lacked a lease; approved
clarification changed its authorization text; ordinary prepared semantic decisions
were discarded before Graph execution. A owns the first two and persistence;
B owns downstream decision restoration and constrained clarification.

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
