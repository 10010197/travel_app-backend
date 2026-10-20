"""마스터 데이터 표 읽기 (0001_catalog.sql). 쓰기는 시드만 한다."""

from typing import Any

from app.db.session import Conn


def load_all(conn: Conn) -> dict[str, list[dict[str, Any]]]:
    """마스터 데이터 6개 표 전체. 작아서(수십 행) 한 번에 읽어 캐시한다."""
    return {
        "menu_kinds": conn.execute("select * from menu_kinds order by sort_order").fetchall(),
        "food_tags": conn.execute("select * from food_tags order by sort_order").fetchall(),
        "food_tag_presets": conn.execute(
            "select * from food_tag_presets order by sort_order"
        ).fetchall(),
        "cities": conn.execute("select * from cities order by sort_order").fetchall(),
        "areas": conn.execute("select * from areas order by city_id, sort_order").fetchall(),
        "must_menus": conn.execute(
            "select * from must_menus order by city_id, sort_order"
        ).fetchall(),
    }
