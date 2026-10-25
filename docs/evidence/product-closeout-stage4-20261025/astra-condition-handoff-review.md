# Independent condition handoff review

Date: 2026-10-25. Scope: current uncommitted `assistant_memory.py` candidate_scalar_updates, its `assistant_turn.py` call, `read_references.py` argument_in_read_scope change and the two stage4 test increments in isolated checkout `E:/Study/RoamSync-product-closeout-stage2-20261024`.

Current latest-increment verdict: **No remaining blocking finding in the reviewed scalar-source counter revision**. The date grammar mismatch reported below is fixed by the shared scalar_tokens function. Review tools and official venv worked normally; this was not a quota-blocked review. This conclusion is limited to the reviewed increment and controls, not the entire pre-existing semantic system or actual product/browser success.

## Latest scalar_tokens revision: final scoped verification

VERIFIED: candidate_scalar_updates counts all affirmative scalar-bearing sources using scalar_tokens before invoking _quoted_scalar for plan equality. _quoted_scalar uses the same tokens, including absolute dates, relative days and 周/星期 forms. Extracted numeric/unit matching and date-substring exclusion preserve the previous validator syntax. Literal-field and selector-update precedence remains unchanged.

MEASURED with the official venv: all five directly invoked condition-projection functions passed, including the full-turn quote, conflicting/repeated sources, mixed 11月9日 plus 下周二 rejection, and affirmative 下周一 recovery. Eight additional date/duration/party-size grammar, mismatch, multiple-value and negation controls passed; a mixed absolute/weekday source produced two tokens as expected.

Final helper file SHA256 (assistant_memory.py): `fcc9135bb8b7b7575318afbf50956b0a9790120e73d55d1c44051c3c61a182f8`.
Final condition test SHA256: `fd15e1ffe9af44f25d55374c5bb12f8cddf11c6b38ebd3f5921325e90993d801`.

No product edit, DB write, provider call or sealed-case access was performed. Real after11 failure and non-frozen full-v5 results remain historical evidence; this review does not replace pending v6 runtime/freeze validation.

## Post-85851dd implementation review

MEASURED: five direct condition-test functions and four additional full-quote explicit-date/display controls passed. The implementation counts source clauses before matching against the plan value, correctly retaining explicit 11月9日 beside a nonscalar preview and rejecting competing/repeated explicit date sources.

Blocking mismatch: source existence uses assistant_operation._quoted_dates, which omits weekday forms supported by the final _quoted_scalar validator. MEASURED with today 2026-10-25: `请生成11月9日的候选，展示下周二的方案` incorrectly emits start_date 2026-11-09 because the second date source is invisible to the counter. `请生成下周一的候选，展示方案` with plan start_date 2026-10-26 emits no update. Reuse the same date-token grammar for source presence and final scalar validation; retain counting before equality. Add both controls.

Reviewed helper file SHA256: `5c10d6b6941fabbe777bda9b91d265153e96e40ba180fbd4e83397ce47ead52a` (assistant_memory.py). Condition test file SHA256: `a2e6d1769a5a894d7ab4741bfc8753c1bb8c208a625728440239d9c969468a9a`.

Parent corrected engineering evidence: full-v5 executed 2018+38 tests but run.json recorded source_unchanged=false due to a test addition during execution. This is parent-reported context, not reviewer-observed frozen verification, and must not be presented as a frozen engineering pass. Real after11 failure remains preserved; v6 is pending.

## Final revision verification

MEASURED using official venv and isolated checkout imports: five direct pure test calls passed (positive failed-place date handoff; current-source/mismatch controls; date/day same-turn withdrawal including companion clauses; inquiry/explanation/negation preservation; decorated identity and alias/address constraints). Both in-memory route-port variants passed, confirming an unchanged verified address can route while a changed retrieved address cannot. Nine additional literal withdrawal controls passed, including hypotheticals, quoted speech, negation, inquiries, and affirmative standalone declarations.

VERIFIED by inspection: withdrawals now require a complete literal declaration clause and retain question marks, while current_user_evidence_reason continues to reject hypothetical/quoted sources. Scalar recovery adds only fields not already owned by literal extraction or selector updates, uses the uniquely affirmative generation clause and exact scalar validation, and creates no formal write authority. Identity fallback preserves normal alias canonicalization while rejecting loss/substitution of explicit current address constraints; fetched route identities are rechecked before use.

Final reviewed SHA256 values:

- assistant_memory.py: `8d48d39d26f9d9d14cee5d99efc9d4a4ccf60feef490e83018f9d97da6d006f1`
- assistant_turn.py: `c4cf766a264c6005e465c0b283060a358bfe881aca3904a5473965f6cc9dd9b5`
- read_references.py: `d98c80b2a4e2a73fa1f638621721ca74ad36ad0c4df79d515e96e3dd63c48b3f`
- assistant_capabilities.py: `422f43123cee415665f91873f5d40c0ee1ead9d112f7d517501538952ec776eb`
- test_stage4_condition_projection.py: `1be8cb29080238f2ac886766f2de70a8341f01c33c3c635428f15bf8e726f915`
- test_stage4_task_contract.py: `10df961f6436d342c05c02d86953f733009c08e6821b8aee837739c7c40cf215`

No product edits, DB operations, real provider calls, official-source changes, deployment, or sealed-case/rubric access occurred in this review. Full regression and real v5 validation remain with the parent agent.

## Design pre-review after commit 85851dd (not implementation approval)

Parent reported actual after11 full-turn command quote contains both `请先生成成都11月9日的一日候选` and `先给我看方案`. Reading 85851dd confirms that every affirmative ACTION_VERBS['generate'] clause participates in the single-source count, so a display clause without any scalar can prevent date recovery. This review did not independently execute the real after11 request.

Proposed narrow change is sound in principle: determine uniqueness independently for each scalar field among affirmative generation clauses that actually contain that field's literal evidence. A clause with no date/duration should not increase either field's count. Keep validate_command, current source, literal-field ownership, selector-update precedence, and the final exact-value check.

Critical implementation condition: count scalar-bearing clauses **before** filtering for equality with the model plan. Using `_quoted_scalar(key, proposed_value, clause) is not None` to select candidate clauses is insufficient: with 11月9日 and 11月10日 in different affirmative clauses, a plan proposing 11月9日 must not make the conflicting 11月10日 disappear. Count all supported literal evidence for that field, then require one source and one compatible literal. Repeated equal-date sources remain ambiguous under the parent's stated fail-closed rule. Multiple same-field tokens inside one clause must remain rejected by the existing scalar validator.

Recommended focused regression matrix (source_quote must be the entire message unless testing a shorter source explicitly):

1. Positive real shape: `请先生成成都11月9日的一日候选，人民公园和宽窄巷子，先给我看方案，不要保存` retains 11月9日 after the normal two-stage memory pipeline.
2. No-scalar display controls: prepend/append `展示候选` or `先给我看方案`; do not lose otherwise valid date evidence.
3. Conflicting date sources: `请生成11月9日的候选，展示11月10日的方案`; no start_date fallback for either proposed date.
4. Repeated same date sources: `请生成11月9日的候选，展示11月9日的方案`; no start_date fallback under the unique-source rule.
5. Multiple dates inside one source: `请生成11月9日或11月10日的候选`; no start_date fallback.
6. Different fields in different affirmative clauses: `请生成11月9日的候选，展示一日方案`; preserve independently verified fields through the existing literal-first pipeline, without joining quotes into invented evidence.
7. Full-turn companion case: `请生成一日候选，朋友11月9日生日，先给我看方案`; no start_date fallback. Existing hypothetical/reported, negation, plan mismatch, and same-turn clear cases must still pass with whole-message command quotes.
8. Conflicting duration sources should not produce new candidate fallback updates. Inspect existing literal extraction separately: the candidate helper must not overwrite any field it already owns, even if that means this narrow fix does not change an older literal-extraction behavior.

No product edit or new runtime measurement was performed for this design pre-review. A subsequent implementation requires its own diff and test verification; the earlier approval applies only to the recorded previous file hashes.

## Revision review, third pass

MEASURED: directly invoked the pure positive date-handoff test, source/mismatch/negative controls, same-turn date/day withdrawal combinations (including 朋友), and decorated-reference/address-conflict tests; all passed. Invoked the route adapter test with its entirely in-memory Port for both unchanged and changed retrieved address; both passed. No real provider or database was used.

One new blocking regression was found in the extracted literal_withdrawals path: with an existing start_date 2026-11-09, either current message `是否取消日期？` or `请解释取消日期是什么意思` produces a start_date clear and apply_memory removes the existing date. Previously literal_conditions' early inquiry/explanation guard returned before withdrawal extraction. current_user_evidence_reason protects quoted/reported/hypothetical evidence, but does not establish that an inquiry is an actual withdrawal instruction. Retain that distinction at the withdrawal clause boundary. Controls `朋友说“日期待定”` and `如果日期待定会怎样` correctly preserve the date.

## Revision review, second pass

MEASURED: same-turn date clear and day-count clear now remain absent after both memory stages; independent companion birthday/arrival clauses no longer supply start_date; the affirmative 11月9日一日 example still retains both correct scalars. The initial direct-name parentheses conflict is rejected, while the intended deictic history-address lookup remains allowed.

One address-provenance finding remains in this revision: the conflict check scans only the proposed base name with parentheses, but fallback binding uses all historical aliases. With historical 拙政园 / alias 甲园 / address 东北街178号, current source `从甲园（东北街179号）到狮子林查步行路线` and proposed value `拙政园（东北街178号）`, argument_in_read_scope still returns True. Current source `从拙政园地址东北街179号到狮子林查步行路线` also returns True for the proposed 178 address. These are current explicit conflicting address qualifications; neither should authorize replacing them with the historical 178 identity. The latter is an address form already recognized by literal_search_subject. Requested fix: align conflict handling with the aliases and address syntaxes supported by the existing provenance resolver.

The newly expanded route_answer adapter rechecks fetched place ID, city and subject/address, and filters a base-name search result by the full decorated subject. Those guards improve provider-result safety, but cannot reject the wrong current argument once the earlier source validator accepted historical 178. No external route request was made by the reviewer.

Additional MEASURED combination: message `请生成成都11月9日一日候选，和朋友一起，日期先待定`, command quote the first clause, still emits start_date 2026-11-09. Existing literal_conditions returns early for a whole-message 朋友 token and skips its later clear extraction, so the new cleared-field set is empty. A control with `我和妈妈同行` retains the clear. This is an existing extraction weakness newly relied upon by the recovery; the new operation must not restore an independently withdrawn date because a separate companion clause is present.

## P1: A literal clear earlier in this same turn is overwritten

MEASURED pure function chain matching semantic_turn's ordering:

- Message: `请生成成都11月9日一日候选，日期先待定`.
- Candidate generate source_quote: `请生成成都11月9日一日候选`; valid one-day plan with start_date 2026-11-09; decision.memory_updates empty.
- First `apply_memory(... literal_conditions(message))` leaves start_date absent and records its withdrawal.
- `candidate_scalar_updates` emits start_date 2026-11-09 because it checks only decision.memory_updates for competing operations.
- Second apply_memory restores start_date and removes the withdrawal. The explicit current clear has been lost.

The caller already has the effective envelope and literal_changed; the new recovery must respect accepted same-turn clear operations, not only model-proposed patches. Add a test through both apply_memory stages with selector memory_updates empty. The existing clear test supplies an explicit selector clear and therefore misses the real omission case.

## P1: An unrelated companion date becomes the trip start date

MEASURED message and whole-command quote `请生成成都一日候选，同行朋友11月9日生日`, plan date 2026-11-09: command validation succeeds, candidate_scalar_updates emits start_date 2026-11-09, and apply_memory accepts it as a trip scalar. Likewise `请生成成都一日候选，妈妈11月9日到成都` supplies an unrelated person's arrival date.

The command validator proves affirmative generation authority; it does not prove every scalar within the quote is a condition of that trip. _quoted_scalar proves the single date token equals the proposal, but does not identify whose date or which event it describes. Since model plan allocations must not become scalar evidence, require a date bound to the actual generation/travel clause; do not recover a scalar from a separate companion birthday/arrival clause merely because it matches the model plan.

## P2: Historical decorated identity overrides a conflicting explicit address

MEASURED places: historical 拙政园 address `东北街178号`, plus 狮子林. Current source: `从拙政园（东北街179号）到狮子林查步行路线`. Proposed argument: `拙政园（东北街178号）`. New argument_in_read_scope(..., capabilities=['poi','route']) returns True. Previous exact-membership fallback did not allow this decorated argument.

subject_matches_place correctly validates the proposed value against the historical card, but the following bare-name occurrence check allows a conflicting current decorated name to donate provenance. Keep the intended `前一个/后一个` case, but reject the historical decorated argument when current explicit address qualification contradicts it. A current literal wrong address may remain a search subject pending provider validation; that does not authorize substituting the history address.

## Other inspected boundaries and limits

- No new formal writer, adopt command, or authorization field is introduced by this increment. Scalar memory is data and must still pass existing planning/write authorization later.
- candidate_scalar_updates verifies create/generate/plan, current unique source and validate_command, quote length <=300, and equality through _quoted_scalar; historical-only dates, hypothetical/reported commands and mismatched plan dates are excluded by those gates in the covered shapes.
- The per-message captured date is reused by the caller, preserving the existing midnight anchor behavior.
- Correct deictic decorated place argument returns True; incorrect proposed address returns False when source contains only deictic references. The reverse conflict described above is missing from current tests.
- All probes used official `E:/Study/RoamSync/backend/.venv/Scripts/python.exe` with isolated backend imports. No DB operation, provider request, official-source edit, product edit or deployment was performed. No sealed cases/rubric or Obsidian files were read or changed. Parent owns targeted/full tests and actual browser verification.
