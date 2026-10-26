"""Hash-bound closeout; live/production gates cannot be replaced by offline success."""
import hashlib,json,re,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'backend/evals/results/travel_facts_integration'
def read(name): return json.loads((OUT/name).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
initial=read('starting_manifest.json');imported=read('import_manifest.json')
assert all(sha(ROOT/n)==v for n,v in imported.items()),'Foundation import changed'
offline,real,knowledge=[read(n) for n in ['companion_eval.json','real_companion.json','knowledge_regression/final_results.json']]
snap=offline['snapshot']
assert all(sha(ROOT/'backend'/n)==v for n,v in snap['files'].items())
assert knowledge['snapshot']['sha256']==snap['sha256']
assert real['snapshot']['sha256']==snap['sha256']
tests={n:ET.parse(OUT/(n+'.xml')).getroot().find('testsuite').attrib for n in ['foundation','focused','backend_final']}
assert all(int(x['failures'])==int(x['errors'])==0 for x in tests.values())
changes=[n for n,v in initial['initial_app_hashes'].items() if sha(ROOT/n)!=v]
assert set(changes)=={'backend/app/assistant_service.py','backend/app/companion_contracts.py','backend/app/companion_graph.py','backend/app/companion_information.py','backend/app/companion_runtime.py'}
old=ROOT/'backend/evals/results/knowledge_coverage';frozen=json.loads((old/'output_freeze.json').read_text(encoding='utf-8'))
assert all(sha(old/n)==v for n,v in frozen['outputs'].items())
positive=[r for r in real['cases'] if r['expected_fact_call']]
live_gate=bool(positive) and all(r['result'] and r['result']['resolved_facts'] and all(x['usable_as_current'] for x in r['result']['resolved_facts']) for r in positive)
production=read('production_smoke.json') if (OUT/'production_smoke.json').exists() else None
complete=live_gate and bool(production and production.get('passed'))
status='COMPLETE' if complete else 'NOT COMPLETE'
verification={'measured_at':datetime.now(timezone.utc).isoformat(),'status':status,'source_sha256':snap['sha256'],'source_files_match':True,'head':initial['head'],
 'foundation_commit':'5f9f5e5','foundation_import_exact':True,'protected_existing_app_files_unchanged':True,'existing_app_files_changed':changes,
 'tests':tests,'offline_eval':offline['summary'],'live_eval':real['summary'],'live_gate':live_gate,'production_gate':complete,
 'knowledge_regression':knowledge['summary'],'previous_knowledge_outputs_unchanged':True,'blocking_condition':None if complete else 'Live Open-Meteo location/forecast chain unavailable (TLS/connection failures); production not deployed or smoked.',
 'artifacts':{str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='verification.json'}}
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=f'''# RoamSync — Travel Facts Integration v1 / Companion Verified Forecast

2026-09-30. **CURRENT SLICE: {status}.** Foundation and Companion implementation plus deterministic, PostgreSQL and full regression gates pass. Real-provider forecast verification is blocked by connection/TLS failures. No production build/restart or production smoke was performed. Offline success is not substituted for the user's live/production exit criteria.

## 1. Starting Reality
main HEAD `{initial['head']}` unchanged; extensive dirty working tree preserved. Phase 2.5 accepted production and later Knowledge Coverage working-tree improvements were separate starting realities. Initial hashes/status and complete `5f9f5e5` diff retained in `backend/evals/results/travel_facts_integration/`. No reset/clean/stash/merge or snapshot-parent import. Audit: `TRAVEL_FACTS_INTEGRATION_REALITY_20260930.md`.

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
Reuse existing stable/live graph branch and stable-topic query projection. Stable source claims and verified forecast server prose merge naturally. Weather failure does not remove historical facts; Knowledge success never validates weather. Other unsupported live components keep an explicit limitation. Deterministic success/failure tests pass; live mixed answer has stable claims but **no verified forecast** during blocked provider run, so live mixed success remains false.

## 13. Planning Safety
Weather/date/place/outdoor-suitability cases route Companion with mutation_requested=false. No Planning tools in Companion graph. Explicit “帮我规划南京三天” retains Planning route/Brief boundary; it is not stolen by Fact system. Original decision explanations remain Decision context. Evaluator planning row routes only, does not create a run; persistence safety separately tested. No auto Activity/Revision/Recovery change.

## 14. Formal State Safety
Real PostgreSQL API test with existing Trip compares entire rows of trips/day_plans/activities/planning_runs/plan_revisions/trip_executions/navigation_sessions before/after weather, mixed, current and past requests: **exactly unchanged**. Session conversation persistence is expected and excluded. Fact read-through original tests separately compare all public tables and SELECT/SET-only SQL. Production Trip/Run/Revision/version smoke snapshot is not yet performed; do not infer it from test DB.

## 15. Files Changed
Existing files changed: {', '.join(changes)}. New `backend/app/companion_facts.py`, two Companion fact test modules, `backend/evals/companion_forecast.py`; exact Foundation import paths in import_manifest. Audit/report/verification script and handoff/architecture notes added. No Web/Android edits; existing Web companion result accepts additive metadata and grounding_status string. No dependency lock, database/migration, Router, Planning graph, Knowledge corpus or legacy transport edits. Initial protected app hashes checked.

## 16. Foundation Tests
Current-main **87 passed / 0 failed**, contracts/freshness/authority/conflict/adapters/execution read-through and PostgreSQL read-only. Deterministic benchmark **28/28**, freshness/provenance/resolution/conflict each 28/28; unavailable honesty 16/16. Imported historical verification does not prove main; new XML/log/benchmark are separate evidence.

## 17. Companion Focused Tests
Final focused **{tests['focused']['tests']} passed / 0 failed**: new weather and formal-safety tests plus Tourism Knowledge, Knowledge Coverage, Companion runtime/knowledge, Phase 2.5 and travel-goal routing. Covers hour windows/prediction/provenance, timezone/context, no model guesses, failure/stale/conflict, mixed independence and zero formal mutation. A test initially used session_id instead of existing API id; corrected test, failure log retained. Tests do not claim real weather accuracy.

## 18. Live Provider Validation
**BLOCKED / NOT PASSED.** Direct and existing 7897 proxy attempts failed with connection/TLS EOF/handshake errors. One diagnostic geocoding transport request succeeded transiently; it is not a successful normalized location→forecast→Companion verification. Initial live_provider.json records unavailable location, zero forecast results. Real provider run includes native unavailable statuses/failure codes; there is no fake adapter fallback. Need a working network/proxy route before live forecast validation and deployment. No successful forecast provider/valid-hour data is claimed.

## 19. Real Model Evaluation
20 offline scenarios (18 weather/fact boundary/fault scenarios plus stable Knowledge and explicit Planning), controlled/no fake live claim. Offline summary: `{json.dumps(offline['summary'],ensure_ascii=False)}`. Recall 13/14 counts a blocked location prerequisite as no weather resolver call, not a silent successful answer; precision 13/13 and unnecessary calls 0. Whole tool preparation versus weather resolve are distinguished.

Real provider/model-configured Runtime subset **14** (12 weather/fact scenarios plus Knowledge/Planning), no fault adapters: `{json.dumps(real['summary'],ensure_ascii=False)}`. Expected weather resolve calls 0/8 because geocoding failed, not because forecast support was verified. Natural unavailable/clarification replies 13/13 Companion cases; this is graceful failure, **not natural successful forecast answer**. Actual model generations **0**, explicitly permitted by server-owned forecast paths. Unsupported dynamic claim/stale usage checks 0 in the tested outputs; they are server-rendering/boundary checks, not independent meteorological accuracy estimates. Full responses, requirements, status/freshness, calls and provenance retained in JSON. Live Companion API/formal safety still awaits live gate and production smoke.

## 20. Full Regression
Clean Linux/Python3.11/PostgreSQL17 temporary DB, migrations through 20260924_0034, full backend **{tests['backend_final']['tests']} passed**, 0 failures, 2 existing Starlette 422 deprecation warnings, 71.95s. One final full run; current app/tests/evals mounted into frozen dependency image. Knowledge same frozen 60-case regression remains need34/60, types48/60, assertions35/44, mixed7/10, errors0; original fixture/outputs preserved. Final source SHA `{snap['sha256']}`. Source hash binds offline eval, Knowledge regression and verification; full/focused logs/XML separate.

## 21. Production Deployment
**NOT PERFORMED.** User authorized deployment only after all gates. Live-provider/real successful forecast gate failed; do not build/restart API/worker as final deployment. Existing Phase 2.5 production image remains; Knowledge Coverage plus Travel Facts changes exist only in working tree. When gates pass, production build must contain **both** slices and verify API/worker file hashes; Web rebuild only if affected. No production reset/data alteration.

## 22. Production Smoke
**NOT RUN.** Prepared sequence remains hello, Nanjing exploration, sourced West Lake history, Hangzhou future forecast, mixed West Lake/history forecast, unsupported current temperature, explicit Nanjing three-day Planning. Capture Trip/PlanningRun/PlanRevision counts and all Trip versions before/after; first six must not create runs. Explain any explicit Planning creation separately; current Brief may first ask missing dates. No passing production smoke is fabricated.

## 23. Known Limitations
Blocking external network/TLS; no successful live forecast/end-to-end or production proof. Limited two-city representative locations, city-level West Lake alias, lexical intent/date expressions, hourly display density, no exact POI microclimate or arbitrary time parser. Underlying issue time unavailable. Single reviewer, synthetic fault tests and inherited bounded in-process cache/thread cancellation limitations. Prior Knowledge source-mode/history/negation failures remain; general model knowledge stays unverified.

## 24. Deferred Issues
Current weather/observation/nowcast/alerts, opening/tickets/crowds/traffic/routes/navigation/execution facts, second weather provider, other cities/entity resolution, official collector, arbitrary-hour dates, forecast-driven itinerary edits, Redis/new tables/vector DB/new agents, Ledger Stage2.2, Memory/Knowledge expansion. Foundation internal contracts remain but Companion does not consume them. No architecture rewrite.

## 25. Recommended Next Slice
First finish **this slice's live network gate, real forecast/API validation, authorized deployment and production smoke**. Do not start another capability milestone while these exit criteria remain open. After closure, evaluate a separately scoped freshness/provenance fact consumer rather than broad Travel Facts rollout.

# CHATGPT HANDOFF SUMMARY

CURRENT SLICE: Travel Facts Integration v1 {status}.

FOUNDATION: exact implementation import, current-main87 tests and28-case benchmark pass.

IMPORT: 5f9f5e5 only, 24 new paths, no branch/snapshot merge, no reset/stash/commit.

COMPANION FACT TOOL: thin read-only typed plan/resolve boundary; server-owned forecast rendering.

SUPPORTED FACT: future hourly weather.forecast, temperature/probability/code; only杭州/南京 representative city coordinates.

UNSUPPORTED FACTS: current/past observations, alerts, other dynamic capabilities; no generalized AMap exposure.

PLACE RESOLUTION: internal exact filtered GeoNames city search, native place.location resolver; no hardcoded coordinates or GCJ relabelling; district ambiguity clarifies.

TIME/FRESHNESS: target timezone; explicit dayparts/hourly requirements; forecast15min/place24h; stale refused; prediction≠observation; model issue time unknown.

LIVE PROVIDER: blocked connection/TLS; no successful forecast chain, no fake fallback.

REAL COMPANION: 14 real-provider/runtime cases, failed/clarification weather paths; actual model calls0; not a successful forecast gate.

PLANNING SAFETY: offline authorization errors0, no Companion Planning tool; explicit Planning route retained.

FORMAL STATE: existing-Trip PostgreSQL API complete formal-row snapshots unchanged; production proof pending.

BACKEND: Foundation87, focused{tests['focused']['tests']}, full{tests['backend_final']['tests']} passed/2 existing warnings; Knowledge frozen regression unchanged.

PRODUCTION: not deployed; old Phase2.5 image remains, new Knowledge+Facts tree unshipped.

KNOWN LIMITATIONS: network block; two-city/hourly scope; no independent weather-accuracy audit; old Knowledge gaps retained.

DO NOT REDO: Foundation, Phase2.5, Router/Runtime identity/Brief/Planning approval architecture, prior frozen labels/corpus.

NEXT RECOMMENDED SLICE: finish remaining live/deployment/smoke gates of this slice first.
'''
def section(number,title,body):
    global report
    report=re.sub(r'## '+str(number)+r'\. .*?(?=\n## |\n# CHATGPT)',f'## {number}. {title}\n{body}\n',report,flags=re.S)
if live_gate:
    section(18,'Live Provider Validation',f'''**PASSED on final source `{snap['sha256']}`.** Initial direct/proxy connection/TLS failures were retained; network recovered without code/config/provider substitution. Final live request used real Open-Meteo geocoding and forecast, normalized through registered resolver. `live_provider_validated.json` records target coordinates/timezone, location result, requested aware hour windows, retrieval timestamps, normalized values, authority/freshness/evidence and actual Companion answer. Hangzhou tomorrow afternoon yielded six fresh hourly predictions. Provider model issue timestamp is unavailable and explicitly recorded as such. No current observation, fake fallback or second weather provider. Failed early artifacts remain historical attempts, not final success evidence.''')
    section(19,'Real Model Evaluation',f'''20 offline scenarios (18 weather/fact boundary/fault scenarios plus Knowledge/Planning). Offline: `{json.dumps(offline['summary'],ensure_ascii=False)}`. Recall13/14 includes a failed location prerequisite before weather resolve; precision13/13. Fault injection is labelled offline.

Final real-provider/model-configured Companion Runtime **14 scenarios** (12 weather/fact scenarios plus Knowledge/Planning): `{json.dumps(real['summary'],ensure_ascii=False)}`. Fact precision/recall8/8; **66 resolved fresh hourly results**, unnecessary fact calls0, Planning authorization errors0, stale usage0, unsupported dynamic claim checks0, 13/13 natural Companion replies; mixed stable knowledge + forecast succeeds. The Planning case is route-only, not a created run. All expected future cases resolved; unsupported current/past and ambiguity/missing dates safely limited/clarified. Actual model generations **0**, allowed because forecast/source paths use server-owned rendering; this is provider/runtime integration, not a generative-model benchmark or independent meteorological accuracy audit. Output validation checks trace numeric forecast prose to native fresh predictions. Production API additionally validates end-to-end responses and zero formal mutation.''')
if complete:
    prod=read('production_verification.json')
    counts={k:production['after'][k] for k in ['trips','planning_runs','plan_revisions']}
    report=report.replace('Foundation and Companion implementation plus deterministic, PostgreSQL and full regression gates pass. Real-provider forecast verification is blocked by connection/TLS failures. No production build/restart or production smoke was performed. Offline success is not substituted for the user\'s live/production exit criteria.', 'Foundation, Companion, deterministic/PostgreSQL/full regression, real-provider forecast and production smoke gates all pass. API and worker were rebuilt/restarted with both Knowledge Coverage and Travel Facts changes. Early network failures remain in historical artifacts; they are not final status.')
    report=report.replace('live mixed answer has stable claims but **no verified forecast** during blocked provider run, so live mixed success remains false.', 'early blocked live mixed attempt retained stable claims without guessing weather; final real Runtime and production API mixed replies both combine supported Knowledge and fresh verified forecasts.')
    report=report.replace('Production Trip/Run/Revision/version smoke snapshot is not yet performed; do not infer it from test DB.', 'Production smoke separately compares counts/versions and formal-row hashes; see section22 for actual production proof.')
    section(21,'Production Deployment',f'''**PASSED.** Built/recreated API and agent-worker after all gates passed. Both Knowledge Coverage and Travel Facts Integration v1 are included; this is not a weather-only deployment. API and worker each verify **165 runtime files** against final source manifest. Image IDs, running status and hash checks in production_binding/production_verification; API live/ready and unchanged Web entry return200, PostgreSQL healthy. Worker process verified running; no Docker worker healthcheck exists. Migration20260924_0034 head. Web not rebuilt because no source/API break; existing additive Companion fields remain compatible. No production reset/approval or formal itinerary edit.''')
    section(22,'Production Smoke',f'''**7/7 passed** in an independent synthetic pre-trip session: hello; Nanjing exploration; sourced West Lake history; real Hangzhou tomorrow-afternoon forecast; mixed history + real forecast; unsupported current temperature; explicit Nanjing three-day Planning. First six are Companion/mutation=false/no run. Forecasts have fresh provider_prediction values/provenance; current temperature is honestly unsupported. Last request routes Planning/mutation=true and prepares a Brief asking missing date; it does not auto-create a Trip/Run without further input/approval.

Before build and after smoke counts remain **Trip {counts['trips']}, PlanningRun {counts['planning_runs']}, PlanRevision {counts['plan_revisions']}**. All Trip versions unchanged; complete Trip/day/activity/revision row hashes unchanged across smoke, including after first six. Explicit PlanningRun delta **{production['explicit_planning_run_delta']}**. Session conversation persistence is the only intended write. Actual final replies, typed results and before/after snapshots in production_smoke.json; no reliance on test-DB proof alone.''')
    section(23,'Known Limitations','''Provider connectivity can fail transiently; initial TLS attempts failed and final live/production success does not guarantee future uptime. Only Hangzhou/Nanjing representative city locations, city-level West Lake alias, bounded lexical/date expressions and verbose hourly display; no exact POI microclimate, arbitrary-clock parser or meteorological accuracy guarantee. Model issue time unavailable. No automated personal outdoor-suitability certification/advice from forecast data. Single reviewer and inherited bounded process cache/blocking-thread cancellation limitations. Prior Knowledge source-mode/history/negation failures remain; general model knowledge stays unverified.''')
    section(25,'Recommended Next Slice','''Recommend **Verified Opening Hours v1** as a separately bounded consumer only after defining trusted source, effective date/window, freshness and conflict semantics. This is a proposal only; opening hours and other dynamic capabilities remain unsupported here. Keep current forecast and Knowledge/Planning/Execution authorities separate; do not reopen completed Foundation/Phase2.5 or broaden this slice.''')
    report=report[:report.index('# CHATGPT HANDOFF SUMMARY')]+f'''# CHATGPT HANDOFF SUMMARY

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

FORMAL STATE: test and production row snapshots unchanged; counts Trip{counts['trips']}/Run{counts['planning_runs']}/Revision{counts['plan_revisions']}, all Trip versions unchanged; explicit Planning run delta0.

BACKEND: Foundation87/focused{tests['focused']['tests']}/full{tests['backend_final']['tests']} passed,2 existing warnings; Knowledge frozen regression unchanged.

PRODUCTION: API+worker built/restarted with Knowledge Coverage+Travel Facts;165 runtime hashes each match;health200;production smoke7/7;Web unchanged.

KNOWN LIMITATIONS: two-city/hourly/representative scope, transient provider failures, issue time unavailable, no independent weather accuracy audit, old Knowledge gaps retained.

DO NOT REDO: Foundation, Phase2.5, Router/Identity/Brief/Planning approval boundaries, frozen Knowledge labels/corpus.

NEXT RECOMMENDED SLICE: Verified Opening Hours v1 (proposal only; not implemented).
'''
(ROOT/'docs/agent/TRAVEL_FACTS_INTEGRATION_V1_20260930.md').write_text(report,encoding='utf-8')
print(status,snap['sha256'])
