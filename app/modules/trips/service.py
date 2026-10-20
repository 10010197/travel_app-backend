"""여행 계획 (trips 경계, F-01~F-08, F-14, F-17). 규칙은 프론트 목(src/mocks/services/tripService.ts,
handlers/trips.ts·slots.ts)과 같다.

- 요청 하나 = 트랜잭션 하나. 중간에 실패하면 아무것도 바뀌지 않는다(여행 만들기, 기간 변경, 일괄 상태 변경)
- 남의 여행·끼니는 RLS 때문에 보이지 않으므로 404 NOT_FOUND (존재를 드러내지 않는다)
- 끼니가 바뀔 때마다 중복이 풀린 "괜찮아요" 기록을 지운다 (F-05 5, cleanupStaleAcks)
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from app.core.errors import AppError, ErrorCode
from app.core.schemas import MealDef, parse_uuid, parse_uuid_or_none
from app.core.security import CurrentUser
from app.db.session import Conn, user_tx
from app.domain.days import (
    RangeError,
    describe_range_label,
    diff_trip_dates,
    enumerate_dates,
    local_date_in,
    validate_trip_range,
)
from app.domain.duplicate import DupAck, DupSlot, stale_acks
from app.domain.time_band import band_for_meal_name, band_order
from app.modules.catalog.schemas import City
from app.modules.catalog.service import (
    classify_menu,
    get_catalog,
    normalize_foods,
    require_supported_city,
)
from app.modules.identity.service import default_meal_names, owns_saved_companion
from app.modules.places.schemas import Placement
from app.modules.places.service import get_place_summary, saved_places_by_id
from app.modules.trips import repository
from app.modules.trips.schemas import (
    Companion,
    CompanionInput,
    CompanionPatch,
    CreateTripInput,
    CustomMenu,
    Day,
    DietCheck,
    DuplicateAck,
    MustPick,
    MustPickDisplay,
    PutMustPicksInput,
    Slot,
    SlotCounts,
    Trip,
    TripSummary,
    UpdateDayInput,
    UpdateSlotInput,
    UpdateSlotsStateInput,
    UpdateTripInput,
)

Row = dict[str, Any]

_TRIP_NOT_FOUND = "여행을 찾을 수 없어요."
_DAY_NOT_FOUND = "날짜를 찾을 수 없어요."
_SLOT_NOT_FOUND = "끼니를 찾을 수 없어요."
_COMPANION_NOT_FOUND = "일행을 찾을 수 없어요."

_RANGE_MESSAGES: dict[RangeError, str] = {
    "start_before_today": "오늘 이전 날짜는 고를 수 없어요.",
    "end_before_start": "종료일은 시작일 이후여야 해요.",
    "too_long": "여행은 최대 14일까지 만들 수 있어요.",
}


def _bad_request(message: str) -> AppError:
    return AppError(400, ErrorCode.VALIDATION_ERROR, message)


def _not_found(message: str) -> AppError:
    return AppError(404, ErrorCode.NOT_FOUND, message)


def _with_topic(word: str) -> str:
    """ "모츠나베는", "하카타 라멘은" (받침에 따라 은/는)"""
    last = word[-1:] if word else ""
    if "가" <= last <= "힣":
        return word + ("은" if (ord(last) - 0xAC00) % 28 else "는")
    return word + "은(는)"


# ---------- 응답 만들기 ----------


def _slot_dto(row: Row, day_date: date) -> Slot:
    return Slot(
        id=str(row["id"]),
        day_id=str(row["day_id"]),
        date=day_date,
        name=row["name"],
        time_band=row["time_band"],
        order=row["sort_order"],
        state=row["state"],
        skip_reason=row["skip_reason"],
        menu=row["menu"],
        kind_id=row["kind_id"],
        kind_source=row["kind_source"],
        menu_tags=list(row["menu_tags"]),
        area_id=row["area_id"],
        area_overridden=row["area_overridden"],
        place_id=row["place_id"],
        must_pick_id=str(row["must_pick_id"]) if row["must_pick_id"] else None,
    )


def _sorted_slots(slots: list[Slot]) -> list[Slot]:
    """시간대 순, 같은 시간대 안에서는 추가한 순 (R-06)"""
    return sorted(slots, key=lambda s: (s.date, band_order(s.time_band), s.order))


def _companion_dto(row: Row) -> Companion:
    return Companion(
        id=str(row["id"]),
        name=row["name"],
        foods_raw=row["foods_raw"],
        food_tags=list(row["food_tags"]),
        tag_status=row["tag_status"],
        strictness=row["strictness"],
        source_saved_id=str(row["source_saved_id"]) if row["source_saved_id"] else None,
    )


def _must_pick_dtos(conn: Conn, picks: list[Row], slots: list[Row]) -> list[MustPick]:
    """꼭 먹을 목록. display(이름·설명·식당 요약)와 placedSlotId는 저장하지 않고 여기서 만든다."""
    catalog = get_catalog()
    placed_by = {
        str(s["must_pick_id"]): str(s["id"])
        for s in slots
        if s["must_pick_id"] and s["state"] != "skipped"
    }
    saved = saved_places_by_id(conn, [p["saved_place_id"] for p in picks if p["saved_place_id"]])

    result: list[MustPick] = []
    for pick in picks:
        menu = catalog.must_menu(pick["must_menu_id"]) if pick["must_menu_id"] else None
        saved_row = saved.get(str(pick["saved_place_id"])) if pick["saved_place_id"] else None
        if pick["type"] == "place":
            place = get_place_summary(saved_row["place_id"]) if saved_row else None
            display = MustPickDisplay(
                name=place.name if place else "정보를 불러오지 못한 식당",
                description=saved_row["menu"] if saved_row else "",
                kind_id=saved_row["kind_id"] if saved_row else None,
                food_tags=[],
                area_id=saved_row["area_id"] if saved_row else None,
                place=place,
            )
        elif menu:
            display = MustPickDisplay(
                name=menu.name,
                description=menu.description,
                kind_id=menu.kind_id,
                food_tags=menu.food_tags,
                area_id=None,
                place=None,
            )
        else:
            display = MustPickDisplay(
                name=pick["custom_menu_name"] or "",
                description="직접 추가",
                kind_id=pick["custom_menu_kind_id"],
                food_tags=[],
                area_id=None,
                place=None,
            )
        custom = (
            CustomMenu(name=pick["custom_menu_name"], kind_id=pick["custom_menu_kind_id"])
            if pick["custom_menu_name"]
            else None
        )
        result.append(
            MustPick(
                id=str(pick["id"]),
                type=pick["type"],
                order=pick["sort_order"],
                checked=pick["checked"],
                must_menu_id=pick["must_menu_id"],
                custom_menu=custom,
                saved_place_id=str(pick["saved_place_id"]) if pick["saved_place_id"] else None,
                display=display,
                placed_slot_id=placed_by.get(str(pick["id"])),
            )
        )
    return result


def _trip_dto(conn: Conn, trip: Row) -> Trip:
    children = repository.trip_children(conn, trip["id"])
    slots_by_day: dict[str, list[Slot]] = {}
    day_dates = {str(d["id"]): d["date"] for d in children["days"]}
    for s in children["slots"]:
        slots_by_day.setdefault(str(s["day_id"]), []).append(
            _slot_dto(s, day_dates[str(s["day_id"])])
        )
    return Trip(
        id=str(trip["id"]),
        city_id=trip["city_id"],
        title=trip["title"],
        start_date=trip["start_date"],
        end_date=trip["end_date"],
        default_meals=[MealDef.model_validate(m) for m in trip["default_meals"]],
        share_token=trip["share_token"],
        created_at=trip["created_at"],
        updated_at=trip["updated_at"],
        days=[
            Day(
                id=str(d["id"]),
                date=d["date"],
                day_number=d["day_number"],
                area_id=d["area_id"],
                slots=_sorted_slots(slots_by_day.get(str(d["id"]), [])),
            )
            for d in children["days"]
        ],
        companions=[_companion_dto(c) for c in children["companions"]],
        duplicate_acks=[
            DuplicateAck(
                day_id=str(a["day_id"]),
                kind_id=a["kind_id"],
                slot_ids=[str(i) for i in a["slot_ids"]],
            )
            for a in children["acks"]
        ],
        diet_checks=[
            DietCheck(
                slot_id=str(c["slot_id"]), companion_id=str(c["companion_id"]), checked=c["checked"]
            )
            for c in children["checks"]
        ],
        must_picks=_must_pick_dtos(conn, children["must_picks"], children["slots"]),
    )


# ---------- 공통 ----------


def _require_trip(conn: Conn, trip_id: str, *, for_update: bool = False) -> Row:
    trip = repository.get_trip(conn, parse_uuid(trip_id, _TRIP_NOT_FOUND), for_update=for_update)
    if trip is None:
        raise _not_found(_TRIP_NOT_FOUND)
    return trip


def _check_range(city: City, start: date, end: date) -> None:
    """기간 검증 (F-01). "오늘"은 여행지 현지 날짜"""
    today = local_date_in(datetime.now(UTC), city.time_zone)
    error = validate_trip_range(start, end, today)
    if error:
        raise _bad_request(_RANGE_MESSAGES[error])


def _add_days(conn: Conn, trip_id: uuid.UUID, dates: list[date], meals: list[MealDef]) -> None:
    """날짜마다 일차와 기본 끼니(빈 끼니)를 만들고 D1, D2 …를 날짜 순으로 다시 매긴다.

    번호 유일 제약은 트랜잭션 끝에서 검사하므로(deferrable) 임시 번호 1로 넣어도 된다.
    """
    for d in dates:
        day = repository.insert_day(conn, trip_id, d, 1)
        for meal in meals:
            repository.insert_slot(conn, trip_id, day, meal.name, meal.time_band)
    repository.renumber_days(conn, trip_id)


def _cleanup_acks(conn: Conn, trip_id: uuid.UUID) -> None:
    """허용 기록 정리 (F-05 5): 지워진 끼니를 목록에서 빼고(2개 미만이면 기록 삭제),
    같은 날·종류의 중복이 풀린 기록을 지운다."""
    slots = repository.list_slots(conn, trip_id)
    existing = {s["id"] for s in slots}
    acks: list[DupAck] = []
    for ack in repository.list_acks(conn, trip_id):
        ids = [i for i in ack["slot_ids"] if i in existing]
        if len(ids) < 2:
            repository.delete_ack(conn, ack["day_id"], ack["kind_id"])
            continue
        if len(ids) != len(ack["slot_ids"]):
            repository.upsert_ack(conn, trip_id, ack["day_id"], ack["kind_id"], ids)
        acks.append(DupAck(str(ack["day_id"]), ack["kind_id"], tuple(str(i) for i in ids)))

    dup_slots = [DupSlot(str(s["id"]), str(s["day_id"]), s["state"], s["kind_id"]) for s in slots]
    for stale in stale_acks(dup_slots, get_catalog().no_repeat_kinds, acks):
        repository.delete_ack(conn, uuid.UUID(stale.day_id), stale.kind_id)


def _companion_values(body: CompanionInput | CompanionPatch, conn: Conn) -> Row:
    values: Row = {}
    sent = body.model_fields_set
    for field in ("name", "strictness"):
        if field in sent:
            values[field] = getattr(body, field)
    if "foods_raw" in sent and body.foods_raw is not None:
        normalized = normalize_foods(body.foods_raw)
        values.update(
            foods_raw=body.foods_raw,
            food_tags=list(normalized.food_tags),
            tag_status=normalized.tag_status,
        )
    if isinstance(body, CompanionInput):
        source = body.source_saved_id
        if source is not None and not owns_saved_companion(conn, source):
            raise _bad_request("자주 함께 가는 일행에서만 불러올 수 있어요.")
        values["source_saved_id"] = parse_uuid_or_none(source)
    return values


# ---------- 여행 ----------


def list_trips(user: CurrentUser) -> list[TripSummary]:
    with user_tx(user) as conn:
        rows = repository.list_summaries(conn)
    return [
        TripSummary(
            id=str(r["id"]),
            city_id=r["city_id"],
            city_name=r["city_name"],
            time_zone=r["time_zone"],
            title=r["title"],
            start_date=r["start_date"],
            end_date=r["end_date"],
            companion_count=r["companion_count"],
            slot_counts=SlotCounts(
                active=r["active_slots"],
                filled=r["filled_slots"],
                onsite=r["onsite_slots"],
                empty=r["empty_slots"],
            ),
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def create_trip(user: CurrentUser, body: CreateTripInput) -> Trip:
    """여행 만들기 (F-01). 일차·빈 끼니·꼭 먹을 목록(대표 메뉴 체크)·보낸 일행을 한 트랜잭션에 만든다."""
    city = require_supported_city(body.city_id)
    if body.start_date and body.end_date:
        _check_range(city, body.start_date, body.end_date)

    with user_tx(user) as conn:
        if user.is_anonymous and repository.has_any_trip(conn):
            raise AppError(
                409, ErrorCode.GUEST_TRIP_LIMIT, "로그인하지 않으면 여행을 하나만 만들 수 있어요."
            )
        meals = body.default_meals or [
            MealDef(name=n, time_band=band_for_meal_name(n)) for n in default_meal_names(conn, user)
        ]
        if body.title:
            title = body.title
        elif body.start_date and body.end_date:
            title = f"{city.name} {describe_range_label(body.start_date, body.end_date)}"
        else:
            title = f"{city.name} 여행"

        trip = repository.insert_trip(
            conn,
            {
                "city_id": city.id,
                "title": title,
                "start_date": body.start_date,
                "end_date": body.end_date,
                "default_meals": [m.model_dump(by_alias=True) for m in meals],
            },
        )
        if body.start_date and body.end_date:
            _add_days(conn, trip["id"], enumerate_dates(body.start_date, body.end_date), meals)
        for companion in body.companions or []:
            repository.insert_companion(conn, trip["id"], _companion_values(companion, conn))
        repository.insert_must_picks_from_menus(
            conn, trip["id"], [(m.id, m.is_signature) for m in city.must_menus]
        )
        return _trip_dto(conn, trip)


def get_trip(user: CurrentUser, trip_id: str) -> Trip:
    with user_tx(user) as conn:
        return _trip_dto(conn, _require_trip(conn, trip_id))


def update_trip(user: CurrentUser, trip_id: str, body: UpdateTripInput) -> Trip:
    """제목·기본 끼니·기간 (F-01 3, Q-01). 보낸 필드만 바꾼다.

    - 기본 끼니: 뺀 끼니는 모든 날짜에서 지우고, 더한 끼니는 모든 날짜에 빈 끼니로 넣는다
    - 기간: 빠진 날짜의 일차·끼니는 메뉴·식당과 함께 지우고, 새 날짜에는 기본 끼니를 넣는다
    """
    sent = body.model_fields_set
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id, for_update=True)
        tid = trip["id"]
        city = get_catalog().city(trip["city_id"])
        assert city is not None

        dates_sent = bool({"start_date", "end_date"} & sent)
        next_start = body.start_date if "start_date" in sent else trip["start_date"]
        next_end = body.end_date if "end_date" in sent else trip["end_date"]
        if dates_sent:
            if not next_start or not next_end:
                raise _bad_request("시작일과 종료일을 함께 정해 주세요.")
            _check_range(city, next_start, next_end)

        values: Row = {}
        if "title" in sent:
            values["title"] = body.title

        meals = [MealDef.model_validate(m) for m in trip["default_meals"]]
        if "default_meals" in sent and body.default_meals is not None:
            before = {m.name for m in meals}
            after = {m.name for m in body.default_meals}
            repository.delete_slots_by_name(conn, tid, sorted(before - after))
            added = [m for m in body.default_meals if m.name not in before]
            for day in repository.list_days(conn, tid):
                for meal in added:
                    repository.insert_slot(conn, tid, day, meal.name, meal.time_band)
            meals = body.default_meals
            values["default_meals"] = [m.model_dump(by_alias=True) for m in meals]

        if dates_sent and next_start and next_end:
            days = repository.list_days(conn, tid)
            diff = diff_trip_dates([d["date"] for d in days], next_start, next_end)
            removed = set(diff.remove)
            repository.delete_days(conn, [d["id"] for d in days if d["date"] in removed])
            _add_days(conn, tid, diff.add, meals)
            values.update(start_date=next_start, end_date=next_end)

        repository.update_trip(conn, tid, values)
        _cleanup_acks(conn, tid)
        return _trip_dto(conn, _require_trip(conn, trip_id))


def delete_trip(user: CurrentUser, trip_id: str) -> None:
    """일차·끼니·일행·체크·허용 기록·꼭 먹을 목록·의견이 외래 키로 함께 지워진다"""
    with user_tx(user) as conn:
        if not repository.delete_trip(conn, parse_uuid(trip_id, _TRIP_NOT_FOUND)):
            raise _not_found(_TRIP_NOT_FOUND)


# ---------- 날짜와 끼니 ----------


def set_day_area(user: CurrentUser, trip_id: str, day_id: str, body: UpdateDayInput) -> Trip:
    """날짜 동네 (F-03). 직접 바꾼 끼니("변경됨")를 뺀 그날 끼니가 같은 동네를 따른다."""
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        day = repository.get_day(conn, trip["id"], parse_uuid(day_id, _DAY_NOT_FOUND))
        if day is None:
            raise _not_found(_DAY_NOT_FOUND)
        if body.area_id and not get_catalog().area_in_city(body.area_id, trip["city_id"]):
            raise _bad_request("이 도시의 동네가 아니에요.")
        repository.set_day_area(conn, day["id"], body.area_id)
        repository.update_trip(conn, trip["id"], {})
        return _trip_dto(conn, _require_trip(conn, trip_id))


def add_slot(user: CurrentUser, trip_id: str, day_id: str, body: MealDef) -> Slot:
    """날짜에 끼니 추가 (F-04 5). 같은 시간대의 맨 뒤, 동네는 날짜 동네."""
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        day = repository.get_day(conn, trip["id"], parse_uuid(day_id, _DAY_NOT_FOUND))
        if day is None:
            raise _not_found(_DAY_NOT_FOUND)
        row = repository.insert_slot(conn, trip["id"], day, body.name, body.time_band)
        repository.update_trip(conn, trip["id"], {})
        return _slot_dto(row, day["date"])


def update_slot(user: CurrentUser, slot_id: str, body: UpdateSlotInput) -> Slot:
    """끼니 바꾸기 (F-04, F-06, F-08, F-17). 보낸 필드만 바꾸고, 메뉴를 넣거나 지우면 상태를 맞춘다.

    - 메뉴를 넣으면 채워짐, 메뉴를 지우면(상태를 따로 안 보냈으면) 비어 있음
    - 빠짐으로 바꿔도 메뉴·식당은 그대로 둔다 ("다시 넣기"로 돌아온다, F-06 2)
    - 끼니 동네가 날짜 동네와 다르면 "변경됨" (F-03 2)
    - 식당을 다른 식당으로 바꾸면 그 끼니의 식이 확인 체크를 지운다 (F-08 2)
    """
    sent = body.model_fields_set
    catalog = get_catalog()
    with user_tx(user) as conn:
        slot = repository.get_slot(conn, parse_uuid(slot_id, _SLOT_NOT_FOUND))
        if slot is None:
            raise _not_found(_SLOT_NOT_FOUND)
        trip_id = slot["trip_id"]

        if body.area_id and not catalog.area_in_city(body.area_id, slot["city_id"]):
            raise _bad_request("이 도시의 동네가 아니에요.")
        if body.kind_id and not catalog.has_menu_kind(body.kind_id):
            raise _bad_request("알 수 없는 메뉴 종류예요.")
        pick_id = parse_uuid_or_none(body.must_pick_id)
        if body.must_pick_id and (
            pick_id is None or not repository.must_pick_in_trip(conn, trip_id, pick_id)
        ):
            raise _bad_request("이 여행의 꼭 먹을 항목이 아니에요.")

        s = dict(slot)
        if "menu" in sent:
            s["menu"] = body.menu or None
        if "kind_id" in sent:
            s["kind_id"] = body.kind_id
        if "kind_source" in sent:
            s["kind_source"] = body.kind_source
        if "menu_tags" in sent and body.menu_tags is not None:
            s["menu_tags"] = body.menu_tags
        if "place_id" in sent:
            if slot["place_id"] and slot["place_id"] != body.place_id:
                repository.delete_diet_checks_for_slot(conn, slot["id"])
            s["place_id"] = body.place_id
        if "must_pick_id" in sent:
            s["must_pick_id"] = pick_id
        if "area_id" in sent:
            s["area_id"] = body.area_id
            s["area_overridden"] = body.area_id != slot["day_area_id"]

        if "state" in sent and body.state is not None:
            s["state"] = body.state
            s["skip_reason"] = (
                (body.skip_reason if body.skip_reason is not None else "직접 삭제")
                if body.state == "skipped"
                else None
            )
        elif "menu" in sent:
            s["state"] = "filled" if s["menu"] else "empty"
        if s["menu"] is None:
            s["kind_id"] = body.kind_id if "kind_id" in sent else None
            s["kind_source"] = s["kind_source"] if s["kind_id"] else None
            if "menu_tags" not in sent:
                s["menu_tags"] = []
        if s["state"] == "filled" and not s["menu"]:
            raise _bad_request("메뉴가 있어야 채운 끼니로 바꿀 수 있어요.")

        columns = (
            "menu", "kind_id", "kind_source", "menu_tags", "place_id", "must_pick_id",
            "area_id", "area_overridden", "state", "skip_reason",
        )  # fmt: skip
        repository.update_slot(conn, slot["id"], {c: s[c] for c in columns})
        repository.update_trip(conn, trip_id, {})
        _cleanup_acks(conn, trip_id)
        return _slot_dto(s, slot["date"])


def set_slots_state(user: CurrentUser, trip_id: str, body: UpdateSlotsStateInput) -> Trip:
    """여러 끼니 상태를 한 번에 (F-17 "남은 n끼는 현장에서 정하기"와 되돌리기).
    메뉴가 없는 끼니(비어 있음·현장에서)끼리만. 하나라도 맞지 않으면 아무것도 바꾸지 않는다."""
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        slots = {str(s["id"]): s for s in repository.list_slots(conn, trip["id"])}
        wanted = list(dict.fromkeys(body.slot_ids))
        if any(i not in slots for i in wanted):
            raise _bad_request("이 여행의 끼니가 아니에요.")
        if any(
            slots[i]["menu"] is not None or slots[i]["state"] not in ("empty", "onsite")
            for i in wanted
        ):
            raise _bad_request("메뉴가 없는 끼니(비어 있음·현장에서)만 한 번에 바꿀 수 있어요.")
        repository.set_slots_state(conn, [slots[i]["id"] for i in wanted], body.state)
        repository.update_trip(conn, trip["id"], {})
        _cleanup_acks(conn, trip["id"])
        return _trip_dto(conn, _require_trip(conn, trip_id))


def ack_duplicate(user: CurrentUser, trip_id: str, body: DuplicateAck) -> None:
    """하루 중복 "괜찮아요" (F-05 4). 같은 날짜·종류의 기록은 새 목록으로 바뀐다."""
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        slots = {str(s["id"]): s for s in repository.list_slots(conn, trip["id"])}
        valid = all(
            (s := slots.get(i)) is not None
            and str(s["day_id"]) == body.day_id
            and s["kind_id"] == body.kind_id
            for i in body.slot_ids
        )
        if not valid:
            raise _bad_request("중복된 끼니 목록이 맞지 않아요.")
        repository.upsert_ack(
            conn,
            trip["id"],
            uuid.UUID(body.day_id),
            body.kind_id,
            [slots[i]["id"] for i in dict.fromkeys(body.slot_ids)],
        )


# ---------- 일행·식이 확인 ----------


def add_companion(user: CurrentUser, trip_id: str, body: CompanionInput) -> Companion:
    """여행 일행 추가 (F-02). 원문은 그대로 두고 서버가 태그로 정규화한다."""
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        row = repository.insert_companion(conn, trip["id"], _companion_values(body, conn))
        repository.update_trip(conn, trip["id"], {})
        return _companion_dto(row)


def update_companion(
    user: CurrentUser, trip_id: str, companion_id: str, body: CompanionPatch
) -> Companion:
    """여행 일행 수정. 불러온 일행이어도 이 여행에서만 바뀐다 (F-02 3)."""
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        cid = parse_uuid(companion_id, _COMPANION_NOT_FOUND)
        if repository.get_companion(conn, trip["id"], cid) is None:
            raise _not_found(_COMPANION_NOT_FOUND)
        values = _companion_values(body, conn)
        row = (
            repository.update_companion(conn, cid, values)
            if values
            else repository.get_companion(conn, trip["id"], cid)
        )
        assert row is not None
        return _companion_dto(row)


def delete_companion(user: CurrentUser, trip_id: str, companion_id: str) -> None:
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        cid = parse_uuid(companion_id, _COMPANION_NOT_FOUND)
        if not repository.delete_companion(conn, trip["id"], cid):
            raise _not_found(_COMPANION_NOT_FOUND)
        repository.update_trip(conn, trip["id"], {})


def set_diet_check(user: CurrentUser, slot_id: str, companion_id: str, checked: bool) -> DietCheck:
    """flex 일행의 "확인함" (F-08). 끼니 × 일행 단위로 저장한다(있으면 덮어쓴다)."""
    with user_tx(user) as conn:
        slot = repository.get_slot(conn, parse_uuid(slot_id, _SLOT_NOT_FOUND))
        if slot is None:
            raise _not_found(_SLOT_NOT_FOUND)
        cid = parse_uuid(companion_id, _COMPANION_NOT_FOUND)
        if repository.get_companion(conn, slot["trip_id"], cid) is None:
            raise _not_found(_COMPANION_NOT_FOUND)
        repository.upsert_diet_check(conn, slot["trip_id"], slot["id"], cid, checked)
        return DietCheck(slot_id=str(slot["id"]), companion_id=str(cid), checked=checked)


# ---------- 꼭 먹을 것 ----------


def put_must_picks(user: CurrentUser, trip_id: str, body: PutMustPicksInput) -> list[MustPick]:
    """꼭 먹을 목록 전체 바꾸기 (F-07). 배열 순서가 order, 보내지 않은 항목은 지운다.

    - 끼니에 넣은 항목은 체크를 풀거나 지울 수 없다 (409 MUST_PICK_PLACED)
    - 식당 항목은 내 맛집 모음의 같은 도시 식당만 (C-2)
    - 직접 추가한 메뉴의 종류가 없으면 서버가 분류한다
    """
    catalog = get_catalog()
    with user_tx(user) as conn:
        trip = _require_trip(conn, trip_id)
        tid = trip["id"]
        slots = repository.list_slots(conn, tid)
        current = _must_pick_dtos(conn, repository.list_must_picks(conn, tid), slots)
        items_by_id = {i.id: i for i in body.items if i.id}
        for placed in (p for p in current if p.placed_slot_id):
            nxt = items_by_id.get(placed.id)
            if nxt is None or not nxt.checked:
                raise AppError(
                    409,
                    ErrorCode.MUST_PICK_PLACED,
                    f"{_with_topic(placed.display.name)} 끼니에서 먼저 빼야 고칠 수 있어요.",
                )

        saved = saved_places_by_id(
            conn, [u for i in body.items if (u := parse_uuid_or_none(i.saved_place_id))]
        )
        current_ids = {p.id for p in current}
        rows: list[Row] = []
        for order, item in enumerate(body.items):
            row: Row = {
                "id": uuid.UUID(item.id) if item.id in current_ids and item.id else uuid.uuid4(),
                "type": item.type,
                "sort_order": order,
                "checked": item.checked,
                "must_menu_id": None,
                "custom_menu_name": None,
                "custom_menu_kind_id": None,
                "saved_place_id": None,
            }
            if item.type == "place":
                place_row = saved.get(item.saved_place_id or "")
                if place_row is None or place_row["city_id"] != trip["city_id"]:
                    raise _bad_request("맛집 모음에 있는 이 도시 식당만 담을 수 있어요.")
                row["saved_place_id"] = place_row["id"]
            elif item.must_menu_id and not item.custom_menu:
                if not catalog.must_menu_in_city(item.must_menu_id, trip["city_id"]):
                    raise _bad_request("이 도시의 필수 메뉴가 아니에요.")
                row["must_menu_id"] = item.must_menu_id
            elif item.custom_menu and not item.must_menu_id:
                kind_id = item.custom_menu.kind_id
                if kind_id is not None and not catalog.has_menu_kind(kind_id):
                    raise _bad_request("알 수 없는 메뉴 종류예요.")
                row["custom_menu_name"] = item.custom_menu.name
                row["custom_menu_kind_id"] = kind_id or classify_menu(item.custom_menu.name).kind_id
            else:
                raise _bad_request("메뉴 항목은 필수 메뉴나 직접 추가한 메뉴 중 하나여야 해요.")
            rows.append(row)

        repository.replace_must_picks(conn, tid, rows)
        repository.update_trip(conn, tid, {})
        return _must_pick_dtos(conn, repository.list_must_picks(conn, tid), slots)


# ---------- 다른 모듈이 쓰는 것 ----------


def slot_search_context(user: CurrentUser, slot_id: str) -> tuple[str | None, str | None, str]:
    """식당 검색에 쓰는 끼니의 (메뉴, 동네, 도시). 내 끼니가 아니면 404"""
    with user_tx(user) as conn:
        row = repository.slot_search_context(conn, parse_uuid(slot_id, _SLOT_NOT_FOUND))
    if row is None:
        raise _not_found(_SLOT_NOT_FOUND)
    return row["menu"], row["area_id"], row["city_id"]


def placements_for_places(conn: Conn, place_ids: list[str]) -> dict[str, list[Placement]]:
    """맛집 모음의 "D2 점심에 넣음" (places 서비스가 같은 트랜잭션에서 부른다)"""
    result: dict[str, list[Placement]] = {}
    for r in repository.placements_for_places(conn, place_ids):
        result.setdefault(r["place_id"], []).append(
            Placement(
                trip_id=str(r["trip_id"]),
                slot_id=str(r["slot_id"]),
                day_number=r["day_number"],
                slot_name=r["slot_name"],
            )
        )
    return result
