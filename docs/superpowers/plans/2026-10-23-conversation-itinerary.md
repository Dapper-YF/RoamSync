# Conversation itinerary implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Follow the approved spec; no repeat permission requests for routine reversible work.

**Goal:** Replace pre-plan adoption with same-source conversational candidates, explicit atomic adoption, and exact-POI illustrated saved itineraries.
**Architecture:** Extend existing Draft/PreparedPlan/promotion; retain legacy protocol and original Validator/Accept. A server-owned presentation binds candidate version/hash to chat and final adoption. No formal Trip during drafting.
**Tech Stack:** FastAPI, Pydantic2, SQLAlchemy/PostgreSQL, React/Vite, existing AMap/place media.
**Spec:** docs/superpowers/specs/2026-10-23-conversation-itinerary-design.md (user approved “是”).

## Global constraints

- Worktree E:/Study/RoamSync-reliability-a2-20261022, branch codex/conversation-itinerary-redesign-20261023, base706a6f2.
- Never start/deploy/change official3000/8000/15432, official files, secrets or DB. No reset/clean. No Obsidian.
- Preserve Validator/Accept, version/owner/evidence/Execution guards; exact identity, not name-only photos.
- v1 historical protocols remain readable/restorable; v1 clients cannot overwrite/adopt v2 candidates.
- Real end-to-end failures are NO-GO; do not replace model/route/candidate evidence with fixtures.
- Scope work by ownership below; coordinator integrates shared interfaces sequentially. No add-A.

## Shared interface and ownership

Task1 owns drafts/contracts.py, draft_promotion/contracts.py and preparation.py plus focused preparation tests. Coordinator owns promotion service/materialize/guard/repository, assistant backend/DTOs/routes and infrastructure. Task4 owns web only. Independent edits may run concurrently after this contract is fixed.

V2 DraftItem extends existing fields with item_ref, kind(visit/meal/rest/free_window/optional/blank_day), duration_minutes, start_time/end_time, source_quote; source classification distinguishes user-explicit from planning allocation. V1 defaults remain compatible. V2 Draft/Plan/PreparedPlan use schema_version=2. PreparedPlan.windows includes ref/kind/label/day_date/start_time/end_time/source_quote. PreparedActivity remains a real-place activity. Operation records protocol_version and execution_mode, defaulting historical values to1/legacy_checkpoint.

Public CandidatePresentation:
```
{protocol_version:2, draft_id,draft_version,prepared_id,prepared_hash,presentation_hash,
 stage:'ready'|'needs_input'|'saving'|'saved'|'needs_review'|'stale'|'failed',
 title,city,start_date,end_date,summary,
 stops:[{ref,name,address,day_date,start_time,end_time,duration_minutes,note,place_ref,images}],
 windows:[{ref,kind,label,day_date,start_time,end_time}],
 routes:[{from_ref,to_ref,day_date,mode,distance_meters,duration_minutes,provider}],
 warnings:[],blockers:[],change_summary:[],trip_id:null,operation_id:null}
```
Expose as optional session.candidate, derive from server session pending_action.kind=itinerary_candidate_v2; ordinary messages remain compatible. Add exact-binding candidate decision endpoint with protocol_version2/prepared/hash/presentation/request_id/accept; old decision endpoint rejects v2. Frontend sends no provider credentials. Natural-language adopt uses the same server authority and current published binding, not a separate writer.

### Task1: Versioned draft schedule and real evidence preparation

Files: drafts/contracts.py, draft_promotion/contracts.py, draft_promotion/preparation.py; test_conversation_preparation.py.
- [ ] Red: create v2 day with two verified visits, lunch window and optional item; show existing DTO rejects/loss or uniform duration. Assert start/end/order, real route and windows, no fake lunch POI.
```python
assert [a.duration_minutes for a in plan.activities] == [120,90]
assert len(plan.windows)==1 and plan.windows[0].kind=='meal'
assert plan.schema_version==2 and valid_hashes(plan)
```
- [ ] Add strict v2 fields/validators, stable refs, day/window conflicts, time bounds and explicit source classification. Keep v1 hash byte semantics.
- [ ] Dispatch prepare v2 only for v2 drafts; real details/routes outside transactions; window gaps fit itinerary, duplicates/unknown identity/unsupported traffic/hard constraints block. Preserve all item kinds and v2 display fields in hash.
- [ ] Green focused contracts/preparation tests plus old promotion preview tests. Commit explicit owned files; hand DTO and examples to coordinator.

### Task2: Atomic promotion and window equivalence

Files: promotion/service.py, materialize.py, guard.py, repository.py, tests/test_draft_promotion.py.
- [ ] Red real PG test: an invalid candidate fails after formal creation; compare all operation-owned formal tables before/after, not only Trip count. Duplicate confirmation cannot create twice; stale draft/owner/hash rejected.
```python
operation = await service.confirm_atomic(owner, request, publication_binding)
assert operation.execution_mode=='atomic_candidate_v2'
assert operation.target_trip_id is None
result = await service.resume(owner,operation.id)
assert result.status=='applied'
assert (await service.resume(owner,operation.id)).target_trip_id==result.target_trip_id
```
- [ ] Extract noncommitting materialization/validation/apply units from existing stages; preserve checkpoint wrappers. Server records immutable v2 mode. Refresh provider facts before transaction.
- [ ] Atomic operation→Trip→Revision→Run→Draft locking; create/validate/Accept/windows/consumption/session publication bind all commit once. Failure rolls all formal writes back; durable operation retains typed recovery state.
- [ ] Extend snapshot_for and formal equivalence to windows/optional/blank days and full source identity. Legacy resume remains legacy; no public field can request downgrade.
- [ ] Green dedicated PG promotion suite, failure injection, concurrent retry and old checkpoint stages. Commit only reviewed coordinator files.

### Task3: One semantic handoff, same-draft conversation and signed presentation

Files: assistant_capabilities.py, assistant_turn.py, assistant_routes.py, assistant_service.py; new conversation_candidate package; integration_runtime.py; targeted backend tests.
- [ ] Red selector create request must yield a real candidate without metadata confirmation/Trip. Same draft modification keeps untouched refs, lunch and constraints; failed modification does not claim new requirements applied.
- [ ] Extend existing one capability decision with scoped candidate planning command, using original authorization/target refs/current constraints. Existing generator may create content but cannot reinterpret authority or replace confirmed POIs.
- [ ] Resolve literal selected POIs through current place service, not city category top25. Prepare v2, derive concise narrative from PreparedPlan, sign one-way presentation publication; do not add free model guarantees.
- [ ] Bind session owner/topic epoch/signature and candidate version persistently. No session locks across network. Publish/retry/cancel/new-chat/save serialize correctly.
- [ ] Natural language save and UI save invoke same exact-hash atomic promotion. Missing/legacy contract returns specific error; save errors never say saved. Already-saved Trip modifications retain original PlanRevision pipeline.
- [ ] Test raw state and error contracts, ignored older responses, expiry, old-client overwrite/adopt refusal, hint-only quoted/negated save rejected. Commit after source-bound PG validation.

### Task4: Conversational presentation and illustrated saved timeline

Files: new web/src/product/ConversationCandidate.tsx and tests; TravelAssistant.tsx, AssistantDecisions.tsx, arrangementApi.ts, shared DTOs; HandbookPhotos.tsx/HandbookJourney.tsx and CSS/tests.
- [ ] Red rendering tests: only metadata is not an adoptable plan; ready candidate shows real ordered stops and concise narrative, no full timeline by default; error/stale/save stage labels honest.
- [ ] Consume exact public interface above. Ready save action uses exact-binding endpoint; continue-adjust leaves current draft bound; details drawer read-only, no Trip navigation. Same-POI time changes reuse media rather than duplicate messages.
- [ ] Saved page keeps complete timeline and embeds identity-bound licensed images per real activity; windows have no bogus photo. Exact canonical/provider binding, address and distance/time/route evidence; onError hides failed image.
- [ ] Preserve design system and responsive1440/390/320; old natural fallback must not expose metadata as current ready candidate.
- [ ] Run meaningful UI tests/type/build, then actual Playwright Edge because Browser plugin absent. No screenshots/temp harness in source except explicitly requested delivery docs.

### Task5: Reviewed media and real acceptance

Files: only audited place_content/reviewed_images.json/media assets if license/identity source validated; outside-Git test runtime and evidence.
- [ ] Audit existing CC0/CC BY-SA assets and exact POI association. Query primary Commons sources for missing second POI; verify content/author/license/original and variant digests. Reject uncertain files; disclose missing media rather than wrong/AI photo.
- [ ] Fresh isolated synthetic DB/runtime, explicit DSN non15432, no fallback. Use real configured model and maps providers without copying secrets to Git. Record current SHA/config/provider presence, never keys.
- [ ] Execute consult→two real places/routes→candidate→same-object duration change→explicit save→saved timeline→saved revision→refresh/failure recovery. Assert no Trip before adopt; nonempty actual activities, windows, real route, exact accepted hash, media load/source identity.
- [ ] Freeze all source, run scripts/run-isolated-tests.py and Web tests/types/production builds, then source/artifact checks. Do not edit app/tests during source-bound runner.
- [ ] Astra Medium task and whole-branch review. Resolve findings; retain failures and precise GO/NO-GO. Update fixed-heading handoffs and report; commit explicit files, no deployment.

## Execution record

User design approval received. Existing worktree verified linked and clean, feature branch correct. Product base matches previous source-bound1713+25 and Web243 checks; those are baseline evidence, not new-change validation.
Ruling: retain approved P3-removal semantics rather than a cosmetic wording-only fix. Cost: candidate and adoption interfaces change, requiring explicit v2/legacy guards.
Ruling: A and implementers may work on disjoint task ownership; shared contracts sent explicitly and coordinator integrates, no cherry-picking unrelated trees.

| Pair/task | Producer/consumer or consistency check | Decision |
|---|---|---|
|1/2|PreparedPlan v2 windows/hash → atomic equivalence|Task2 consumes same DTO, no shadow fields|
|1/3|draft item_ref/window semantics → structured model input|Task3 uses exact stable refs, not generated POI IDs|
|2/3|atomic operation + session binding|Coordinator owns both; integrate sequentially|
|3/4|session.candidate DTO + exact decision|Public interface fixed above; frontend can build concurrently|
|4/5|canonical/provider media → real screenshots|Missing asset is explicit, no fake completion|
|1|v1 compatibility against v2 strict additions|Separate version path, old hashes unchanged|
|2|atomic rollback against historical roll-forward|Mode persisted server-side; keep legacy wrappers|
|3|same candidate against model whole-plan rewrite|Server merge preserves untargeted refs|
|4|chat concise vs saved complete|Separate projections, common underlying data|
|5|mocks vs real acceptance|Record separately; no GO without real chain|
