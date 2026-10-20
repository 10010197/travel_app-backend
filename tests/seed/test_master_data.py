"""마스터 데이터 시드: JSON → 행 변환과 seed.sql 최신 상태 확인."""

import json

from app.seed.master_data import MASTER_DIR, SEED_SQL_PATH, build_catalog_rows, render_seed_sql


def test_rows_match_master_data_json() -> None:
    rows = build_catalog_rows()
    fukuoka = json.loads((MASTER_DIR / "cities" / "fukuoka.json").read_text(encoding="utf-8"))
    kinds = json.loads((MASTER_DIR / "menu-kinds.json").read_text(encoding="utf-8"))["kinds"]

    assert [c["id"] for c in rows["cities"]] == ["fukuoka"]
    assert len(rows["areas"]) == len(fukuoka["areas"])
    assert len(rows["must_menus"]) == len(fukuoka["mustMenus"])
    assert len(rows["menu_kinds"]) == len(kinds)
    assert {m["id"] for m in rows["must_menus"] if m["is_signature"]} == {
        m["id"] for m in fukuoka["mustMenus"] if m.get("isSignature")
    }


def test_parent_food_tags_come_before_children() -> None:
    tags = build_catalog_rows()["food_tags"]
    seen: set[str] = set()
    for tag in tags:
        assert tag["parent_id"] is None or tag["parent_id"] in seen
        seen.add(tag["id"])
    assert next(t for t in tags if t["id"] == "pork")["parent_id"] == "meat"


def test_committed_seed_sql_is_up_to_date() -> None:
    """data/master-data를 바꾸고 seed.sql을 다시 만들지 않으면 실패한다.

    고치려면: `uv run python -m app.seed.master_data --sql`
    """
    expected = render_seed_sql(build_catalog_rows())
    assert SEED_SQL_PATH.read_text(encoding="utf-8") == expected


def test_seed_sql_escapes_quotes() -> None:
    rows = build_catalog_rows()
    rows["cities"][0]["name"] = "O'Kuoka"
    assert "'O''Kuoka'" in render_seed_sql(rows)
