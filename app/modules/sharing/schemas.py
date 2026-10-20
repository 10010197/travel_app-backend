"""공유 링크와 일행 의견 (frontend/src/api/schemas/share.ts)."""

import datetime as dt
from typing import Self

from pydantic import model_validator

from app.core.schemas import ApiModel, Body100, Id, Instant, Name12, SlotState, TimeBand


class ShareLink(ApiModel):
    token: str
    url: str


class ShareComment(ApiModel):
    id: str
    slot_id: str
    author_name: str
    body: str
    like: bool
    created_at: Instant


class CommentInput(ApiModel):
    slot_id: Id
    author_name: Name12
    body: Body100
    like: bool

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.like and not self.body:
            raise ValueError("의견이나 좋아요 중 하나는 있어야 합니다")
        return self


class SharedSlot(ApiModel):
    id: str
    name: str
    time_band: TimeBand
    state: SlotState
    menu: str | None
    place_name: str | None
    area_name: str | None


class SharedDay(ApiModel):
    date: dt.date
    day_number: int
    area_name: str | None
    slots: list[SharedSlot]


class SharedTrip(ApiModel):
    title: str
    city_name: str
    time_zone: str
    start_date: dt.date | None
    end_date: dt.date | None
    owner_name: str | None
    companion_names: list[str]
    days: list[SharedDay]
    comments: list[ShareComment]
