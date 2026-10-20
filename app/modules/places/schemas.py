"""식당 검색·상세·맛집 모음 (frontend/src/api/schemas/place.ts)."""

from typing import Literal

from app.core.schemas import ApiModel, Id, Instant, Menu40
from app.integrations.places.models import PlaceDetail, PlaceSummary

__all__ = [
    "AreaScope",
    "CityScope",
    "PlaceDetail",
    "PlaceSearchResponse",
    "PlaceSearchResult",
    "PlaceSummary",
    "Placement",
    "SavePlaceInput",
    "SavedPlace",
]


class PlaceSearchResult(PlaceSummary):
    # 동네 중심에서의 거리(m). 도시 전체 검색이면 null
    distance_meters: int | None


class AreaScope(ApiModel):
    kind: Literal["area"] = "area"
    area_id: str
    area_name: str


class CityScope(ApiModel):
    kind: Literal["city"] = "city"


class PlaceSearchResponse(ApiModel):
    scope: AreaScope | CityScope
    query: str
    results: list[PlaceSearchResult]
    fallback_maps_url: str


class Placement(ApiModel):
    trip_id: str
    slot_id: str
    day_number: int
    slot_name: str


class SavedPlace(ApiModel):
    id: str
    city_id: str
    place_id: str
    menu: str
    kind_id: str | None
    area_id: str | None
    source: Literal["search"]
    saved_at: Instant
    place: PlaceSummary | None
    placements: list[Placement]


class SavePlaceInput(ApiModel):
    city_id: Id
    place_id: Id
    menu: Menu40
    kind_id: Id | None = None
