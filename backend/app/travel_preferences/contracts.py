from typing import Literal
from pydantic import Field, field_validator
from app.place_content.contracts import DTO, GeoPoint, Place

Category = Literal["attraction", "food", "lodging"]

class TravelPreferences(DTO):
    version: Literal["travel-preferences-v1"] = "travel-preferences-v1"
    preferred_categories: list[Category] = Field(default_factory=list, max_length=3)
    interests: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values):
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 30 for value in cleaned):
            raise ValueError("interest must be at most 30 characters")
        return cleaned

class DiscoveryQuery(DTO):
    city: str = Field(min_length=1, max_length=100)

    @field_validator("city")
    @classmethod
    def valid_city(cls, value):
        if not value.strip():
            raise ValueError("city must not be blank")
        return value.strip()
    query: str = Field(default="", max_length=200)
    category: Category | None = None
    center: GeoPoint | None = None
    radius_meters: int = Field(default=3000, ge=1, le=50000)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_food_price_yuan: float | None = Field(default=None, ge=0)
    include_unknown: bool = True
    use_preferences: bool = True

class DiscoveryItem(DTO):
    place: Place
    reasons: list[str]

class DiscoveryResponse(DTO):
    items: list[DiscoveryItem]
    status: Literal["ok", "empty"]
    preference_applied: bool
    source: Literal["amap"] = "amap"
    note: str = "筛选只针对本次供应商返回结果；未知评分或餐饮参考价按选择保留。酒店实时价格和库存不支持。"
