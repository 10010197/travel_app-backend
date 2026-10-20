"""모든 모듈이 같이 쓰는 요청·응답 모델 도구 (API 계약: frontend/src/api/schemas).

- JSON 필드는 camelCase. 파이썬 쪽은 snake_case로 쓰고 alias로 바꾼다
- 문자열 입력은 zod의 .trim()처럼 앞뒤 공백을 지운 뒤 길이를 검사한다
- 응답은 계약대로 모든 필드를 항상 넣는다(nullable은 null로)
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel

from app.core.errors import AppError, ErrorCode


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _trimmed(min_length: int, max_length: int) -> StringConstraints:
    """앞뒤 공백을 지운 뒤 길이를 검사한다 (zod z.string().trim().min().max())"""
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


Id = Annotated[str, StringConstraints(min_length=1)]
Name12 = Annotated[str, _trimmed(1, 12)]
"""일행·끼니 이름, 의견 작성자 (1~12자)"""
FoodsRaw60 = Annotated[str, _trimmed(0, 60)]
Menu40 = Annotated[str, _trimmed(1, 40)]
MenuOrEmpty40 = Annotated[str, _trimmed(0, 40)]
Title30 = Annotated[str, _trimmed(1, 30)]
TitleOrEmpty30 = Annotated[str, _trimmed(0, 30)]
Body100 = Annotated[str, _trimmed(0, 100)]
SkipReason20 = Annotated[str, StringConstraints(max_length=20)]

Instant = Annotated[datetime, AfterValidator(lambda v: v.astimezone(UTC))]
"""시각은 ISO 8601 UTC ("…Z")로 내보낸다. DB 연결의 시간대와 상관없이 UTC로 바꾼다"""

TimeBand = Literal["morning", "late_morning", "lunch", "afternoon", "dinner", "night", "late_night"]
SlotState = Literal["filled", "empty", "onsite", "skipped"]
Strictness = Literal["avoid", "flex"]
KindSource = Literal["ai", "user"]
TagStatus = Literal["ok", "needs_check"]


class LatLng(ApiModel):
    lat: float
    lng: float


class MealDef(ApiModel):
    name: Name12
    time_band: TimeBand


def parse_uuid(value: str, not_found_message: str) -> uuid.UUID:
    """경로의 id를 UUID로. 형식이 틀리면 없는 것과 같으므로 404 (다른 사용자 것과 구분하지 않는다)."""
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppError(404, ErrorCode.NOT_FOUND, not_found_message) from exc


def parse_uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None
