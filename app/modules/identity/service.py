"""내 정보·설정·자주 함께 가는 일행 (identity 경계, F-16, F-18).

계정 자체(로그인·게스트·계정 연결)는 프론트가 Supabase Auth로 직접 한다. 여기에는 앱 데이터만 있다.
"""

from typing import Any

from app.core.errors import AppError, ErrorCode
from app.core.schemas import parse_uuid
from app.core.security import CurrentUser, require_registered
from app.db.session import Conn, user_tx
from app.modules.catalog.service import normalize_foods
from app.modules.identity import repository
from app.modules.identity.schemas import (
    SavedCompanion,
    SavedCompanionInput,
    SavedCompanionPatch,
    User,
    UserSettings,
)

DEFAULT_MEALS = ["점심", "저녁"]
_COMPANION_NOT_FOUND = "일행을 찾을 수 없어요."


def _companion(row: dict[str, Any]) -> SavedCompanion:
    return SavedCompanion(
        id=str(row["id"]),
        name=row["name"],
        foods_raw=row["foods_raw"],
        food_tags=list(row["food_tags"]),
        strictness=row["strictness"],
    )


def get_me(user: CurrentUser) -> User:
    with user_tx(user) as conn:
        profile = repository.get_profile(conn, user.id)
    return User(
        id=user.id,
        is_anonymous=user.is_anonymous,
        display_name=profile["display_name"] if profile else None,
        email=user.email,
    )


def default_meal_names(conn: Conn, user: CurrentUser) -> list[str]:
    """새 여행의 기본 끼니 이름 (trips 서비스가 같은 트랜잭션에서 부른다)"""
    row = repository.get_settings(conn, user.id)
    return list(row["default_meals"]) if row else list(DEFAULT_MEALS)


def get_settings(user: CurrentUser) -> UserSettings:
    with user_tx(user) as conn:
        row = repository.get_settings(conn, user.id)
    if row is None:
        # 가입 트리거가 만들지만, 혹시 없으면 기본값을 보여 준다
        return UserSettings(
            default_meals=DEFAULT_MEALS, time_display="auto", notify_empty_slots=False
        )
    return UserSettings.model_validate(row)


def put_settings(user: CurrentUser, body: UserSettings) -> UserSettings:
    with user_tx(user) as conn:
        row = repository.update_settings(conn, user.id, body.model_dump())
    if row is None:
        raise AppError(404, ErrorCode.NOT_FOUND, "설정을 찾을 수 없어요.")
    return UserSettings.model_validate(row)


def list_saved_companions(user: CurrentUser) -> list[SavedCompanion]:
    with user_tx(user) as conn:
        return [_companion(r) for r in repository.list_saved_companions(conn)]


def create_saved_companion(user: CurrentUser, body: SavedCompanionInput) -> SavedCompanion:
    """저장은 로그인 사용자만 (F-18 7). 서버가 원문을 태그로 정규화한다."""
    require_registered(user)
    values = body.model_dump()
    values["food_tags"] = list(normalize_foods(body.foods_raw).food_tags)
    with user_tx(user) as conn:
        return _companion(repository.insert_saved_companion(conn, values))


def update_saved_companion(
    user: CurrentUser, companion_id: str, body: SavedCompanionPatch
) -> SavedCompanion:
    """보낸 필드만 바꾼다. 이 일행을 불러온 여행 일행은 복사본이라 바뀌지 않는다 (F-02 3)."""
    cid = parse_uuid(companion_id, _COMPANION_NOT_FOUND)
    values = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "foods_raw" in values:
        values["food_tags"] = list(normalize_foods(values["foods_raw"]).food_tags)
    with user_tx(user) as conn:
        row = (
            repository.update_saved_companion(conn, cid, values)
            if values
            else repository.get_saved_companion(conn, cid)
        )
    if row is None:
        raise AppError(404, ErrorCode.NOT_FOUND, _COMPANION_NOT_FOUND)
    return _companion(row)


def delete_saved_companion(user: CurrentUser, companion_id: str) -> None:
    cid = parse_uuid(companion_id, _COMPANION_NOT_FOUND)
    with user_tx(user) as conn:
        if not repository.delete_saved_companion(conn, cid):
            raise AppError(404, ErrorCode.NOT_FOUND, _COMPANION_NOT_FOUND)


def owns_saved_companion(conn: Conn, companion_id: str) -> bool:
    """여행 일행을 불러올 때 그 원본이 내 것인지 (trips 서비스가 같은 트랜잭션에서 부른다)"""
    try:
        cid = parse_uuid(companion_id, _COMPANION_NOT_FOUND)
    except AppError:
        return False
    return repository.get_saved_companion(conn, cid) is not None
