"""Google Places (New) 제공자 (B4, F-09, C-8).

- 검색: Text Search (POST /v1/places:searchText), center 둘레 locationBias 원
- 상세: Place Details (GET /v1/places/{id})
- 필드 마스크로 PlaceSummary·PlaceDetail에 필요한 필드만 받는다 (요금 등급도 필드로 정해진다)
- 사진: 사진 media 엔드포인트를 skipHttpRedirect로 불러 키가 없는 photoUri를 받는다. 응답에 API 키를 넣지 않는다
- 받은 값은 저장하지 않는다. 캐시·범위 거르기·호출 한도는 places 서비스가 맡는다
"""

from typing import Any
from urllib.parse import quote

import httpx

from app.core.schemas import LatLng
from app.integrations.places.models import (
    AuthorAttribution,
    OpeningPeriod,
    OpeningPoint,
    Photo,
    PlaceDetail,
    PriceLevel,
)

# 경로는 /v1/…로 쓴다 ("places:searchText"만 쓰면 places:가 URL scheme으로 읽힌다)
BASE_URL = "https://places.googleapis.com"
LANGUAGE_CODE = "ko"
# 검색 결과 수 (Text Search 한 페이지 최대 20)
SEARCH_PAGE_SIZE = 20
# locationBias 원 반경. 결과를 가까운 곳 쪽으로 기울일 뿐이고 실제 범위는 서비스가 거른다
SEARCH_BIAS_RADIUS_METERS = 5_000.0
PHOTO_MAX_WIDTH_PX = 800

_SUMMARY_FIELDS = (
    "id",
    "displayName",
    "primaryType",
    "priceLevel",
    "rating",
    "userRatingCount",
    "formattedAddress",
    "location",
    "utcOffsetMinutes",
    "regularOpeningHours.periods",
    "servesVegetarianFood",
    "googleMapsUri",
)
# 검색 결과는 요약만 쓰므로 사진을 받지 않는다 (상세에서만)
SEARCH_FIELD_MASK = ",".join(f"places.{f}" for f in _SUMMARY_FIELDS)
DETAIL_FIELD_MASK = ",".join((*_SUMMARY_FIELDS, "photos"))

_PRICE_LEVELS: dict[str, PriceLevel] = {
    "PRICE_LEVEL_INEXPENSIVE": "INEXPENSIVE",
    "PRICE_LEVEL_MODERATE": "MODERATE",
    "PRICE_LEVEL_EXPENSIVE": "EXPENSIVE",
    "PRICE_LEVEL_VERY_EXPENSIVE": "VERY_EXPENSIVE",
}


class GooglePlacesProvider:
    def __init__(
        self, api_key: str, *, timeout: float, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"X-Goog-Api-Key": api_key},
            transport=transport,
        )

    def text_search(
        self, query: str, *, center: tuple[float, float], ignore: tuple[str, ...]
    ) -> list[PlaceDetail]:
        # ignore(도시·동네 이름)는 Google이 위치 단서로 잘 쓰므로 검색어에서 빼지 않는다
        lat, lng = center
        response = self._client.post(
            "/v1/places:searchText",
            headers={"X-Goog-FieldMask": SEARCH_FIELD_MASK},
            json={
                "textQuery": query,
                "languageCode": LANGUAGE_CODE,
                "pageSize": SEARCH_PAGE_SIZE,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": SEARCH_BIAS_RADIUS_METERS,
                    }
                },
            },
        )
        response.raise_for_status()
        places: list[dict[str, Any]] = response.json().get("places", [])
        return [map_place(p) for p in places]

    def get(self, place_id: str) -> PlaceDetail | None:
        response = self._client.get(
            f"/v1/places/{quote(place_id, safe='')}",
            params={"languageCode": LANGUAGE_CODE},
            headers={"X-Goog-FieldMask": DETAIL_FIELD_MASK},
        )
        # 없는 id는 404, 모양이 틀린 id(예: 샘플 데이터의 mock-…)는 400 INVALID_ARGUMENT
        if response.status_code in (400, 404):
            return None
        response.raise_for_status()
        raw: dict[str, Any] = response.json()
        photos: list[dict[str, Any]] = raw.get("photos") or []
        photo = self._photo(photos[0]) if photos else None
        return map_place(raw, photo)

    def _photo(self, raw: dict[str, Any]) -> Photo | None:
        """첫 사진의 키 없는 URL과 작성자 표시. 받지 못하면 사진 없이 상세를 보여 준다."""
        try:
            response = self._client.get(
                f"/v1/{raw['name']}/media",
                params={"maxWidthPx": PHOTO_MAX_WIDTH_PX, "skipHttpRedirect": "true"},
            )
            response.raise_for_status()
            url: str = response.json()["photoUri"]
        except (httpx.HTTPError, KeyError, ValueError):
            return None
        return Photo(
            url=url,
            author_attributions=[
                AuthorAttribution(display_name=a.get("displayName", ""), uri=a.get("uri", ""))
                for a in raw.get("authorAttributions", [])
            ],
        )


def map_place(raw: dict[str, Any], photo: Photo | None = None) -> PlaceDetail:
    """Places(New) Place 객체 → PlaceDetail. proto3 JSON은 0·false 값을 빼므로 없으면 0으로 본다."""
    place_id: str = raw["id"]
    location = raw.get("location", {})
    hours = raw.get("regularOpeningHours")
    return PlaceDetail(
        place_id=place_id,
        name=raw.get("displayName", {}).get("text", ""),
        primary_type=raw.get("primaryType", "restaurant"),
        price_level=_PRICE_LEVELS.get(raw.get("priceLevel", "")),
        rating=raw.get("rating"),
        user_rating_count=raw.get("userRatingCount"),
        address=raw.get("formattedAddress", ""),
        location=LatLng(lat=location.get("latitude", 0.0), lng=location.get("longitude", 0.0)),
        utc_offset_minutes=raw.get("utcOffsetMinutes", 0),
        regular_hours=[_period(p) for p in hours.get("periods", [])] if hours else None,
        serves_vegetarian_food=raw.get("servesVegetarianFood"),
        google_maps_uri=raw.get("googleMapsUri")
        or f"https://www.google.com/maps/place/?q=place_id:{place_id}",
        photo=photo,
    )


def _point(raw: dict[str, Any]) -> OpeningPoint:
    return OpeningPoint(day=raw.get("day", 0), hour=raw.get("hour", 0), minute=raw.get("minute", 0))


def _period(raw: dict[str, Any]) -> OpeningPeriod:
    # 24시간 영업은 open(일 0시 0분)만 있고 close가 없다
    close = raw.get("close")
    return OpeningPeriod(open=_point(raw.get("open", {})), close=_point(close) if close else None)
