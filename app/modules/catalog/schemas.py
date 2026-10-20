"""마스터 데이터 응답·요청 모델 (frontend/src/api/schemas/city.ts)."""

from app.core.schemas import ApiModel, Id, LatLng, Menu40


class Area(ApiModel):
    id: str
    name: str
    center: LatLng
    radius_meters: int


class MustMenu(ApiModel):
    id: str
    name: str
    kind_id: str
    description: str
    food_tags: list[str]
    is_signature: bool


class CitySummary(ApiModel):
    id: str
    name: str
    country_code: str
    time_zone: str


class City(CitySummary):
    center: LatLng
    areas: list[Area]
    must_menus: list[MustMenu]


class MenuKind(ApiModel):
    id: str
    label: str
    allow_daily_repeat: bool


class ClassifyMenuInput(ApiModel):
    menu: Menu40
    # 예약 필드. 지금은 쓰지 않는다 (모든 지원 도시의 필수 메뉴에서 이름이 같은 것을 찾는다)
    city_id: Id | None = None


class ClassifyMenuResult(ApiModel):
    kind_id: str | None
    confidence: str
    menu_tags: list[str]
