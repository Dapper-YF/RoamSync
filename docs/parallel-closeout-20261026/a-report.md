# Lane A: new-city candidate generation (2026-10-26)

## Status and scope

Development result: **limited pass for two real provider candidates; overall product remains NO-GO**. Worktree `E:/Study/RoamSync-closeout-a-candidates-20261026`, common WIP base `8e53fd68d91720f1cf1674a97483e67f9bff8bf3`. No official-source edit, deployment, production DB access, new table or public writer. Original Planner → Revision → Validator → Accept authority remains unchanged. This lane does not claim a browser chain, actual adoption, a new sealed score or formal acceptance.

## Before failure and cause

- Historical public real4 (`E:/Study/RoamSync-stage6-evidence-20261025/batch3-public-real4.json`, source commit `48d1b04`) returned a `needs_input` Nanjing candidate after the user specified “鸡鸣寺路1号的鸡鸣寺”. AMap's actual search result was **古鸡鸣寺**, at **鸡鸣寺路1号钟山风景名胜区玄武湖景区内西南侧**. There was no exact name/alias match. The unresolved visit was still rendered in a candidate, clearly blocked from adoption, but without presenting the provider's full identity for a productive confirmation.
- The same historical capture rejected Xiamen because the selector's `candidate_command.source_quote` omitted the generating prefix. The common WIP base already contained `bind_generation_source`: it can replace a unique literal child span only with an independently supplied, uniquely located, valid parent generation quote. This lane tested it but did not broaden it.
- Before the code change, new `test_search_name_mismatch_requests_provider_identity_instead_of_guessing` failed with `Failed: DID NOT RAISE <class 'ValueError'>`: `resolve_plan` returned an unknown identity after a provider search for 鸡鸣寺 produced 古鸡鸣寺. This is the direct local reproduction.

## Change and negative boundaries

When a required visit has no exact provider name/alias match, `resolve_plan` now surfaces fresh, city-matched attraction search results containing the query, with their real provider names and addresses, and requests explicit confirmation. A partial name match or search ranking never binds an ID. Non-attraction results such as 鸡鸣寺(地铁站) are excluded from the prompt. A later explicit user statement naming 古鸡鸣寺 and its full address can pass the existing source, identity and preparation checks. No alias is hardcoded, and no unknown input is removed or silently corrected.

Targeted tests cover the former unknown result, explicit canonical confirmation, exclusion of the station, and generation-source uniqueness/denial controls. No changes were made to B-owned selector/contract files; the common WIP source binder remains their integration responsibility.

## Verification

`run_tests.py` was copied to the A evidence directory and repointed at this exact worktree and `roamsync_s6_a_fixture_test` on 127.0.0.1:15435. It uses Windows `SelectorEventLoopPolicy`. Final targeted command ran six candidate test modules: **92 passed, 0 failed**; two Python deprecation warnings for the event-loop policy. `git diff --check` passed. The first attempt to start live verification failed before DB creation because the dedicated PostgreSQL container was recovering after an interrupted shutdown; retry ran after its ready log. That environment failure is retained in `docs/evidence/parallel-closeout-20261026/a/preflight-recovery.txt`, not counted as a product pass.

The copied `run_public_empty.py` rejects every app root except this A worktree, requires a `roamsync_s6_a_` DB name, and refuses an existing DB or output. Live capture used newly created `roamsync_s6_a_live1_test`, real GLM selector (`glm-5.3-flash`) and AMap, with settings read from the official `.env` without printing keys. It used the public inputs in `candidate-public.json`, adding a natural third Nanjing confirmation after the provider ambiguity. No place facts or candidate rows were seeded. The capture's app source hash before/after is identical: `64434a9b16975bc31d9a5e8c9e89948857cdf6640d55c607478579b5617c2bf8`.

| Turn | Seconds | Observed outcome |
|---|---:|---|
| Nanjing 1 | 12.621 | Multiple 玄武湖 identities presented; no candidate saved. |
| Nanjing 2 | 13.096 | Actual AMap 古鸡鸣寺 name/address presented; no candidate saved. |
| Nanjing 3 | 12.437 | `ready` preview: 玄武湖景区 and 古鸡鸣寺 both have provider refs; 2026-11-21, 10:00–18:00, lunch 12:00–13:00, walk route 3550 m / 48 min. |
| Xiamen 1 | 13.127 | `ready` preview: 南普陀寺 and 中山路步行街 both have provider refs; same date/window/lunch/walk, route 3085 m / 42 min. The unique generation parent quote was bound successfully. |

Across every turn, the eight formal business tables (Trip, DayPlan, Activity, TripPreferences, TripArrangementItem, RouteLeg, PlanningRun, PlanRevision) had count zero and unchanged row hashes before/after. Both successful presentations have empty blockers and `stage=ready`; neither was adopted. Full model input/output, AMap tool results, selected decision, pending presentation, per-turn formal state and elapsed seconds are in `docs/evidence/parallel-closeout-20261026/a/a-live1.json` (SHA-256 `a98b536dc5898d638e372610a78ffd4ceb79bfbef3c3a4b9c65d1ba0d9c0c235`). Public fixture SHA-256: `c6f54acea2bab01d7db323a5e9db471679d8eaa8159bc834fdea1104278fae6c`. The JSON and harness files were explicitly checked for Git tracking.

## Remaining issues for coordinator

The provider confirmation list can include multiple attraction sublocations; the user must select the full name/address, and no selection is inferred. Routes are provider estimates; opening/onsite status is unverified. The successful previews were direct service calls on a fresh DB, not a fresh browser journey or actual Accept. Integrate this product commit into the isolated integration branch and official source per the coordinator plan, then measure same-source final gates. Preserve the common WIP's original `public-real4` failure as regression evidence; these new turns are development evidence only.
