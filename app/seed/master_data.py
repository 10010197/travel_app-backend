"""마스터 데이터 시드 (catalog 경계, docs/ARCHITECTURE.md 6장).

원본은 backend/data/master-data/*.json 하나다. 프론트 레포의 목(src/mocks/data/master-data)은 이 파일의 복사본이다.
이 모듈은 JSON을 catalog 테이블 행으로 바꾸고, 두 가지 방법으로 넣는다.

- `uv run python -m app.seed.master_data`        Supabase에 upsert (service_role 키 필요)
- `uv run python -m app.seed.master_data --sql`  DB/init.sql(스키마)과 DB/data.sql(초기 데이터)을 다시 만든다

Supabase는 `supabase start`·`db reset` 때 supabase/migrations를 적용하고 DB/data.sql을 시드로 넣는다(config.toml).
DB/init.sql은 그 마이그레이션들을 번호 순서로 이은 합본이다(빈 Supabase DB에 한 번에 적용하거나 스키마를 한눈에 볼 때).

upsert라 여러 번 실행해도 된다. JSON에서 지운 행은 지우지 않는다(이미 여행이 참조할 수 있어서). 지울 때는 마이그레이션으로 한다.
"""

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MASTER_DIR = BACKEND_ROOT / "data" / "master-data"
MIGRATIONS_DIR = BACKEND_ROOT / "supabase" / "migrations"
DB_DIR = BACKEND_ROOT / "DB"
INIT_SQL_PATH = DB_DIR / "init.sql"
SEED_SQL_PATH = DB_DIR / "data.sql"

Row = dict[str, Any]

# 넣는 순서 = 외래 키 순서. (테이블, 충돌 키)
TABLE_ORDER: tuple[tuple[str, str], ...] = (
    ("menu_kinds", "id"),
    ("food_tags", "id"),
    ("food_tag_presets", "label"),
    ("cities", "id"),
    ("areas", "id"),
    ("must_menus", "id"),
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_catalog_rows(master_dir: Path = MASTER_DIR) -> dict[str, list[Row]]:
    """data/master-data의 JSON을 테이블별 행 목록으로 바꾼다. 순서(sort_order)는 JSON 순서를 따른다."""
    kinds = _read(master_dir / "menu-kinds.json")["kinds"]
    tags_doc = _read(master_dir / "food-tags.json")

    parent_of: dict[str, str] = {}
    for tag in tags_doc["tags"]:
        for child in tag.get("children", []):
            parent_of[child] = tag["id"]
    food_tags = [
        {
            "id": tag["id"],
            "label": tag["label"],
            "parent_id": parent_of.get(tag["id"]),
            "sort_order": i,
        }
        for i, tag in enumerate(tags_doc["tags"])
    ]
    # 상위 태그를 먼저 넣어야 parent_id 외래 키가 맞는다
    food_tags.sort(key=lambda t: (t["parent_id"] is not None, t["sort_order"]))

    rows: dict[str, list[Row]] = {
        "menu_kinds": [
            {
                "id": k["id"],
                "label": k["label"],
                "allow_daily_repeat": k["allowDailyRepeat"],
                "sort_order": i,
            }
            for i, k in enumerate(kinds)
        ],
        "food_tags": food_tags,
        "food_tag_presets": [
            {"label": p["label"], "tags": list(p["tags"]), "sort_order": i}
            for i, p in enumerate(tags_doc.get("presets", []))
        ],
        "cities": [],
        "areas": [],
        "must_menus": [],
    }

    # 도시 순서(= 도시 목록 API 순서)는 JSON의 sortOrder. 없으면 파일 이름 순서 뒤에 둔다
    cities = [_read(path) for path in sorted((master_dir / "cities").glob("*.json"))]
    cities.sort(key=lambda c: c.get("sortOrder", len(cities)))
    for city_index, city in enumerate(cities):
        rows["cities"].append(
            {
                "id": city["id"],
                "name": city["name"],
                "country_code": city["countryCode"],
                "time_zone": city["timeZone"],
                "center_lat": city["center"]["lat"],
                "center_lng": city["center"]["lng"],
                "sort_order": city_index,
            }
        )
        rows["areas"].extend(
            {
                "id": a["id"],
                "city_id": city["id"],
                "name": a["name"],
                "center_lat": a["center"]["lat"],
                "center_lng": a["center"]["lng"],
                "radius_meters": a["radiusMeters"],
                "sort_order": i,
            }
            for i, a in enumerate(city["areas"])
        )
        rows["must_menus"].extend(
            {
                "id": m["id"],
                "city_id": city["id"],
                "name": m["name"],
                "kind_id": m["kindId"],
                "description": m["description"],
                "food_tags": list(m.get("foodTags", [])),
                "is_signature": bool(m.get("isSignature", False)),
                "sort_order": i,
            }
            for i, m in enumerate(city["mustMenus"])
        )
    return rows


def _sql_literal(value: Any) -> str:
    """시드 SQL용 값 표기. 마스터 데이터에 나오는 타입(문자열·숫자·불리언·null·문자열 배열)만 다룬다."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, list):
        if not value:
            return "'{}'::text[]"
        return "array[" + ", ".join(_sql_literal(v) for v in value) + "]::text[]"
    raise TypeError(f"시드 SQL로 쓸 수 없는 값: {value!r}")


def _upsert_sql(table: str, key: str, rows: Iterable[Row]) -> str:
    rows = list(rows)
    if not rows:
        return ""
    columns = list(rows[0])
    values = ",\n  ".join(
        "(" + ", ".join(_sql_literal(row[c]) for c in columns) + ")" for row in rows
    )
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != key)
    return (
        f"insert into public.{table} ({', '.join(columns)}) values\n  {values}\n"
        f"on conflict ({key}) do update set {updates};\n"
    )


def render_seed_sql(rows: dict[str, list[Row]]) -> str:
    """DB/data.sql 내용: 앱이 돌려면 꼭 있어야 하는 초기 데이터(마스터 데이터). 직접 고치지 말고 이 함수로 다시 만든다."""
    header = (
        "-- 자동 생성 파일: app/seed/master_data.py --sql\n"
        "-- 초기 데이터(마스터 데이터). 원본은 data/master-data/*.json. 이 파일을 직접 고치지 않는다.\n"
        "-- DB/init.sql 다음에 적용한다. upsert라 여러 번 적용해도 된다.\n\n"
    )
    return header + "\n".join(_upsert_sql(t, key, rows[t]) for t, key in TABLE_ORDER)


def render_init_sql(migrations_dir: Path = MIGRATIONS_DIR) -> str:
    """DB/init.sql 내용: supabase/migrations를 번호 순서로 이은 스키마 전체.

    스키마의 원본은 마이그레이션 파일이다(바꿀 때는 새 번호를 더한다). 이 파일은 합본이라 직접 고치지 않는다.
    """
    header = (
        "-- 자동 생성 파일: app/seed/master_data.py --sql\n"
        "-- 스키마 전체 (테이블·제약·RLS·인덱스·뷰). 원본은 supabase/migrations/*.sql. 직접 고치지 않는다.\n"
        "-- auth 스키마와 anon·authenticated·service_role 역할이 있는 빈 Supabase DB에 적용한다.\n"
    )
    parts = [
        f"\n-- ===== {path.name} =====\n\n{path.read_text(encoding='utf-8').strip()}\n"
        for path in sorted(migrations_dir.glob("*.sql"))
    ]
    return header + "".join(parts)


def upsert_to_supabase(rows: dict[str, list[Row]]) -> None:
    """service_role 클라이언트로 테이블 순서대로 upsert한다 (RLS를 건너뛴다)."""
    from app.db.supabase import (
        admin_client,
    )  # 키가 없는 환경(--sql)에서도 모듈을 쓸 수 있게 늦게 import

    client = admin_client()
    for table, key in TABLE_ORDER:
        if rows[table]:
            client.table(table).upsert(rows[table], on_conflict=key).execute()


def main() -> None:
    parser = argparse.ArgumentParser(description="data/master-data → catalog 테이블")
    parser.add_argument(
        "--sql", action="store_true", help="DB/init.sql과 DB/data.sql을 다시 만든다"
    )
    args = parser.parse_args()

    rows = build_catalog_rows()
    if args.sql:
        DB_DIR.mkdir(exist_ok=True)
        INIT_SQL_PATH.write_text(render_init_sql(), encoding="utf-8")
        SEED_SQL_PATH.write_text(render_seed_sql(rows), encoding="utf-8")
        print(f"{INIT_SQL_PATH}, {SEED_SQL_PATH} 를 다시 만들었어요")
    else:
        upsert_to_supabase(rows)
        print(
            "마스터 데이터를 Supabase에 넣었어요: "
            + ", ".join(f"{t} {len(rows[t])}" for t, _ in TABLE_ORDER)
        )


if __name__ == "__main__":
    main()
