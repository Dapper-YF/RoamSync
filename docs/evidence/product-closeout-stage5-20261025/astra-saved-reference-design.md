# Stage5 saved reference design review

Status: VERIFIED code inspection; INFERRED design recommendation. No implementation, DB access, model calls, new acceptance questions, official source/deployment access, or Obsidian writes performed. Historical stage4 4/20 remains frozen regression evidence only.

## Findings

1. `saved_trip_reads.py` already captures a detached read-only REPEATABLE READ snapshot. `displayed_revision` is loaded only from an explicit revision id/run/hash, pending status, matching Trip base version and complete review. This is the correct read provenance and must remain. `selection_summary()` exposes it to the selector.
2. `assistant_capabilities.py:_answer_leaf_impl` handles pending changes only when capability `itinerary` and purpose `pending_changes` are selected. Direct decisions construct InformationNeed with trip_context_required/itinerary_required false. `companion_context.py:load` never exposes displayed_revision even when an immutable read_snapshot is supplied. `CompanionContext` has no dedicated field; `_provider_context` serializes only that contract. Thus the server knows the displayed candidate but the answer model does not. Prompt-only repair cannot solve the missing context channel.
3. `assistant_operation.py:approved_draft` requires each activity_mentions string to occur literally in raw_text. The requirement correctly prevents invented target authority, but selector replacement of “第一天第一项” with a stored name violates it. `_ground_semantic_intent` resolves aliases and selected activity only. `_ActivityEntity` currently lacks position, so grounding cannot recover ordinal semantics itself.
4. `SavedTripReadSnapshot.project` already has position-aware ordinal reading plus coverage guards. Separate private grammars in selector normalization, read projection and planning grounding would make the same user phrase mean different objects.

## Minimal shared contract

Introduce one internal saved-reference module, without a new business table, external writer, planner or acceptance path. Two distinct types:

- `SavedReferenceRequest`: object_domain (`formal_activity` or `displayed_revision`), reference_kind (`literal_name`, `selected`, `day_ordinal_activity`, `displayed`), exact current-message source_quote/source span, and reference arguments appropriate to that kind. Ordinals are explicitly 1-based. Do not accept selector-supplied stable IDs as authoritative resolution. Every ordinal/day/date argument must have literal source support; typed numbers alone do not establish that support.
- `ResolvedSavedReference`: result status (`resolved`, `ambiguous`, `incomplete`, `stale`, `unavailable`), original source, trip_id/trip_version/captured_at, and typed target. Formal target: day_id/date, activity_id/activity_version, ordered-scope identity/coverage. Revision target: revision_id/run_id/presentation_hash/base_trip_version/status, server review. These are constructed by server resolution only, never by the model. Preserve the original user wording separately from resolved display names.

A pure resolver consumes detached facts. Names resolve uniquely inside explicit day scope; selection is a contextual fallback only for a selected reference; explicit ordinal/name overrides unrelated UI selection. Ordinal resolution uses the canonical displayed formal Activity ordering, not database fetch order, row UUID, lexical name, or a reconstructed candidate. Reuse/extract the existing ordering logic but first confirm it matches the web formal list. Define whether “项” counts Activities only; if UI intermixes lunch/free-window rows, either use the same typed mixed order or return ambiguity. Do not quietly count a different list. Require complete requested-day coverage and unambiguous order; duplicate/absent positions need an explicitly documented canonical UI ordering, otherwise fail closed.

The request type may be model-extracted in the state-specific selector schema, but resolution and source validation remain server-owned. A smaller implementation can retain literal activity_mentions on the wire and convert them into this typed request centrally. Both choices are valid; adding several unrelated regex routes to fix individual utterances is not.

## Read path

Add a dedicated typed `displayed_revision`/`saved_read_context` to CompanionContext. When an already validated snapshot for the current authorized trip contains a displayed Revision, transport its read-only review regardless of the selector choosing direct. This is context visibility, not capability escalation: do not invoke extra reads, external lookup, Run creation, adoption or formal mutation. Formal values and proposed changes must remain separate fields. Provider instructions must identify pending/preview status and explain that the observed before/after values are not accepted changes or original validated rationale.

The explicit itinerary/pending_changes path may retain deterministic rendering, but it and Companion consume the identical server projection. Absence must have a reason (not displayed, stale, hash mismatch, incomplete), rather than falsely asserting there is no pending candidate anywhere. Never fall back to the latest pending Revision. Keep run_id in the projected identity along with hash/version; validate trip/session provenance upstream exactly as today. A different browsing city must not make the read context an inferred travel requirement for that city.

## Modification path

The selector must preserve `activity_mentions=["第一天第一项"]` (or typed ordinal reference with identical exact source), never substitute “人民公园” into source evidence. `approved_draft` still validates exact full operation clause, affirmative current action, negation/hypothetical/revocation and target-bound authority. Resolved target identity does not waive any of these checks. The amount and operator must independently remain grounded: increase 15 is delta +15, not set duration 15.

After approval, resolve against the saved snapshot to a unique formal Activity. Carry resolved ID and original source as internal evidence into existing planning intent grounding; do not synthesize an authorization quote containing its stored name and do not rewrite the user message. Add position (and version where required for comparison) to detached planning facts. Re-resolve/revalidate within the existing short write transaction and fail stale if Trip/version/order changed; never silently target the new first activity after reorder. Compare stable ID/day membership/activity version, protected/locked constraints and the existing current-state policy. Existing Planner produces a Revision, Validator checks it, current explicit Accept is the only formal adoption route.

Do not piggyback this onto UI `selected_activity_id` by overwriting that field: source-derived references and UI selection have different provenance. Multiple operations require per-operation target bindings; flattening all references into one global ID union can apply one delta to all targets. If downstream currently cannot preserve those associations, restrict the new path to one supported target operation with a clear unresolved result for other operations until it can, never silently omit one.

## Required adversarial / invariant cases

1. Direct decision + verified displayed pending Revision yields accessible candidate context and unchanged formal state. Explicit pending_changes returns the same revision id/hash and values. No new Run.
2. No displayed ref with two pending rows: unavailable, never newest. Wrong trip/run/hash, accepted/discarded Revision, changed Trip version or incomplete review: no stale review presented as current.
3. Formal 75 and pending 60: “现在保存多少” answers formal 75; “这次改了多少” exposes 75→60; neither accepts. “先别采用，解释区别” stays read only.
4. First day/first activity +15 binds its stable ID; same-name peer on another day unaffected; unrelated UI selection must not join target IDs. Preserve lunch, peers, windows, preferences and source quote.
5. Day 99, item 0/out of range, truncated day, unresolved mixed Activity/window ordinal, ambiguous ordering: targeted clarification, no Run/write authorized by fallback.
6. Snapshot v2 resolves A first, concurrent reorder creates v3/B first: stale rejection, not retarget B. Activity version or lock changes are revalidated by existing pipeline.
7. “如果第一项增加15分钟会怎样”, “第一项不要增加15分钟”, quoted third-party instructions: no modify authority. “第一项+15，第二项不变” cannot bind delta to the protected peer.
8. “第一项+15，第二项-10”: preserve separate source/target/delta pairs or explicitly decline unsupported multi-operation precision; no cross-product of IDs and amounts.
9. Selector supplies ordinal 2 for literal “第一项”, invents ID, uses historical source span, changes +15 to set 15 or renames target not in source: rejected before planning.
10. Pending candidate first item is not formal first item; domains must not be interchangeable. Displayed Revision reference cannot authorize candidate modification or adoption by mere presence.

Recommendation: proceed with this boundary. Acceptance is conditional on implementation tests demonstrating the shared reference resolution, direct-answer context transport and unchanged existing Accept guards; this review is not a claim of end-to-end product success.
