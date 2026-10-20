"""공유 API (API_SPEC 3.11, #37~#41). /share/*는 토큰 없이 연다."""

from fastapi import APIRouter, Request, Response

from app.core.security import CurrentUserDep
from app.modules.sharing import service
from app.modules.sharing.schemas import CommentInput, ShareComment, SharedTrip, ShareLink

router = APIRouter(tags=["sharing"])


@router.post("/trips/{trip_id}/share", response_model=ShareLink)
def create_link(trip_id: str, user: CurrentUserDep) -> ShareLink:
    return service.create_link(user, trip_id)


@router.delete("/trips/{trip_id}/share", status_code=204)
def disable_link(trip_id: str, user: CurrentUserDep) -> Response:
    service.disable_link(user, trip_id)
    return Response(status_code=204)


@router.get("/trips/{trip_id}/comments", response_model=list[ShareComment])
def list_comments(trip_id: str, user: CurrentUserDep) -> list[ShareComment]:
    return service.list_comments(user, trip_id)


@router.get("/share/{token}", response_model=SharedTrip)
def get_shared_trip(token: str) -> SharedTrip:
    return service.get_shared_trip(token)


@router.post("/share/{token}/comments", response_model=ShareComment, status_code=201)
def add_comment(token: str, body: CommentInput, request: Request) -> ShareComment:
    client = request.client.host if request.client else "unknown"
    return service.add_comment(token, body, client)
