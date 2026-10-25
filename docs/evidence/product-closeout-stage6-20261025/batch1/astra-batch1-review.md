# Stage6 batch1 saved-reference review

VERIFIED static review of current uncommitted saved_references.py, saved_trip_reads.py and test_stage6_saved_references.py; inspected handbookModel.ts and existing saved-read fixture source. No private-sealed material accessed, product edits, DB access or tests executed. Parent reports baseline3 failures and current31 passing; not independently measured here.

Disposition: HOLD batch exit for the scope/coverage issues below. This is a read-only correctness review, not a product GO assessment.

## P2 — clause splitting loses negative and exclusive read scope

render_saved_request splits the message before requested_dates sees it. Each clause containing a date is independently rendered even if negated. Example: “不看第一天，只看第二天活动” emits first-day data from the first clause and second-day data from the second. The prior requested_dates whole-message focusing for explicit 只看 is bypassed. This is not unauthorized writing, but contradicts a user's explicit read scope and can provide the wrong itinerary answer.

Resolve affirmative/negative scope at the request/task level before projection. Retain exact source and qualifiers on each goal; do not use “contains date” as sufficient read-goal authority. Tests must include excluded-day requests, quoted/contrasting date mentions, and an independent affirmative peer that remains answered.

## P2 — inherited date overrides an explicit whole-trip goal

The day_scope string persists across every following clause and is prefixed whenever requested_dates finds no literal date. Example: “第一天午餐和全程所有活动” becomes a first-day ISO date plus “全程所有活动”; project handles explicit date before all_days and therefore returns only day1. The model-independent answer incorrectly narrows a clearly global request.

Represent scope as a typed goal property: explicit whole-trip scope clears inherited local scope; explicit day/date overrides it; genuine ellipsis may inherit. Do not concatenate a date prefix that creates higher-precedence evidence than the user's own scope. Test day-local→whole-trip and whole-trip→day-local combinations, plus invalid-date parent scope followed by an explicitly global goal.

## P2 — bare ordinal can resolve despite incomplete arrangement-item coverage

resolve_activity_position receives expected_count for Activities, but no completeness information for arrangement items. If the Activity slice is complete while the item limit omits a free_window/optional row on that day, `第一项` resolves an activity as unambiguous. The caller later sets arrangement_items_complete=false, but already returns a stable target with coverage.ambiguous=false. A warning after returning the guessed identity is insufficient, especially because this module is intended for later shared write grounding.

Pass typed coverage into the resolver. Bare mixed-agenda ordinals must be unresolved when relevant item coverage is incomplete; explicit “第一项活动” can still resolve from a complete activity scope. If only trip-global item_count is available, conservative rejection of bare ordinal is safer than claiming complete day ordering. Test an activity-complete snapshot with omitted non-activity item, plus the explicit-activity control.

## P2 — unsupported multiple ordinal references silently become a broad read

activity_reference returns None both for “no ordinal” and for “more than one ordinal”. Thus `第一天第一项到第三项活动` is treated as an ordinary first-day activity read and returns the entire day; `第一天第一项、第二项` works only because the outer split happens to separate it. A shared reference parser cannot conflate unsupported/ambiguous references with absence.

Return a typed parse state (absent/resolved/multiple-or-unsupported). Preserve independent references as goals where supported, otherwise clarify the unsupported range without widening the scope. Require day resolution based on complete days/explicit scope, not the number of dates left in a truncated activity slice. A multi-day ordinal should not silently degrade into listing all rows either.

## P2 — deduplication can turn existing items into false absence

For repeated or overlapping meal/window goals, items are filtered through seen_items before the absence branch. Example: `第三天午餐和第三天午餐` with one matching saved meal renders it once, then adds “该读取范围内没有保存的对应餐饮或留白记录。” because the second deduplicated item list is empty. The item exists; it was already answered.

Separate matched_count from newly_rendered_count. An empty post-dedup list means already covered, not absent. The same separation should drive truthful coverage wording when activities are filtered or deduplicated. Add repeated and overlapping lunch/free-window tests.

## Additional parser and ordering limits

- Splitting on every 和/及/以及 is not entity-aware: literal names containing these characters can be broken and the resulting explicit-day clause can broaden a named query to the whole day. Preserve known literal entity spans or consume a validated typed goal list instead of adding a per-place exception. Example pattern: a stored activity named “和平公园” in a day-specific saved-activity query.
- Time-first ordering matches Handbook's primary sort. Handbook's equal-time tie order is its input order (stable JS sort), whereas the new resolver explicitly uses position. Verify that the API builds day.activities in position order before claiming exact tie parity. Rejecting identical time/position pairs is appropriately conservative. No UUID tie-break should pretend to establish user-visible ordinal identity.
- Bare 项 mixed with unlinked non-cancelled items correctly rejects when those items are present. Explicit 活动/景点 and 站 currently count Activities. Document that 站 is activity-only; do not reuse it to resolve an arbitrary mixed timeline position.
- Invalid day plus ordinal currently may overwrite the specific date_not_in_trip issue with activity_ordinal_out_of_range, though it still rejects. Prefer preserving the original invalid scope for an accurate clarification.
- No DB mutation or Accept path is changed in this batch. Stable IDs in returned rows and captured Trip/preferences versions remain intact. New SavedActivityReference carries literal ordinal phrase, not resolved ID or authorization; that is a suitable limited start, not the entire approved shared reference contract.

## Required batch evidence

The three new tests cover reordered chronology, same-day residual goals and visible mixed-window rejection. They do not cover the negative/global/partial-items/multiple-ordinal/dedup cases above. Add pure detached-snapshot tests for these boundaries where possible; database setup is unnecessary for parser/coverage behavior. Preserve baseline and failure evidence, then run the relevant existing read suite and actual model regression later. Passing the current31 tests does not establish these omitted contracts.

## Follow-up: after4 scope corrections and conversation focus

VERIFIED current diff and added test sources only. No DB/model calls, product edits or private-sealed material. Original concrete multi-clause denial example, direct whole-trip successor, incomplete-item bare ordinal, multiple-ordinal and duplicate-item examples now have explicit guards and regression assertions. The fixes address those cases, but two remaining saved-read scope paths and a new focus regression prevent batch acceptance.

### P2 — all-denied goals re-enter the broad fallback

For “不看第一天”, the new prefix guard skips the only clause. parts stays empty, so the final `render_saved_read(snapshot.project(message), message)` reads the denied first day anyway. The same happens when all clauses are skipped/otherwise unrecognized. A rejection/denial result must be distinct from “no specialized parse”; do not fall back to a broad saved read after a recognized exclusion. Test a single denied request and multiple entirely denied goals. Also count detection currently occurs before denial filtering, so denied total-day questions can still emit the count.

### P2 — explicit whole-trip scope is not retained for later ellipsis

whole_trip suppresses the day prefix for that clause but never clears day_scope. For “第一天活动，全程所有活动，午餐”, the third clause still inherits day1 rather than the newly explicit whole-trip scope. Track scope transitions, not merely whether to apply a string prefix on this iteration. Test local→global→elliptical meal and invalid-local→global→elliptical goal.

### P2 — new focus discards explicit subjects when any reference occurs

In place_catalog, targets uses `(referred if references else named)`. With ordered active [A,B], “前者和B比较” collects referred={A} and named={B}, then ignores B and marks A as the sole focus. A subsequent “它” resolves to A although the previous user turn had two competing subjects. “别看前者，介绍B” likewise selects A from the denied pronoun and ignores explicit affirmative B. This is a concrete cross-object misbinding, not just lack of a feature.

Build focus candidates from both named and resolved reference occurrences, retaining their source clauses. Only a uniquely supported active subject may become focus; multiple or conflicting objects clear focus. Reuse existing source/polarity validation rather than treating any regex match as an affirmative user read goal. A denied-only reference should not establish a new positive focus. For mixed denial/affirmative requests, affirmative B can focus B if validated as such; otherwise clear and clarify. Do not authorize a write from this read focus.

Required regressions: [A,B]→“前者和B比较”→“它”; [A,B]→“别看前者，介绍B”→“它”; prior focus A→denied-only B reference; multiple reference words resolving to the same A; and tool-return order B,A after a user focus on A. Preserve comparison order throughout.

### Focus identity and provenance observations

The new focus is keyed by stable place_id when available, with raw:name only for unresolved search subjects; it is reconstructed from current-topic/city cards and not persisted as a mutation. The returned `_reference_focus` flag is overwritten server-side, so a card cannot simply supply a trusted true flag. These boundaries are sound. Resolved names, however, are used as an intermediate set before IDs are selected; duplicate-name identities must remain ambiguous. A raw mention that upgrades to a stable ID can invalidate old focus (safe loss rather than wrong binding); if preserving it, migrate only through the same unique upgrade mapping. A turn about an object outside the active catalog should not silently keep an old object as the next “它” target merely because neither named nor references matched; use validated task/topic scope when detecting focus transitions, not tool ranking.

The previously documented unconditional 和/及 split through literal entity names is still present. Keep it as a known limitation to resolve via source-aware task splitting rather than city/POI-specific exceptions. The new prefix-only denial guard does not constitute a general source/polarity contract.

Disposition remains HOLD for the concrete all-denied fallback, scope transition and mixed-subject focus failures. Parent-reported successful real saved multi-goal read and unchanged10-table state are valuable bounded evidence, but not evidence that these other branches are correct. Historical product status and independent scores remain unchanged.

## Current-file review after5 (supersedes the prior follow-up's three examples)

VERIFIED reread of current source. The all-denied day fallback, explicit whole-trip→ellipsis transition, and same-clause mixed explicit/pronoun subjects described in the preceding follow-up have been corrected. The saved-read test source now includes single denied day and global-scope successor checks; focus tests include “前者和乙馆比较” and “别看前者，介绍乙馆”. These old examples are no longer findings against the current code.

Two remaining concrete paths are visible in current source:

### P2 — within-turn focus resolution uses a frozen prior-turn scope

Minimal input, with two valid same-city uniquely named persisted cards ordered [甲馆,乙馆]:

history = [comparison_of_甲馆_乙馆, {user: "介绍前者"}, {user: "介绍乙馆，再说它的地址"}]

Current control flow: turn2 sets focus=甲馆. At the start of turn3, `scoped` is built once with 甲馆 focused. The first clause finds 乙馆 and sets local focus=乙馆. The second clause resolves “它” using the unchanged `scoped`, so it resolves to 甲馆 and sets focus back to甲馆. The next resolve_read_text("它", place_catalog(history,...)) consequently returns甲馆.

Expected: 乙馆, or conservatively unresolved if same-turn pronoun interpretation is unsupported; never the prior甲馆. Recompute scoped from the current focus at each effective clause boundary (and use that same clause scope consistently for resolution/argument checks). Add this exact multi-turn test. This is distinct from the previously fixed same-clause explicit/pronoun union problem.

### P2 — negated total-day read bypasses clause denial

Minimal call: render_saved_request(snapshot, "不读总天数") for any3-day snapshot. `count` is computed over the entire message before denial filtering, so parts immediately contains “这份已保存行程共3天。” The clause is skipped but parts is nonempty, so the denied_read empty-result guard never applies. Expected: no total-day value is returned; the same denied-read acknowledgement as for “不看第一天” is acceptable.

Compute count goals only from effective non-denied source clauses and preserve positive sibling goals. Test both denied-only count and “不读总天数，只看第二天活动”. This is not a database write risk; it is incorrect obedience to the requested read scope.

Disposition: retain HOLD only for these currently demonstrated focus/source paths; do not interpret the prior superseded examples as additional unresolved findings. Parent-reported77 passing and real replay evidence are not independently executed by this reviewer. No product GO conclusion.

## Final limited review after6

VERIFIED current source for the two requested final corrections: place_catalog now rebuilds scoped from the updated focus before every non-denied clause; render_saved_request now computes count only from clauses for which read_clause_denied is false. Test source includes the exact prior-focus→new-name→same-turn-pronoun regression and denied-total-count assertion. These two outstanding concrete findings are resolved. No new blocking finding was identified in this deliberately limited re-review.

Inspected only the explicitly authorized public JSON artifacts:

- batch1-real-saved-after1.json records a real selector/answer-provider replay returning one saved day, 拙政园75 minutes, 狮子林90 minutes and12:00–13:00 lunch/free window. The artifact declares exact11-table cloning, formal_unchanged=true and source_unchanged=true, with equal before/after app hashes. This is recorded bounded public replay evidence, not an independently rerun database check.
- batch1-real-references-after1.json records three public development-regression turns: ordered 个园/何园 discussion, second-place address resolving to何园, then opening reference material alongside 个园→何园 walking route approximately2.1km/29 minutes. The opening answer explicitly says current applicability is unverified; the route identifies provider estimates and excludes on-site visiting/waiting. Artifact declares real model/selector, synthetic trip state, external_provider_facts_seeded=false, formal_state_unchanged=true and equal before/after app hashes.

These artifacts have different recorded app hashes because they are separate public runs; do not combine them as one frozen all-current-source acceptance execution. after6 test completion was still pending in the parent's request and is not asserted as passed here.

Batch-limited disposition: ACCEPT the reviewed read-reference/multi-goal correctness changes at the internal architectural boundary, conditional on the owner's after6 tests and batch exit evidence. Prior concrete blocking findings in this report are superseded by the verified fixes. No new write authority, formal adoption path or latest-pending selection is introduced. Broader source-language generality limitations noted earlier remain limitations, not claims this small batch exhaustively solves all natural-language scope. No whole-product GO, independent score revision or new sealed-test claim.

## Task reference-binding follow-up

VERIFIED current bind_read_task_reference and its call site after exact source_quote containment checking, plus downstream fact/source/identity validation and added regression source. No execution, product edit or private-sealed access.

The intended fix is sound: a unique server-owned pronoun binding may correct a model paraphrase without inventing an ID or write authority, and clearing unused free query avoids keeping a contradictory model search string. The observed positive test binds “它今天开放到几点” to the second focused place and restores its opening fact task. However the current implementation is broader than the stated single-deictic-task boundary in two concrete ways.

### P2 — an explicit user subject omitted by the model can be erased

The guard `not any(name in source for name in task.names)` means “none of the MODEL's supplied names occurs in source”, not “the USER supplied no explicit name”. Catalog scanning cannot detect a new named peer outside the current catalog.

Minimal input: active catalog=[甲园,乙馆], focus=乙馆; ReadTask(source_quote="丙馆比它关门更早吗？", names=["甲园"], fact_kind="opening_hours", capabilities=[]). The helper resolves它→乙馆, sees only乙馆 among catalog targets, overwrites names=[乙馆], clears query and upgrades facts. The explicit丙馆 comparison subject is lost. Downstream argument checks see乙馆 in the resolved source and do not prove that the omitted丙馆 goal was retained.

Expected: preserve丙馆 plus the resolved乙馆 as a comparison with separate requirements, or keep the task unresolved if the limited repair cannot establish all subjects. Never present a single乙馆 fact lookup as recovery of this two-subject question. A repair scoped to a single deictic subject must establish that source-task structure independently of the model's already-wrong names. Prefer validated source/task representation; do not add a list of special venue names. Add this unknown-explicit-peer regression and a known explicit peer case.

### P2 — capability restoration is outside successful-binding conditions

The opening-hours→facts branch executes whether references exist, whether they resolve, whether targets are unique, and whether origin/destination prevent binding. This violates the stated narrow correction boundary. Example helper call with source="它今天开放吗？", unresolved catalog focus, names=[], fact_kind=opening_hours, capabilities=[] still gains facts; a no-pronoun task does too. Subsequent validators may clarify some inputs, but the helper itself does not guarantee the limited transformation claimed.

Gate the recovery on a successful validated single-subject binding and the intended task class; exclude route tasks explicitly instead of relying only on origin/destination being nonempty. If broader recovery of explicit named opening requests is desired, specify and test it as a separate source-backed rule rather than obtaining it accidentally through this pronoun repair.

## Boundaries confirmed

- Exact current source_quote membership is checked before helper invocation. Normal subsequent validators remain; facts with hypothetical/conditional or 不查/不用查/不要查/先不查 are blocked by the existing code. The helper is not an authorization bypass.
- Tasks with populated origin/destination skip name rebinding. Existing route capabilities are not rewritten by the empty-cap branch. Nevertheless explicit route exclusion is preferable for malformed/partially extracted route tasks.
- The helper adds only names/query/capabilities, never stable IDs, coordinates, planner commands or adoption. A raw_mention with place_id=None remains a name/search requirement; it cannot become a verified route identity through this helper. Tests should assert that boundary rather than claiming the name itself proves identity.
- An explicitly supplied task name occurring in source suppresses overwriting. Two matching catalog identities cannot satisfy len(targets)==1. This preserves ordinary literal-name/duplicate-identity cases, but does not cover omitted new explicit names above.

Disposition: HOLD this new helper addition for the two scope corrections and targeted tests; previously accepted batch changes are not reopened. The real replay failure is valid evidence of a model-to-server binding defect, but neither a positive targeted test nor correct route sibling proves that a broad repair preserves all read goals.

## Final bounded helper review (after9 source)

VERIFIED reread of the final helper and added test source, restricted to the requested repair boundary. Prior helper HOLD findings are resolved within this deliberately narrow scope:

- Repair now requires fact_kind=opening_hours, exactly one recognized reference occurrence, and no residual source text beyond the declared time/property/request/question atoms. Unknown new venue names, comparative relations and adjacent-place wording leave residual text and do not trigger replacement. The original丙馆 comparison and adjacent丙馆 cases are explicitly covered by test assertions preserving names/capabilities.
- Populated route origin/destination prevents recovery. Exactly one server-resolved catalog target and argument_in_read_scope remain necessary before names/query change.
- Empty capabilities become facts only after this successful name binding. Missing/ambiguous references no longer acquire facts solely because an opening-hours word appears. Existing capabilities are not expanded by this branch.
- Hypothetical and negative example phrases leave residual text, and normal downstream source/polarity/identity checks remain in place. The new tests assert the helper does not recover either example. No ID/coordinates or write/adopt authority is created; raw unresolved catalog objects remain name-based lookup inputs.

This is a bounded repair for an observed erroneous/missing selector field, not general language parsing. The atom-stripping recognizer is intentionally incomplete: valid requests outside the supported vocabulary, explicit named comparisons, plural subjects and complex constraints may remain unresolved. Its vocabulary must not be advertised as proof of universal semantic equivalence or grown into city-specific exceptions. Preserve full current source and downstream validators; do not use this read helper for write authorization or general operation normalization.

Disposition: LIMITED ACCEPT for this helper at the reviewed read-only contract boundary; no new blocking finding in this final single-boundary review. The original positive test remains and the new negative/route test source covers the reported counterexamples. after9 execution was still running at the time of the request; no independent test pass or new model success is asserted here. Public real replay failures remain part of the evidence and no independent acceptance score or whole-product GO changes.
