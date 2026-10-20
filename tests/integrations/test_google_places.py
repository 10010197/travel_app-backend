"""Google Places(New) 제공자: 요청 모양과 응답 → PlaceDetail 변환. 실제 API는 부르지 않는다 (httpx.MockTransport)."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import get_settings
from app.integrations.places import get_places_provider
from app.integrations.places.google import (
    DETAIL_FIELD_MASK,
    SEARCH_FIELD_MASK,
    GooglePlacesProvider,
)
from app.integrations.places.sample import SamplePlacesProvider

API_KEY = "test-places-key"
PHOTO_NAME = "places/ChIJabc/photos/AXCi2Q"
PHOTO_URI = "https://lh3.googleusercontent.com/places/AXCi2Q=s800"

# Places(New) 응답 (공식 문서 예시 모양). 0인 값(day 0, minute 0)은 proto3 JSON이라 빠진다
RAMEN: dict[str, Any] = {
    "id": "ChIJabc",
    "displayName": {"text": "텐진 돈코츠 하루", "languageCode": "ko"},
    "primaryType": "ramen_restaurant",
    "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    "rating": 4.3,
    "userRatingCount": 2140,
    "formattedAddress": "일본 후쿠오카현 후쿠오카시 주오구 텐진 2-1",
    "location": {"latitude": 33.5915, "longitude": 130.3995},
    "utcOffsetMinutes": 540,
    "regularOpeningHours": {
        "periods": [
            {"open": {"hour": 11}, "close": {"day": 1, "hour": 2, "minute": 30}},
            {"open": {"day": 1, "hour": 11}, "close": {"day": 2, "hour": 2}},
        ]
    },
    "servesVegetarianFood": False,
    "googleMapsUri": "https://maps.google.com/?cid=123",
}
ALL_DAY: dict[str, Any] = {
    "id": "ChIJ24h",
    "displayName": {"text": "24시 우동"},
    "priceLevel": "PRICE_LEVEL_FREE",
    "location": {"latitude": 33.59, "longitude": 130.42},
    "utcOffsetMinutes": 540,
    "regularOpeningHours": {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]},
}

Handler = Callable[[httpx.Request], httpx.Response]


def provider(handler: Handler) -> tuple[GooglePlacesProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return GooglePlacesProvider(API_KEY, timeout=1.0, transport=httpx.MockTransport(record)), seen


def test_text_search_request_and_mapping() -> None:
    google, seen = provider(lambda _: httpx.Response(200, json={"places": [RAMEN, ALL_DAY]}))

    found = google.text_search("라멘 텐진", center=(33.59, 130.40), ignore=("후쿠오카",))

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://places.googleapis.com/v1/places:searchText"
    assert request.headers["X-Goog-Api-Key"] == API_KEY
    assert request.headers["X-Goog-FieldMask"] == SEARCH_FIELD_MASK
    assert "photos" not in SEARCH_FIELD_MASK
    body = json.loads(request.content)
    assert body["textQuery"] == "라멘 텐진"
    assert body["locationBias"]["circle"]["center"] == {"latitude": 33.59, "longitude": 130.40}

    ramen, all_day = found
    assert ramen.model_dump(by_alias=True) == {
        "placeId": "ChIJabc",
        "name": "텐진 돈코츠 하루",
        "primaryType": "ramen_restaurant",
        "priceLevel": "INEXPENSIVE",
        "rating": 4.3,
        "userRatingCount": 2140,
        "address": "일본 후쿠오카현 후쿠오카시 주오구 텐진 2-1",
        "location": {"lat": 33.5915, "lng": 130.3995},
        "utcOffsetMinutes": 540,
        "regularHours": [
            {
                "open": {"day": 0, "hour": 11, "minute": 0},
                "close": {"day": 1, "hour": 2, "minute": 30},
            },
            {
                "open": {"day": 1, "hour": 11, "minute": 0},
                "close": {"day": 2, "hour": 2, "minute": 0},
            },
        ],
        "servesVegetarianFood": False,
        "googleMapsUri": "https://maps.google.com/?cid=123",
        "photo": None,
    }
    # 빠진 필드는 null·기본값, FREE는 계약 밖이라 null, 24시간은 close null
    assert all_day.price_level is None
    assert all_day.rating is None
    assert all_day.primary_type == "restaurant"
    assert all_day.regular_hours is not None
    assert all_day.regular_hours[0].close is None
    assert all_day.google_maps_uri == "https://www.google.com/maps/place/?q=place_id:ChIJ24h"


def test_text_search_empty_response() -> None:
    google, _ = provider(lambda _: httpx.Response(200, json={}))
    assert google.text_search("없는 메뉴", center=(0, 0), ignore=()) == []


def test_text_search_error_raises() -> None:
    # 서비스가 잡아 빈 결과 + 지도 링크로 바꾼다
    google, _ = provider(lambda _: httpx.Response(500, json={"error": {"code": 500}}))
    with pytest.raises(httpx.HTTPStatusError):
        google.text_search("라멘", center=(0, 0), ignore=())


def detail_handler(photo_response: httpx.Response) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v1/{PHOTO_NAME}/media":
            return photo_response
        return httpx.Response(
            200,
            json={
                **RAMEN,
                "photos": [
                    {
                        "name": PHOTO_NAME,
                        "widthPx": 4032,
                        "heightPx": 3024,
                        "authorAttributions": [
                            {
                                "displayName": "Kim",
                                "uri": "https://maps.google.com/maps/contrib/1",
                                "photoUri": "https://lh3.googleusercontent.com/a/x",
                            }
                        ],
                    },
                    {"name": "places/ChIJabc/photos/second"},
                ],
            },
        )

    return handle


def test_get_detail_with_photo_without_key_in_url() -> None:
    google, seen = provider(
        detail_handler(httpx.Response(200, json={"name": PHOTO_NAME, "photoUri": PHOTO_URI}))
    )

    place = google.get("ChIJabc")

    assert place is not None
    detail, media = seen
    assert detail.url.path == "/v1/places/ChIJabc"
    assert detail.headers["X-Goog-FieldMask"] == DETAIL_FIELD_MASK
    assert media.url.params["skipHttpRedirect"] == "true"
    assert media.url.params["maxWidthPx"] == "800"
    assert place.photo is not None
    assert place.photo.model_dump(by_alias=True) == {
        "url": PHOTO_URI,
        "authorAttributions": [
            {"displayName": "Kim", "uri": "https://maps.google.com/maps/contrib/1"}
        ],
    }
    assert API_KEY not in place.model_dump_json()
    assert place.summary().place_id == "ChIJabc"


def test_get_detail_photo_failure_keeps_place() -> None:
    google, _ = provider(detail_handler(httpx.Response(403, json={})))
    place = google.get("ChIJabc")
    assert place is not None
    assert place.photo is None


@pytest.mark.parametrize("status", [400, 404])
def test_get_unknown_place_is_none(status: int) -> None:
    google, seen = provider(lambda _: httpx.Response(status, json={"error": {"code": status}}))
    assert google.get("mock-fuk-01/../x") is None
    assert seen[0].url.raw_path == b"/v1/places/mock-fuk-01%2F..%2Fx?languageCode=ko"


def test_get_server_error_raises() -> None:
    google, _ = provider(lambda _: httpx.Response(503, json={}))
    with pytest.raises(httpx.HTTPStatusError):
        google.get("ChIJabc")


def test_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(get_places_provider(), SamplePlacesProvider)

    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", API_KEY)
    get_settings.cache_clear()
    assert isinstance(get_places_provider(), GooglePlacesProvider)
