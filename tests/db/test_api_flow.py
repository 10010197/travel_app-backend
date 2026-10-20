"""API 흐름 테스트: 실제 라우터 → 서비스 → DB(RLS)까지 (목 핸들러 테스트 시나리오에서 고른 것).

tests/db의 임시 데이터베이스(스텁 + 마이그레이션 + DB/data.sql)에 앱을 붙이고, 테스트 토큰(HS256)으로 부른다.
사용자 행은 autocommit 연결로 만들어 앱의 다른 연결에서도 보이게 한다.
"""

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import close_pool
from app.modules.catalog.service import get_catalog
from tests.conftest import make_token


@pytest.fixture
def api(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.main import create_app

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    get_catalog.cache_clear()
    close_pool()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    close_pool()


def new_user(
    database_url: str, *, anonymous: bool = False, name: str | None = None
) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    meta = psycopg.types.json.Jsonb({"full_name": name} if name else {})
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            "insert into auth.users (id, is_anonymous, raw_user_meta_data) values (%s, %s, %s)",
            (user_id, anonymous, meta),
        )
    return {"Authorization": f"Bearer {make_token(user_id, anonymous=anonymous)}"}


def day(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def create_trip(api: TestClient, headers: dict[str, str], **extra: object) -> dict:
    r = api.post(
        "/api/trips",
        headers=headers,
        json={"cityId": "fukuoka", "startDate": day(30), "endDate": day(32), **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


def code(r: object) -> str:
    return r.json()["error"]["code"]  # type: ignore[attr-defined, no-any-return]


def test_master_data_is_public(api: TestClient) -> None:
    assert api.get("/api/cities").json()[0]["id"] == "fukuoka"
    city = api.get("/api/cities/fukuoka").json()
    assert len(city["areas"]) == 7 and len(city["mustMenus"]) == 10
    r = api.get("/api/cities/seoul")
    assert r.status_code == 404 and code(r) == "CITY_NOT_SUPPORTED"


def test_create_trip_builds_days_slots_and_must_picks(api: TestClient, database_url: str) -> None:
    guest = new_user(database_url, anonymous=True)
    trip = create_trip(
        api, guest, companions=[{"name": "민지", "foodsRaw": "비건", "strictness": "flex"}]
    )
    assert trip["title"] == "후쿠오카 2박 3일"
    assert [[s["name"] for s in d["slots"]] for d in trip["days"]] == [["점심", "저녁"]] * 3
    assert sum(p["checked"] for p in trip["mustPicks"]) == 4
    assert trip["companions"][0]["foodTags"] == ["dairy", "egg", "meat", "seafood"]

    r = api.post(
        "/api/trips", headers=guest, json={"cityId": "fukuoka", "startDate": None, "endDate": None}
    )
    assert r.status_code == 409 and code(r) == "GUEST_TRIP_LIMIT"

    other = new_user(database_url)
    r = api.get(f"/api/trips/{trip['id']}", headers=other)
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
    assert api.get("/api/trips", headers=other).json() == []


def test_slot_changes_clean_up_acks_and_bulk_state_is_all_or_nothing(
    api: TestClient, database_url: str
) -> None:
    user = new_user(database_url)
    trip = create_trip(api, user)
    d1 = trip["days"][0]
    lunch, dinner = d1["slots"]
    for slot, menu in ((lunch, "하카타 라멘"), (dinner, "우동")):
        r = api.patch(
            f"/api/slots/{slot['id']}", headers=user, json={"menu": menu, "kindId": "noodle"}
        )
        assert r.json()["state"] == "filled"
    r = api.post(
        f"/api/trips/{trip['id']}/duplicate-acks",
        headers=user,
        json={"dayId": d1["id"], "kindId": "noodle", "slotIds": [lunch["id"], dinner["id"]]},
    )
    assert r.status_code == 204
    api.patch(
        f"/api/slots/{dinner['id']}", headers=user, json={"menu": "미즈타키", "kindId": "hotpot"}
    )
    assert api.get(f"/api/trips/{trip['id']}", headers=user).json()["duplicateAcks"] == []

    empties = [s["id"] for d in trip["days"][1:] for s in d["slots"]]
    r = api.patch(
        f"/api/trips/{trip['id']}/slots",
        headers=user,
        json={"slotIds": [*empties, lunch["id"]], "state": "onsite"},
    )
    assert r.status_code == 400
    states = {
        s["state"]
        for d in api.get(f"/api/trips/{trip['id']}", headers=user).json()["days"]
        for s in d["slots"]
    }
    assert "onsite" not in states
    r = api.patch(
        f"/api/trips/{trip['id']}/slots", headers=user, json={"slotIds": empties, "state": "onsite"}
    )
    assert sum(s["state"] == "onsite" for d in r.json()["days"] for s in d["slots"]) == len(empties)


def test_period_change_deletes_and_adds_days(api: TestClient, database_url: str) -> None:
    user = new_user(database_url)
    trip = create_trip(api, user)
    r = api.patch(
        f"/api/trips/{trip['id']}", headers=user, json={"startDate": day(31), "endDate": day(33)}
    )
    days = r.json()["days"]
    assert [d["date"] for d in days] == [day(31), day(32), day(33)]
    assert [d["dayNumber"] for d in days] == [1, 2, 3]
    assert days[0]["id"] == trip["days"][1]["id"]


def test_placed_must_pick_cannot_be_unchecked(api: TestClient, database_url: str) -> None:
    user = new_user(database_url)
    trip = create_trip(api, user)
    pick = next(p for p in trip["mustPicks"] if p["mustMenuId"] == "fuk-motsunabe")
    slot = trip["days"][0]["slots"][1]
    api.patch(
        f"/api/slots/{slot['id']}",
        headers=user,
        json={"menu": "모츠나베", "kindId": "hotpot", "mustPickId": pick["id"]},
    )
    items = [
        {
            "id": p["id"],
            "type": "menu",
            "checked": p["id"] != pick["id"],
            "mustMenuId": p["mustMenuId"],
        }
        for p in trip["mustPicks"]
    ]
    r = api.put(f"/api/trips/{trip['id']}/must-picks", headers=user, json={"items": items})
    assert r.status_code == 409 and code(r) == "MUST_PICK_PLACED"


def test_share_link_public_view_and_disable(api: TestClient, database_url: str) -> None:
    guest = new_user(database_url, anonymous=True)
    guest_trip = create_trip(api, guest)
    r = api.post(f"/api/trips/{guest_trip['id']}/share", headers=guest)
    assert r.status_code == 403 and code(r) == "LOGIN_REQUIRED"

    owner = new_user(database_url, name="이서현")
    trip = create_trip(
        api,
        owner,
        companions=[{"name": "혜인", "foodsRaw": "갑각류 알레르기", "strictness": "avoid"}],
    )
    token = api.post(f"/api/trips/{trip['id']}/share", headers=owner).json()["token"]
    shared = api.get(f"/api/share/{token}")
    assert shared.status_code == 200
    assert shared.json()["ownerName"] == "이서현"
    assert shared.json()["companionNames"] == ["혜인"]
    assert "갑각류" not in shared.text

    slot_id = trip["days"][0]["slots"][0]["id"]
    r = api.post(
        f"/api/share/{token}/comments",
        json={"slotId": slot_id, "authorName": "지수", "body": "좋아요", "like": True},
    )
    assert r.status_code == 201
    api.delete(f"/api/trips/{trip['id']}/share", headers=owner)
    r = api.get(f"/api/share/{token}")
    assert r.status_code == 404 and code(r) == "SHARE_DISABLED"
    assert len(api.get(f"/api/trips/{trip['id']}/comments", headers=owner).json()) == 1


def test_collection_save_is_upsert_and_shows_placements(api: TestClient, database_url: str) -> None:
    user = new_user(database_url)
    trip = create_trip(api, user)
    r = api.post(
        "/api/collection",
        headers=user,
        json={"cityId": "fukuoka", "placeId": "mock-fuk-05", "menu": "미즈타키"},
    )
    assert r.status_code == 201 and r.json()["kindId"] == "hotpot"
    slot = trip["days"][0]["slots"][1]
    api.patch(f"/api/slots/{slot['id']}", headers=user, json={"placeId": "mock-fuk-05"})
    r = api.post(
        "/api/collection",
        headers=user,
        json={"cityId": "fukuoka", "placeId": "mock-fuk-05", "menu": "미즈타키 코스"},
    )
    assert r.status_code == 200
    assert r.json()["placements"][0]["slotId"] == slot["id"]
