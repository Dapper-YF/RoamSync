# RoamSync — Travel Facts Integration v1 / Companion Verified Forecast

2026-09-30. **CURRENT SLICE: COMPLETE.** Foundation, Companion, deterministic/PostgreSQL/full regression, real-provider forecast and production smoke gates all pass. API and worker were rebuilt/restarted with both Knowledge Coverage and Travel Facts changes. Early network failures remain in historical artifacts; they are not final status.

## 1. Starting Reality
main HEAD `5572849209c943c5f5ad1579db4cef0ba2fb5b25` unchanged; extensive dirty working tree preserved. Phase 2.5 accepted production and later Knowledge Coverage working-tree improvements were separate starting realities. Initial hashes/status and complete `5f9f5e5` diff retained in `backend/evals/results/travel_facts_integration/`. No reset/clean/stash/merge or snapshot-parent import. Audit: `TRAVEL_FACTS_INTEGRATION_REALITY_20260930.md`.

## 2. Foundation Integration Strategy
Import added-only paths from the implementation commit, byte for byte, without Git index/history mutation. All 24 paths were absent in main; no collision. Configuration, dependencies, external_facts.py, provider transports, database/migrations and core Companion/Planning were not replaced. Foundation Gate ran before Companion edits.

## 3. 5f9f5e5 Import Result
11 travel_facts modules, three test modules, deterministic benchmark fixtures/runner/historical evidence, isolated report and handoff imported. All 24 file hashes still match commit. Old 492-passed evidence explicitly remains historical. Current main Foundation Gate: **87/87**. Initial reused temporary DB contained old seed data and hit a duplicate Trip primary key; clean temporary PostgreSQL passed. Initial failure log preserved; production database never reset.

## 4. Authority Ownership
Companion verified forecasts come only from TravelFactService, registered authority and freshness. `external_facts.fetch_open_meteo` is reused as network transport/data envelope, not a second verified truth owner. Legacy Planning raw weather consumption remains unmigrated and is not promoted as Companion verified authority. No new WeatherFact contract or weather agent. Fact/Recommendation/Knowledge boundaries remain separate.

## 5. Companion Fact Boundary
Graph consumes a thin FactToolPort: deterministic forecast preparation returning native FactRequirements, then resolve_facts returning native ResolvedFacts. It knows no HTTP payload, provider retry/cache/authority internals. CompanionFactAdapter composes existing Foundation service/policies/repository/WeatherForecastAdapter. Graph server-renders valid forecast results separately from Knowledge claims; weather paths never invoke model generation. Assistant service supplies the tool; tests/runners can inject it. No new Agent or write capability.

## 6. InformationNeed → FactRequirement
Additive `forecast_required` and bounded native `fact_requirements`. Weather intent distinguished from stable Knowledge and other unsupported live needs. Location/time prerequisites can yield minimal clarification before forecast calls. Each native requirement has weather.forecast, WGS84 destination, aware one-hour TimeScope, specialist minimum authority, 900-second freshness and allow_stale=false. Other FactTypes are not consumed by Companion. Tool intent is lexical and bounded; this is not a general semantic router.

## 7. Place Resolution
Foundation AMap adapter requires exact existing POI ID and emits GCJ-02; it cannot safely resolve free city text to WGS84/IANA timezone. Added an internal Open-Meteo/GeoNames city-location adapter, using existing place.location contracts/resolver and explicit specialist registration. Exact localized city name + China + administrative area + city feature required, exactly one match; no first fuzzy result. Currently supports **杭州 and 南京**. No hardcoded coordinates, city IDs or coordinate-system relabelling. Prior explicit conversation destination is reused; provider-resolved city is retained in conversation context. “西湖” is a documented Hangzhou city-weather alias, visibly representative city scope, not exact lake coordinates. “西湖区” without city/context clarifies. Generic place/AMap capability is not exposed.

Source: [Open-Meteo geocoding documentation](https://open-meteo.com/en/docs/geocoding-api) specifies WGS84 coordinates, location IDs and IANA timezone.

## 8. Time / Timezone Resolution
Resolved location's timezone owns local date, not server UTC/browser/model. Deterministic dayparts: morning 06–12, afternoon 12–18, evening 18–24, full day 00–24; end exclusive. Each hour resolved separately, never pretending one hour covers an afternoon. Today includes only future whole hours; no current/past observation. Tomorrow/day-after and optional-year month/day supported. Omitted year uses current local year and never silently rolls forward. Invalid/multiple dates, multiple dayparts and arbitrary clock times clarify; past and beyond six local days limit safely. Local-midnight crossing tested.

## 9. Freshness Policy
Explicit product policy: forecast 15 min, internal city location 24 h. Existing resolver evaluates age/authority after provider work, refreshes stale cache, and never publishes stale when allow_stale=false. Bounded native in-memory repository (128 subjects, 64 history items/subject); no Redis/table/long-term weather storage. Per-turn/day payload sharing avoids one network call per hour; typed facts still resolve individually. UTC day boundaries can require two payload requests. Cache is optimization; native result usability/freshness determines publication.

## 10. Prediction Semantics
Existing Foundation requires provider_prediction for weather.forecast. Natural reply uses “预报/预计”, shows hour window, city scope, timezone, provider, retrieval time and 15-minute check; explicitly states prediction is not observation/guarantee. Underlying values are temperature °C, precipitation probability % and WMO code only. Prose shows temperature/probability, retains WMO code in facts; no invented wind/current/alert fields. Existing transport does **not** supply model issue time; retrieval time is not mislabeled as publication/observation time. [Forecast API documentation](https://open-meteo.com/en/docs).

## 11. Provider Failure Behavior
Tests cover timeout, 5xx, malformed/empty forecast, unsupported date/time, location failure/duplicate entity, stale response and stale-cache-only refresh failure. Natural unavailable response; no general/model-weather fallback. Same-priority conflict preserved and shown as unresolved, never chosen by model. Provider failures sanitize exception details. Underlying blocking thread may continue until transport timeout after resolver cancellation, an inherited limitation.

## 12. Mixed Knowledge + Fact
Reuse existing stable/live graph branch and stable-topic query projection. Stable source claims and verified forecast server prose merge naturally. Weather failure does not remove historical facts; Knowledge success never validates weather. Other unsupported live components keep an explicit limitation. Deterministic success/failure tests pass; early blocked live mixed attempt retained stable claims without guessing weather; final real Runtime and production API mixed replies both combine supported Knowledge and fresh verified forecasts.

## 13. Planning Safety
Weather/date/place/outdoor-suitability cases route Companion with mutation_requested=false. No Planning tools in Companion graph. Explicit “帮我规划南京三天” retains Planning route/Brief boundary; it is not stolen by Fact system. Original decision explanations remain Decision context. Evaluator planning row routes only, does not create a run; persistence safety separately tested. No auto Activity/Revision/Recovery change.

## 14. Formal State Safety
Real PostgreSQL API test with existing Trip compares entire rows of trips/day_plans/activities/planning_runs/plan_revisions/trip_executions/navigation_sessions before/after weather, mixed, current and past requests: **exactly unchanged**. Session conversation persistence is expected and excluded. Fact read-through original tests separately compare all public tables and SELECT/SET-only SQL. Production smoke separately compares counts/versions and formal-row hashes; see section22 for actual production proof.

## 15. Files Changed
Existing files changed: backend/app/assistant_service.py, backend/app/companion_contracts.py, backend/app/companion_graph.py, backend/app/companion_information.py, backend/app/companion_runtime.py. New `backend/app/companion_facts.py`, two Companion fact test modules, `backend/evals/companion_forecast.py`; exact Foundation import paths in import_manifest. Audit/report/verification script and handoff/architecture notes added. No Web/Android edits; existing Web companion result accepts additive metadata and grounding_status string. No dependency lock, database/migration, Router, Planning graph, Knowledge corpus or legacy transport edits. Initial protected app hashes checked.

## 16. Foundation Tests
Current-main **87 passed / 0 failed**, contracts/freshness/authority/conflict/adapters/execution read-through and PostgreSQL read-only. Deterministic benchmark **28/28**, freshness/provenance/resolution/conflict each 28/28; unavailable honesty 16/16. Imported historical verification does not prove main; new XML/log/benchmark are separate evidence.

## 17. Companion Focused Tests
Final focused **245 passed / 0 failed**: new weather and formal-safety tests plus Tourism Knowledge, Knowledge Coverage, Companion runtime/knowledge, Phase 2.5 and travel-goal routing. Covers hour windows/prediction/provenance, timezone/context, no model guesses, failure/stale/conflict, mixed independence and zero formal mutation. A test initially used session_id instead of existing API id; corrected test, failure log retained. Tests do not claim real weather accuracy.

## 18. Live Provider Validation
**PASSED on final source `7e01c9cee0537824e94e931e009fdfb552184d8110d5870819c7ce67dd948d3d`.** Initial direct/proxy connection/TLS failures were retained; network recovered without code/config/provider substitution. Final live request used real Open-Meteo geocoding and forecast, normalized through registered resolver. `live_provider_validated.json` records target coordinates/timezone, location result, requested aware hour windows, retrieval timestamps, normalized values, authority/freshness/evidence and actual Companion answer. Hangzhou tomorrow afternoon yielded six fresh hourly predictions. Provider model issue timestamp is unavailable and explicitly recorded as such. No current observation, fake fallback or second weather provider. Failed early artifacts remain historical attempts, not final success evidence.

## 19. Real Model Evaluation
20 offline scenarios (18 weather/fact boundary/fault scenarios plus Knowledge/Planning). Offline: `{"cases": 20, "errors": 0, "fact_tool_precision": "13/13", "fact_tool_recall": "13/14", "unnecessary_fact_calls": 0, "planning_authorization_errors": 0, "stale_fact_usage": 0, "unsupported_dynamic_claim_count": 0, "natural_answers": 19, "actual_model_calls": 0, "resolved_statuses": {"resolved": 66, "unavailable": 24, "stale": 6}}`. Recall13/14 includes a failed location prerequisite before weather resolve; precision13/13. Fault injection is labelled offline.

Final real-provider/model-configured Companion Runtime **14 scenarios** (12 weather/fact scenarios plus Knowledge/Planning): `{"cases": 14, "errors": 0, "fact_tool_precision": "8/8", "fact_tool_recall": "8/8", "unnecessary_fact_calls": 0, "planning_authorization_errors": 0, "stale_fact_usage": 0, "unsupported_dynamic_claim_count": 0, "natural_answers": 13, "actual_model_calls": 0, "resolved_statuses": {"resolved": 66}}`. Fact precision/recall8/8; **66 resolved fresh hourly results**, unnecessary fact calls0, Planning authorization errors0, stale usage0, unsupported dynamic claim checks0, 13/13 natural Companion replies; mixed stable knowledge + forecast succeeds. The Planning case is route-only, not a created run. All expected future cases resolved; unsupported current/past and ambiguity/missing dates safely limited/clarified. Actual model generations **0**, allowed because forecast/source paths use server-owned rendering; this is provider/runtime integration, not a generative-model benchmark or independent meteorological accuracy audit. Output validation checks trace numeric forecast prose to native fresh predictions. Production API additionally validates end-to-end responses and zero formal mutation.

## 20. Full Regression
Clean Linux/Python3.11/PostgreSQL17 temporary DB, migrations through 20260924_0034, full backend **768 passed**, 0 failures, 2 existing Starlette 422 deprecation warnings, 71.95s. One final full run; current app/tests/evals mounted into frozen dependency image. Knowledge same frozen 60-case regression remains need34/60, types48/60, assertions35/44, mixed7/10, errors0; original fixture/outputs preserved. Final source SHA `7e01c9cee0537824e94e931e009fdfb552184d8110d5870819c7ce67dd948d3d`. Source hash binds offline eval, Knowledge regression and verification; full/focused logs/XML separate.

## 21. Production Deployment
**PASSED.** Built/recreated API and agent-worker after all gates passed. Both Knowledge Coverage and Travel Facts Integration v1 are included; this is not a weather-only deployment. API and worker each verify **165 runtime files** against final source manifest. Image IDs, running status and hash checks in production_binding/production_verification; API live/ready and unchanged Web entry return200, PostgreSQL healthy. Worker process verified running; no Docker worker healthcheck exists. Migration20260924_0034 head. Web not rebuilt because no source/API break; existing additive Companion fields remain compatible. No production reset/approval or formal itinerary edit.

## 22. Production Smoke
**7/7 passed** in an independent synthetic pre-trip session: hello; Nanjing exploration; sourced West Lake history; real Hangzhou tomorrow-afternoon forecast; mixed history + real forecast; unsupported current temperature; explicit Nanjing three-day Planning. First six are Companion/mutation=false/no run. Forecasts have fresh provider_prediction values/provenance; current temperature is honestly unsupported. Last request routes Planning/mutation=true and prepares a Brief asking missing date; it does not auto-create a Trip/Run without further input/approval.

Before build and after smoke counts remain **Trip 178, PlanningRun 105, PlanRevision 35**. All Trip versions unchanged; complete Trip/day/activity/revision row hashes unchanged across smoke, including after first six. Explicit PlanningRun delta **0**. Session conversation persistence is the only intended write. Actual final replies, typed results and before/after snapshots in production_smoke.json; no reliance on test-DB proof alone.

## 23. Known Limitations
Provider connectivity can fail transiently; initial TLS attempts failed and final live/production success does not guarantee future uptime. Only Hangzhou/Nanjing representative city locations, city-level West Lake alias, bounded lexical/date expressions and verbose hourly display; no exact POI microclimate, arbitrary-clock parser or meteorological accuracy guarantee. Model issue time unavailable. No automated personal outdoor-suitability certification/advice from forecast data. Single reviewer and inherited bounded process cache/blocking-thread cancellation limitations. Prior Knowledge source-mode/history/negation failures remain; general model knowledge stays unverified.

## 24. Deferred Issues
Current weather/observation/nowcast/alerts, opening/tickets/crowds/traffic/routes/navigation/execution facts, second weather provider, other cities/entity resolution, official collector, arbitrary-hour dates, forecast-driven itinerary edits, Redis/new tables/vector DB/new agents, Ledger Stage2.2, Memory/Knowledge expansion. Foundation internal contracts remain but Companion does not consume them. No architecture rewrite.

## 25. Recommended Next Slice
Recommend **Verified Opening Hours v1** as a separately bounded consumer only after defining trusted source, effective date/window, freshness and conflict semantics. This is a proposal only; opening hours and other dynamic capabilities remain unsupported here. Keep current forecast and Knowledge/Planning/Execution authorities separate; do not reopen completed Foundation/Phase2.5 or broaden this slice.

# CHATGPT HANDOFF SUMMARY

CURRENT SLICE: Travel Facts Integration v1 COMPLETE.

FOUNDATION: exact5f9f5e5 import; current-main87 tests and benchmark28/28 passed.

IMPORT: 24 added-only paths; no branch/snapshot merge, reset/stash or commit.

COMPANION FACT TOOL: thin read-only native FactRequirement→ResolvedFact boundary; server renders forecasts, no model weather guessing.

SUPPORTED FACT: future hourly forecast, temperature/probability/code;杭州/南京 city representative locations.

UNSUPPORTED FACTS: current/past observations, alerts, opening/ticket/crowd/traffic/route/navigation/execution; no second weather provider.

PLACE RESOLUTION: exact filtered GeoNames city WGS84/timezone; no hardcoded coordinates/GCJ relabelling; West Lake city alias visibly scoped; district ambiguity clarifies.

TIME/FRESHNESS: local date/dayparts; one requirement per hour; forecast15min/place24h; stale refused; prediction≠observation; provider model issue time unavailable.

LIVE PROVIDER: final Open-Meteo gate passed, six hours in dedicated validated sample; early network failure history retained.

REAL COMPANION:14 scenarios/12 weather boundaries; fact precision/recall8/8;66 fresh hourly results;0 unnecessary/stale/unsupported dynamic checks/Planning authorization errors; actual model generation0; mixed succeeds.

PLANNING SAFETY: weather queries Companion/mutation=false/no run; explicit Planning retains Brief/date clarification, no automatic itinerary mutation.

FORMAL STATE: test and production row snapshots unchanged; counts Trip178/Run105/Revision35, all Trip versions unchanged; explicit Planning run delta0.

BACKEND: Foundation87/focused245/full768 passed,2 existing warnings; Knowledge frozen regression unchanged.

PRODUCTION: API+worker built/restarted with Knowledge Coverage+Travel Facts;165 runtime hashes each match;health200;production smoke7/7;Web unchanged.

KNOWN LIMITATIONS: two-city/hourly/representative scope, transient provider failures, issue time unavailable, no independent weather accuracy audit, old Knowledge gaps retained.

DO NOT REDO: Foundation, Phase2.5, Router/Identity/Brief/Planning approval boundaries, frozen Knowledge labels/corpus.

NEXT RECOMMENDED SLICE: Verified Opening Hours v1 (proposal only; not implemented).
