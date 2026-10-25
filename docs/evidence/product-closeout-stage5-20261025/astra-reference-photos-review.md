# Stage5 reference photographs — implementation contract review

VERIFIED static inspection of current uncommitted reference_images.py, place_content/routes.py, integration_runtime.py, HandbookPhotos.tsx, AssistantAnswer.tsx and added test sources; traced project_search, AMap detail normalization and search_tavily. No source edits, DB/model/network calls or new acceptance questions. No product GO evaluation.

## Findings requiring correction

### P1 — venue photo path admits generic dish images

`PlaceReferenceImages.load` calls `project_search(fact, place.name + "的图片")`, then filters only by city substring. `project_search` intentionally permits a dish fallback for names containing 火锅 or 串串: exact_subject OR dish is accepted. Therefore an authentic POI “海底捞火锅(某店)” in 苏州 can acquire an image described only as “苏州火锅美食”, with no restaurant/branch identity anywhere. The returned POI wrapper still contains the correct canonical/provider identity, so the frontend accepts it and captions the generic image with the restaurant's name. Matching the wrapper does not bind the photograph to that POI.

Fix the place-reference path to require the complete provider name (or explicitly supported, identity-bound aliases) in image metadata. Disable generic dish fallback for venue photos; preserve it only in the existing dish illustration use case. Prefer a shared projection option/typed match receipt rather than new name-specific rules. Add a regression with a provider-verified restaurant containing 火锅, a same-city generic dish image, and a nonmatching branch; both must remain unavailable. Explicitly verify a genuine full-name matching photo remains search_reference.

Even exact name+city description is relevance evidence, not scene identity verification: descriptions can mention multiple cities/branches or be wrong. Retain the existing unverified label and do not advertise this as guaranteed actual venue photography. Coordinates currently validate the POI wrapper only, not geolocation of the image. A caption should stay visibly framed as a search reference; no license/current-conditions assertion is established.

### P2 — invalid detail results bypass negative cache

Inside `load`, invalid/missing/mismatched provider detail returns `empty` from the try body. Python executes finally but skips the cache insertion after finally. Repeated sequential requests for the same stale/deleted provider id therefore issue repeated AMap detail calls, despite the intended 30-second unavailable cache. This affects ordinary refreshes and duplicate card mounts after the first request has finished; same-inflight deduplication does not help.

Use one return after cache insertion for all completed outcomes (cancellation semantics can remain separate). Test two sequential calls for None, wrong ref and missing city: provider called once within negative TTL; retry allowed after expiry.

### P2 — unbounded catalog request blocks all same-city fallback

HandbookPhoto awaits the shared city catalog Promise before attempting reference-images. The initial fetch has neither AbortController nor a timeout. A stalled request remains cached indefinitely because its catch never runs; all same-city cards and subsequent mounts reuse it and never start fallback, even though the backend fallback has a bounded time budget. This is a photo-availability failure, not a formal itinerary failure.

Give the shared catalog lookup a bounded timeout and remove failed/timed-out promise entries without one consumer cancelling others' useful shared work. Reference lookup should also have a browser-side deadline/abort on target cleanup to avoid abandoned connections. Add a controlled never-resolving catalog test that proves fallback proceeds after the defined timeout, and a target-switch test proving late A results never appear on B.

## Verified safe boundaries

- Canonical UUID must equal stable_place_id(provider_place_id) before provider calls. Detail response must have the exact PlaceRef, provider_identity status, nonempty city/name. The endpoint accepts provider ID, not an arbitrary search query or URL. ExternalRef uses the fixed AMap provider contract.
- Queries use provider-issued name/city; no client activity custom title is used as a search identity. The frontend checks canonical id, provider and provider id, current city, and (when available) supplied coordinate proximity before accepting returned place metadata. Supporting custom display titles is correct because stored canonical identity wins over names.
- Reviewed licensed media remains preferred. Search results retain usage_basis=search_reference, no inferred license fields, and source_url is the actual image URL rather than an invented publisher. Source-link availability is not a redistribution license. Existing public_image_url filtering runs before output. No backend image downloader/proxy or media persistence is added.
- Production integration's existing API middleware protects the new route like other content reads. This route itself has no owner dependency, consistent with public content lookup behavior; do not mount the integrated router publicly and assume route-level authentication exists.
- lookup receives only provider/settings; it never calls ContentRepository, trip/activity writes, planner or Accept. Provider.detail normalizes metadata without database writes. In-memory cache is not a formal saved-trip mutation.
- Cache is bounded to 128 completed entries; positive TTL600 and intended negative TTL30. Identical keys share shielded task; semaphore allows four active coroutines and timeout20 includes queue waiting. The inflight map itself has no entry-count bound, so a burst of distinct keys queues tasks until their deadlines.
- Cancellation of a requester does not kill the shared task, which is appropriate for coalesced users. However AMap and Tavily use asyncio.to_thread for synchronous HTTP: coroutine timeout does not cancel an already running OS-thread request. Thus the semaphore bounds active async jobs, not a hard invariant of four physical network requests. Preserve native transport timeouts; do not claim otherwise in evidence. This is an inherited transport limitation, not a formal write risk.
- Frontend `active` cleanup plus loaded.key equality prevents late responses from a previous target from rendering on a new target. SearchImage is keyed by image URL, so failed/loaded state normally resets on a new image. Reviewed and reference images remain alternative branches.

## Test/evidence gaps

Existing test sources cover happy path, same-key concurrent requests/cache, provider mismatch/no city/unsafe URL/explicit exception and endpoint argument validation. The timeout case raises TimeoutError immediately; it does not exercise the actual 20-second timeout or queue waiting. Add deadline and cancellation/coalescing assertions with controllable async providers where useful.

The frontend test named “does not show photos returned for a different provider identity” also uses a different city and does not provide a valid catalog-shaped response. It can pass before reaching identity validation. Make catalog response `{items:[]}`, keep the expected city equal, and change only the provider id to isolate the claimed guard. Add separate city/coordinate mismatches and deferred target-switch tests.

Do not claim actual photograph identity, location, license, or current scene verification from mock tests or rendered image visibility. Later real browser evidence should record canonical/provider identity, query, returned image/description/source, actual rendered target and refresh behavior; missing images should remain missing rather than be filled with a generic same-city photograph.

Conclusion: preserve the read-only integration, but fix venue-specific relevance, negative-cache bypass and stalled catalog fallback before considering this photo batch ready. No current GO conclusion and no independent acceptance score changes.

## Final correction follow-up

VERIFIED final source inspection only; no code execution or product edits. All three originally reported implementation paths are corrected:

1. Venue-scoped images are now prefiltered on the original title+description for complete canonical provider name AND city, before calling project_search and before its three-image limit. A generic “苏州火锅” image no longer reaches dish fallback for “海底捞火锅(园区店)”. A Chinese identifying title with an English description remains usable. The new test sources exercise both cases. This is search relevance binding, not independent image/branch/scene verification; a misleading or multi-place caption can still match, so the search_reference semantics remain essential.
2. Missing or invalid provider detail now raises an internal ValueError and passes through the shared unavailable-result cache insertion. The new sequential-lookup test checks that a missing POI causes only one detail call. The same code branch handles mismatched ref, missing city/name and invalid identity status. Thirty-second expiry is evident in code, but expiry behavior is not exercised by that new test.
3. Shared catalog fetch now uses AbortSignal.timeout(6000), causing a failed/timed-out promise to be evicted and the awaiting consumer to continue with an empty catalog and attempt fallback. Reference fetch uses AbortSignal.timeout(22000), larger than the backend20-second budget. This fixes the indefinite active-page catalog wait in browsers supporting AbortSignal.timeout. AbortSignal timeout follows browser active-time semantics; it is not a hard elapsed-clock guarantee in suspended tabs. Target cleanup still suppresses stale results rather than immediately cancelling an individual fallback; the request remains bounded, so this is a resource optimization, not a remaining correctness blocker.

The added frontend test explicitly defers A, switches to B, resolves B and then A, and asserts A does not return. This matches the intended active/key protection. The image-load failure test verifies that image failure preserves saved activity text. Existing backend source tests still use mocks and cannot establish real image correctness.

One nonblocking test-precision issue remains: the “different provider identity” frontend case still uses a mismatched city and a non-catalog response, so it can pass on the city guard without testing provider-id rejection. Isolate provider-id mismatch with an otherwise valid same-city response before citing that test specifically as provider-identity evidence. The final suite also lacks a simulated AbortSignal timeout/fallback test; implementation inspection supports the correction, but do not describe the current tests as exercising the real deadline.

Reconfirmed no repository/Trip/Activity/Planner/Accept write call was added. Canonical UUID/provider id checks, exact returned ref, current frontend city and optional coordinate proximity, reviewed-media preference, safe URL projection and search_reference/unknown-license boundaries remain intact. No new authorization or license inference appears.

Parent reports real isolated-browser photographs for 拙政园 and 狮子林, unchanged10/11-table snapshots, and retained first/second provider failures. Those artifacts were not independently inspected by this reviewer and are not upgraded to VERIFIED here. They should be reported as bounded visible-photo evidence, never whole-product GO or guaranteed photographic identity.

Final architectural disposition: original three findings resolved; no remaining blocking contract finding in the inspected photo batch. Retain the precise test caveat, native-thread cancellation limitation, search-reference qualification and historical failures. No product GO conclusion.
