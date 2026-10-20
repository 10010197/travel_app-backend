"""여행 표 읽기·쓰기 (0003_trips.sql, 0007 trip_summaries). RLS가 내 여행만 보여 준다.

남의 여행·끼니는 RLS 때문에 조회 결과가 비므로, 서비스는 "없음"으로 404를 낸다(존재를 드러내지 않는다).
"""

import uuid
from datetime import date
from typing import Any

from psycopg.types.json import Jsonb

from app.db.session import Conn

Row = dict[str, Any]


# ---------- 여행 ----------


def list_summaries(conn: Conn) -> list[Row]:
    return conn.execute(
        """select s.*, t.created_at
           from trip_summaries s join trips t on t.id = s.id
           order by t.created_at, s.id"""
    ).fetchall()


def get_trip(conn: Conn, trip_id: uuid.UUID, *, for_update: bool = False) -> Row | None:
    lock = " for update" if for_update else ""
    return conn.execute(f"select * from trips where id = %s{lock}", (trip_id,)).fetchone()


def has_any_trip(conn: Conn) -> bool:
    return conn.execute("select exists (select 1 from trips) as found").fetchone() == {
        "found": True
    }


def insert_trip(conn: Conn, values: Row) -> Row:
    row = conn.execute(
        """insert into trips (city_id, title, start_date, end_date, default_meals)
           values (%(city_id)s, %(title)s, %(start_date)s, %(end_date)s, %(default_meals)s)
           returning *""",
        {**values, "default_meals": Jsonb(values["default_meals"])},
    ).fetchone()
    assert row is not None
    return row


def update_trip(conn: Conn, trip_id: uuid.UUID, values: Row) -> None:
    """보낸 열만 바꾼다. 값이 없어도 updated_at은 트리거가 새로 매긴다(끼니만 바뀐 경우)."""
    values = {k: Jsonb(v) if k == "default_meals" else v for k, v in values.items()}
    sets = ", ".join([*(f"{k} = %({k})s" for k in values), "updated_at = now()"])
    conn.execute(f"update trips set {sets} where id = %(id)s", {**values, "id": trip_id})


def delete_trip(conn: Conn, trip_id: uuid.UUID) -> bool:
    return conn.execute("delete from trips where id = %s", (trip_id,)).rowcount > 0


# ---------- 여행 상세 (GET /trips/{id}에 들어가는 표 전부) ----------


def trip_children(conn: Conn, trip_id: uuid.UUID) -> dict[str, list[Row]]:
    q = {
        "days": "select * from trip_days where trip_id = %s order by date",
        "slots": "select * from slots where trip_id = %s",
        "companions": "select * from trip_companions where trip_id = %s order by created_at, id",
        "acks": "select * from duplicate_acks where trip_id = %s order by day_id, kind_id",
        "checks": "select * from diet_checks where trip_id = %s order by slot_id, companion_id",
        "must_picks": "select * from must_picks where trip_id = %s order by sort_order, id",
    }
    return {key: conn.execute(sql, (trip_id,)).fetchall() for key, sql in q.items()}


# ---------- 일차 ----------


def get_day(conn: Conn, trip_id: uuid.UUID, day_id: uuid.UUID) -> Row | None:
    return conn.execute(
        "select * from trip_days where id = %s and trip_id = %s", (day_id, trip_id)
    ).fetchone()


def list_days(conn: Conn, trip_id: uuid.UUID) -> list[Row]:
    return conn.execute(
        "select * from trip_days where trip_id = %s order by date", (trip_id,)
    ).fetchall()


def insert_day(conn: Conn, trip_id: uuid.UUID, day: date, day_number: int) -> Row:
    row = conn.execute(
        """insert into trip_days (trip_id, date, day_number) values (%s, %s, %s) returning *""",
        (trip_id, day, day_number),
    ).fetchone()
    assert row is not None
    return row


def delete_days(conn: Conn, day_ids: list[uuid.UUID]) -> None:
    """일차를 지우면 끼니·식이 체크·허용 기록·의견이 외래 키로 함께 지워진다 (Q-01)"""
    if day_ids:
        conn.execute("delete from trip_days where id = any(%s)", (day_ids,))


def renumber_days(conn: Conn, trip_id: uuid.UUID) -> None:
    """D1, D2 …를 날짜 순으로 다시 매긴다. 번호 유일 제약은 트랜잭션 끝에서 검사한다(deferrable)."""
    conn.execute(
        """update trip_days d set day_number = n.num
           from (select id, row_number() over (order by date) as num
                 from trip_days where trip_id = %s) n
           where d.id = n.id and d.day_number <> n.num""",
        (trip_id,),
    )


def set_day_area(conn: Conn, day_id: uuid.UUID, area_id: str | None) -> None:
    """날짜 동네를 바꾸고, 직접 바꾼 끼니("변경됨")를 뺀 그날 끼니가 따르게 한다 (F-03 2)"""
    conn.execute("update trip_days set area_id = %s where id = %s", (area_id, day_id))
    conn.execute(
        """update slots set area_id = %s
           where day_id = %s and not area_overridden and area_id is distinct from %s""",
        (area_id, day_id, area_id),
    )


# ---------- 끼니 ----------


def get_slot(conn: Conn, slot_id: uuid.UUID) -> Row | None:
    """끼니와 그 날짜·여행 도시 (내 여행일 때만)"""
    return conn.execute(
        """select s.*, d.date, d.area_id as day_area_id, t.city_id
           from slots s
           join trip_days d on d.id = s.day_id
           join trips t on t.id = s.trip_id
           where s.id = %s""",
        (slot_id,),
    ).fetchone()


def list_slots(conn: Conn, trip_id: uuid.UUID) -> list[Row]:
    return conn.execute("select * from slots where trip_id = %s", (trip_id,)).fetchall()


def insert_slot(conn: Conn, trip_id: uuid.UUID, day: Row, name: str, time_band: str) -> Row:
    """날짜에 빈 끼니를 더한다. 같은 시간대의 맨 뒤에 붙고, 동네는 날짜 동네를 따른다 (F-04 5, F-03 2)"""
    row = conn.execute(
        """insert into slots (trip_id, day_id, name, time_band, sort_order, area_id)
           values (%(trip_id)s, %(day_id)s, %(name)s, %(time_band)s,
                   coalesce((select max(sort_order) + 1 from slots
                             where day_id = %(day_id)s and time_band = %(time_band)s), 0),
                   %(area_id)s)
           returning *""",
        {
            "trip_id": trip_id,
            "day_id": day["id"],
            "name": name,
            "time_band": time_band,
            "area_id": day["area_id"],
        },
    ).fetchone()
    assert row is not None
    return row


def update_slot(conn: Conn, slot_id: uuid.UUID, values: Row) -> None:
    sets = ", ".join(f"{k} = %({k})s" for k in values)
    conn.execute(f"update slots set {sets} where id = %(id)s", {**values, "id": slot_id})


def delete_slots_by_name(conn: Conn, trip_id: uuid.UUID, names: list[str]) -> None:
    """기본 끼니에서 뺀 끼니를 모든 날짜에서 지운다 (F-01 3)"""
    if names:
        conn.execute("delete from slots where trip_id = %s and name = any(%s)", (trip_id, names))


def set_slots_state(conn: Conn, slot_ids: list[uuid.UUID], state: str) -> None:
    conn.execute(
        "update slots set state = %s, skip_reason = null where id = any(%s)", (state, slot_ids)
    )


def slot_search_context(conn: Conn, slot_id: uuid.UUID) -> Row | None:
    return conn.execute(
        """select s.menu, s.area_id, t.city_id
           from slots s join trips t on t.id = s.trip_id where s.id = %s""",
        (slot_id,),
    ).fetchone()


def placements_for_places(conn: Conn, place_ids: list[str]) -> list[Row]:
    """이 식당들을 넣은 내 끼니 ("D2 점심에 넣음"). 빠진 끼니는 넣은 것으로 치지 않는다"""
    if not place_ids:
        return []
    return conn.execute(
        """select s.place_id, s.trip_id, s.id as slot_id, d.day_number, s.name as slot_name
           from slots s join trip_days d on d.id = s.day_id
           where s.place_id = any(%s) and s.state <> 'skipped'
           order by d.date, s.created_at""",
        (place_ids,),
    ).fetchall()


# ---------- 일행·식이 체크 ----------


def insert_companion(conn: Conn, trip_id: uuid.UUID, values: Row) -> Row:
    row = conn.execute(
        """insert into trip_companions
             (trip_id, name, foods_raw, food_tags, tag_status, strictness, source_saved_id)
           values (%(trip_id)s, %(name)s, %(foods_raw)s, %(food_tags)s, %(tag_status)s,
                   %(strictness)s, %(source_saved_id)s)
           returning *""",
        {**values, "trip_id": trip_id},
    ).fetchone()
    assert row is not None
    return row


def get_companion(conn: Conn, trip_id: uuid.UUID, companion_id: uuid.UUID) -> Row | None:
    return conn.execute(
        "select * from trip_companions where id = %s and trip_id = %s", (companion_id, trip_id)
    ).fetchone()


def update_companion(conn: Conn, companion_id: uuid.UUID, values: Row) -> Row | None:
    sets = ", ".join(f"{k} = %({k})s" for k in values)
    return conn.execute(
        f"update trip_companions set {sets} where id = %(id)s returning *",
        {**values, "id": companion_id},
    ).fetchone()


def delete_companion(conn: Conn, trip_id: uuid.UUID, companion_id: uuid.UUID) -> bool:
    """일행을 지우면 그 일행의 식이 확인 체크도 외래 키로 함께 지워진다 (F-02 2)"""
    return (
        conn.execute(
            "delete from trip_companions where id = %s and trip_id = %s", (companion_id, trip_id)
        ).rowcount
        > 0
    )


def delete_diet_checks_for_slot(conn: Conn, slot_id: uuid.UUID) -> None:
    conn.execute("delete from diet_checks where slot_id = %s", (slot_id,))


def upsert_diet_check(
    conn: Conn, trip_id: uuid.UUID, slot_id: uuid.UUID, companion_id: uuid.UUID, checked: bool
) -> None:
    conn.execute(
        """insert into diet_checks (slot_id, companion_id, trip_id, checked)
           values (%s, %s, %s, %s)
           on conflict (slot_id, companion_id) do update set checked = excluded.checked""",
        (slot_id, companion_id, trip_id, checked),
    )


# ---------- 허용 기록 ----------


def list_acks(conn: Conn, trip_id: uuid.UUID) -> list[Row]:
    return conn.execute("select * from duplicate_acks where trip_id = %s", (trip_id,)).fetchall()


def upsert_ack(
    conn: Conn, trip_id: uuid.UUID, day_id: uuid.UUID, kind_id: str, slot_ids: list[uuid.UUID]
) -> None:
    conn.execute(
        """insert into duplicate_acks (day_id, kind_id, trip_id, slot_ids) values (%s, %s, %s, %s)
           on conflict (day_id, kind_id) do update set slot_ids = excluded.slot_ids""",
        (day_id, kind_id, trip_id, slot_ids),
    )


def delete_ack(conn: Conn, day_id: uuid.UUID, kind_id: str) -> None:
    conn.execute("delete from duplicate_acks where day_id = %s and kind_id = %s", (day_id, kind_id))


# ---------- 꼭 먹을 것 ----------


def list_must_picks(conn: Conn, trip_id: uuid.UUID) -> list[Row]:
    return conn.execute(
        "select * from must_picks where trip_id = %s order by sort_order, id", (trip_id,)
    ).fetchall()


def must_pick_in_trip(conn: Conn, trip_id: uuid.UUID, pick_id: uuid.UUID) -> bool:
    row = conn.execute(
        "select 1 as found from must_picks where id = %s and trip_id = %s", (pick_id, trip_id)
    ).fetchone()
    return row is not None


def replace_must_picks(conn: Conn, trip_id: uuid.UUID, rows: list[Row]) -> None:
    """보내지 않은 항목은 지우고(넣은 끼니의 연결은 외래 키가 비운다), 나머지는 순서대로 넣거나 고친다"""
    keep = [r["id"] for r in rows]
    conn.execute(
        "delete from must_picks where trip_id = %s and not (id = any(%s))", (trip_id, keep)
    )
    for row in rows:
        conn.execute(
            """insert into must_picks
                 (id, trip_id, type, sort_order, checked, must_menu_id,
                  custom_menu_name, custom_menu_kind_id, saved_place_id)
               values (%(id)s, %(trip_id)s, %(type)s, %(sort_order)s, %(checked)s,
                       %(must_menu_id)s, %(custom_menu_name)s, %(custom_menu_kind_id)s,
                       %(saved_place_id)s)
               on conflict (id) do update set
                 type = excluded.type, sort_order = excluded.sort_order,
                 checked = excluded.checked, must_menu_id = excluded.must_menu_id,
                 custom_menu_name = excluded.custom_menu_name,
                 custom_menu_kind_id = excluded.custom_menu_kind_id,
                 saved_place_id = excluded.saved_place_id""",
            {**row, "trip_id": trip_id},
        )


def insert_must_picks_from_menus(
    conn: Conn, trip_id: uuid.UUID, menus: list[tuple[str, bool]]
) -> None:
    """새 여행의 꼭 먹을 목록: 도시 필수 메뉴 전부, 대표 메뉴만 체크 (F-07 2)"""
    for order, (must_menu_id, checked) in enumerate(menus):
        conn.execute(
            """insert into must_picks (trip_id, type, sort_order, checked, must_menu_id)
               values (%s, 'menu', %s, %s, %s)""",
            (trip_id, order, checked, must_menu_id),
        )
