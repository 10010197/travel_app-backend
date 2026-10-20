"""여행·일차·끼니·일행·꼭 먹을 것 (frontend/src/api/schemas/trip.ts)."""

import datetime as dt
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from app.core.schemas import (
    ApiModel,
    FoodsRaw60,
    Id,
    Instant,
    KindSource,
    MealDef,
    Menu40,
    MenuOrEmpty40,
    Name12,
    SkipReason20,
    SlotState,
    Strictness,
    TagStatus,
    TimeBand,
    Title30,
    TitleOrEmpty30,
)
from app.integrations.places.models import PlaceSummary

# ---------- 응답 ----------


class Slot(ApiModel):
    id: str
    day_id: str
    date: dt.date
    name: str
    time_band: TimeBand
    order: int
    state: SlotState
    skip_reason: str | None
    menu: str | None
    kind_id: str | None
    kind_source: KindSource | None
    menu_tags: list[str]
    area_id: str | None
    area_overridden: bool
    place_id: str | None
    must_pick_id: str | None


class Day(ApiModel):
    id: str
    date: dt.date
    day_number: int
    area_id: str | None
    slots: list[Slot]


class Companion(ApiModel):
    id: str
    name: str
    foods_raw: str
    food_tags: list[str]
    tag_status: TagStatus
    strictness: Strictness
    source_saved_id: str | None


class DuplicateAck(ApiModel):
    day_id: Id
    kind_id: Id
    slot_ids: Annotated[list[Id], Field(min_length=2)]


class DietCheck(ApiModel):
    slot_id: str
    companion_id: str
    checked: bool


class CustomMenu(ApiModel):
    name: str
    kind_id: str | None


class MustPickDisplay(ApiModel):
    name: str
    description: str
    kind_id: str | None
    food_tags: list[str]
    area_id: str | None
    place: PlaceSummary | None


class MustPick(ApiModel):
    id: str
    type: Literal["menu", "place"]
    order: int
    checked: bool
    must_menu_id: str | None
    custom_menu: CustomMenu | None
    saved_place_id: str | None
    display: MustPickDisplay
    placed_slot_id: str | None


class Trip(ApiModel):
    id: str
    city_id: str
    title: str
    start_date: dt.date | None
    end_date: dt.date | None
    default_meals: list[MealDef]
    share_token: str | None
    created_at: Instant
    updated_at: Instant
    days: list[Day]
    companions: list[Companion]
    duplicate_acks: list[DuplicateAck]
    diet_checks: list[DietCheck]
    must_picks: list[MustPick]


class SlotCounts(ApiModel):
    active: int
    filled: int
    onsite: int
    empty: int


class TripSummary(ApiModel):
    id: str
    city_id: str
    city_name: str
    time_zone: str
    title: str
    start_date: dt.date | None
    end_date: dt.date | None
    companion_count: int
    slot_counts: SlotCounts
    updated_at: Instant


# ---------- 요청 ----------


class _NoExplicitNull(ApiModel):
    """보낸 필드만 바꾸는 PATCH 본문에서 null을 보낼 수 없는 필드 (zod .optional(), .nullable() 아님)"""

    NON_NULLABLE: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _reject_null(self) -> Self:
        for name in self.model_fields_set & set(type(self).NON_NULLABLE):
            if getattr(self, name) is None:
                raise ValueError(f"{name}에는 null을 보낼 수 없어요")
        return self


class CompanionInput(ApiModel):
    name: Name12
    foods_raw: FoodsRaw60
    strictness: Strictness
    source_saved_id: Id | None = None


class CompanionPatch(_NoExplicitNull):
    NON_NULLABLE = ("name", "foods_raw", "strictness")

    name: Name12 | None = None
    foods_raw: FoodsRaw60 | None = None
    strictness: Strictness | None = None
    source_saved_id: Id | None = None


class CreateTripInput(ApiModel):
    city_id: Id
    title: TitleOrEmpty30 | None = None
    start_date: dt.date | None
    end_date: dt.date | None
    default_meals: Annotated[list[MealDef], Field(min_length=1)] | None = None
    companions: Annotated[list[CompanionInput], Field(max_length=20)] | None = None

    @model_validator(mode="after")
    def _dates_pair(self) -> Self:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("시작일과 종료일은 함께 정해야 합니다")
        return self


class UpdateTripInput(_NoExplicitNull):
    NON_NULLABLE = ("title", "start_date", "end_date", "default_meals")

    title: Title30 | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    default_meals: Annotated[list[MealDef], Field(min_length=1)] | None = None


class UpdateDayInput(ApiModel):
    area_id: Id | None


class UpdateSlotInput(_NoExplicitNull):
    NON_NULLABLE = ("state", "menu_tags")

    state: SlotState | None = None
    skip_reason: SkipReason20 | None = None
    menu: MenuOrEmpty40 | None = None
    kind_id: Id | None = None
    kind_source: KindSource | None = None
    menu_tags: list[str] | None = None
    area_id: Id | None = None
    place_id: Id | None = None
    must_pick_id: Id | None = None


class UpdateSlotsStateInput(ApiModel):
    slot_ids: Annotated[list[Id], Field(min_length=1, max_length=200)]
    state: Literal["empty", "onsite"]


class DietCheckInput(ApiModel):
    checked: bool


class CustomMenuInput(ApiModel):
    name: Menu40
    kind_id: Id | None


class MustPickInput(ApiModel):
    id: Id | None = None
    type: Literal["menu", "place"]
    checked: bool
    must_menu_id: Id | None = None
    custom_menu: CustomMenuInput | None = None
    saved_place_id: Id | None = None


class PutMustPicksInput(ApiModel):
    items: list[MustPickInput]
