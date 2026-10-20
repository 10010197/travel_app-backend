"""식당 검색·상세·맛집 모음 (places 경계, F-09, F-15, C-8).

- 식당 정보는 저장하지 않는다. 제공자(Google Places, 키가 없으면 샘플)에서 받아 10분 동안만 메모리에 둔다
- 검색은 사용자별 호출 한도를 센다 (TECH_STACK 4-1, 429 RATE_LIMITED)
- 검색이 실패해도 fallbackMapsUrl(같은 검색어의 구글 지도 링크)로 화면 흐름이 이어진다 (F-09 5)
"""

import logging
import time
from threading import Lock
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.schemas import parse_uuid
from app.core.security import CurrentUser
from app.db.session import Conn, user_tx
from app.domain.geo import (
    AREA_SEARCH_RADIUS_FACTOR,
    Point,
    area_of_location,
    build_google_maps_search_url,
    build_search_query,
    distance_meters,
)
from app.integrations.places import get_places_provider
from app.modules.catalog.schemas import Area, City
from app.modules.catalog.service import classify_menu, get_catalog, require_supported_city
from app.modules.places import repository
from app.modules.places.schemas import (
    AnywhereScope,
    AreaScope,
    CityScope,
    PlaceDetail,
    Placement,
    PlaceSearchResponse,
    PlaceSearchResult,
    PlaceSummary,
    SavedPlace,
    SavePlaceInput,
)

logger = logging.getLogger(__name__)

# 한 번에 받을 수 있는 식당 수 (frontend placeQueries의 PLACES_BATCH_LIMIT와 같다)
PLACES_BATCH_LIMIT = 50
# 도시 중심에서 이 거리 안의 식당만 그 도시 식당으로 본다 (다자이후처럼 시 경계 밖 근교 포함)
CITY_RADIUS_METERS = 50_000
# 식당 상세 캐시 (Places 약관: 저장하지 않고 짧게만 둔다. 프론트도 10분 캐시)
PLACE_CACHE_SECONDS = 600

_SAVED_NOT_FOUND = "저장한 식당을 찾을 수 없어요."
_PLACE_NOT_FOUND = "식당 정보를 찾을 수 없어요."

_cache: dict[str, tuple[float, PlaceDetail | None]] = {}
_cache_lock = Lock()
_search_limiter: RateLimiter | None = None


def _limiter() -> RateLimiter:
    global _search_limiter
    if _search_limiter is None:
        _search_limiter = RateLimiter(get_settings().search_limit_per_hour)
    return _search_limiter


def get_place(place_id: str) -> PlaceDetail | None:
    """식당 상세 (없으면 None). 같은 식당은 10분 동안 다시 부르지 않는다."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(place_id)
        if hit and now - hit[0] < PLACE_CACHE_SECONDS:
            return hit[1]
    try:
        place = get_places_provider().get(place_id)
    except Exception:  # 제공자 오류는 "정보 없음"으로 (화면은 지도 링크로 대신한다)
        logger.exception("식당 상세 조회 실패")
        return None
    with _cache_lock:
        _cache[place_id] = (now, place)
    return place


def get_place_summary(place_id: str | None) -> PlaceSummary | None:
    place = get_place(place_id) if place_id else None
    return place.summary() if place else None


def _in_city(city: City, place: PlaceSummary) -> bool:
    center = Point(city.center.lat, city.center.lng)
    return (
        distance_meters(center, Point(place.location.lat, place.location.lng)) <= CITY_RADIUS_METERS
    )


# ---------- 상세 ----------


def get_place_detail(place_id: str) -> PlaceDetail:
    place = get_place(place_id)
    if place is None:
        raise AppError(404, ErrorCode.NOT_FOUND, _PLACE_NOT_FOUND)
    return place


def get_places(ids_param: str) -> list[PlaceDetail]:
    """여러 식당을 한 번에 (?ids=a,b,c). 중복은 한 번만, 없는 식당은 빼고 돌려준다."""
    ids = list(dict.fromkeys(i.strip() for i in ids_param.split(",") if i.strip()))
    if not 1 <= len(ids) <= PLACES_BATCH_LIMIT:
        raise AppError(
            400, ErrorCode.VALIDATION_ERROR, f"식당 id를 1~{PLACES_BATCH_LIMIT}개 보내 주세요."
        )
    return [p for p in (get_place(i) for i in ids) if p is not None]


# ---------- 검색 ----------


def _search(city: City, query: str, area: Area | None) -> list[PlaceSearchResult]:
    """도시 안에서 검색어에 맞는 식당. area가 있으면 동네 반경 × 1.5 안만, 가까운 순(같으면 평점 순)."""
    center = area.center if area else city.center
    ignore = (city.name, *(a.name for a in city.areas))
    try:
        found = get_places_provider().text_search(
            query, center=(center.lat, center.lng), ignore=ignore
        )
    except Exception:  # 실패해도 빈 결과 + 지도 링크로 흐름을 잇는다 (F-09 5)
        logger.exception("식당 검색 실패")
        return []

    results: list[tuple[int | None, PlaceDetail]] = []
    for place in found:
        if not _in_city(city, place):
            continue
        distance = None
        if area:
            distance = distance_meters(
                Point(area.center.lat, area.center.lng),
                Point(place.location.lat, place.location.lng),
            )
            if distance > area.radius_meters * AREA_SEARCH_RADIUS_FACTOR:
                continue
        results.append((distance, place))
    results.sort(key=lambda r: (r[0] or 0, -(r[1].rating or 0)))
    return [PlaceSearchResult(**p.summary().model_dump(), distance_meters=d) for d, p in results]


def search_for_slot(user: CurrentUser, slot_id: str, q: str | None) -> PlaceSearchResponse:
    """끼니 동네 범위 검색 (F-09 1). 검색어가 없으면 "메뉴 + 끼니 동네 + 도시".

    끼니에 동네가 없으면 도시 전체로 찾고 scope로 알린다 (F-03 3).
    """
    from app.modules.trips.service import slot_search_context  # trips ↔ places 순환 import 방지

    _limiter().hit(f"search:{user.id}")
    menu, area_id, city_id = slot_search_context(user, slot_id)
    city = require_supported_city(city_id)
    area = get_catalog().area(area_id) if area_id else None
    query = (q or "").strip() or build_search_query(menu, area.name if area else None, city.name)
    return PlaceSearchResponse(
        scope=AreaScope(area_id=area.id, area_name=area.name) if area else CityScope(),
        query=query,
        results=_search(city, query, area),
        fallback_maps_url=build_google_maps_search_url(query),
    )


def search_city(user: CurrentUser, city_id: str, q: str | None) -> PlaceSearchResponse:
    """도시 범위 검색 (맛집 모음 F-15 1)"""
    city = require_supported_city(city_id)
    _limiter().hit(f"search:{user.id}")
    keyword = (q or "").strip()
    full_query = build_search_query(keyword, None, city.name)
    return PlaceSearchResponse(
        scope=CityScope(),
        query=full_query,
        results=[
            r.model_copy(update={"distance_meters": None}) for r in _search(city, keyword, None)
        ],
        fallback_maps_url=build_google_maps_search_url(full_query),
    )


# 다른 지역 검색의 검색어 길이 (메뉴 40자 + 지역 이름)
ANYWHERE_QUERY_MAX = 80


def search_anywhere(user: CurrentUser, q: str, city_id: str | None) -> PlaceSearchResponse:
    """다른 지역 검색: 여행 도시 밖 식당도 끼니에 넣을 수 있게 도시 제한 없이 찾는다.

    여행은 도시 하나로 두고(타이베이 여행에 타이중 식당 하나 넣기 같은 경우), 검색어에 지역을 직접 적는다
    ("타이중 우육면"). city_id가 지원 도시면 결과를 그 도시 쪽으로만 기울인다. 거리는 없고 순서는 제공자 순서다.
    """
    query = q.strip()
    if not 1 <= len(query) <= ANYWHERE_QUERY_MAX:
        raise AppError(
            400, ErrorCode.VALIDATION_ERROR, f"검색어를 1~{ANYWHERE_QUERY_MAX}자로 적어 주세요."
        )
    _limiter().hit(f"search:{user.id}")
    city = get_catalog().city(city_id) if city_id else None
    center = (city.center.lat, city.center.lng) if city else None
    results: list[PlaceSearchResult] = []
    try:
        found = get_places_provider().text_search(query, center=center, ignore=())
        results = [
            PlaceSearchResult(**p.summary().model_dump(), distance_meters=None) for p in found
        ]
    except Exception:  # 실패해도 빈 결과 + 지도 링크로 흐름을 잇는다 (F-09 5)
        logger.exception("다른 지역 식당 검색 실패")
    return PlaceSearchResponse(
        scope=AnywhereScope(),
        query=query,
        results=results,
        fallback_maps_url=build_google_maps_search_url(query),
    )


# ---------- 맛집 모음 ----------


def _saved_place(row: dict[str, Any], placements: list[Placement]) -> SavedPlace:
    return SavedPlace(
        id=str(row["id"]),
        city_id=row["city_id"],
        place_id=row["place_id"],
        menu=row["menu"],
        kind_id=row["kind_id"],
        area_id=row["area_id"],
        source=row["source"],
        saved_at=row["saved_at"],
        place=get_place_summary(row["place_id"]),
        placements=placements,
    )


def _placements(conn: Conn, place_ids: list[str]) -> dict[str, list[Placement]]:
    from app.modules.trips.service import placements_for_places

    return placements_for_places(conn, place_ids)


def list_collection(user: CurrentUser, city_id: str | None) -> list[SavedPlace]:
    with user_tx(user) as conn:
        rows = repository.list_saved_places(conn, city_id or None)
        placements = _placements(conn, [r["place_id"] for r in rows])
    return [_saved_place(r, placements.get(r["place_id"], [])) for r in rows]


def save_place(user: CurrentUser, body: SavePlaceInput) -> tuple[SavedPlace, bool]:
    """저장 (같은 식당이면 메뉴만 바꾼다). 동네는 식당 좌표로 정한다. 반환: (저장한 식당, 새로 저장했는지)"""
    catalog = get_catalog()
    city = catalog.city(body.city_id)
    place = get_place(body.place_id)
    if city is None or place is None or not _in_city(city, place):
        raise AppError(404, ErrorCode.NOT_FOUND, _PLACE_NOT_FOUND)
    if body.kind_id is not None and not catalog.has_menu_kind(body.kind_id):
        raise AppError(400, ErrorCode.VALIDATION_ERROR, "알 수 없는 메뉴 종류예요.")

    values = {
        "city_id": city.id,
        "place_id": place.place_id,
        "menu": body.menu,
        "kind_id": body.kind_id or classify_menu(body.menu).kind_id,
        "area_id": area_of_location(
            catalog.area_circles(city.id), Point(place.location.lat, place.location.lng)
        ),
    }
    with user_tx(user) as conn:
        row, created = repository.upsert_saved_place(conn, values)
        placements = _placements(conn, [row["place_id"]])
    return _saved_place(row, placements.get(row["place_id"], [])), created


def delete_saved_place(user: CurrentUser, saved_place_id: str) -> None:
    sid = parse_uuid(saved_place_id, _SAVED_NOT_FOUND)
    with user_tx(user) as conn:
        if not repository.delete_saved_place(conn, sid):
            raise AppError(404, ErrorCode.NOT_FOUND, _SAVED_NOT_FOUND)


def saved_places_by_id(conn: Conn, ids: list[Any]) -> dict[str, dict[str, Any]]:
    """내 맛집 모음 행 (꼭 먹을 목록 표시·검증용, trips 서비스가 같은 트랜잭션에서 부른다)"""
    return {str(r["id"]): r for r in repository.get_saved_places(conn, ids)}
