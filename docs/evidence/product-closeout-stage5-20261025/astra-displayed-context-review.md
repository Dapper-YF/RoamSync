# Displayed Revision context diff review

VERIFIED static inspection of current four-file diff and test_stage5_saved_context.py. No product edits, DB execution/writes, model calls or new acceptance questions. Parent-reported after2 49 passing is not independently rerun here.

Decision: the visibility fix is architecturally acceptable. No new mutation authority, latest-pending selection or extra database read is introduced. No blocking cross-trip flaw found in this diff. The changes correctly repair direct consultation context transport while leaving formal itinerary values separate.

## Verified boundaries

- Reader rejects mismatched snapshot.trip.id before copying review. No trip clears any incoming displayed_revision; valid trip with no snapshot also initializes it to None. Fallback loading without an explicit revision_ref does not discover a pending object. Incoming context cannot impersonate the server-read field on the normal Reader path.
- deepcopy isolates the shared detached snapshot from each answer context. Multiple read tasks can receive the same identity without mutating or independently choosing revisions. Aggregation updates a same-name receipt key; this is safe only because all children use the same snapshot. It is not evidence that each child answered a revision question.
- Saved values remain in formal_itinerary_summary and existing deterministic saved_values projection. Preview is separately named. Provider rule explicitly disallows treating proposal values as saved or treating discussion as adoption. This is an instruction-level language guard, not proof of model compliance.
- Current upstream snapshot capture still enforces exact supplied id/run/hash, pending status, base Trip version and complete review. The Reader deliberately trusts that producer; it does not independently validate a dict. This is acceptable for an internal injected snapshot, not a public serialized snapshot endpoint.
- Existing captured_at/version semantics remain: a detached read describes state at capture. No repeat read is added while providers run. Concurrent acceptance/rejection after capture may make the proposal no longer current at answer delivery, as with any detached read. Do not describe the new field as a perpetual freshness guarantee. Existing Accept rechecks remain mandatory.

## Corrections / evidence precision

1. Low-severity prompt mismatch: companion_provider.py says `review.before/after`, while revision_presentation.py returns `review.changes[].before/after`. Use the actual path and mention additions/removals can have one side null. This avoids a misleading contract cue precisely where the model must distinguish before from proposal.
2. Receipt precision: assistant_capabilities.py emits `revision_read: available` from read_snapshot presence, not evidence that Companion loaded it. companion_graph.py:gather_context skips reader.load when prior gaps exist. Therefore this receipt proves captured/available context only, not successful context delivery or answer completion. Either explicitly define this as snapshot availability (with captured_at), or set it using a Reader-load flag if it is intended as completion evidence. Never use this alone to grade “candidate question answered”.
3. Receipt parity: existing explicit pending_changes return has id/version but omits presentation_hash, whereas this new direct path includes it. Prefer a shared receipt helper with identical source identity/hash/version/captured_at for both. No need to change write semantics.
4. Type depth: `displayed_revision: dict | None` provides a named channel but not a fully typed review contract. It is sufficient for this narrowly scoped transport fix with one trusted producer; a shared read-reference follow-up should type the projection and retain run_id/provenance. Do not claim this batch already implements the complete typed-reference design.

## Coverage recommended before freezing this batch

The new test verifies valid direct consultation, rejection of a wrong hash and missing explicit ref, detachment, formal-summary separation, and unchanged fixture state. It does not yet independently exercise:

- No trip + forged context; trip + no supplied snapshot + forged context; valid empty-review snapshot replacing forged context.
- Wrong snapshot trip rejects before any query/provider use (pure fake session is sufficient).
- Accepted/discarded revision, changed base Trip version, wrong run and incomplete review rejected at snapshot producer (existing tests may supply these; link them instead of duplicating).
- Two Reader calls sharing one snapshot: mutate first result; second retains same id/hash and original changes. This can be a pure unit test.
- Provider serialization actually includes the field (`_provider_context` currently uses model_dump, so static evidence says yes); transport test can assert this without a model.
- A direct answer attempt with pre-existing graph gaps does not claim successful delivery solely from snapshot availability.
- Formal saved75 / pending60 remain separate in context, and explicit saved_values route returns75. Language correctness still needs actual model evidence later; static prompt assertions cannot substitute.

No request to broaden this small batch into new reads or freshness queries. Correct the wording/receipt semantics, preserve current boundaries, and use deterministic tests for transport. The product NO-GO and historical 4/20 result remain unchanged.

## Final diff follow-up

VERIFIED by rereading the final five-file diff and updated test source. The previously identified prompt-path error is fixed (`review.changes[].before/after`). The snapshot projection now retains trip_id and run_id alongside id/hash/version/captured_at. The deterministic pending_changes receipt now includes presentation_hash. The conversational receipt now says context_available and explicitly states captured_context_not_answer_completion_or_adoption; delivered_to_answer_context is local to each leaf and becomes true only after the injected Reader actually loads a nonempty displayed_revision. If graph context gathering skips the Reader, it stays false. This resolves the earlier receipt-overstatement concern. True still means transport to the runtime context, not a successful model answer, as the semantics field correctly states.

The added parameterized test source checks both load/no-load paths through a stub runtime. This is meaningful transport/receipt coverage; it does not itself run the actual graph gap branch or verify model interpretation. The reported after5 run, prior stub failure and selector APIConnectionError/RemoteProtocolError replay have not been independently executed or inspected by this reviewer. Preserve those failure artifacts and label any subsequent public replay separately; none revises historical independent acceptance scores.

Reconfirmed original production boundaries: `_capture_saved_trip_read` selects only the supplied Revision id matching trip_id and planning_run_id, checks pending status and run.base_trip_version against the captured Trip version, compares the presentation hash, then requires complete review. Missing ref leaves displayed=None; wrong hash/id/run/trip cannot fall back to another pending row. `load_saved_trip_read` retains the post-capture Trip/preferences freshness fence. This diff modifies only the returned projection, not these queries or guards. Reader checks the outer snapshot trip identity; this trust boundary relies on the single internal producer to ensure nested projection trip_id/run_id consistency and is not permission to accept arbitrary caller dictionaries.

No-trip and no-verified-snapshot cases still clear untrusted incoming displayed_revision. Mismatched outer snapshot trip raises before copying. Each valid delivery deep-copies the snapshot, so duplicate read tasks cannot mutate each other's candidate review. The newly added local delivery flag is per invocation and does not create cross-task shared authority. Existing pending_changes rendering and conversational context remain separate from formal saved-values rendering. No adoption normalization, command, planner write, Accept handler, business table, endpoint or privilege changes appear in this final diff.

Final decision: ACCEPT this narrow internal read-context transport batch on static architectural review; no remaining blocking finding. The existing direct-context integration test plus parameterized receipt test support the intended boundary, conditional on the owner's successful execution evidence. Earlier optional pure tests for no-trip/empty/mismatched snapshots and duplicate-load isolation remain useful coverage suggestions, not grounds to broaden or block this batch. Actual model accuracy and end-to-end product completion remain unproven here; product NO-GO and stage4 4/20 are unchanged.
