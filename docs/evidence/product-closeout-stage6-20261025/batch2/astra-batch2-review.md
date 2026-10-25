# Stage6 batch2 duration binding — architectural review

VERIFIED static inspection of current uncommitted saved_operation_bindings.py, planning_intent_service.py, schemas.py, planning_goals.py, plan_revision_service.py, planning_graph.py, assistant_operation.py and assistant_capabilities.py; inspected the4 new operation-binding test sources and existing validation/Accept code. No code changes, DB/model execution or private-sealed access. Parent-reported baseline4 failures/current4 passing not independently rerun.

Disposition: HOLD. The server-owned per-operation delta and final Accept revalidation are the right architecture, but source-target authority and atomic request completeness have blocking holes.

## P1 — positive quantity is not source-bound to its selected target

`approved_draft` validates source containment and a positive action but deliberately skips affirmative_entity_source for replan_trip. `bind_duration_change` then checks only one regex duration expression and one resolved target. It never proves that the expression's subject is that target.

Minimal current source: “甲园附近的乙馆增加15分钟”. Both甲园 and乙馆 are real, unlocked, planned activities on the same day. Selector emits one replan_trip operation with that exact raw_text and activity_mentions=["甲园"]. The mention is a literal substring, the overall operation has a positive increase, exact alias resolution produces甲园, and the new binder assigns甲园 before+15. The hard goal then enforces the incorrectly bound甲园 change. There is no hypothetical/negation/protection text to rescue this case.

Expected: reject/clarify the mismatched target proposal, or bind乙馆 only through validated source structure. Before constructing SavedDurationChange, validate the duration action/quantity belongs to its exact target mention in the current affirmative operation clause. Reuse the source/entity checks with appropriate ordinal support; do not rewrite source text into a resolved stored name. A whole-clause authorization is not authority for every name mentioned inside it. Add an adversarial selector-draft test through approved_draft→grounding, not just direct grounding of correctly supplied mentions.

## P1 — unresolved replan targets permit partial requests

`_ground_semantic_intent` records unresolved_activity_mentions but calls bind_duration_change only when targets is nonempty. `_decide_intent_policy` treats unresolved mentions as blocking only for remove/replace/reorder, not replan_trip. Thus a duration operation that fails identity binding can disappear from duration_changes while a valid sibling proceeds.

Minimal two-operation request: “甲园增加15分钟，未存馆减少10分钟”, with literal per-operation raw_text and activity_mentions, only甲园 present. Result contains甲园+15 and unresolved未存馆; no duration issue is appended for the zero-target sibling. The policy can remain plan_preview. A proposal changing only甲园 meets the new hard duration goal, so the second requested operation is not enforced.

Expected: atomic clarification before Run/preview when any requested saved-duration target fails binding. Include replan-duration unresolved references in policy incompleteness and require every operation in the supported batch to produce either a complete binding or a blocking issue. Test unknown target, duplicate name, invalid ordinal, and unresolved sibling after a valid operation. Do not use the union of successful target IDs as proof all operations resolved.

## P2 — mixed operations conflict with the duration-only hard goal, yet missing peers are not enforced

`_duration_change_result` marks every changed activity not in duration_changes as unapproved, regardless of other explicitly authorized operation types. A correct request “甲园增加15分钟，删除乙馆” with two grounded operations therefore rejects a proposal that correctly removes乙馆. Conversely, a proposal that leaves乙馆 and only changes甲园 can satisfy this duration hard goal; the inspected existing validator enforces scope/protection but has no general positive requirement that every requested removal occurs. The remove_activity check around line346 is a protected-activity omission check, not a complete removal-fulfilment requirement.

Expected for this narrowly scoped batch: explicitly decline unsupported mixtures atomically before planning. Alternatively, represent and validate each operation's exact expected effect; do not relax non-target protection wholesale. Never claim the request succeeded after applying only the supported duration subset. Test correct mixed candidate and ignored-removal candidate; both must not be treated as successful duration-only completion when mixed semantics are unsupported.

## P2 — unrecognized duration forms silently remove exact hard constraints

`bind_duration_change` returns (None,None) when _DURATION finds no match. There is no distinct “this is a duration request but syntax unsupported” state. For “甲园增加15分钟，乙馆再待10分钟”, the first operation binds; 再待 is accepted by the top-level authorization grammar but is absent from _DURATION. If the second draft is also replan_trip with乙馆, it produces no binding/issue. The hard goal requires only甲园 and protects乙馆 against any difference, rewarding a partial answer.

Similar incompleteness exists for duration phrases outside this recognizer (e.g. hour units), which must not accidentally become unconstrained general replans. Do not solve by adding one observed phrase alone: declare the supported duration-operation boundary, distinguish unrelated replanning from an unsupported scalar change, and block a duration batch with any unsupported requested effect. Add a supported/unsupported sibling test and confirm no candidate is accepted as full completion.

## Boundaries that are sound / must remain

- SavedDurationChange retains operation_index/source_quote, stable activity/day IDs, baseline activity/Trip versions, set/add/subtract, operand and before/after values. Recognized “增加15” computes before+15; “减少10” computes before−10; set verbs use the target value. Values outside1..1440 reject. Existing minimum-duration/venue/window validators remain necessary and may impose stricter bounds.
- UI selected_activity_id no longer automatically joins the target union. It is consumed only by explicit selected/pronoun mentions. Exact aliases are scoped to target_day; duplicate matches stay unresolved. This is a meaningful reduction of accidental scope.
- Prepared multi-day operations already add multiple_operation_days and clarify. Do not bypass that in the new binder. The binder currently receives a single global target_day rather than each operation's independent date; multi-day support must remain explicitly unavailable until represented.
- Ordinal resolution reuses chronological ordering, rejects ambiguous ties and bare ordinals with visible mixed agenda. Database planning snapshot loads all arrangement items, so the read-limit truncation issue from batch1 is not introduced here. The helper still needs explicit agenda completeness when called without the production snapshot.
- schedule_locked/non-planned targets and protected_activity_ids block duration binding. Duplicate duration operations on the same stable ID add duration_conflicting_operations rather than arbitrarily choosing one. Keep this conflict policy until sequential composition is deliberately specified.
- Worker compares original stored duration bindings with regrounded bindings, preserving baseline identity/version/source. Existing stale prepared-draft guards remain. Final candidate validation extracts these goals from stored intent_resolution and Accept invokes the validator again before mutation under the existing chain.
- Duration hard-goal review checks baseline activity version/duration and Trip version, exact requested after duration, and unchanged place/date/time/cost/lock within its target-day scope. Existing validator separately protects days outside scope. `revision_review` is a presentation projection that normalizes protected items; therefore it must remain paired with the original protection validator, never used as a standalone proof all raw proposal fields are legal.
- No new writer, business table, public adoption path or direct chat formal mutation appears in this diff. Strict fixed-time preservation may make +minutes infeasible when the next activity starts too soon; report inability to satisfy both constraints rather than silently shift peers.

## Evidence needed at batch exit

The4 initial tests exercise correctly extracted operation mentions, explicit UI selection exclusion, add/subtract pair and name day scope. They do not exercise malicious/wrong selector mentions, unresolved siblings, unsupported duration syntax, mixed-operation completeness or final hard-goal/Accept behavior. Add unit tests across source approval→grounding→policy, candidate mismatch checks, and existing database Accept safety cases (stale/repeated/rollback/concurrent/protected). Real model success must show correct before/after values and every independent operation or a truthful atomic clarification. Keep failed evidence; no product GO or independent score refresh follows from this review.

## After4 correction review

VERIFIED current source/test inspection only. The previous missing-target blocker is closed: replan_trip unresolved_activity_mentions now participates in policy clarification, and binding is called even with no targets. The mixed non-replan operation blocker is also closed by duration_mixed_operations. The exact “甲园附近的乙馆增加15分钟” misbinding now fails affirmative_entity_source. Added DB test source checks30+15=45, wrong15, peer changes, activity-version drift, original Accept rejection/unchanged state, successful target-only change and duplicate idempotence. Parent-reported47 passes not independently rerun.

Three concrete paths still require correction:

### P1 — source proof may come from a different occurrence of the same verb

bind_duration_change passes re.escape(expression[1]) to affirmative_entity_source against the entire raw_text. That helper searches every occurrence of the verb, not the one paired with the captured number.

Minimal raw_text: “甲园增加休息，乙馆增加15分钟”; incorrect selector activity_mentions=["甲园"], with both activities valid and unlocked. There is exactly one _DURATION match, the乙馆+15 phrase. affirmative_entity_source checks the甲园-containing clause and finds the OTHER增加 directly beside甲园, so it approves. The resulting SavedDurationChange still assigns甲园+15. The earlier附近 test is fixed but does not test occurrence identity.

Expected: bind target authorization to the exact captured action/quantity span and its containing source clause. Reject this malformed single-operation proposal or require independently complete operations; do not accept any same-spelled affirmative verb elsewhere as authority for the captured scalar. Add an operation-source test through approval and binding.

### P2 — the original unsupported sibling example remains unhandled

Current _VERBS still omits再待, and both _DURATION and the unsupported-expression detector depend on _VERBS. Thus the original review example “甲园增加15分钟，乙馆再待10分钟” with two replan_trip operations still yields a binding for甲园 and (None,None) for乙馆. The mixed-operation check only rejects a non-replan type, so these two replan operations can still preview with only甲园's hard goal. A sibling generic replan operation with no duration binding has the same completeness issue.

Expected: when entering the duration-only batch, require every mutation operation to have a supported complete binding or explicitly clarify the whole request. Broader replan mixtures must not become partially enforced requests merely because every operation carries the same replan_trip enum. This avoids chasing unsupported synonyms one at a time. Add the exact再待 sibling regression and a duration+non-duration replan sibling.

### P1 — partial hour-expression matches change the requested amount

New hour support matches a prefix of common compound quantities. “甲园增加一小时半” matches增加一小时 and ignores the trailing半, producing60 extra minutes instead of90. With baseline60, the new hard goal enforces120 instead of the intended150. “一小时十五分钟” similarly leaves the second duration component outside the captured expression.

Expected: parse the full quantity/unit expression or reject it as unsupported; never silently accept a shorter prefix. Boundary-check both sides and any continuation before constructing the typed change. Decimal arithmetic protects fractional-minute calculation after parsing, but does not protect against omitted quantity suffixes. Add一小时半/一小时十五分钟 negative-or-correct tests plus supported半小时 and1.5小时 controls. Also reject malformed Chinese-number mixtures rather than relying on chinese_number's permissive defaults.

Disposition remains HOLD for these current paths. No new formal writer or Accept bypass was found; the danger is that the existing hard-goal/Accept machinery faithfully enforces an incorrectly sourced or incomplete expected delta. Keep the new DB checks and extend the source/completeness tests before claiming batch acceptance.

## Follow-up: action occurrence and complete-operation corrections

VERIFIED current source and test assertions. The captured duration match now determines its containing original clause and supplies action_offset to affirmative_entity_source. The optional helper argument filters to that exact action occurrence while existing callers retain their prior default behavior. This closes both same-clause and cross-clause borrowing of a different增加 occurrence in the previously reported examples.

The duration batch now requires len(duration_changes)==len(draft.operations), in addition to rejecting non-replan mixtures. This closes the ordinary replan sibling partial-enforcement path once any duration binding exists. 再待 is now explicitly additive and the positive two-operation test checks乙馆90→100. The direct一小时半 example is now rejected and new test source preserves the source-mismatch/quantity/duplicate-target cases. Existing original Accept/goal tests remain in place.

One remaining concrete scalar boundary prevents claiming complete quantity consumption:

- Input “甲园增加一小时 半” (ordinary whitespace between unit and continuation) matches增加一小时; the suffix guard uses re.match directly on the remaining string, whose first character is a space. It therefore misses半. Quantity counting finds only one unit-bearing quantity and the binder constructs+60 rather than rejecting/representing90. The new hard goal would enforce the wrong value. Normalize only whitespace at the numeric continuation boundary and inspect the full scalar span; do not treat raw immediate adjacency as proof the quantity ended. Add spaced compound-quantity controls, including full-width whitespace.
- The Chinese-number branch still delegates arbitrary matching character mixtures to permissive chinese_number defaults. For example十半分钟 is interpreted as10 because the helper defaults unknown ones to0. A strict full-token Chinese numeral validator should reject malformed mixtures; do not reinterpret unknown text numerically. This is a robustness requirement of the claimed exact scalar contract, not a request to support every natural-language quantity.

Disposition: previous source-occurrence and operation-completeness blockers CLOSED; HOLD remains solely for exact quantity parsing/continuation before the new duration goal can be considered reliable. No additional write/Accept authorization changes found in this limited rereview.

Parent reports legacy planning tests first failed because their demo fixture required estimated routing while the wrapper prohibited estimates and no provider key was available. Preserve that failed run. A subsequent explicitly labeled legacy-unit-estimates engineering run may validate old unit/integration behavior, but cannot establish real-provider routes or the no-estimates product path. The real regression must retain its no-estimates setting; report the two configurations separately. No independent execution was performed by this reviewer.

## Latest numeric / literal-prefix limited review

VERIFIED current saved_operation_bindings.py and updated operation-binding test source. The last exact-scalar blocker is closed for the reported cases: continuation checking now lstrips whitespace, so both“一小时半” and“一小时 半” fail rather than silently become60 minutes. Chinese quantities require a full allowed numeral structure (single digit/两, valid十/tens forms),半, or a decimal token before conversion;十半 can no longer inherit permissive chinese_number defaults. Integral-minute and1..1440 bounds remain after Decimal conversion. The tests explicitly retain spaced-half and malformed-Chinese cases.

The compatibility helper `_literal_name_matches` accepts exact equality first, or a complete alias suffix whose entire preceding text matches the bounded date/time/request-prefix grammar. It does not accept arbitrary infixes, nearby-place descriptions, fuzzy substrings or address decorations. Entity selection still filters by target_day and requires exactly one entity, so same-name peers remain ambiguous rather than adopting the first. The original raw mention remains in source validation; it is not replaced by the bare stored name for authority checks. Literal temporal prefix parsing does not itself establish the target date: the existing operation scope/date parser must continue to provide and validate target_day and multi-day ambiguity. Keep the accepted prefix grammar documented as a bounded compatibility adapter, not a general place-name normalizer.

No new blocking finding in this limited rereview. Prior concrete HOLD findings in this report are now superseded by the verified fixes. Batch-limited disposition: ACCEPT the inspected per-operation duration binding and goal/Accept contract, conditional on final owner-run batch evidence. Original source/quantity/coverage counterexamples must remain regression tests. No new writer/table/direct adoption path was added, and the existing Planner→Revision→Validator→Accept chain remains authoritative.

Parent reports162 legacy planning regression passes under explicitly labeled legacy-unit-estimates engineering configuration; this reviewer did not rerun or inspect those logs. That result cannot stand in for the still-running75+15 real Worker regression with estimates prohibited. Do not freeze or claim end-to-end success until that real run and final source-stability/batch-exit evidence are recorded. No whole-product GO or independent acceptance score change.

## Real-replay follow-up: authorization, quantity query hints, preservation text

VERIFIED inspection of the three new changes and targeted test source. No source edits, database/provider execution or sealed material access. Parent-reported185 engineering passes and running real after3 not independently reproduced.

### P1 new authorization regression — explicit named revocation loses its object

The per-action absolute-offset check is an improvement for action-family precision, but affirmative_action_source now calls `_non_authorizing_context(message, match[0], start=absolute_action_position)` with quote containing only the verb. The later revocation matcher still decides object ownership with `obj in quote`. It can no longer match an explicitly named target in the original operation clause.

Minimal deterministic helper input:

`affirmative_action_source("甲园增加15分钟，先别修改甲园", "甲园增加15分钟", "增加")`

Current result is True by code path: initial clause/quote check skips revocations; action增加 belongs to modify; later修改 also belongs to modify; obj becomes甲园, but quote is only增加, so the same-object revocation is ignored. The user has explicitly cancelled the requested modification. Existing new tests use objectless暂不修改, and historical tests use no object/它, so they do not cover this regression.

Expected False. Preserve exact action position/family AND the action's source-bound target/atomic clause when evaluating subsequent revocations. Do not reintroduce the original save-noun false revocation. Add three controls: cancel explicit甲园 rejects甲园 operation; cancel explicit乙馆 does not revoke甲园;暂不采用 does not revoke a valid modification preview. Check through validate_decision/approved_draft as well as the helper because the duration binder subsequently receives only the operation raw_text and cannot recover an omitted later cancellation.

Disposition for this new authorization change: HOLD until named-object revocation is restored. Prior accepted quantity/binding changes are not reopened.

### Quantity-to-place-query cleanup: limited acceptance

The new cleanup runs only when all semantic operations have server-grounded duration bindings and no place_mentions. It removes only requested_place_queries exactly equal to scalar text captured from those same operation sources. It does not remove unknown hints, alter the source message, rewrite operation targets or create identities. This is an appropriate correction of the legacy增加X extractor misclassifying15分钟 as a place. Downstream policy still evaluates ambiguities, so this cleanup cannot authorize an otherwise rejected operation. Keep exact-string/complete-binding gating; do not broaden to arbitrary numbers or remove actual duration-containing venue names.

### Preserve-current-fields projection: limited acceptance

is_context_only_statement now recognizes a full closed grammar of known saved field names plus保持原样/不变 variants. The fullmatch excludes new numeric values, unknown subjects and modification verbs. It leaves source text intact for current-operation constraints while preventing a duplicate durable preference record. Tests distinguish the observed preserve-only clause from个人偏好改为不喝酒 and预算最多100元保持原样. No new preference writer or broader suppression of unknown requirement text is introduced. Preserve-only recognition is not evidence those constraints were actually satisfied; candidate/Accept validation remains responsible for that.

Retain failed real after1/after2 and intermediate regression artifacts. A successful isolated after3 must still separately show delta correctness, no unrelated preference/requirement mutation, unchanged source during the run and explicit adoption behavior. No full-product GO or independent-score claim.

## Final authorization-only follow-up

VERIFIED current authorization source and targeted test assertions. The explicit named-object revocation regression is closed: each exact action occurrence still determines its action family and absolute position, while action_context retains the original source quote for subsequent explicit object matching. Tests now assert same-target甲园 cancellation rejects and different-target乙馆 cancellation does not revoke a甲园-only quote. The earlier保存版本 noun no longer acts as modification/adoption authority.

For modify only, blanket先不/暂不/先别 rejection has been removed from the whole-quote pattern; actual negative prefixes and subsequent matching action revocations remain checked at the precise action occurrence. Hypothetical-only/discussion and explicit不要修改/不要安排/不用修改 exclusions remain. Thus a full quote containing a positive preview modification plus暂不采用 can pass without granting adoption, while暂不修改 still cancels the modification. Create retains its prior whole-quote block rules. The full-quote暂不采用 test and prior暂不修改 control document these intended distinctions.

No new blocking authority finding in this limited rereview. LIMITED ACCEPT for the inspected authorization repair; the earlier P1 named-revocation HOLD is superseded. Continue to require approved_draft's per-operation source/affirmative validation and the duration action-offset target checks: the top-level quote gate alone is not proof that every operation is authorized.

Conservative limitation: action_context is the whole supplied quote. If that quote contains multiple named objects, a later named cancellation may cause broader rejection because the object's name occurs somewhere in the quote, even if it belongs to another independent action. This can reduce completion, but does not grant extra modification permission. Do not describe the helper as a complete per-object semantic parser; per-operation exact source remains the stronger boundary.

Parent-reported regression7=185 passes and legacy read-only profile success have not been independently executed here. Preserve intermediate import/expired-timestamp failures as fixture/execution evidence with their actual causes. The running real after4 still needs source-stable result, exact duration and unchanged unrelated formal/preferences evidence before batch exit. No product GO or independent-score change.

## Final prefix-only adoption review

VERIFIED the latest commands.py diff is exactly one prefix-alternative addition: 明确 joins the existing请/确认/同意等 lead-in words for the adopt/discard full-clause grammar. No action verb, target grammar, suffix, neutral-clause set, future-approval rule, source uniqueness or inquiry/quotation/negation validation was removed. The same prefix is shared by discard; “明确放弃…” is consequently recognized only through its existing explicit discard grammar, not as adoption.

The positive test invokes explicit_revision_adoption with “明确采用当前这份修改候选并保存。” Negative test source covers是否,解释,等我确认后 and不要 prefixes. Each still fails the full-clause/actual-current-request checks. Matching the prefix alone does not issue a command.

bound_adoption_context still requires an existing revision_id and revision_hash, invokes explicit_revision_adoption, and changes only the existing action_target.operation to accept_plan. This narrow diff does not select a newer revision, synthesize IDs/hash, relax versions, bypass review completeness or alter the original Accept validation/locking/idempotency chain.

Disposition: LIMITED ACCEPT of the 明确 prefix addition; no new blocking finding in this requested single-change review. Parent-reported regression8=187 and real after5 75→90/review-complete/read-and-pause results were not independently inspected here. Preserve the failed natural-adoption record. The running after6 must regenerate and adopt within one recorded source-stable chain before claiming that end-to-end public regression succeeds. No whole-product GO or independent-score update.

## Latest route / explicit-activity-scope review

VERIFIED current _duration_change_result, preserve_out_of_scope_activities and validate_candidate_plan scope/route checks. No execution, source modification or sealed material access.

The new explicit_activity_scope condition correctly treats grounded.duration_changes as activity-specific: omitted peers are restored through the existing planner projection, and represented peers cannot silently change saved activity fields in the original validator. Re-presenting a peer with altered duration/time/place/cost is still rejected rather than silently overwritten. Protected execution/locked activity handling remains the existing separate path.

For routes on selected target days, the new hard goal maps candidate references back to saved activity IDs and compares the mode against the same saved endpoint pair, falling back to the saved day route_mode when no prior leg exists. Unresolved endpoint identities or missing mode reject. Existing validator independently checks leg count, ordered endpoint structure, mode agreement with destination activity and travel-time feasibility; a missing route cannot evade validation merely because the new loop only visits present legs.

### P2 blocking boundary — non-target-day transport changes are skipped

The new mode check builds `days` from scoped['days'], which contains only goals.target_days, and immediately continues when a proposed leg belongs to another day. Existing explicit_activity_scope compares saved Activity fields but not CandidateActivity.transport_mode_to_here. The original route structural validator only requires proposed leg.mode == proposed destination.transport_mode_to_here, not equality with the saved mode.

Minimal2-day candidate: user requests only day1甲园+15 minutes. Keep every activity on day2 identical in place/start/duration/cost/lock, but change day2 destination CandidateActivity.transport_mode_to_here fromwalk todriving and its corresponding leg.mode todriving, with otherwise valid provider evidence and feasible timing. New duration goal skips day2; activity-scope comparison sees no formal activity difference; original route structure sees consistent driving. Thus unrelated day2 transport can change even though the request is duration-only and peers are protected.

Expected: reject unapproved_transport_change for any preserved day whose saved endpoint pair changes mode. Apply the duration-only mode guard across all retained days (while duration/activity-delta checking can remain scoped), or add equivalent out-of-scope route-mode preservation to the existing validator. Add this cross-day test, plus unchanged-mode refreshed-provider metadata control. Do not merely assert that the target-day mode test proves whole-trip transport preservation.

Disposition: HOLD the new route-preservation contract for this cross-day hole; target-day protection and explicit Activity scope themselves are sound. Previously reviewed source/duration authority remains unchanged.

Reported after6/followup2 outcome distinguishes business facts from route-row identity: same588m/8min/walk can coexist with refreshed row IDs/timestamps/provider labels. That should be reported as unchanged route facts with refreshed route records, not all route tables unchanged. A new source-stable after7 is still needed after the final patch. Parent-reported187 regression passes were not rerun by this reviewer. No product GO or independent acceptance score change.

### Implementation guidance requested while after7 is running

Changing only the route guard's days map to all context days is insufficient: its refs map currently comes from the scoped proposal.activities and bound_ref tests membership in scoped old. A legal non-target-day candidate ref would then resolve to None and fail. Keep scoped structures for duration differences, but construct separate route identity structures from full snapshot.activities and every saved Activity in context.days. Use the full context day map for route-mode checks, preserving the original validator's date/endpoint structure validation.

Checked Accept assignments: CandidateActivity.transport_mode_to_here is not written to Activity or DayPlan.route_mode. It is an incoming-route planning field, consumed by route validation; actual persisted modes come from snapshot.route_legs. Therefore a first/no-incoming-leg activity's unused mode field does not itself create a formal transport change. There is no need to invent a leg merely to validate it. Do not claim all candidate mode fields are byte-identical; claim persisted route modes are preserved. For activities with incoming legs, existing structural validation requires leg mode to equal that destination field, so checking every persisted leg's saved endpoint-mode is the relevant boundary.

The existing preserve_out_of_scope_activities function only appends missing preserved peers. It does not replace candidate rows that already name a saved peer; an explicitly proposed out-of-scope change remains present and is rejected by validation. Restoring an omitted peer is deliberate existing deterministic preservation semantics, not hiding a mutation that will be adopted. Keep original model draft/normalized candidate in trace evidence when reporting the model's behavior, and keep validator scope checks after this projection. Protected-item normalization remains governed by the separate existing execution/lock invariants.

## Final cross-day route guard review

VERIFIED final patch: route refs now come from all snapshot.activities, the date map from all context.days, and route_activity_ids from the full saved activity set. Scoped duration-difference checking remains unchanged. This closes the reported non-target-day mode hole without incorrectly rejecting valid non-target-day candidate references merely because they are outside the duration day.

The added test source builds a second preserved day, changes both its candidate incoming transport fields and route leg todriving, asserts unsatisfied, then restoreswalk and asserts satisfied. It uses the saved day route_mode fallback (the synthetic second day has no prior route legs); same-endpoint prior-mode comparison is also present in implementation and the existing target-day mode test. This is a goal-check regression using a detached synthetic second-day projection, not an independent full cross-day Accept/physical DB state experiment. Describe its evidence at that level.

Unknown route dates still continue in this helper, but the existing candidate-date/route-set structure validator remains required and owns rejecting routes outside valid trip/activity dates; this helper is not a standalone route legality validator. Original mode/endpoint, feasibility, version, source-target and Accept guards remain intact. Refreshed provider metadata does not itself establish a transport change.

Disposition: LIMITED ACCEPT of the final cross-day route-mode preservation patch; the prior route HOLD is superseded, and no additional blocking finding was identified in this final requested review. regression10 was still running in the request and is not asserted as passed here. Preserve the reproduced pre-fix failure artifact and finish the final source-stable real chain/batch exit before any broader completion claim. No product GO or independent-score change.

## Final read-task parser-metadata repair review

VERIFIED the new metadata_only branch, existing one-attempt protocol-repair path, SAVED selector instructions and positive/negative test source. Scope: saved Trip with read_coverage and no unsaved candidate; intent=itinerary; nonempty read_tasks with no substantive top-level write/memory payload; absent/empty root capabilities; only root extra-field errors forconfidence/parser/parser_version. Confidence is restricted to an actual int/float in0..1 (bool excluded); parser/model and parser_version/v1 are the only accepted representations when supplied.

The repair request computes required_representation by retaining recognized fields exactly. It does not insert root capabilities, infer a task, replace a source span, add a budget, manufacture IDs or supply adoption authority. The model must visibly return that same JSON, followed by wire validation, Pydantic validation, exact normalized JSON equality and ordinary validate_decision provenance/policy checks. Malformed nested tasks may reach the second call if the initial wire validator stops at extra root fields, but cannot be accepted because strict validation still fails; no silent repair loop exists. One total selection deadline and one repair attempt remain.

The new positive test uses the actual three misplaced metadata fields with omitted root capabilities and verifies two calls, original invalid payload visibility and client closure. Negative source tests reject an unknown budget field, nonnumeric confidence, unknown parser and a memory update. Existing equality tests still own rejection of any changed recognized field or new capability/action.

SAVED instructions now put planning metadata explicitly inside planning_draft and prohibit it on read roots. The additional literal ordinal/source guidance is consistent with the already-reviewed server resolver; it does not itself grant target authority.

Disposition: LIMITED ACCEPT of the new read-task-only metadata recovery branch; no new blocking finding. This acceptance applies to the new omission-of-root-capabilities branch, not a new claim that every historical repair case accepts only these three metadata fields. Existing explicit-itinerary repair policy remains unchanged by this patch. Preserve the real after8/followup4 schema failure and its causal record; regression11/after9 still require completion evidence. Do not combine earlier successes into a same-source complete chain or revise independent acceptance scores. No product GO.
