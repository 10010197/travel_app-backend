"""공유 (sharing 경계, F-11).

- 링크는 로그인 사용자만 만든다(게스트 403). 이미 있으면 같은 토큰을 돌려준다
- 링크를 끄면 공유 페이지는 바로 404 SHARE_DISABLED. 의견은 남는다
- 공개 응답에는 일행 이름만 넣는다(식이 원문·식이 상태·계정 정보 없음). 빠진 끼니는 메뉴·식당 없이
- 공개 의견 쓰기는 토큰·접속 주소별 호출 한도를 센다 (429 RATE_LIMITED)
"""

import secrets
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.schemas import parse_uuid, parse_uuid_or_none
from app.core.security import CurrentUser, require_registered
from app.db.session import service_tx, user_tx
from app.domain.time_band import band_order
from app.modules.catalog.service import get_catalog
from app.modules.places.service import get_place_summary
from app.modules.sharing import repository
from app.modules.sharing.schemas import (
    CommentInput,
    ShareComment,
    SharedDay,
    SharedSlot,
    SharedTrip,
    ShareLink,
)

_TRIP_NOT_FOUND = "여행을 찾을 수 없어요."
_SHARE_DISABLED = "공유가 끝난 일정이에요."

_comment_limiter: RateLimiter | None = None


def _limiter() -> RateLimiter:
    global _comment_limiter
    if _comment_limiter is None:
        _comment_limiter = RateLimiter(get_settings().comment_limit_per_hour)
    return _comment_limiter


def _comment(row: dict[str, Any]) -> ShareComment:
    return ShareComment(
        id=str(row["id"]),
        slot_id=str(row["slot_id"]),
        author_name=row["author_name"],
        body=row["body"],
        like=row["like"],
        created_at=row["created_at"],
    )


def _link(token: str) -> ShareLink:
    return ShareLink(token=token, url=f"/share/{token}")


# ---------- 소유자 ----------


def create_link(user: CurrentUser, trip_id: str) -> ShareLink:
    tid = parse_uuid(trip_id, _TRIP_NOT_FOUND)
    with user_tx(user) as conn:
        row = repository.get_share_token(conn, tid)
        if row is None:
            raise AppError(404, ErrorCode.NOT_FOUND, _TRIP_NOT_FOUND)
        require_registered(user)
        token: str = row["share_token"] or secrets.token_hex(16)
        if row["share_token"] is None:
            repository.set_share_token(conn, tid, token)
    return _link(token)


def disable_link(user: CurrentUser, trip_id: str) -> None:
    tid = parse_uuid(trip_id, _TRIP_NOT_FOUND)
    with user_tx(user) as conn:
        if repository.get_share_token(conn, tid) is None:
            raise AppError(404, ErrorCode.NOT_FOUND, _TRIP_NOT_FOUND)
        repository.set_share_token(conn, tid, None)


def list_comments(user: CurrentUser, trip_id: str) -> list[ShareComment]:
    tid = parse_uuid(trip_id, _TRIP_NOT_FOUND)
    with user_tx(user) as conn:
        if repository.get_share_token(conn, tid) is None:
            raise AppError(404, ErrorCode.NOT_FOUND, _TRIP_NOT_FOUND)
        return [_comment(r) for r in repository.list_comments(conn, tid)]


# ---------- 공개 ----------


def _disabled() -> AppError:
    return AppError(404, ErrorCode.SHARE_DISABLED, _SHARE_DISABLED)


def get_shared_trip(token: str) -> SharedTrip:
    catalog = get_catalog()
    with service_tx() as conn:
        trip = repository.trip_by_token(conn, token)
        if trip is None:
            raise _disabled()
        parts = repository.shared_parts(conn, trip["id"])

    city = catalog.city(trip["city_id"])

    def area_name(area_id: str | None) -> str | None:
        area = catalog.area(area_id) if area_id else None
        return area.name if area else None

    slots_by_day: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for s in parts["slots"]:
        slots_by_day.setdefault(s["day_id"], []).append(s)

    def shared_slot(s: dict[str, Any]) -> SharedSlot:
        skipped = s["state"] == "skipped"
        place = get_place_summary(s["place_id"]) if s["place_id"] and not skipped else None
        return SharedSlot(
            id=str(s["id"]),
            name=s["name"],
            time_band=s["time_band"],
            state=s["state"],
            menu=None if skipped else s["menu"],
            place_name=place.name if place else None,
            area_name=area_name(s["area_id"]),
        )

    return SharedTrip(
        title=trip["title"],
        city_name=city.name if city else trip["city_id"],
        time_zone=city.time_zone if city else "Asia/Seoul",
        start_date=trip["start_date"],
        end_date=trip["end_date"],
        owner_name=trip["owner_name"],
        companion_names=[c["name"] for c in parts["companions"]],
        days=[
            SharedDay(
                date=d["date"],
                day_number=d["day_number"],
                area_name=area_name(d["area_id"]),
                slots=[
                    shared_slot(s)
                    for s in sorted(
                        slots_by_day.get(d["id"], []),
                        key=lambda s: (band_order(s["time_band"]), s["sort_order"]),
                    )
                ],
            )
            for d in parts["days"]
        ],
        comments=[_comment(c) for c in parts["comments"]],
    )


def add_comment(token: str, body: CommentInput, client: str) -> ShareComment:
    """의견 남기기 (이름만, 로그인 없음). 이 공유 일정의 끼니에만."""
    _limiter().hit(f"comment:{token}:{client}")
    with service_tx() as conn:
        trip = repository.trip_by_token(conn, token)
        if trip is None:
            raise _disabled()
        slot_id = parse_uuid_or_none(body.slot_id)
        if slot_id is None or not repository.slot_in_trip(conn, trip["id"], slot_id):
            raise AppError(400, ErrorCode.VALIDATION_ERROR, "이 일정의 끼니가 아니에요.")
        row = repository.insert_comment(
            conn,
            trip["id"],
            slot_id,
            {"author_name": body.author_name, "body": body.body, "like": body.like},
        )
    return _comment(row)
