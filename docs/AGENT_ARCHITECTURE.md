# RoamSync Agent architecture contract

This document is the source of truth for the first Agent planning workflow. It
defines boundaries for the first LangGraph runtime before a real model provider
is enabled.

## Product boundary

The Agent produces a reviewable `PlanRevision`; it never writes a formal trip
directly. Formal `Activity` and `RouteLeg` rows are changed only by the existing
transactional revision-acceptance service after deterministic validation and a
user decision.

The first intent vocabulary is deliberately small:

- `create_plan`
- `replan_trip`
- `modify_day`
- `unknown`

The strict Pydantic contracts are `PlanningIntent`, `PlanningRequest`, and
`CandidatePlanSnapshot`. Additional intents require fixtures and acceptance
tests before they can be added.

Intent parsing starts with the versioned, high-precision `rules-v1` router. It
uses UI-selected IDs and persisted trip entities to resolve days and protected
activities. Unsupported input returns `unknown`; invalid dates, missing target
days, and non-unique activity names produce explicit clarification questions.
The initial fixture suite contains more than sixty Chinese utterances. A future
model parser may handle the `unknown` branch, but it must emit the same strict
contract and pass the same resolver and clarification gates.

## Responsibilities and permissions

| Component | May do | Must not do |
| --- | --- | --- |
| Intent parser | Convert text and UI context to a strict intent object | Search maps, write planning data, or choose approval |
| Intent resolver | Resolve dates and known entity references; report ambiguity | Guess between multiple matching entities |
| Research node | Query configured providers and persist verified candidates/sources | Invent POIs or silently use demo results |
| Planner | Arrange only supplied candidate IDs into a structured snapshot | Query the database, invent prices, or write formal plans |
| Route enrichment | Resolve adjacent route evidence through the configured map provider | Hide provider failures or fabricate production routes |
| Validator | Enforce ownership, time, route, budget, lock, and version rules | Ask an LLM whether a hard constraint passed |
| Reviewer | Return bounded correction advice from validation issues | Override validation or approve a revision |
| Acceptance service | Atomically apply a valid, current revision after user approval | Accept stale or invalid revisions |

## Candidate evidence

Every candidate activity references a trip-owned `PlaceCandidate` and its
`SourceRecord`. Every adjacent pair in the complete candidate day, including
formal locked/active/completed activities that remain in place, has a
`CandidateRouteLeg`. The route evidence is stored both in the immutable proposed
snapshot and in normalized audit rows tied to the revision.

Production requires the configured AMap Web Service key. Estimated routes are a
test/development escape hatch controlled by `ALLOW_MAP_ESTIMATES`; they are not a
silent production fallback.

## LangGraph runtime boundary

The graph now orchestrates intent resolution, bounded clarification, draft
generation, route enrichment, deterministic validation, revision persistence,
and approval. `PlanningRun.id` is its `thread_id`. PostgreSQL checkpoints hold
recoverable execution state, while `PlanningRun`, `PlanRevision`, and candidate
evidence remain the product and audit source of truth.

The Draft Provider is an injected protocol. Production uses the configured
DeepSeek Responses API with JSON Schema output and a second local Pydantic
validation pass. The model may select only supplied place IDs and dates; costs,
sources, replacement IDs, and routes are resolved by backend code. Missing
configuration records `planner_not_configured`. A failed deterministic
validation may trigger exactly one correction pass containing the prior draft
and explicit validation issues. A second failure records
`planner_constraints_unsatisfied`; the Reviewer cannot override validation.

The graph state must contain JSON-serializable values only. Database sessions,
ORM entities, API clients, secrets, and arbitrary executable objects are
forbidden. Human clarification and final approval use explicit interrupts;
side effects before an interrupt must be idempotent.

## Failure rules

- Missing provider credentials produce a stable configuration error.
- Provider rejection, timeout, or quota exhaustion remains visible to the run.
- Unknown or ambiguous intent pauses for clarification instead of guessing.
- Reviewer correction is bounded to one round in the first implementation.
- A route-time, ownership, budget, protected-activity, or trip-version failure
  prevents acceptance.
