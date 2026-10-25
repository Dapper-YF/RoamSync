# Stage4 visual goal contract independent review

Date: 2026-10-25. Reviewed the uncommitted changes in `backend/app/assistant_capabilities.py`, `backend/tests/test_stage4_cross_city_visuals.py`, and the subsequently requested `backend/app/read_references.py` expression change in `E:/Study/RoamSync-product-closeout-stage2-20261024`.

Final verdict after revision: **No remaining blocking finding in this reviewed increment**. The initial findings below are retained as historical evidence and were fixed by the parent agent. This is a scoped contract-review conclusion, not product acceptance or browser/image success.

## Final revision verification

MEASURED: ran external `astra_visual_goal_probes.py` with the official venv and isolated checkout on PYTHONPATH. All six probe results passed: denied address, explicit photo target, cross-city equal name, invalid source, and two explanatory denials. Each of the first four probes validates three times, compares full task signatures, checks the five-task ceiling and checks absent candidate/planning/write authorization fields.

VERIFIED by inspection: `requested_visual_subjects` is shared with final image projection and narrows existing names; newly recovered POI arguments additionally pass `argument_in_read_scope(..., capabilities=['poi'])`; coverage compares city before comparing literal subjects; explanation negation includes 解释/了解/知道. Name preservation remains downstream of task-local source validation. No product edits were made by this reviewer.

Reviewed final file SHA256 values:

- `backend/app/assistant_capabilities.py`: `2066b533a8afe1ced9f229f3ee7e9e5f52c6f0abb46a56dc37ddc52b5017bb7f`
- `backend/app/assistant_images.py`: `cb0f070a05a2486abf4c0e01db762315058ec2d2900eadeeb1a2bc046b2af443`
- `backend/app/read_references.py`: `da6788a83b7fe0893b50fcaaf363381739887b45661b487c0decb4eee61ac469`
- `backend/tests/test_stage4_cross_city_visuals.py`: `f6cc77d829ac6055fd0358a4d72762e241bd19572aa9ef19fc91bc1c0b1e887a`

Residual scope: visual target projection still represents names rather than a complete city-plus-place identity. This review proves the supplied separate-city lookup obligation is retained; it does not establish accurate provider imagery for same-named places in multiple cities. Actual image/provider/browser verification remains necessary as already planned by the parent agent.

Initial verdict before revision: **Changes requested**. No new formal-write authority was observed, but the new photo identity recovery bypassed a read-denial boundary and was not idempotent on that input. Cross-city identity deduplication also lost an explicitly requested target.

## Findings

### P1 — Photo recovery must validate the derived POI operation, not inherit direct-read permission

Location: `assistant_capabilities.py`, new `if image_requested(message)` block (approximately lines 514–524).

MEASURED with the official venv, isolated checkout imports, pure `validate_decision` calls:

- Message: `介绍苏州拙政园，拙政园地址不要查，只给狮子林照片`.
- Input task 1: source `介绍苏州拙政园，拙政园地址不要查`, no capabilities, city 苏州, names `[拙政园]`.
- Input task 2: source `只给狮子林照片`, capabilities `[web]`, city 苏州, names `[狮子林]`.
- First validation adds an executable `[poi]` task for 拙政园 despite the explicit denial and despite the visual request naming only 狮子林.
- Second validation correctly blocks that old POI task through `argument_in_read_scope(..., capabilities=['poi'])`, then appends a fresh executable POI task for 拙政园. Task count grows from 4 to 5.
- Third validation blocks the second copy and raises the maximum-task clarification. Task count remains 5, but the original two-goal request has accumulated rejected duplicates.

The fresh derived tasks are appended after the validation loop. Direct explanations and POI reads have deliberately different negation rules, so source-validated direct names do not establish authorization for the derived POI operation. `_identity_only` does not make this harmless: it still triggers the real place adapter. Fix by scoping visual targets and passing newly derived POI reads through the existing operation-specific source/negation boundary before appending. Test repeated validation at least three times, comparing task contracts rather than only `len <= 5`.

### P2 — Photo identity coverage ignores the city

Location: same new block, `literal_subjects_cover` coverage test.

MEASURED input message `查上海中山公园地址，给我看北京中山公园照片`, with a 上海 `[poi]` task for 中山公园 and a 北京 `[web]` task for 中山公园, each bound to its literal clause. Validation never adds the required 北京 POI task because the 上海 task's equal name satisfies coverage. Repeating validation three times preserves the omission.

An equal literal name across two explicitly different cities does not cover the same lookup obligation. Require matching effective city in this deduplication; retain the existing address-decoration rules within that scope. Downstream use of the wrong city's card is an inferred risk, not a measured provider outcome in this review.

### P2 — Broad visual switch adds lookup subjects outside an explicit photo target

MEASURED message `比较苏州拙政园和狮子林，只给狮子林配图`, with a two-name comparison web task and a 狮子林 photo web task: recovery creates a combined `[拙政园, 狮子林]` POI task from the comparison. The new test covers final image projection but does not assert the derived lookup scope. This is the same root cause as P1's global image switch and consumes unnecessary lookup/task budget even without an explicit address denial. Scope recovery to positively requested visual subjects before coverage and budget decisions.

## Other checked boundaries

- VERIFIED by inspection: preserving `task.names` occurs after local-source checks and after a nested decision returning `clarify` is rejected. No UUID or place identity is supplied by this preservation.
- MEASURED: a task whose source is `只给苏州狮子林照片` but whose names contain 拙政园 is rejected, with no derived tasks, across three validations.
- MEASURED: the probes retained at most five tasks and never created `candidate_command`, `planning_draft`, or `authorization_quote`. The five-task ceiling itself holds; the P1 duplicate growth still makes the bound harmful to valid independent goals.
- VERIFIED by inspection: over-budget additions are discarded together and a clarification is recorded. This can suppress all recovered goals; no claim is made here that the existing policy changed, except that broader photo recovery makes it easier to reach.
- The added `值得看(?:什么|的东西|哪)?` form fixes the positive phrase `各有什么值得看`. MEASURED negation probes: `不用介绍拙政园值得看什么` and `拙政园有什么值得看先不要讲` return false, but `不用解释拙政园有什么值得看` and `不想知道拙政园有什么值得看` return true. This is a pre-existing verb-coverage weakness newly exposed for the shorter `值得看` form. Include explicit explanatory-denial cases before claiming complete negative-scope handling; it does not grant write authority.

## Scope and limits

Used `E:/Study/RoamSync/backend/.venv/Scripts/python.exe` for pure validation/helper probes with the isolated checkout's backend as working directory. No provider calls, browser actions, database writes, product edits, official-source edits, deployment, or Obsidian writes. Did not read sealed cases or rubric. Full and targeted suite execution remains with the parent agent. This review does not certify actual images, factual comparison quality, or browser success.
