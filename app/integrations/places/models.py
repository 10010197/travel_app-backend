"""식당 정보 모양 (frontend/src/api/schemas/place.ts의 PlaceSummary·PlaceDetail).

Places에서 받은 값을 이 모양으로 바꿔 내보낸다. 저장하지 않는다(C-8). 사용자 데이터에는 place_id만 남긴다.
"""

from typing import Literal

from app.core.schemas import ApiModel, LatLng

PriceLevel = Literal["INEXPENSIVE", "MODERATE", "EXPENSIVE", "VERY_EXPENSIVE"]


class OpeningPoint(ApiModel):
    day: int
    hour: int
    minute: int


class OpeningPeriod(ApiModel):
    open: OpeningPoint
    # None이면 24시간 영업
    close: OpeningPoint | None


class PlaceSummary(ApiModel):
    place_id: str
    name: str
    primary_type: str
    price_level: PriceLevel | None
    rating: float | None
    user_rating_count: int | None
    address: str
    location: LatLng
    utc_offset_minutes: int
    regular_hours: list[OpeningPeriod] | None
    serves_vegetarian_food: bool | None
    google_maps_uri: str


class AuthorAttribution(ApiModel):
    display_name: str
    uri: str


class Photo(ApiModel):
    url: str
    author_attributions: list[AuthorAttribution]


class PlaceDetail(PlaceSummary):
    photo: Photo | None

    def summary(self) -> PlaceSummary:
        return PlaceSummary.model_validate(self.model_dump(exclude={"photo"}))
