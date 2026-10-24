# B3 scoped saved-trip reads

BASE:89b81e8d6cf5561f2bbab1a9ac437aa9dde88fb9. Isolated branch
codex/agent-read-b3-20261024; no production, UI or candidate writer changes.

Problem proven by public source audit: selection sees100 activities, Companion
sees the first10; verified page-selected IDs stop before semantic reading;
approved itinerary reads lose the original-rationale purpose. A confirmed these
connection files are no longer being edited on its integration branch.

Implement a bounded server-owned detached read snapshot shared by selection and
answering. It carries Trip version, actual activity identities/status/locks,
day counts, selected read context and explicit coverage. Current-day or selected
reads prioritize those actual rows before applying a limit. Literal date/day
references narrow only their own read question; multiple subtask projections
reuse the same bounded state and retain incomplete coverage. No client payload
can inject snapshot facts or turn read selection into action authorization.

Existing message selected_day/activity fields remain; pass them only as internal
read context after membership validation. No persistence of selection as memory,
schema migration, changed action_target/Validator/Accept or new planner. Original
saved rationale remains the existing accepted-revision reader's responsibility;
the approved need must retain that purpose rather than regenerate a decision.

For explicit overview/saved-value reads, deterministic saved-state rendering can
answer names/date/time/duration and distinguish optional/cancelled/free-window
state. It may state only the returned scope; a bounded incomplete snapshot must
not imply exhaustiveness. Advice/impact/current facts continue to existing tools.

Validation: real isolated PostgreSQL synthetic15+ activity fixture, public
last-day/duplicate-name/selected-reference reads, incomplete scope, original
rationale absence, reset, compound reads and zero changes in formal tables.
Before/after captures include visible reply, read scope/coverage, source version,
elapsed time and failures. Injected selector proves server behavior, not model
routing accuracy; real-model public replay is a separate measured gate. Preserve
B2/C2 scores; these are new public development inputs, never a fresh holdout.

Steps: meaningful red reader tests; implement detached snapshot and wiring;
targeted PG/permission/context regressions; inspect same-input raw results;
record remaining gaps and deliver exact commits to A without deployment.
