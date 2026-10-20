"""profiles·user_settings·saved_companions 읽기·쓰기 (0002_identity.sql). RLS가 본인 행만 보여 준다."""

import uuid
from typing import Any

from app.db.session import Conn

Row = dict[str, Any]

_COMPANION_COLUMNS = "id, name, foods_raw, food_tags, strictness"


def get_profile(conn: Conn, user_id: str) -> Row | None:
    return conn.execute("select display_name from profiles where id = %s", (user_id,)).fetchone()


def get_settings(conn: Conn, user_id: str) -> Row | None:
    return conn.execute(
        "select default_meals, time_display, notify_empty_slots from user_settings where user_id = %s",
        (user_id,),
    ).fetchone()


def update_settings(conn: Conn, user_id: str, values: Row) -> Row | None:
    return conn.execute(
        """update user_settings
           set default_meals = %(default_meals)s, time_display = %(time_display)s,
               notify_empty_slots = %(notify_empty_slots)s
           where user_id = %(user_id)s
           returning default_meals, time_display, notify_empty_slots""",
        {**values, "user_id": user_id},
    ).fetchone()


def list_saved_companions(conn: Conn) -> list[Row]:
    return conn.execute(
        f"select {_COMPANION_COLUMNS} from saved_companions order by created_at, id"
    ).fetchall()


def get_saved_companion(conn: Conn, companion_id: uuid.UUID) -> Row | None:
    return conn.execute(
        f"select {_COMPANION_COLUMNS} from saved_companions where id = %s", (companion_id,)
    ).fetchone()


def insert_saved_companion(conn: Conn, values: Row) -> Row:
    row = conn.execute(
        f"""insert into saved_companions (name, foods_raw, food_tags, strictness)
            values (%(name)s, %(foods_raw)s, %(food_tags)s, %(strictness)s)
            returning {_COMPANION_COLUMNS}""",
        values,
    ).fetchone()
    assert row is not None
    return row


def update_saved_companion(conn: Conn, companion_id: uuid.UUID, values: Row) -> Row | None:
    sets = ", ".join(f"{column} = %({column})s" for column in values)
    return conn.execute(
        f"update saved_companions set {sets} where id = %(id)s returning {_COMPANION_COLUMNS}",
        {**values, "id": companion_id},
    ).fetchone()


def delete_saved_companion(conn: Conn, companion_id: uuid.UUID) -> bool:
    cur = conn.execute("delete from saved_companions where id = %s", (companion_id,))
    return cur.rowcount > 0
