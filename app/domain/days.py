"""여행 기간과 일차 규칙 (FEATURE_SPEC F-01, Q-01). 프론트 src/domain/days.ts·localDate.ts와 같다.

여행 만들기·수정 서비스가 기간 검증, 제목("2박 3일"), 일차 날짜 목록, 기간 변경 시 더할·지울 날짜 계산에 쓴다.
날짜는 여행지 현지 날짜(date)만 다룬다. 시각·기기 시간대와 섞지 않는다.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

MAX_TRIP_DAYS = 14

RangeError = Literal["end_before_start", "start_before_today", "too_long"]


def local_date_in(instant: datetime, time_zone: str) -> date:
    """그 시간대의 오늘 날짜 (여행지 현지 기준 "오늘")"""
    return instant.astimezone(ZoneInfo(time_zone)).date()


def days_between(a: date, b: date) -> int:
    """b − a 일수. a가 b보다 늦으면 음수."""
    return (b - a).days


def enumerate_dates(start: date, end: date) -> list[date]:
    """시작일부터 종료일까지(양 끝 포함). 종료일이 앞서면 빈 목록."""
    return [start + timedelta(days=i) for i in range(max(0, days_between(start, end) + 1))]


def validate_trip_range(
    start: date, end: date, today: date, max_days: int = MAX_TRIP_DAYS
) -> RangeError | None:
    """기간이 고를 수 있는 값인지 (F-01). today는 여행지 현지 오늘. 문제가 없으면 None."""
    if days_between(today, start) < 0:
        return "start_before_today"
    if days_between(start, end) < 0:
        return "end_before_start"
    if days_between(start, end) + 1 > max_days:
        return "too_long"
    return None


def describe_range_label(start: date, end: date) -> str:
    """기간 이름 "2박 3일", 하루면 "당일치기" (여행 기본 제목에 쓴다)"""
    days = days_between(start, end) + 1
    nights = days - 1
    return "당일치기" if nights == 0 else f"{nights}박 {days}일"


@dataclass(frozen=True, slots=True)
class DateDiff:
    keep: list[date]
    add: list[date]
    remove: list[date]


def diff_trip_dates(existing: list[date], new_start: date, new_end: date) -> DateDiff:
    """기간을 바꿨을 때 남길·새로 만들·지울 날짜 (Q-01). 지울 날짜의 끼니는 메뉴·식당과 함께 사라진다."""
    nxt = enumerate_dates(new_start, new_end)
    current = set(existing)
    next_set = set(nxt)
    return DateDiff(
        keep=[d for d in nxt if d in current],
        add=[d for d in nxt if d not in current],
        remove=sorted(d for d in existing if d not in next_set),
    )
