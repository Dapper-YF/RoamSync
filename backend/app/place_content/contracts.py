from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GeoPoint(DTO):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    coordinate_system: Literal["GCJ02"] = "GCJ02"


class ExternalRef(DTO):
    provider: Literal["amap"] = "amap"
    namespace: Literal["poi"] = "poi"
    provider_place_id: str


class PlaceRef(DTO):
    place_id: UUID
    external_ref: ExternalRef


class Source(DTO):
    provider: Literal["amap"] = "amap"
    source_url: str
    fetched_at: datetime
    expires_at: datetime
    # fetched_at is our retrieval time, never a claimed provider update time.
    provider_updated_at: datetime | None = None
    freshness: Literal["fresh", "stale"] = "fresh"


class Price(DTO):
    amount: float = Field(ge=0)
    currency: Literal["CNY"] = "CNY"
    unit: Literal["per_person_reference"] = "per_person_reference"
    provenance: Literal["provider_reference"] = "provider_reference"
    verified_live_quote: Literal[False] = False


class Image(DTO):
    url: str
    attribution: str
    source_url: str
    usage_basis: str
    place_ref: PlaceRef | None = None
    provider: Literal["wikimedia_commons"] | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    changes: str | None = None
    reviewed_at: str | None = None


class ReviewedExperience(DTO):
    summary: str
    attributes: list[str]
    source_url: str
    source_title: str
    reviewed_at: str
    confidence: Literal["reviewed_stable_description"] = "reviewed_stable_description"
    usage_basis: Literal["original_factual_summary_with_attribution"] = "original_factual_summary_with_attribution"
    unknown: list[str]
    scope: str


class Place(DTO):
    opening_hours_reference: str | None = None
    provider_tags: list[str] = Field(default_factory=list)
    ref: PlaceRef
    name: str
    category: Literal["attraction", "food", "lodging", "other"]
    provider_type: str | None = None
    aliases: list[str] = Field(default_factory=list, max_length=20)
    address: str | None = None
    city: str | None = None
    district: str | None = None
    location: GeoPoint
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_scale: Literal[5] = 5
    rating_status: Literal["provided", "unknown"] = "unknown"
    price: Price | None = None
    price_status: Literal["provider_reference", "unknown"] = "unknown"
    images: list[Image] = Field(default_factory=list)
    image_status: Literal["available", "missing", "withheld_pending_license"] = "missing"
    reviews_status: Literal["unavailable"] = "unavailable"
    identity_status: Literal["provider_identity", "provider_unavailable", "provider_id_invalid", "uncertain"] = "provider_identity"
    source: Source
    experience: ReviewedExperience | None = None


class SearchQuery(DTO):
    query: str = Field(default="", max_length=200)
    city: str | None = Field(default=None, max_length=100)
    category: Literal["attraction", "food", "lodging"] | None = None
    center: GeoPoint | None = None
    radius_meters: int = Field(default=3000, ge=1, le=50000)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=12, ge=1, le=25)

    @field_validator("city", mode="before")
    @classmethod
    def trim_city(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def scoped_search(self):
        if not self.city and self.center is None:
            raise ValueError("需要 city 区域或 GCJ02 center")
        if not self.query.strip() and self.category is None:
            raise ValueError("需要关键词或分类")
        return self


class SearchResponse(DTO):
    items: list[Place]
    page: int
    page_size: int
    total: int | None = None
    status: Literal["ok", "empty"]


class Favorite(DTO):
    place: Place
    saved_at: datetime


class FavoriteState(DTO):
    place_id: UUID
    is_favorite: bool


class RouteQuery(DTO):
    origin: GeoPoint
    destination: GeoPoint
    mode: Literal["walk", "driving"] = "walk"


class RouteResult(DTO):
    origin: GeoPoint
    destination: GeoPoint
    mode: Literal["walk", "driving"]
    distance_meters: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    path: list[GeoPoint]
    source: Source
    duration_semantics: Literal["provider_estimated_travel_time"] = "provider_estimated_travel_time"
    is_estimated_fallback: Literal[False] = False
    navigation_available: Literal[False] = False
