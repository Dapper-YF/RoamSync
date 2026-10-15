# Travel Fact Resolution Benchmark

From `backend`, with the frozen backend environment:

```powershell
uv run --frozen python -m evals.travel_facts.run --output evals/travel_facts/results.json
```

Docker (isolated project, no keys needed):

```powershell
docker compose -p roamsync-travel-facts-test -f compose.test.yaml build api-test
docker compose -p roamsync-travel-facts-test -f compose.test.yaml run --rm --no-deps api-test uv run --no-sync python -m evals.travel_facts.run
```

28 synthetic, deterministic cases compare actual typed result with the explicit
expected status, freshness, value subset, current usability, evidence count and
conflict count in `cases.json`. Honesty is measured on cases expecting no value.
No LLM or live Provider call; TEST TTLs are not production SLAs. PostgreSQL
read-only guarantees are separately exercised by `test_travel_facts_execution.py`.

`baseline.json` records the measured pre-change full suite. `verification.json`
records final suite/environment/source hashes; `results.json` is the actual
benchmark output. A payload fingerprint is not a recoverable raw blob.

Service usage requires the caller's **explicit product policy**, not this
fixture policy:

```python
from app.travel_facts.adapters import AMapRouteAdapter
from app.travel_facts.models import FactRequirement, GeoPoint, RouteSubject
from app.travel_facts.policies import FactAuthorityPolicy, FactFreshnessPolicy
from app.travel_facts.repository import InMemoryFactRepository
from app.travel_facts.service import TravelFactService

async def route_duration(configured_freshness: FactFreshnessPolicy):
    resolver = TravelFactService(
        InMemoryFactRepository(), configured_freshness,
        FactAuthorityPolicy.existing_providers(),
        [AMapRouteAdapter(configured_freshness)],
    )
    return await resolver.resolve_fact(FactRequirement(
        fact_type="route.duration",
        subject=RouteSubject(
            ref="caller-stable-leg-id",
            origin=GeoPoint(longitude=120.1, latitude=30.2, coordinate_system="gcj02"),
            destination=GeoPoint(longitude=120.2, latitude=30.3, coordinate_system="gcj02"),
            travel_mode="walk",
        ),
        reason="check route duration for a planning decision",
    ))
```

The result carries typed minutes, provenance, retrieval/freshness/confidence and
resolution status; it can instead report a gap. The caller checks status and
`usable_as_current`, retains conflicts, and reasons above the fact boundary.
`route.duration` is a Provider prediction, not a navigation ETA observation.
