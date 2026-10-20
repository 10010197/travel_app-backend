"""좌표·지도 링크 (FEATURE_SPEC F-09, F-15). 프론트 src/domain/mapsUrl.ts, mocks/places/search.ts와 같다.

식당 검색 범위(동네 반경 × 1.5), 맛집 모음의 동네 정하기, 검색 실패 때의 구글 지도 링크에 쓴다.
"""

import math
from dataclasses import dataclass
from urllib.parse import quote

# 동네 범위 검색은 동네 반경보다 조금 넓게 본다 (F-09 1)
AREA_SEARCH_RADIUS_FACTOR = 1.5


@dataclass(frozen=True, slots=True)
class Point:
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class AreaCircle:
    id: str
    center: Point
    radius_meters: int


def distance_meters(a: Point, b: Point) -> int:
    """두 좌표 사이 거리(m). 지구를 구로 보는 하버사인 공식"""
    r = 6_371_000
    d_lat = math.radians(b.lat - a.lat)
    d_lng = math.radians(b.lng - a.lng)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(d_lng / 2) ** 2
    )
    return round(2 * r * math.asin(math.sqrt(h)))


def area_of_location(areas: list[AreaCircle], location: Point) -> str | None:
    """식당 좌표로 동네를 정한다. 어느 동네 반경에도 없으면 None("동네 미정", F-15 5)"""
    inside = [
        (distance_meters(a.center, location), a.id)
        for a in areas
        if distance_meters(a.center, location) <= a.radius_meters
    ]
    return min(inside)[1] if inside else None


def build_search_query(menu: str | None, area_name: str | None, city_name: str) -> str:
    """식당 검색어: "메뉴명 + 끼니 동네 + 도시". 비어 있는 부분은 건너뛴다."""
    parts = (p.strip() for p in (menu, area_name, city_name) if p)
    return " ".join(p for p in parts if p)


def build_google_maps_search_url(query: str) -> str:
    """구글 지도 검색 URL (단일 유틸리티로만 만든다). encodeURIComponent와 같은 인코딩"""
    return "https://www.google.com/maps/search/?api=1&query=" + quote(
        query.strip(), safe="-_.!~*'()"
    )
