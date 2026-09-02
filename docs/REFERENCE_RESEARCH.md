# RoamSync product reference study

This document records interaction principles only. RoamSync does not copy code,
stylesheets, assets, icons, or brand elements from the products below.

## Sources and decisions

| Reference | Useful pattern | RoamSync decision | Rejected or deferred |
| --- | --- | --- | --- |
| TREK | Map-led day planner, synchronized place/timeline selection, trip-scoped tools | Keep the current map workbench and use trip UUIDs for every write | No AGPL source, CSS, assets, or brand elements are copied |
| Wanderlog | Trip setup centered on destination, dates, and accommodation | Treat accommodation as a first-class POI anchor during trip creation | Reservations and email import are deferred |
| Google Maps | Search, preview, then confirm a place | Keep search results transient and persist a POI snapshot only after selection | No Google visual or brand cloning |
| TripIt | Clear trip directory and lifecycle organization | Group trips as upcoming, active, completed, or archived | Authentication and traveler sharing are deferred |
| MapLibre / Organic Maps | Explicit map layer ownership and route overlay lifecycle | Keep markers and routes isolated inside the map component | Replacing AMap rendering is not planned in this stage |

## RoamSync interaction principles

1. A trip is created from a verified city, dates, budget, and optional verified accommodation.
2. Every product route uses a persisted trip UUID; `demo` is not a product identifier.
3. Search results do not become planning data until the user confirms a place.
4. Archive is safer and more prominent than delete. Delete requires an impact preview.
5. Map provider failures are explicit and never replaced with invented production data.
6. Provider calls are debounced, cached where safe, and never log API keys.

## License boundary

TREK is studied as an AGPL-3.0 product reference only. RoamSync's implementation
is independent. New runtime packages must be reviewed before being added and
recorded in `THIRD_PARTY_NOTICES.md` when attribution is required.
