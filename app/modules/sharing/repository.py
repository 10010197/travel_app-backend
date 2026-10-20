"""공유 (0005_sharing.sql, trips.share_token).

소유자 기능(링크 켜기·끄기, 받은 의견)은 user_tx(RLS)로, 공개 조회·의견 쓰기는 service_tx로 부른다.
공개 조회는 공유 응답에 넣을 열만 읽는다(식이 원문·이메일은 처음부터 읽지 않는다).
"""

import uuid
from typing import Any

from app.db.session import Conn

Row = dict[str, Any]


# ---------- 소유자 (RLS) ----------


def get_share_token(conn: Conn, trip_id: uuid.UUID) -> Row | None:
    """내 여행이면 {share_token}, 아니면 None"""
    return conn.execute(
        "select share_token from trips where id = %s for update", (trip_id,)
    ).fetchone()


def set_share_token(conn: Conn, trip_id: uuid.UUID, token: str | None) -> None:
    conn.execute("update trips set share_token = %s where id = %s", (token, trip_id))


def list_comments(conn: Conn, trip_id: uuid.UUID) -> list[Row]:
    return conn.execute(
        """select id, slot_id, author_name, body, "like", created_at
           from share_comments where trip_id = %s order by created_at, id""",
        (trip_id,),
    ).fetchall()


# ---------- 공개 (service_role) ----------


def trip_by_token(conn: Conn, token: str) -> Row | None:
    return conn.execute(
        """select t.id, t.title, t.city_id, t.start_date, t.end_date, p.display_name as owner_name
           from trips t left join profiles p on p.id = t.owner_id
           where t.share_token = %s""",
        (token,),
    ).fetchone()


def shared_parts(conn: Conn, trip_id: uuid.UUID) -> dict[str, list[Row]]:
    return {
        "companions": conn.execute(
            "select name from trip_companions where trip_id = %s order by created_at, id",
            (trip_id,),
        ).fetchall(),
        "days": conn.execute(
            "select id, date, day_number, area_id from trip_days where trip_id = %s order by date",
            (trip_id,),
        ).fetchall(),
        "slots": conn.execute(
            """select id, day_id, name, time_band, sort_order, state, menu, place_id, area_id
               from slots where trip_id = %s""",
            (trip_id,),
        ).fetchall(),
        "comments": list_comments(conn, trip_id),
    }


def slot_in_trip(conn: Conn, trip_id: uuid.UUID, slot_id: uuid.UUID) -> bool:
    row = conn.execute(
        "select 1 as found from slots where id = %s and trip_id = %s", (slot_id, trip_id)
    ).fetchone()
    return row is not None


def insert_comment(conn: Conn, trip_id: uuid.UUID, slot_id: uuid.UUID, values: Row) -> Row:
    row = conn.execute(
        """insert into share_comments (trip_id, slot_id, author_name, body, "like")
           values (%(trip_id)s, %(slot_id)s, %(author_name)s, %(body)s, %(like)s)
           returning id, slot_id, author_name, body, "like", created_at""",
        {**values, "trip_id": trip_id, "slot_id": slot_id},
    ).fetchone()
    assert row is not None
    return row
