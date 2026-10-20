"""내 정보 API (API_SPEC 3.2, #4~#10). /auth/*는 만들지 않는다(프론트가 Supabase Auth를 직접 쓴다)."""

from fastapi import APIRouter, Response

from app.core.security import CurrentUserDep
from app.modules.identity import service
from app.modules.identity.schemas import (
    SavedCompanion,
    SavedCompanionInput,
    SavedCompanionPatch,
    User,
    UserSettings,
)

router = APIRouter(prefix="/me", tags=["identity"])


@router.get("", response_model=User)
def get_me(user: CurrentUserDep) -> User:
    return service.get_me(user)


@router.get("/settings", response_model=UserSettings)
def get_settings(user: CurrentUserDep) -> UserSettings:
    return service.get_settings(user)


@router.put("/settings", response_model=UserSettings)
def put_settings(body: UserSettings, user: CurrentUserDep) -> UserSettings:
    return service.put_settings(user, body)


@router.get("/companions", response_model=list[SavedCompanion])
def list_companions(user: CurrentUserDep) -> list[SavedCompanion]:
    return service.list_saved_companions(user)


@router.post("/companions", response_model=SavedCompanion, status_code=201)
def create_companion(body: SavedCompanionInput, user: CurrentUserDep) -> SavedCompanion:
    return service.create_saved_companion(user, body)


@router.patch("/companions/{companion_id}", response_model=SavedCompanion)
def update_companion(
    companion_id: str, body: SavedCompanionPatch, user: CurrentUserDep
) -> SavedCompanion:
    return service.update_saved_companion(user, companion_id, body)


@router.delete("/companions/{companion_id}", status_code=204)
def delete_companion(companion_id: str, user: CurrentUserDep) -> Response:
    service.delete_saved_companion(user, companion_id)
    return Response(status_code=204)
