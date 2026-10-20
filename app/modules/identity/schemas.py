"""내 정보·마이 설정·자주 함께 가는 일행 (frontend/src/api/schemas/user.ts)."""

from typing import Annotated, Literal

from pydantic import Field

from app.core.schemas import ApiModel, FoodsRaw60, Name12, Strictness


class User(ApiModel):
    id: str
    is_anonymous: bool
    display_name: str | None
    email: str | None


class UserSettings(ApiModel):
    default_meals: Annotated[list[Name12], Field(min_length=1)]
    time_display: Literal["auto"]
    notify_empty_slots: bool


class SavedCompanion(ApiModel):
    id: str
    name: str
    foods_raw: str
    food_tags: list[str]
    strictness: Strictness


class SavedCompanionInput(ApiModel):
    name: Name12
    foods_raw: FoodsRaw60
    strictness: Strictness


class SavedCompanionPatch(ApiModel):
    name: Name12 | None = None
    foods_raw: FoodsRaw60 | None = None
    strictness: Strictness | None = None
