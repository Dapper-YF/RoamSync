"""Existing AMap/Open-Meteo seams only; no search-to-truth or estimate fallback."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Callable
from zoneinfo import ZoneInfo

from .interfaces import ProviderUnavailable
from .models import (CategoryValue, FactBundle, FactRequirement, FactType, GeoPoint, IdentityValue,
                     LocationValue, MeasurementValue, WeatherValue)
from .normalization import evidence_record, fact_record
from .policies import FactFreshnessPolicy


async def _poi_gateway(name, destination):
    from app.maps_service import search_amap_location_pois
    return await search_amap_location_pois(name, destination)


async def _route_gateway(subject):
    # The existing network-only seam avoids resolve_route_result's DB writes
    # and RoamSync Estimate fallback. Private seam compatibility is tested.
    from app.maps_service import _fetch_amap_route
    origin = SimpleNamespace(longitude=subject.origin.longitude, latitude=subject.origin.latitude)
    destination = SimpleNamespace(longitude=subject.destination.longitude, latitude=subject.destination.latitude)
    return await _fetch_amap_route(origin, destination, subject.travel_mode, subject.destination_city)


async def _weather_gateway(subject, time_scope, now):
    from app.config import get_settings
    from app.external_facts import fetch_open_meteo
    start = (time_scope.start if time_scope else now).astimezone(UTC)
    end = (time_scope.end - timedelta(microseconds=1)).astimezone(UTC) if time_scope and time_scope.end else start
    return await fetch_open_meteo(get_settings(), latitude=subject.location.latitude, longitude=subject.location.longitude,
                                 start_date=start.date(), end_date=end.date(), timezone="UTC")


class AMapPoiAdapter:
    name, read_through = "amap_poi", False
    def __init__(self, freshness: FactFreshnessPolicy, *, gateway=_poi_gateway, clock: Callable = lambda: datetime.now(UTC)):
        self.freshness, self.gateway, self.clock = freshness, gateway, clock

    def supports(self, requirement):
        return requirement.fact_type in {FactType.PLACE_IDENTITY, FactType.PLACE_LOCATION, FactType.PLACE_CATEGORY}

    async def fetch(self, requirement: FactRequirement, *, now: datetime) -> FactBundle:
        subject = requirement.subject
        if not subject.ref.startswith("amap:") or not subject.name or not subject.destination:
            return FactBundle()  # Exact identity requires a supplied stable ID.
        items = await self.gateway(subject.name, subject.destination)
        matches = [item for item in items if item.poi_id == subject.ref.removeprefix("amap:")]
        if len(matches) != 1:
            return FactBundle()  # Never pick a first/fuzzy/duplicate name match.
        item = matches[0]
        kind = requirement.fact_type
        if kind == FactType.PLACE_IDENTITY:
            value = IdentityValue(provider_place_id=item.poi_id, name=item.name)
        elif kind == FactType.PLACE_LOCATION:
            value = LocationValue(point=GeoPoint(longitude=item.longitude, latitude=item.latitude, coordinate_system="gcj02"))
        elif item.type_name:
            value = CategoryValue(category=item.type_name)  # Native provider type, not heuristic classification.
        else:
            return FactBundle()
        retrieved = self.clock()
        evidence = evidence_record(provider="amap", source_type="structured_api", source_reference="amap:poi:"+item.poi_id,
            retrieved_at=retrieved, normalized_snapshot={"fact_type":kind.value, "value":value.model_dump(mode="json")},
            metadata={"source_observation_time":"not_supplied_by_existing_adapter"})
        fact = fact_record(fact_type=kind, subject=subject, value=value, evidence=evidence, freshness=self.freshness,
                           nature="provider_assertion")
        return FactBundle(facts=(fact,), evidence=(evidence,))


class AMapRouteAdapter:
    name, read_through = "amap_route", False
    def __init__(self, freshness: FactFreshnessPolicy, *, gateway=_route_gateway, clock: Callable = lambda: datetime.now(UTC)):
        self.freshness, self.gateway, self.clock = freshness, gateway, clock

    def supports(self, requirement):
        return requirement.fact_type in {FactType.ROUTE_DISTANCE, FactType.ROUTE_DURATION}

    async def fetch(self, requirement: FactRequirement, *, now: datetime) -> FactBundle:
        subject = requirement.subject
        if subject.origin.coordinate_system != "gcj02" or subject.destination.coordinate_system != "gcj02":
            return FactBundle()
        # Existing gateway cannot predict a requested future departure.
        if requirement.time_scope is not None and requirement.time_scope.start > now:
            return FactBundle()
        if subject.travel_mode == "transit" and not subject.destination_city:
            return FactBundle()
        result = await self.gateway(subject)
        distance, duration, provider, estimated, path, alternatives = result
        if (estimated or not provider.startswith("AMap") or isinstance(distance, bool) or isinstance(duration, bool)
            or distance <= 0 or duration <= 0):
            raise ProviderUnavailable("invalid_provider_data")
        kind = requirement.fact_type
        value = MeasurementValue(amount=duration if kind == FactType.ROUTE_DURATION else distance,
                                 unit="minutes" if kind == FactType.ROUTE_DURATION else "meters")
        retrieved = self.clock()
        evidence = evidence_record(provider="amap", source_type="structured_api", source_reference="amap:route:"+subject.ref,
            retrieved_at=retrieved, normalized_snapshot={"distance_meters":distance, "duration_minutes":duration,
                "travel_mode":subject.travel_mode, "is_estimated":False}, raw_payload=list(result),
            metadata={"duration_semantics":"provider_prediction_rounded_up_to_minutes", "source_observation_time":"not_supplied"})
        expiry = self.freshness.fresh_until(kind, retrieved)
        fact = fact_record(fact_type=kind, subject=subject, value=value, evidence=evidence, freshness=self.freshness,
            nature="provider_prediction" if kind == FactType.ROUTE_DURATION else "provider_assertion",
            effective_from=retrieved, effective_until=expiry, specificity="time_specific")
        return FactBundle(facts=(fact,), evidence=(evidence,))


class WeatherForecastAdapter:
    name, read_through = "open_meteo", False
    def __init__(self, freshness: FactFreshnessPolicy, *, gateway=_weather_gateway):
        self.freshness, self.gateway = freshness, gateway

    def supports(self, requirement):
        # Existing Open-Meteo adapter requests hourly forecast only, NOT current.
        return requirement.fact_type == FactType.WEATHER_FORECAST

    async def fetch(self, requirement: FactRequirement, *, now: datetime) -> FactBundle:
        subject = requirement.subject
        if subject.location.coordinate_system != "wgs84":
            return FactBundle()
        result = await self.gateway(subject, requirement.time_scope, now)
        return normalize_weather(result, requirement, self.freshness, now=now)


def normalize_weather(result, requirement: FactRequirement, freshness: FactFreshnessPolicy, *, now: datetime) -> FactBundle:
    if result.provider not in {"open_meteo", "open-meteo"}:
        raise ProviderUnavailable("invalid_provider_data")
    payload = result.payload
    if abs(result.latitude - requirement.subject.location.latitude) > 0.01 or abs(result.longitude - requirement.subject.location.longitude) > 0.01:
        raise ProviderUnavailable("invalid_provider_data")
    hourly, units = payload.get("hourly", {}), payload.get("hourly_units", {})
    if (units.get("temperature_2m") != "°C" or units.get("precipitation_probability") != "%"
        or units.get("weather_code") != "wmo code"):
        raise ProviderUnavailable("invalid_provider_data")
    times = hourly.get("time", [])
    keys = ("temperature_2m", "precipitation_probability", "weather_code")
    if not times or len(times) > 744 or any(len(hourly.get(key, [])) != len(times) for key in keys):
        raise ProviderUnavailable("invalid_provider_data")
    timezone = ZoneInfo(payload["timezone"])
    starts = [datetime.fromisoformat(stamp) for stamp in times]
    starts = [stamp.replace(tzinfo=timezone) if stamp.tzinfo is None else stamp for stamp in starts]
    if any(second - first != timedelta(hours=1) for first,second in zip(starts, starts[1:])):
        raise ProviderUnavailable("invalid_provider_data")
    target = requirement.time_scope.start if requirement.time_scope else now
    slots = [index for index,start in enumerate(starts) if start <= target < start + timedelta(hours=1)]
    if len(slots) != 1:
        return FactBundle()
    index, start = slots[0], starts[slots[0]]
    if any(hourly[key][index] is None or isinstance(hourly[key][index], bool) for key in keys):
        raise ProviderUnavailable("invalid_provider_data")
    value = WeatherValue(temperature_celsius=hourly[keys[0]][index],
        precipitation_probability_percent=hourly[keys[1]][index], weather_code=hourly[keys[2]][index])
    retrieved = datetime.fromisoformat(result.queried_at)
    evidence = evidence_record(provider="open_meteo", source_type="structured_api", source_reference="open_meteo:forecast:"+requirement.subject.ref,
        retrieved_at=retrieved, normalized_snapshot={"forecast_start":start.isoformat(), "value":value.model_dump(mode="json")},
        raw_payload=payload, metadata={"model_issue_time":"not_supplied", "time_semantics":"forecast_valid_time_not_observation_time"})
    fact = fact_record(fact_type=FactType.WEATHER_FORECAST, subject=requirement.subject, value=value, evidence=evidence,
        freshness=freshness, nature="provider_prediction", effective_from=start, effective_until=start+timedelta(hours=1),
        specificity="time_specific")
    return FactBundle(facts=(fact,), evidence=(evidence,))
