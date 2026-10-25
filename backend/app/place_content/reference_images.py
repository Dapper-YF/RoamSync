"""Optional sourced photographs for a verified POI, never planning evidence.

Only provider-issued names/cities enter search. No image downloading, media
licence inference, trip writes or model-authored URLs. Reviewed media remains
the preferred presentation and is not mixed with this search-reference schema.
"""
import asyncio
from collections import OrderedDict
from dataclasses import replace
from time import monotonic

from app.assistant_search import project_search
from app.external_facts import search_tavily
from .contracts import ExternalRef, PlaceRef
from .provider import stable_place_id


class PlaceReferenceImages:
    def __init__(self, provider, settings, *, search=search_tavily):
        self.provider, self.settings, self.search = provider, settings, search
        self.cache = OrderedDict()
        self.inflight = {}
        self.slots = asyncio.Semaphore(4)

    async def lookup(self, place_id, provider_place_id):
        empty = {"status": "unavailable", "images": [],
            "semantics": "search_reference_not_verified_scene_or_current_conditions"}
        if stable_place_id(provider_place_id) != place_id:
            return empty
        key = (place_id, provider_place_id)
        cached = self.cache.get(key)
        if cached and cached[0] > monotonic():
            self.cache.move_to_end(key)
            return cached[1]
        if key in self.inflight:
            return await asyncio.shield(self.inflight[key])

        async def load():
            result = empty
            try:
                # Queueing and both providers share one bounded time budget.
                async with asyncio.timeout(20), self.slots:
                    ref = PlaceRef(place_id=place_id, external_ref=ExternalRef(provider_place_id=provider_place_id))
                    place = await self.provider.detail(ref)
                    if (place is None or place.ref != ref or place.identity_status != "provider_identity"
                        or not place.city or not place.name):
                        raise ValueError('Unverified provider identity')
                    options = self.settings.model_copy(update={"search_timeout_seconds": min(15, self.settings.search_timeout_seconds)})
                    fact = await self.search(options, query=f"{place.city} {place.name} 实景照片",
                        max_results=2, include_images=True, retry_attempts=1)
                    city = place.city.removesuffix('市')
                    # Filter the provider's original title + description BEFORE
                    # the shared projector's three-image limit. Descriptions
                    # are often English while the original title is Chinese.
                    # Full venue identity is mandatory; the chat projector's
                    # generic dish fallback cannot establish a branch match.
                    scoped = []
                    for item in fact.payload.get('images', [])[:12]:
                        if not isinstance(item, dict):
                            continue
                        identity = f"{item.get('title', '')} {item.get('description', '')}".casefold()
                        if city.casefold() in identity and place.name.casefold() in identity:
                            scoped.append(item)
                    projected = project_search(replace(fact, payload={**fact.payload, 'images': scoped}), place.name + "的图片")
                    images = [{**image, "usage_basis": "search_reference"}
                        for image in projected['images']][:1]
                    result = {**empty, "status": "available" if images else "unavailable",
                        "place": {"ref": place.ref.model_dump(mode='json'), "name": place.name,
                            "city": place.city, "location": place.location.model_dump(mode='json')},
                        "images": images, "queried_at": fact.queried_at}
            except Exception:
                # Optional photos cannot prevent itinerary viewing; never echo
                # provider errors, credentials or arbitrary response bodies.
                pass
            finally:
                self.inflight.pop(key, None)
            self.cache[key] = (monotonic() + (600 if result['images'] else 30), result)
            self.cache.move_to_end(key)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
            return result

        task = asyncio.create_task(load())
        self.inflight[key] = task
        return await asyncio.shield(task)
