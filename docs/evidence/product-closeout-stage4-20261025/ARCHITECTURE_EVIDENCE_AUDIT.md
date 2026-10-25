# Changed-path architecture evidence audit

Scope: frozen736e3b7, existing chat/read/candidate/Revision path only. This is not a whole-backend architecture acceptance or a passing baseline. Product remains NO-GO. No BACKEND_ARCHITECTURE_SSOT.md is created.

## Rules and evidence

| Rule | Source / path | Verification / actual result | Verdict |
|---|---|---|---|
| Isolated development and persistence | AGENTS.md; runtime-final-v6.ps1; compose.test.yaml | new DB on15435, API18102/Web3102; officialHEADea3ba83 and original six tracked edits preserved | Verified for this run |
| Typed request validation | assistant_routes.py MessageInput/CandidateDecisionInput; assistant_capabilities.py CapabilityDecision | Pydantic extra=forbid; scalar/operation evidence follows schema; unit and recorded actual invalid requests retained | Verified boundary; product interpretation fails |
| Ordinary chat cannot direct-write duration | assistant_arrangement.py; assistant_turn.py; plan_revision_service.py | pending60 formal unchanged, exact same pending survives refresh; explicit UI adoption writes target75→60 only | Verified in actual sample |
| One existing acceptance chain | conversation_candidate/service.py; draft_promotion/service.py; plan_revision_service.py | no new tables/endpoints; real-object-safety-final.json locks/hash/version/rollback checks all pass | Verified bounded cases |
| Provider truth separate from requirement support | requirement_support.py; assistant_images.py; assistant_research.py | route8min only inter-place; search photos marked reference; actual opening facts remain partial | Guards implemented, answer usefulness incomplete |
| Consistent effective conditions | assistant_memory.py and assistant_context.py | scoped receipts and withdrawals covered; frozen DD/MM/YYYY rejection and incomplete recall remain | Not accepted for product completeness |
| Stable task references and saved reads | read_references.py; saved_trip_reads.py | Suzhou identity/route succeeds; sealed ordinal, first-item+15 and compound saved reads fail | Not accepted |
| Runtime / DB health | main.py live/ready; database.py get_session | architecture-read-probes.json live200/ready200; ready executes SELECT1 | Verified isolated runtime |
| Auth boundary | integration runtime existing access middleware, X-RoamSync-Access | wrong Bearer header returns401; correct documented header returns detail200/list200 | Verified local access gate, not a broad auth audit |
| Global error/envelope standard | main.py handlers and response models | detail200, invalidUUID422 with field location, missing404; list is a direct list, not globally paginated envelope | Existing heterogeneous contract; not globally accepted |
| Request logging | assistant_reliability.py, runtime_recorded.py | source-bound visible model outputs, redacted provider calls, correlation/stage/duration; external traces | Verified actual changed flow |
| Global severe500 / all endpoint authorization | whole backend | no new production exception injection or complete endpoint audit performed | Unverified |

## Directory responsibilities

| Directory/path | Responsibility and future content | Prohibited content | Origin |
|---|---|---|---|
| app/assistant_routes.py | FastAPI DTOs, dependency wiring, HTTP/SSE adaptation | model-owned IDs/permission bypass | business customization on FastAPI |
| app/assistant_*.py, read_references.py | source validation, context projection, retained subgoals | new formal writer / duplicated Accept | business customization |
| app/conversation_candidate | source-bound candidate operations/presentation/publication | unknown-field deletion, invented acceptance | business customization |
| app/draft_promotion, plan_revision_service.py | existing validate/lock/hash/accept and atomic writes | accepting an unpresented stale snapshot | business customization |
| app/repository.py, database.py | ORM persistence and sessions | generated conversational claims | SQLAlchemy plus business customization |
| app/main.py | legacy routes and app composition | further unrelated orchestration growth | existing mixed composition; coupling risk retained |
| backend/tests | regression, DB boundary/fault tests | external provider fixture as actual facts | project convention |
| docs/evidence | immutable evidence/indexes and failure history | secrets, changing old independent scores | project convention |

Known coupling: main.py still contains legacy routes and directly uses repository/session components; assistant_turn coordinates model, context and persistence. This closeout did not refactor the whole application or introduce a competing Agent/write architecture.

## Representative request trace

GET /api/v1/trips/{trip_id}: main.py get_trip_endpoint validates UUID through FastAPI, injects database.get_session, calls repository.get_trip, handles TripNotFoundError, returns TripResponse. repository.py executes ORM read, database.py owns async session. Response/detail and errors are existing route/global FastAPI shapes, not a new universal wrapper.

POST assistant session message: assistant_routes.py MessageInput → assistant_service.send_message → assistant_turn.semantic_turn → validate_decision/context → read adapters or existing candidate/Planner path. Formal modification is Run/Revision preview; plan_revision_service.accept_plan_revision owns transaction/hash/version. Evidence: api-trace.ndjson, browser-states/pending60/adopted60-after-refresh, real-object-safety-final.json. Existing route handlers may access sessions directly; an independent service/repository layer is not universally enforced.

## Response scenarios

| Scenario | Request / evidence | Result | Scope |
|---|---|---|---|
| list | GET /api/v1/trips, architecture-authenticated-read-probes.json |200 direct list | no pagination claim |
| detail | GET actual Suzhou Trip |200 version3 | real isolated DB |
| explicit update/accept | real-object-safety-final.json, original API/form and Accept calls |200 winner or409 conflict; state assertions | not another live mutation |
| empty list | before-generation.json formal tables empty | DB empty, no separate list HTTP capture | HTTP empty-list unverified |
| invalid field | GET /api/v1/trips/not-a-uuid |422 UUID field validation | actual HTTP |
| unauthenticated/wrong credential surface | first read probes use incorrect Bearer instead of required header |401 | failed probe retained |
| missing resource | GET zero UUID |404 | actual HTTP |
| severe unexpected500 | no new injection | unverified | do not claim global standardization |

## Framework reuse, wrappers and execution

FastAPI/Pydantic handle routing, DTOs, dependencies and validation; SQLAlchemy/PostgreSQL handle ORM, sessions and real locking; Alembic handles migrations. Existing custom selection_contract/selection_repair enforce the state wire grammar and bounded exact repairs; read_references preserves ordered provider-bound subjects; revision_presentation binds review content/hash. All are used, but remaining task failures show these wrappers are not a complete semantic resolver.

Dependency installation is backend/Dockerfile's uv sync --frozen (test stage includes dev dependencies). Final checks use run-full-final-v6.ps1 → existing run_batch.py and compose.test.yaml with fresh tmpfs Postgres and no official env. Isolated runtime uses runtime-final-v6.ps1, explicit synthetic token/owner and independent DSN; init already migrated via Alembic and checkpoint setup. API18102/Web3102, health/live and health/ready200. Required config names, credential-presence booleans and provider/model fingerprint appear in runtime manifest; values remain private.

Actual model/provider logging is outside product user flow: api-trace.ndjson and contract-real-after12.trace.ndjson include visible outputs and timings; browser SSLEOF image failure and database stopped/recovery are retained. No production auth/DB/deployment test performed. Architecture acceptance is incomplete and product score4/20; no passing SSOT/baseline claim is justified.
