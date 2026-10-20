"""마스터 데이터 (catalog 경계). 다른 모듈은 도시·동네·필수 메뉴·메뉴 종류를 이 서비스로 받는다.

마스터 데이터는 시드로만 바뀌므로 프로세스마다 처음 한 번 읽어 메모리에 둔다.
시드를 다시 넣었으면 서버를 다시 시작한다(테스트는 get_catalog.cache_clear()).
"""

from dataclasses import dataclass, field
from functools import lru_cache

from app.core.errors import AppError, ErrorCode
from app.db.session import public_tx
from app.domain.geo import AreaCircle, Point
from app.integrations.ai import get_food_normalizer, get_menu_classifier
from app.integrations.ai.ports import FoodVocabulary, KnownMenu, NormalizedFoods
from app.modules.catalog import repository
from app.modules.catalog.schemas import (
    Area,
    City,
    CitySummary,
    ClassifyMenuResult,
    MenuKind,
    MustMenu,
)


@dataclass(frozen=True, slots=True)
class FoodTag:
    id: str
    label: str
    parent_id: str | None


@dataclass(frozen=True, slots=True)
class FoodTagPreset:
    label: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    menu_kinds: list[MenuKind]
    food_tags: list[FoodTag]
    presets: list[FoodTagPreset]
    cities: list[City]
    _areas: dict[str, tuple[Area, str]] = field(default_factory=dict)
    _must_menus: dict[str, tuple[MustMenu, str]] = field(default_factory=dict)

    def city(self, city_id: str) -> City | None:
        return next((c for c in self.cities if c.id == city_id), None)

    def area(self, area_id: str) -> Area | None:
        found = self._areas.get(area_id)
        return found[0] if found else None

    def area_in_city(self, area_id: str, city_id: str) -> bool:
        found = self._areas.get(area_id)
        return found is not None and found[1] == city_id

    def must_menu(self, must_menu_id: str) -> MustMenu | None:
        found = self._must_menus.get(must_menu_id)
        return found[0] if found else None

    def must_menu_in_city(self, must_menu_id: str, city_id: str) -> bool:
        found = self._must_menus.get(must_menu_id)
        return found is not None and found[1] == city_id

    def has_menu_kind(self, kind_id: str) -> bool:
        return any(k.id == kind_id for k in self.menu_kinds)

    @property
    def no_repeat_kinds(self) -> set[str]:
        """하루에 두 번 나오면 중복 경고인 종류 (R-01)"""
        return {k.id for k in self.menu_kinds if not k.allow_daily_repeat}

    def area_circles(self, city_id: str) -> list[AreaCircle]:
        city = self.city(city_id)
        return [
            AreaCircle(a.id, Point(a.center.lat, a.center.lng), a.radius_meters)
            for a in (city.areas if city else [])
        ]


@lru_cache
def get_catalog() -> Catalog:
    with public_tx() as conn:
        rows = repository.load_all(conn)

    areas_by_city: dict[str, list[Area]] = {}
    for r in rows["areas"]:
        areas_by_city.setdefault(r["city_id"], []).append(
            Area(
                id=r["id"],
                name=r["name"],
                center={"lat": r["center_lat"], "lng": r["center_lng"]},
                radius_meters=r["radius_meters"],
            )
        )
    menus_by_city: dict[str, list[MustMenu]] = {}
    for r in rows["must_menus"]:
        menus_by_city.setdefault(r["city_id"], []).append(
            MustMenu(
                id=r["id"],
                name=r["name"],
                kind_id=r["kind_id"],
                description=r["description"],
                food_tags=list(r["food_tags"]),
                is_signature=r["is_signature"],
            )
        )
    cities = [
        City(
            id=r["id"],
            name=r["name"],
            country_code=r["country_code"],
            time_zone=r["time_zone"],
            center={"lat": r["center_lat"], "lng": r["center_lng"]},
            areas=areas_by_city.get(r["id"], []),
            must_menus=menus_by_city.get(r["id"], []),
        )
        for r in rows["cities"]
    ]
    return Catalog(
        menu_kinds=[
            MenuKind(id=r["id"], label=r["label"], allow_daily_repeat=r["allow_daily_repeat"])
            for r in rows["menu_kinds"]
        ],
        food_tags=[FoodTag(r["id"], r["label"], r["parent_id"]) for r in rows["food_tags"]],
        presets=[FoodTagPreset(r["label"], tuple(r["tags"])) for r in rows["food_tag_presets"]],
        cities=cities,
        _areas={a.id: (a, c.id) for c in cities for a in c.areas},
        _must_menus={m.id: (m, c.id) for c in cities for m in c.must_menus},
    )


# ---------- API ----------


def list_cities() -> list[CitySummary]:
    return [
        CitySummary(id=c.id, name=c.name, country_code=c.country_code, time_zone=c.time_zone)
        for c in get_catalog().cities
    ]


def get_city(city_id: str) -> City:
    city = get_catalog().city(city_id)
    if city is None:
        raise AppError(404, ErrorCode.CITY_NOT_SUPPORTED, "아직 준비 중인 도시예요.")
    return city


def require_supported_city(city_id: str) -> City:
    """여행·맛집 모음을 만들 때의 도시 검사. 상세 조회(404)와 달리 400이다."""
    city = get_catalog().city(city_id)
    if city is None:
        raise AppError(400, ErrorCode.CITY_NOT_SUPPORTED, "아직 준비 중인 도시예요.")
    return city


def list_menu_kinds() -> list[MenuKind]:
    return get_catalog().menu_kinds


def classify_menu(menu: str) -> ClassifyMenuResult:
    """메뉴 → 종류·음식 태그 (F-04 1). 종류는 허용 목록 안의 값이거나 None.

    모든 지원 도시의 필수 메뉴 중 이름이 같은 것이 있으면 그 종류·태그를 그대로 쓴다.
    """
    catalog = get_catalog()
    known = [
        KnownMenu(m.name, m.kind_id, tuple(m.food_tags))
        for c in catalog.cities
        for m in c.must_menus
    ]
    result = get_menu_classifier().classify(menu, known)
    kind_id = result.kind_id if result.kind_id and catalog.has_menu_kind(result.kind_id) else None
    return ClassifyMenuResult(
        kind_id=kind_id,
        confidence=result.confidence if kind_id else "low",
        menu_tags=list(result.menu_tags),
    )


def normalize_foods(raw: str) -> NormalizedFoods:
    """못 먹는 음식 원문 → 정규화 태그 (F-02 4). 일행 추가·수정과 자주 함께 가는 일행 저장이 쓴다."""
    catalog = get_catalog()
    vocabulary = FoodVocabulary(
        tags=tuple((t.id, t.label) for t in catalog.food_tags),
        presets=tuple((p.label, p.tags) for p in catalog.presets),
    )
    result = get_food_normalizer().normalize(raw, vocabulary)
    known = {t.id for t in catalog.food_tags}
    return NormalizedFoods(tuple(t for t in result.food_tags if t in known), result.tag_status)
