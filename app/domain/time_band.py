"""끼니 시간대 규칙 (FEATURE_SPEC R-06). 프론트 src/domain/timeBand.ts와 같다.

시간대는 끼니 순서를 정하기 위한 것이며 예약 시간이 아니다.
"""

from app.core.schemas import TimeBand

TIME_BANDS: tuple[TimeBand, ...] = (
    "morning",
    "late_morning",
    "lunch",
    "afternoon",
    "dinner",
    "night",
    "late_night",
)

# 기본 끼니와 빠른 선택 끼니의 시간대 (R-06 표)
DEFAULT_MEAL_BANDS: dict[str, TimeBand] = {
    "아침": "morning",
    "브런치": "late_morning",
    "해장": "late_morning",
    "점심": "lunch",
    "간식": "afternoon",
    "저녁": "dinner",
    "2차": "night",
    "야식": "late_night",
}

# 직접 추가한 끼니의 시간대 기본값 (R-06: "밤")
CUSTOM_MEAL_DEFAULT_BAND: TimeBand = "night"


def band_for_meal_name(name: str) -> TimeBand:
    """끼니 이름에 맞는 시간대. 모르는 이름이면 "밤"."""
    return DEFAULT_MEAL_BANDS.get(name, CUSTOM_MEAL_DEFAULT_BAND)


def band_order(band: str) -> int:
    return TIME_BANDS.index(band)
