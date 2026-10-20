"""맛집 모음 표 읽기·쓰기 (0004_places.sql). RLS가 내 행만 보여 준다. place_id만 저장한다 (C-8)."""

import uuid
from typing import Any

from app.db.session import Conn

Row = dict[str, Any]


def list_saved_places(conn: Conn, city_id: str | None) -> list[Row]:
    if city_id:
        return conn.execute(
            "select * from saved_places where city_id = %s order by saved_at, id", (city_id,)
        ).fetchall()
    return conn.execute("select * from saved_places order by saved_at, id").fetchall()


def get_saved_places(conn: Conn, ids: list[uuid.UUID]) -> list[Row]:
    if not ids:
        return []
    return conn.execute("select * from saved_places where id = any(%s)", (ids,)).fetchall()


def upsert_saved_place(conn: Conn, values: Row) -> tuple[Row, bool]:
    """같은 식당을 다시 저장하면 새 행이 아니라 메뉴·종류만 바꾼다 (F-15 6). 반환: (행, 새로 만들었는지)"""
    row = conn.execute(
        """insert into saved_places (city_id, place_id, menu, kind_id, area_id)
           values (%(city_id)s, %(place_id)s, %(menu)s, %(kind_id)s, %(area_id)s)
           on conflict (user_id, place_id) do update
             set menu = excluded.menu, kind_id = excluded.kind_id
           returning *, (xmax = 0) as inserted""",
        values,
    ).fetchone()
    assert row is not None
    return row, bool(row.pop("inserted"))


def delete_saved_place(conn: Conn, saved_place_id: uuid.UUID) -> bool:
    """지우면 이 식당을 담은 꼭 먹을 항목도 외래 키로 함께 빠진다. 끼니의 place_id는 그대로 남는다"""
    return conn.execute("delete from saved_places where id = %s", (saved_place_id,)).rowcount > 0
