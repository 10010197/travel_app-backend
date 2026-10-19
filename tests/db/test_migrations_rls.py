"""마이그레이션과 RLS 검증 (B1 완료 기준: 다른 사용자 데이터가 RLS로 차단됨).

각 테스트는 트랜잭션 안에서 돌고 끝나면 되돌린다. as_user()로 역할·토큰 클레임을 바꿔 Supabase 요청을 흉내 낸다.
"""

import json

import psycopg
import pytest
from psycopg import errors

from tests.db.conftest import as_user, create_user

pytestmark = pytest.mark.db

MEALS = json.dumps([{"name": "점심", "timeBand": "lunch"}, {"name": "저녁", "timeBand": "dinner"}])


def insert_trip(conn: psycopg.Connection, title: str = "후쿠오카 2박 3일") -> str:
    row = conn.execute(
        "insert into public.trips (city_id, title, start_date, end_date, default_meals) "
        "values ('fukuoka', %s, '2026-11-14', '2026-11-16', %s) returning id",
        (title, MEALS),
    ).fetchone()
    assert row is not None
    return str(row[0])


def insert_day_and_slot(conn: psycopg.Connection, trip_id: str) -> tuple[str, str]:
    day = conn.execute(
        "insert into public.trip_days (trip_id, date, day_number, area_id) "
        "values (%s, '2026-11-14', 1, 'hakata') returning id",
        (trip_id,),
    ).fetchone()
    assert day is not None
    slot = conn.execute(
        "insert into public.slots (trip_id, day_id, name, time_band, sort_order) "
        "values (%s, %s, '점심', 'lunch', 0) returning id",
        (trip_id, day[0]),
    ).fetchone()
    assert slot is not None
    return str(day[0]), str(slot[0])


# ---------- 마스터 데이터 ----------


def test_seed_loads_master_data(db: psycopg.Connection) -> None:
    with as_user(db, None):
        cities = db.execute("select id, time_zone from public.cities").fetchall()
        signature = db.execute(
            "select count(*) from public.must_menus where is_signature"
        ).fetchone()
        noodle = db.execute(
            "select allow_daily_repeat from public.menu_kinds where id = 'noodle'"
        ).fetchone()
    assert ("fukuoka", "Asia/Tokyo") in cities
    assert signature == (4,)
    assert noodle == (False,)


def test_catalog_is_read_only_for_users(db: psycopg.Connection) -> None:
    user = create_user(db)
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, user):
        db.execute("insert into public.menu_kinds values ('x', 'x', true, 99)")
    with as_user(db, user):
        updated = db.execute("update public.cities set name = 'x' returning id").fetchall()
    assert updated == []  # 정책이 없으니 고칠 행이 보이지 않는다


# ---------- 가입 트리거 ----------


def test_signup_creates_profile_and_default_settings(db: psycopg.Connection) -> None:
    user = create_user(db, anonymous=True)
    with as_user(db, user, anonymous=True):
        settings = db.execute("select default_meals from public.user_settings").fetchall()
        profiles = db.execute("select id from public.profiles").fetchall()
    assert settings == [(["점심", "저녁"],)]
    assert [str(p[0]) for p in profiles] == [user]


# ---------- 다른 사용자 데이터 차단 ----------


def test_users_cannot_see_or_change_other_users_trips(db: psycopg.Connection) -> None:
    alice, bob = create_user(db), create_user(db)
    with as_user(db, alice):
        trip = insert_trip(db)
        insert_day_and_slot(db, trip)

    with as_user(db, bob):
        assert db.execute("select * from public.trips").fetchall() == []
        assert db.execute("select * from public.slots").fetchall() == []
        changed = db.execute(
            "update public.trips set title = 'hacked' where id = %s returning id", (trip,)
        ).fetchall()
        deleted = db.execute(
            "delete from public.trips where id = %s returning id", (trip,)
        ).fetchall()
    assert changed == [] and deleted == []

    with as_user(db, alice):
        assert db.execute("select title from public.trips").fetchall() == [("후쿠오카 2박 3일",)]


def test_cannot_create_trip_for_someone_else(db: psycopg.Connection) -> None:
    alice, bob = create_user(db), create_user(db)
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, bob):
        db.execute(
            "insert into public.trips (owner_id, city_id, title, default_meals) "
            "values (%s, 'fukuoka', 'x', '[]')",
            (alice,),
        )


def test_cannot_add_rows_to_another_users_trip(db: psycopg.Connection) -> None:
    alice, bob = create_user(db), create_user(db)
    with as_user(db, alice):
        trip = insert_trip(db)
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, bob):
        db.execute(
            "insert into public.trip_days (trip_id, date, day_number) values (%s, '2026-11-14', 1)",
            (trip,),
        )


def test_child_rows_must_belong_to_the_same_trip(db: psycopg.Connection) -> None:
    """외래 키 검사는 RLS를 거치지 않으므로, 복합 외래 키로 남의 날짜에 끼니를 붙이지 못하게 한다."""
    alice, bob = create_user(db), create_user(db)
    with as_user(db, alice):
        alice_day, _ = insert_day_and_slot(db, insert_trip(db))
    with as_user(db, bob):
        bob_trip = insert_trip(db)
    with pytest.raises(errors.ForeignKeyViolation), as_user(db, bob):
        db.execute(
            "insert into public.slots (trip_id, day_id, name, time_band, sort_order) "
            "values (%s, %s, '점심', 'lunch', 0)",
            (bob_trip, alice_day),
        )


def test_saved_places_and_must_picks_are_private(db: psycopg.Connection) -> None:
    alice, bob = create_user(db), create_user(db)
    with as_user(db, alice):
        place = db.execute(
            "insert into public.saved_places (city_id, place_id, menu) "
            "values ('fukuoka', 'mock-fuk-05', '미즈타키') returning id"
        ).fetchone()
    assert place is not None
    with as_user(db, bob):
        assert db.execute("select * from public.saved_places").fetchall() == []
        bob_trip = insert_trip(db)
    # 남의 맛집 모음 식당을 내 꼭 먹을 목록에 담을 수 없다 (C-2)
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, bob):
        db.execute(
            "insert into public.must_picks (trip_id, type, sort_order, saved_place_id) "
            "values (%s, 'place', 0, %s)",
            (bob_trip, place[0]),
        )


# ---------- 게스트 제한 (F-18) ----------


def test_guest_can_create_only_one_trip(db: psycopg.Connection) -> None:
    guest = create_user(db, anonymous=True)
    with as_user(db, guest, anonymous=True):
        insert_trip(db)
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, guest, anonymous=True):
        insert_trip(db, "두 번째 여행")


def test_registered_user_can_create_many_trips(db: psycopg.Connection) -> None:
    user = create_user(db)
    with as_user(db, user):
        insert_trip(db)
        insert_trip(db, "두 번째 여행")
        assert db.execute("select count(*) from public.trips").fetchone() == (2,)


def test_guest_cannot_save_companions(db: psycopg.Connection) -> None:
    guest = create_user(db, anonymous=True)
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, guest, anonymous=True):
        db.execute(
            "insert into public.saved_companions (name, foods_raw, strictness) "
            "values ('민지', '비건', 'flex')"
        )


# ---------- 공유 의견 ----------


def test_only_trip_owner_reads_share_comments_and_anon_cannot_write(db: psycopg.Connection) -> None:
    alice, bob = create_user(db), create_user(db)
    with as_user(db, alice):
        trip = insert_trip(db)
        _, slot = insert_day_and_slot(db, trip)
    # 의견 쓰기는 sharing 서비스가 service_role로 한다 (RLS 우회)
    db.execute("set local role service_role")
    db.execute(
        'insert into public.share_comments (trip_id, slot_id, author_name, body, "like") '
        "values (%s, %s, '혜인', '여기 예약 꼭', true)",
        (trip, slot),
    )
    db.execute("reset role")

    with as_user(db, alice):
        assert db.execute("select author_name from public.share_comments").fetchall() == [("혜인",)]
    with as_user(db, bob):
        assert db.execute("select * from public.share_comments").fetchall() == []
    with pytest.raises(errors.InsufficientPrivilege), as_user(db, None):
        db.execute(
            'insert into public.share_comments (trip_id, slot_id, author_name, "like") '
            "values (%s, %s, '익명', true)",
            (trip, slot),
        )


# ---------- 제약 ----------


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-11-16", "2026-11-14"), ("2026-11-01", "2026-11-15"), ("2026-11-14", None)],
    ids=["end-before-start", "longer-than-14-days", "only-one-date"],
)
def test_trip_date_constraints(db: psycopg.Connection, start: str, end: str | None) -> None:
    user = create_user(db)
    with pytest.raises(errors.CheckViolation), as_user(db, user):
        db.execute(
            "insert into public.trips (city_id, title, start_date, end_date, default_meals) "
            "values ('fukuoka', 'x', %s, %s, '[]')",
            (start, end),
        )


def test_filled_slot_needs_menu_and_deleting_saved_place_drops_must_pick(
    db: psycopg.Connection,
) -> None:
    user = create_user(db)
    with as_user(db, user):
        trip = insert_trip(db)
        _, slot = insert_day_and_slot(db, trip)
    with pytest.raises(errors.CheckViolation), as_user(db, user):
        db.execute("update public.slots set state = 'filled' where id = %s", (slot,))

    with as_user(db, user):
        place = db.execute(
            "insert into public.saved_places (city_id, place_id, menu) "
            "values ('fukuoka', 'mock-fuk-05', '미즈타키') returning id"
        ).fetchone()
        assert place is not None
        db.execute(
            "insert into public.must_picks (trip_id, type, sort_order, saved_place_id) "
            "values (%s, 'place', 0, %s)",
            (trip, place[0]),
        )
        db.execute("delete from public.saved_places where id = %s", (place[0],))
        assert db.execute("select count(*) from public.must_picks").fetchone() == (0,)


# ---------- 조회 구조 (0007) ----------

# 마스터 데이터는 거의 지우지 않으므로, 그쪽을 가리키는 외래 키에는 인덱스를 두지 않는다 (쓰기 비용만 늘어난다)
CATALOG_TABLES = {"cities", "areas", "must_menus", "menu_kinds", "food_tags", "food_tag_presets"}


def test_every_foreign_key_to_user_data_has_a_supporting_index(db: psycopg.Connection) -> None:
    """부모 행을 지울 때 자식 행을 표 전체를 훑지 않고 찾도록, 외래 키의 첫 열로 시작하는 인덱스가 있어야 한다."""
    rows = db.execute(
        """
        select con.conrelid::regclass::text as child,
               con.confrelid::regclass::text as parent,
               (select attname from pg_attribute
                 where attrelid = con.conrelid and attnum = con.conkey[1]) as first_column
        from pg_constraint con
        join pg_namespace n on n.oid = con.connamespace
        where con.contype = 'f' and n.nspname = 'public'
        """
    ).fetchall()
    missing = []
    for child, parent, first_column in rows:
        if parent.replace("public.", "") in CATALOG_TABLES:
            continue
        has_index = db.execute(
            """
            select exists (
              select 1 from pg_index i
              join pg_attribute a on a.attrelid = i.indrelid and a.attnum = i.indkey[0]
              where i.indrelid = %s::regclass and a.attname = %s
            )
            """,
            (child, first_column),
        ).fetchone()
        if not (has_index and has_index[0]):
            missing.append(f"{child}.{first_column} -> {parent}")
    assert missing == []


def test_trip_summaries_counts_slots_and_only_shows_own_trips(db: psycopg.Connection) -> None:
    alice, bob = create_user(db), create_user(db)
    with as_user(db, alice):
        trip = insert_trip(db)
        day, slot = insert_day_and_slot(db, trip)
        for name, state, menu in [
            ("저녁", "filled", "라멘"),
            ("간식", "onsite", None),
            ("야식", "skipped", None),
        ]:
            db.execute(
                "insert into public.slots (trip_id, day_id, name, time_band, sort_order, state, menu) "
                "values (%s, %s, %s, 'dinner', 1, %s, %s)",
                (trip, day, name, state, menu),
            )
        db.execute(
            "insert into public.trip_companions (trip_id, name, foods_raw, strictness) "
            "values (%s, '민지', '비건', 'flex')",
            (trip,),
        )
        summary = db.execute(
            "select city_name, time_zone, companion_count, active_slots, filled_slots, "
            "onsite_slots, empty_slots from public.trip_summaries"
        ).fetchall()
    # 끼니 4개: 비어 있음(점심) · 채움(저녁) · 현장에서(간식) · 빠짐(야식, 활성에서 제외)
    assert summary == [("후쿠오카", "Asia/Tokyo", 1, 3, 1, 1, 1)]
    with as_user(db, bob):
        assert db.execute("select * from public.trip_summaries").fetchall() == []
