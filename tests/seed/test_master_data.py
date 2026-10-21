"""마스터 데이터 시드: JSON → 행 변환과 DB/data.sql·DB/init.sql 최신 상태 확인."""

import json

from app.seed.master_data import (
    INIT_SQL_PATH,
    MASTER_DIR,
    MIGRATIONS_DIR,
    SEED_SQL_PATH,
    build_catalog_rows,
    render_init_sql,
    render_seed_sql,
)


def test_rows_match_master_data_json() -> None:
    rows = build_catalog_rows()
    cities = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((MASTER_DIR / "cities").glob("*.json"))
    ]
    kinds = json.loads((MASTER_DIR / "menu-kinds.json").read_text(encoding="utf-8"))["kinds"]

    assert [c["id"] for c in rows["cities"]] == ["fukuoka", "osaka", "tokyo", "taipei", "bangkok"]
    assert len(rows["areas"]) == sum(len(c["areas"]) for c in cities)
    assert len(rows["must_menus"]) == sum(len(c["mustMenus"]) for c in cities)
    assert len(rows["menu_kinds"]) == len(kinds)
    assert {m["id"] for m in rows["must_menus"] if m["is_signature"]} == {
        m["id"] for c in cities for m in c["mustMenus"] if m.get("isSignature")
    }


def test_city_references_are_consistent() -> None:
    """동네 id는 도시를 넘어 유일하고(areas 기본 키), 메뉴 종류와 음식 태그는 목록에 있는 것만 쓴다."""
    rows = build_catalog_rows()
    area_ids = [a["id"] for a in rows["areas"]]
    assert len(area_ids) == len(set(area_ids))
    menu_ids = [m["id"] for m in rows["must_menus"]]
    assert len(menu_ids) == len(set(menu_ids))
    kind_ids = {k["id"] for k in rows["menu_kinds"]}
    tag_ids = {t["id"] for t in rows["food_tags"]}
    for menu in rows["must_menus"]:
        assert menu["kind_id"] in kind_ids, menu["id"]
        assert set(menu["food_tags"]) <= tag_ids, menu["id"]


def test_parent_food_tags_come_before_children() -> None:
    tags = build_catalog_rows()["food_tags"]
    seen: set[str] = set()
    for tag in tags:
        assert tag["parent_id"] is None or tag["parent_id"] in seen
        seen.add(tag["id"])
    assert next(t for t in tags if t["id"] == "pork")["parent_id"] == "meat"


def test_committed_seed_sql_is_up_to_date() -> None:
    """data/master-data를 바꾸고 DB/data.sql을 다시 만들지 않으면 실패한다.

    고치려면: `uv run python -m app.seed.master_data --sql`
    """
    expected = render_seed_sql(build_catalog_rows())
    assert SEED_SQL_PATH.read_text(encoding="utf-8") == expected


def test_seed_sql_escapes_quotes() -> None:
    rows = build_catalog_rows()
    rows["cities"][0]["name"] = "O'Kuoka"
    assert "'O''Kuoka'" in render_seed_sql(rows)


def test_committed_init_sql_matches_migrations() -> None:
    """마이그레이션을 더하거나 고치고 DB/init.sql을 다시 만들지 않으면 실패한다.

    고치려면: `uv run python -m app.seed.master_data --sql`
    """
    init_sql = INIT_SQL_PATH.read_text(encoding="utf-8")
    assert init_sql == render_init_sql()
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        assert f"-- ===== {migration.name} =====" in init_sql
